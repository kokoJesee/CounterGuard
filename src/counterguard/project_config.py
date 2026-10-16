"""Strict declarative mappings; configuration never supplies executable code."""

import re
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, StringConstraints, model_serializer, model_validator

from counterguard.digests import digest_bytes
from counterguard.models import FrozenModel

CONFIG_LIMIT = 128 * 1024
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.I)
_AUXILIARY_ROOT_FILES = frozenset(
    {
        ".editorconfig",
        ".gitattributes",
        ".gitignore",
        ".gitlab-ci.yml",
        ".mailmap",
        ".travis.yml",
        "azure-pipelines.yml",
    }
)
_AUXILIARY_ROOT_PREFIXES = (
    "authors",
    "changelog",
    "code_of_conduct",
    "contributing",
    "license",
    "notice",
    "security",
)


def repository_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or not path.parts
        or len(value) > 512
        or path.is_absolute()
        or str(path) != value
        or unicodedata.normalize("NFC", value) != value
        or any(c in value for c in '\\:\x00*?"<>|')
        or any(unicodedata.category(c).startswith("C") for c in value)
        or any(
            p.casefold() in {".", "..", ".git"} or p.endswith((".", " ")) or _RESERVED.match(p)
            for p in path.parts
        )
    ):
        raise ValueError("Expected a safe canonical repository-relative POSIX file path")
    return value


RepositoryPath = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=512),
    AfterValidator(repository_path),
]
Identifier = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")]
Symbol = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$", max_length=128)]
Module = Annotated[
    str,
    StringConstraints(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$",
        max_length=256,
    ),
]


def is_explicit_auxiliary_path(value: str) -> bool:
    """Allow exact declarations only for files outside target execution semantics."""
    path = PurePosixPath(value)
    folded = value.casefold()
    if path.suffix.casefold() in {".md", ".rst"}:
        return True
    if len(path.parts) == 1:
        name = path.name.casefold()
        return name in _AUXILIARY_ROOT_FILES or any(
            name == prefix or name.startswith(prefix + ".") for prefix in _AUXILIARY_ROOT_PREFIXES
        )
    if len(path.parts) == 3 and path.parts[:2] == (".github", "workflows"):
        return path.suffix.casefold() in {".yml", ".yaml"}
    return folded in {
        ".circleci/config.yml",
        ".github/dependabot.yml",
        ".github/dependabot.yaml",
    }


class TargetMapping(FrozenModel):
    target_id: Identifier
    guard_id: Annotated[str, StringConstraints(pattern=r"^grd_[a-zA-Z0-9_-]+$", max_length=96)]
    source_ref: RepositoryPath
    module: Module | None = None
    symbol: Symbol
    contract_ref: RepositoryPath
    dependency_refs: Annotated[tuple[RepositoryPath, ...], Field(max_length=64)] = ()
    import_root: Literal[".", "src"] = "."

    @model_serializer(mode="wrap")
    def legacy_root(self, handler):
        payload = handler(self)
        if self.import_root == ".":
            payload.pop("import_root", None)
        return payload

    @model_validator(mode="after")
    def file_types(self) -> Self:
        if not self.source_ref.endswith(".py") or not self.contract_ref.endswith(".json"):
            raise ValueError(
                "Targets require a .py source and an explicit .json contract reference"
            )
        source = self.source_ref
        if self.import_root != ".":
            prefix = self.import_root + "/"
            if not source.startswith(prefix):
                raise ValueError("Source must be below the declared import root")
            source = source.removeprefix(prefix)
        source_module = source.removesuffix(".py").replace("/", ".")
        if source_module.endswith(".__init__"):
            source_module = source_module.removesuffix(".__init__")
        if self.module is not None and self.module != source_module:
            raise ValueError("Declared module must be the import path of source_ref")
        if len(set(self.dependency_refs)) != len(self.dependency_refs):
            raise ValueError("Dependency references must be distinct")
        return self

    def input_refs(self) -> tuple[str, ...]:
        return tuple(sorted({self.source_ref, self.contract_ref, *self.dependency_refs}))


class ProjectConfig(FrozenModel):
    schema_version: Literal["project-config.v1", "project-config.v2"] = "project-config.v1"
    project_id: Identifier
    targets: Annotated[tuple[TargetMapping, ...], Field(min_length=1, max_length=128)]
    ignored_paths: Annotated[tuple[RepositoryPath, ...], Field(max_length=128)] = ()
    audit_refs: Annotated[tuple[RepositoryPath, ...], Field(max_length=64)] = ()

    @model_serializer(mode="wrap")
    def legacy_audit_refs(self, handler):
        payload = handler(self)
        if self.schema_version == "project-config.v1":
            payload.pop("audit_refs", None)
        return payload

    @model_validator(mode="after")
    def distinct_bindings(self) -> Self:
        if self.schema_version == "project-config.v1" and (
            "audit_refs" in self.model_fields_set
            or any("import_root" in target.model_fields_set for target in self.targets)
        ):
            raise ValueError("Import-root and audit declarations require project-config.v2")
        if len(set(self.audit_refs)) != len(self.audit_refs):
            raise ValueError("Audit references must be distinct")
        if len({t.target_id for t in self.targets}) != len(self.targets):
            raise ValueError("Target identities must be unique")
        bound = {p for t in self.targets for p in t.input_refs()} | set(self.audit_refs)
        if len(set(self.ignored_paths)) != len(self.ignored_paths) or bound.intersection(
            self.ignored_paths
        ):
            raise ValueError("Ignored paths must be unique and cannot hide a mapped input")
        if any(not is_explicit_auxiliary_path(p) for p in self.ignored_paths):
            raise ValueError(
                "Ignored paths must be exact documentation, repository metadata, "
                "or CI control files"
            )
        return self


def load_project_config(path: str | Path) -> tuple[ProjectConfig, str]:
    path = Path(path).absolute()
    reject_links(path)
    with path.open("rb") as stream:
        raw = stream.read(CONFIG_LIMIT + 1)
    if len(raw) > CONFIG_LIMIT:
        raise ValueError("Project configuration exceeds 128 KiB")
    try:
        config = ProjectConfig.model_validate_json(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError(
            "Project config must match project-config.v1 using JSON syntax, not general YAML"
        ) from error
    return config, digest_bytes(raw)


def reject_links(path: Path) -> None:
    """Check each existing component before resolution, including Windows reparse points."""
    for component in (*reversed(path.parents), path):
        try:
            stat = component.lstat()
        except FileNotFoundError:
            continue
        if component.is_symlink() or getattr(stat, "st_file_attributes", 0) & 0x400:
            raise ValueError("Linked/reparse repository or configuration paths are unsupported")
