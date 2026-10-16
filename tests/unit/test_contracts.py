"""The declared exception and typed-value boundary must stay explicit."""

import pytest

from counterguard.contracts import convert_contract_value, resolve_exception


@pytest.mark.parametrize(
    "name, expected",
    [
        ("ValueError", ValueError),
        ("TypeError", TypeError),
        ("OverflowError", OverflowError),
    ],
)
def test_resolves_only_supported_exceptions(name: str, expected: type[Exception]) -> None:
    assert resolve_exception(name) is expected


@pytest.mark.parametrize(
    "name", ["Exception", "SystemExit", "KeyboardInterrupt", "str", "eval", "os.system"]
)
def test_rejects_unlisted_and_non_exception_names(name: str) -> None:
    with pytest.raises(ValueError, match="unsupported contract exception"):
        resolve_exception(name)


@pytest.mark.parametrize("value, kind", [(True, "integer"), ("NaN", "decimal"), (1, "boolean")])
def test_rejects_invalid_typed_values(value: object, kind: str) -> None:
    with pytest.raises(ValueError, match="contract value does not match"):
        convert_contract_value(value, kind)
