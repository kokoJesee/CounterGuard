"""Non-executable, explicitly unreviewed projections of committed test syntax."""

import math
from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from counterguard.contracts import ExceptionName
from counterguard.digests import digest_json_artifact
from counterguard.models import Digest, FrozenModel
from counterguard.project_config import Module, RepositoryPath, Symbol


class DraftLiteral(FrozenModel):
    kind: Literal["none", "boolean", "integer", "float", "string", "bytes", "list", "tuple", "dict"]
    value: JsonValue = None
    items: tuple["DraftLiteral", ...] = ()
    entries: tuple[tuple["DraftLiteral", "DraftLiteral"], ...] = ()

    @model_validator(mode="after")
    def coherent_literal(self):
        scalar = {
            "none": self.value is None,
            "boolean": type(self.value) is bool,
            "integer": type(self.value) is int and self.value.bit_length() <= 256,
            "float": type(self.value) is float and math.isfinite(self.value),
            "string": isinstance(self.value, str) and len(self.value) <= 4096,
            "bytes": isinstance(self.value, str)
            and len(self.value) <= 8192
            and len(self.value) % 2 == 0
            and all(x in "0123456789abcdef" for x in self.value),
        }
        if self.kind in scalar:
            valid = scalar[self.kind] and not self.items and not self.entries
        elif self.kind in {"list", "tuple"}:
            valid = self.value is None and not self.entries and len(self.items) <= 128
        else:
            valid = self.value is None and not self.items and len(self.entries) <= 128
        if not valid:
            raise ValueError("Malformed draft literal")
        return self


class DraftKeyword(FrozenModel):
    name: Symbol
    literal: DraftLiteral


class DraftCase(FrozenModel):
    case_id: Annotated[str, Field(pattern=r"^case_[a-f0-9]{24}$")]
    source_line: Annotated[int, Field(ge=1)]
    assertion_index: Annotated[int, Field(ge=1)]
    parameter_index: Annotated[int, Field(ge=1)]
    assertion_digest: Digest
    positional_args: tuple[DraftLiteral, ...]
    keyword_args: tuple[DraftKeyword, ...]
    oracle: Literal["eq", "ne", "is", "is_not", "truthy", "falsey", "raises"]
    expected: DraftLiteral | None = None
    exception: ExceptionName | None = None

    @model_validator(mode="after")
    def coherent_oracle(self):
        if self.oracle in {"eq", "ne", "is", "is_not"}:
            if self.expected is None or self.exception is not None:
                raise ValueError("Comparison requires a literal expectation")
            if self.oracle in {"is", "is_not"} and self.expected.kind not in {"none", "boolean"}:
                raise ValueError("Only singleton identity assertions are supported")
        elif self.expected is not None or (self.oracle == "raises") != (self.exception is not None):
            raise ValueError("Draft oracle fields contradict each other")
        names = [item.name for item in self.keyword_args]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate keyword argument")
        return self


class DraftUnsupported(FrozenModel):
    source_line: Annotated[int, Field(ge=1)]
    reason_code: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]+$")]
    assertion_count: Annotated[int, Field(ge=0)] = 0


class ContractProposal(FrozenModel):
    schema_version: Literal["contract-proposal.v1"] = "contract-proposal.v1"
    extractor_version: Literal["literal-test-projection.v1"] = "literal-test-projection.v1"
    status: Literal["draft_ready", "partial", "unsupported"]
    requested_revision: str
    commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    test_ref: RepositoryPath
    test_object_id: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    test_digest: Digest
    test_function: Symbol
    target_module: Module
    target_symbol: Symbol
    cases: Annotated[tuple[DraftCase, ...], Field(max_length=256)]
    unsupported: tuple[DraftUnsupported, ...]
    source_assertions: Annotated[int, Field(ge=0)]
    represented_assertions: Annotated[int, Field(ge=0)]
    human_review_required: Literal[True] = True
    execution_allowed: Literal[False] = False
    binding_trust: Literal["syntactic_only_requires_owner_review"] = (
        "syntactic_only_requires_owner_review"
    )
    next_action: str
    implementation_digests: dict[str, Digest]
    artifact_digest: Digest

    @model_validator(mode="after")
    def coherent_coverage(self):
        ids = [case.case_id for case in self.cases]
        represented = len({case.assertion_index for case in self.cases})
        if represented != self.represented_assertions or len(ids) != len(set(ids)):
            raise ValueError("Draft coverage or case identity mismatch")
        if (
            represented + sum(item.assertion_count for item in self.unsupported)
            != self.source_assertions
        ):
            raise ValueError("Unsupported assertions must not disappear")
        expected = (
            "unsupported" if not self.cases else "partial" if self.unsupported else "draft_ready"
        )
        if self.status != expected or self.artifact_digest != digest_json_artifact(self):
            raise ValueError("Draft status or digest mismatch")
        return self
