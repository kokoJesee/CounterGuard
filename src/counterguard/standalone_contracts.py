"""Head-committed literal contracts, with no execution or owner authentication."""

import json
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from counterguard.contract_draft_models import DraftCase, DraftLiteral, DraftMatchCase
from counterguard.models import Digest, FrozenModel
from counterguard.project_config import Module, RepositoryPath, Symbol

CommitId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$", strict=True)]
ContractId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{0,95}$", strict=True)]
CONTRACT_LIMIT = 128 * 1024


class StandaloneTestOrigin(FrozenModel):
    test_ref: RepositoryPath
    test_function: Symbol
    test_object_id: CommitId
    test_digest: Digest
    extractor_version: Literal["literal-test-projection.v1"] = "literal-test-projection.v1"
    projection_digest: Digest


class StandaloneContract(FrozenModel):
    """A repository declaration. Runtime consumers must obtain separate authorization."""

    schema_version: Literal["contract.v3"] = "contract.v3"
    profile: Literal["standalone-literals.v1"] = "standalone-literals.v1"
    contract_id: ContractId
    buggy_commit: CommitId
    fixed_commit: CommitId
    target_module: Module
    target_symbol: Symbol
    source_ref: RepositoryPath
    import_root: Literal[".", "src"]
    runtime_refs: Annotated[tuple[RepositoryPath, ...], Field(min_length=1, max_length=256)]
    test_origin: StandaloneTestOrigin
    cases: Annotated[tuple[DraftCase, ...], Field(min_length=1, max_length=256)]
    authority: Literal["repository_declaration_not_execution_authorization"] = (
        "repository_declaration_not_execution_authorization"
    )

    @model_validator(mode="after")
    def coherent_contract(self):
        if self.schema_version == "contract.v3" and any(
            isinstance(case, DraftMatchCase) for case in self.cases
        ):
            raise ValueError("Message cases require contract.v4")
        if self.buggy_commit == self.fixed_commit:
            raise ValueError("Buggy and fixed commits must differ")
        if self.runtime_refs != tuple(sorted(set(self.runtime_refs))):
            raise ValueError("Runtime refs must be sorted and unique")
        if self.source_ref not in self.runtime_refs:
            raise ValueError("Runtime refs must include the target source")
        ids = [case.case_id for case in self.cases]
        if ids != sorted(set(ids)):
            raise ValueError("Case IDs must be sorted and unique")
        prefix = "" if self.import_root == "." else "src/"
        stem = prefix + self.target_module.replace(".", "/")
        if self.source_ref not in {stem + ".py", stem + "/__init__.py"}:
            raise ValueError("Target source contradicts the declared import mapping")
        if not self.test_origin.test_function.startswith("test_"):
            raise ValueError("Test origin must identify a test_* function")
        count = 0
        for case in self.cases:
            if len(case.positional_args) + len(case.keyword_args) > 32:
                raise ValueError("Case argument budget exceeded")
            pending = [
                (value, 0)
                for value in (
                    *case.positional_args,
                    *(item.literal for item in case.keyword_args),
                    *((case.expected,) if case.expected is not None else ()),
                )
            ]
            while pending:
                value, depth = pending.pop()
                count += 1
                if depth > 8 or count > 10000:
                    raise ValueError("Contract literal budget exceeded")
                pending.extend((item, depth + 1) for item in value.items)
                pending.extend((item, depth + 1) for pair in value.entries for item in pair)
                if value.kind == "dict":
                    for key, _ in value.entries:
                        if not _hashable_literal(key):
                            raise ValueError("Dictionary keys must be hashable literal values")
        return self


class StandaloneTestOriginV2(StandaloneTestOrigin):
    extractor_version: Literal["literal-test-projection.v2"] = "literal-test-projection.v2"


class StandaloneContractV4(StandaloneContract):
    schema_version: Literal["contract.v4"] = "contract.v4"
    profile: Literal["standalone-literals-match.v1"] = "standalone-literals-match.v1"
    test_origin: StandaloneTestOriginV2
    cases: Annotated[tuple[DraftMatchCase | DraftCase, ...], Field(min_length=1, max_length=256)]


class StandaloneContractV5(StandaloneContractV4):
    schema_version: Literal["contract.v5"] = "contract.v5"
    profile: Literal["standalone-static-reexport.v1"] = "standalone-static-reexport.v1"
    test_origin: StandaloneTestOriginV2 | StandaloneTestOrigin
    definition_module: Module
    definition_symbol: Symbol
    definition_ref: RepositoryPath

    @model_validator(mode="after")
    def coherent_export(self):
        prefix = "" if self.import_root == "." else "src/"
        if (
            "." in self.target_module
            or self.source_ref != prefix + self.target_module + "/__init__.py"
            or not self.definition_module.startswith(self.target_module + ".")
            or len(self.definition_module.split(".")) != 2
            or self.definition_ref != prefix + self.definition_module.replace(".", "/") + ".py"
            or self.definition_ref not in self.runtime_refs
        ):
            raise ValueError("Static export mapping must name one direct child definition")
        if any(isinstance(case, DraftMatchCase) for case in self.cases) and not isinstance(
            self.test_origin, StandaloneTestOriginV2
        ):
            raise ValueError("Message cases require projection.v2")
        return self


class StandaloneContractV6(StandaloneContractV5):
    schema_version: Literal["contract.v6"] = "contract.v6"
    profile: Literal["standalone-static-reexport.v2"] = "standalone-static-reexport.v2"
    export_algorithm: Literal["static-root-reexport.v2"] = "static-root-reexport.v2"
    closure_algorithm: Literal["module-import-closure.v2"] = "module-import-closure.v2"
    hook_grammar: Literal["finite-raise-hook.v1"] = "finite-raise-hook.v1"


def _hashable_literal(value: DraftLiteral) -> bool:
    return value.kind not in {"list", "dict"} and (
        value.kind != "tuple" or all(_hashable_literal(item) for item in value.items)
    )


def strict_json(raw: bytes, *, limit: int) -> dict:
    """Reject duplicate keys and non-JSON numbers before model validation."""
    if len(raw) > limit:
        raise ValueError("JSON byte budget exceeded")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("Non-finite JSON number")

    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def read_standalone_contract(raw: bytes) -> StandaloneContract:
    value = strict_json(raw, limit=CONTRACT_LIMIT)
    model = {
        "contract.v4": StandaloneContractV4,
        "contract.v5": StandaloneContractV5,
        "contract.v6": StandaloneContractV6,
    }.get(value.get("schema_version"), StandaloneContract)
    return model.model_validate_json(raw)
