"""Audited architectural package metadata, independent of benchmark scope labels."""

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import StringConstraints, model_validator

from evidenceguard.digests import digest_json_artifact
from evidenceguard.errors import ArtifactIntegrityError
from evidenceguard.models import Digest, FrozenModel, NonEmptyText

ModulePrefix = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$")]
SCOPE_V1_CONTEXT_DIGEST = "sha256:08f548c920924dac44f2058014b64c79e6d18f348b820a6535be7b1795f1ad6a"


class ModuleRule(FrozenModel):
    module_prefix: ModulePrefix
    module_group: NonEmptyText
    basis: NonEmptyText


class ModuleContext(FrozenModel):
    schema_version: Literal["module-context.v1"] = "module-context.v1"
    context_id: NonEmptyText
    owner: NonEmptyText
    provenance: NonEmptyText
    rules: tuple[ModuleRule, ...]
    artifact_digest: Digest

    @model_validator(mode="after")
    def unique_architectural_prefixes(self) -> Self:
        prefixes = [rule.module_prefix for rule in self.rules]
        if not prefixes or len(prefixes) != len(set(prefixes)):
            raise ValueError("Module rules must be nonempty and unique")
        for first in prefixes:
            if any(second.startswith(first + ".") for second in prefixes if second != first):
                raise ValueError("Overlapping package rules are ambiguous")
        return self

    def resolve_group(self, module: str) -> str:
        matches = [
            rule.module_group
            for rule in self.rules
            if module == rule.module_prefix or module.startswith(rule.module_prefix + ".")
        ]
        if len(matches) != 1:
            raise ValueError("Module must match exactly one audited architectural package rule")
        return matches[0]


def load_module_context(path: Path) -> ModuleContext:
    try:
        context = ModuleContext.model_validate_json(path.read_bytes())
    except (OSError, ValueError) as error:
        raise ArtifactIntegrityError(f"Invalid module context: {path}") from error
    if digest_json_artifact(context) != context.artifact_digest:
        raise ArtifactIntegrityError("Module context digest mismatch")
    if (
        context.context_id == "scope_v1_module_context"
        and context.artifact_digest != SCOPE_V1_CONTEXT_DIGEST
    ):
        raise ArtifactIntegrityError("Frozen scope_v1 module context changed; use a new protocol")
    return context
