"""The frozen, presence-only feature vocabulary shared by extraction and scope rules."""

from typing import Literal

from pydantic import field_serializer

from evidenceguard.digests import canonical_json_bytes, digest_bytes
from evidenceguard.models import FrozenModel, NonEmptyText

EXTRACTOR_VERSION = "ast-features.v1"
AstFeature = Literal[
    "branch:is_member",
    "branch:none",
    "decimal:multiply",
    "decimal:subtract",
    "int:parse",
    "regex:ascii_digits",
    "range:check",
    "round:half_up",
    "str:isascii",
    "str:isdecimal",
]
VOCABULARY = {
    "branch:is_member": "If/IfExp test references the is_member formal parameter",
    "branch:none": "If/IfExp test compares a formal parameter with None using is/is not",
    "decimal:multiply": "BinOp Mult in the target body; no numeric type inference",
    "decimal:subtract": "BinOp Sub in the target body; no numeric type inference",
    "int:parse": "Call to unshadowed built-in int",
    "regex:ascii_digits": "Call to imported re.fullmatch with literal [0-9] or [0-9]+",
    "range:check": "Numeric lower and upper comparisons for the same expression in one test",
    "round:half_up": "Load of imported decimal.ROUND_HALF_UP",
    "str:isascii": "Call to an isascii attribute; no receiver type inference",
    "str:isdecimal": "Call to an isdecimal attribute; no receiver type inference",
}
VOCABULARY_DIGEST = digest_bytes(canonical_json_bytes(VOCABULARY))
METADATA_FIELDS = ("contract_family", "contract_version", "interface_kind", "symbol_signature")


class FeatureVector(FrozenModel):
    contract_family: NonEmptyText
    contract_version: NonEmptyText
    interface_kind: NonEmptyText
    symbol_signature: NonEmptyText
    module_group: NonEmptyText
    ast_features: frozenset[AstFeature]

    @field_serializer("ast_features")
    def sorted_features(self, value: frozenset[str]) -> list[str]:
        return sorted(value)
