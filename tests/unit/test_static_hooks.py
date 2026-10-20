"""Finite hook observations preserve module/alias uncertainty and exception pins."""

import random

import pytest

from counterguard.bootstrap_plan import inspect_target_closure
from counterguard.digests import canonical_json_bytes, digest_bytes

EXCEPTIONS = b'''class InvalidKey(Exception):
    """Tool-owned exception."""
    def __init__(self, message: str) -> None:
        super().__init__(message)
'''
HOOK = b"""from __future__ import annotations
from .errors import InvalidKey
class MetaPalette(type):
    def __getattr__(cls, name: str) -> NoReturn:
        raise InvalidKey(f"Invalid key: {name}")
"""


def tree(hook=HOOK, errors=EXCEPTIONS):
    return {
        "sample/__init__.py": b"from .hooks import MetaPalette\n",
        "sample/hooks.py": hook,
        "sample/errors.py": errors,
    }


def inspect(files=None, version="module-import-closure.v2"):
    return inspect_target_closure(
        tree() if files is None else files, module="sample", import_root=".", algorithm=version
    )


def codes(value):
    return {x["code"] for x in value["findings"]}


def test_finite_metaclass_raise_is_observed_with_both_source_identities():
    value = inspect()
    assert value["status"] == "review_required" and value["findings"] == []
    (hook,) = value["hook_observations"]
    assert hook["scope"] == "metaclass" and hook["recognition"] == "finite_raise"
    assert hook["qualified_name"] == "MetaPalette.__getattr__"
    assert hook["content_digest"] == digest_bytes(HOOK)
    assert hook["exception"] == {
        "module": "sample.errors",
        "symbol": "InvalidKey",
        "path": "sample/errors.py",
        "content_digest": digest_bytes(EXCEPTIONS),
    }
    old = inspect(version="module-import-closure.v1")
    assert old["status"] == "unknown" and "module_lookup_hook_requires_review" in codes(old)
    assert "hook_observations" not in old


@pytest.mark.parametrize("base", [b"", b"(object)"])
def test_ordinary_class_has_a_distinct_scope_observation(base):
    value = inspect(tree(HOOK.replace(b"(type)", base)))
    assert value["status"] == "review_required"
    assert value["hook_observations"][0]["scope"] == "class"


@pytest.mark.parametrize(
    "source",
    [
        b"def __getattr__(name): return 0\n",
        b"if True:\n def __getattr__(name): return 0\n",
        b"try:\n pass\nexcept Exception:\n def __getattr__(name): return 0\n",
        b"from .errors import InvalidKey as __getattr__\n",
        b"__getattr__ = lambda name: 0\n",
        b"for __getattr__ in []: pass\n",
        b"with manager() as __getattr__: pass\n",
        b"del __getattr__\n",
        b"class __getattr__: pass\n",
        b"def install():\n global __getattr__\n __getattr__ = lambda name: 0\n",
        b"try:\n pass\nexcept Exception as __getattr__:\n pass\n",
        b"match 1:\n case __getattr__: pass\n",
    ],
)
def test_real_module_hooks_in_branches_aliases_and_bindings_stay_unknown(source):
    value = inspect(tree(source))
    assert value["status"] == "unknown"
    assert "module_lookup_hook_requires_review" in codes(value)


def test_nested_function_is_not_mislabelled_as_a_module_hook():
    value = inspect(tree(b"def helper():\n def __getattr__(name): return name\n return 0\n"))
    assert value["status"] == "review_required"
    assert value["hook_observations"][0]["scope"] == "nested_function"
    assert value["hook_observations"][0]["recognition"] == "unrecognized"


@pytest.mark.parametrize(
    "replacement",
    [
        b"return name",
        b"return getattr(cls, name)",
        b"raise InvalidKey(helper(name))",
        b"raise InvalidKey(f'{name!r}')",
        b"raise InvalidKey(f'{name:10}')",
        b"raise InvalidKey('x') from Exception()",
        b"raise InvalidKey(name)",
        b"raise InvalidKey('x', 'y')",
        b"raise InvalidKey(message='x')",
        b"import os; raise InvalidKey('x')",
        b"open('sentinel'); raise InvalidKey('x')",
    ],
)
def test_class_hook_computation_forwarding_and_effects_stay_unknown(replacement):
    value = inspect(tree(HOOK.replace(b'raise InvalidKey(f"Invalid key: {name}")', replacement)))
    assert value["status"] == "unknown"
    assert "class_lookup_hook_requires_review" in codes(value)
    assert value["hook_observations"][0]["exception"] is None


@pytest.mark.parametrize(
    "hook",
    [
        HOOK + b"InvalidKey = object\n",
        HOOK + b"type = object\n",
        HOOK + b"MetaPalette = object\n",
        HOOK + b"def replace():\n global InvalidKey\n InvalidKey = object\n",
        HOOK + b"def replace(x=(InvalidKey := object)): pass\n",
        HOOK.replace(b"class MetaPalette", b"@decorator\nclass MetaPalette"),
        HOOK.replace(b"(type)", b"(type, other)"),
        HOOK.replace(b"(type)", b"(type, metaclass=other)"),
        HOOK.replace(b"    def __getattr__", b"    @staticmethod\n    def __getattr__"),
        HOOK.replace(b"name: str", b"name: str = 'x'"),
        HOOK.replace(b"name: str", b"*name: str"),
        HOOK.replace(b"__getattr__", b"__getattribute__"),
        HOOK.replace(b"from __future__ import annotations\n", b""),
        HOOK.replace(b"    def __getattr__", b"    InvalidKey = object\n    def __getattr__"),
        HOOK + b"class Other:\n __getattr__ = helper\n",
    ],
)
def test_ambiguous_exception_binding_or_nonfinite_class_cannot_be_silently_ignored(hook):
    value = inspect(tree(hook))
    assert value["status"] == "unknown"
    assert "class_lookup_hook_requires_review" in codes(value)


@pytest.mark.parametrize(
    "errors",
    [
        EXCEPTIONS + b"InvalidKey = object\n",
        EXCEPTIONS + b"open('sentinel')\n",
        EXCEPTIONS.replace(b"Exception", b"Other"),
        EXCEPTIONS.replace(b"super().__init__(message)", b"open(message)"),
        EXCEPTIONS + b"super = helper\n",
        EXCEPTIONS.replace(b"class InvalidKey", b"@decorator\nclass InvalidKey"),
        EXCEPTIONS.replace(
            b"    def __init__", b"    def __new__(cls): return helper()\n    def __init__"
        ),
        EXCEPTIONS.replace(b"message: str", b"message: helper()"),
        b"from external import InvalidKey\n",
    ],
)
def test_exception_constructor_is_checked_from_full_pinned_source(errors):
    value = inspect(tree(errors=errors))
    assert value["status"] == "unknown"
    assert "class_lookup_hook_requires_review" in codes(value)


def test_twenty_shuffles_preserve_hook_observations_files_and_digest():
    items = list(tree().items())
    expected = canonical_json_bytes(inspect(dict(items)))
    for seed in range(20):
        random.Random(seed).shuffle(items)
        assert canonical_json_bytes(inspect(dict(items))) == expected


def test_unrelated_dynamic_and_resource_findings_are_never_cleared_by_a_finite_hook():
    value = inspect(tree(HOOK + b"getattr(object(), 'x')\nopen('sentinel')\n"))
    assert value["hook_observations"][0]["recognition"] == "finite_raise"
    assert value["status"] == "unknown"
    assert {
        "dynamic_code_or_lookup_requires_review",
        "resource_or_native_access_requires_review",
    } <= (codes(value))
