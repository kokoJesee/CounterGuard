"""Validate stable case identities before runtime evidence capture relies on them."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATHS = sorted((PROJECT_ROOT / "examples").glob("**/contracts/*.json"))
CASE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$")
POSITIONAL_CASE_ID_PATTERN = re.compile(r"^(?:case|test)-?\d+$")


def load_contract(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def contract_path_id(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


@pytest.mark.parametrize("contract_path", CONTRACT_PATHS, ids=contract_path_id)
def test_contract_cases_have_stable_unique_ids_and_one_oracle(contract_path: Path) -> None:
    contract = load_contract(contract_path)
    case_ids: list[str] = []

    for position, case in enumerate(contract["cases"]):
        case_id = case.get("case_id")

        assert isinstance(case_id, str) and CASE_ID_PATTERN.fullmatch(case_id), (
            f"{contract_path}: case {position} must have a semantic lowercase kebab-case case_id"
        )
        assert not POSITIONAL_CASE_ID_PATTERN.fullmatch(case_id), (
            f"{contract_path}: {case_id!r} encodes an array position and is not stable"
        )
        assert ("expected" in case) ^ ("raises" in case), (
            f"{contract_path}: {case_id!r} must declare exactly one of expected or raises"
        )
        case_ids.append(case_id)

    assert len(case_ids) == len(set(case_ids)), (
        f"{contract_path}: case_id values must be unique within the contract"
    )
