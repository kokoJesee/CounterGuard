"""Explicit value and exception vocabulary shared by contract consumers."""

from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Literal

ContractType = Literal["boolean", "decimal", "integer", "optional_string"]
ExceptionName = Literal["ValueError", "TypeError", "OverflowError"]

EXCEPTION_TYPES = MappingProxyType(
    {"ValueError": ValueError, "TypeError": TypeError, "OverflowError": OverflowError}
)


def resolve_exception(name: str) -> type[Exception]:
    """Resolve only the declared exception whitelist, never arbitrary names."""
    if not isinstance(name, str) or name not in EXCEPTION_TYPES:
        raise ValueError(f"unsupported contract exception: {name!r}")
    return EXCEPTION_TYPES[name]


def convert_contract_value(value: object, declared_type: ContractType) -> object:
    """Validate JSON values before turning them into typed call arguments."""
    if declared_type == "boolean" and isinstance(value, bool):
        return value
    if declared_type == "integer" and isinstance(value, int) and not isinstance(value, bool):
        return value
    if declared_type == "optional_string" and (value is None or isinstance(value, str)):
        return value
    if declared_type == "decimal" and isinstance(value, str):
        try:
            converted = Decimal(value)
        except InvalidOperation:
            converted = None
        if converted is not None and converted.is_finite():
            return converted
    raise ValueError(f"contract value does not match {declared_type}: {value!r}")
