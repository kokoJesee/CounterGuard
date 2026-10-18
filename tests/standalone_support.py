"""Build only tool-owned Git histories; never import their Python on the host."""

from pathlib import Path
from textwrap import indent

from counterguard.bootstrap_binding import bind_contract, prepare_contract
from tests.repository_support import git


def standalone_history(
    workspace: Path, *, import_root=".", import_failure=False, message_match=False, reexport=False
):
    repo = workspace / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "CounterGuard fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    package = repo / ("sample" if import_root == "." else "src/sample")
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("# Tool-owned Docker fixture\n", encoding="utf-8")
    if reexport:
        assert message_match and not import_failure
        (package / "__init__.py").write_text("from .core import price\n", encoding="utf-8")
    guard = (
        "import os\n"
        "if os.environ.get('COUNTERGUARD_CONTRACT') != 'cg_control/contract.json':\n"
        "    raise RuntimeError('this fixture must only run in admitted Docker')\n"
    )
    buggy_source = guard + (
        "raise ImportError('fixture import failure')\n" if import_failure else ""
    )
    buggy_function = (
        "def price(x):\n if x == 1: raise ValueError('old message')\n return x+1\n"
        if message_match
        else "def price(x): return x+1 if x == 0 else x\n"
    )
    if reexport:
        buggy_source = ""
        buggy_function = buggy_function.replace(
            "def price(x):\n", "def price(x):\n" + indent(guard, " ")
        )
    (package / "core.py").write_text(
        buggy_source + buggy_function,
        encoding="utf-8",
    )
    tests = repo / "tests"
    tests.mkdir()
    (tests / "conftest.py").write_text("raise RuntimeError('upstream hook must never load')\n")
    (repo / "pyproject.toml").write_text(
        '[project]\nname="sample"\ndependencies=[]\nrequires-python=">=3.12"\n'
        '[tool.pytest.ini_options]\nminversion="999.0"\nrequired_plugins=["not-installed"]\n',
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "tool-owned buggy fixture")
    buggy = git(repo, "rev-parse", "HEAD")
    fixed_function = (
        "def price(x):\n if x == 1: raise ValueError('expected message')\n return x+1\n"
        if message_match
        else "def price(x): return x+1\n"
    )
    if reexport:
        fixed_function = fixed_function.replace(
            "def price(x):\n", "def price(x):\n" + indent(guard, " ")
        )
    (package / "core.py").write_text(("" if reexport else guard) + fixed_function, encoding="utf-8")
    regression = (
        "import pytest\ndef test_price():\n assert price(0) == 1\n"
        " with pytest.raises(ValueError, match='expected message'): price(1)\n"
        if message_match
        else "def test_price():\n assert price(0) == 1\n assert price(1) == 2\n"
    )
    (tests / "test_price.py").write_text(
        "raise RuntimeError('upstream test module must not load')\n"
        + ("from sample import price\n" if reexport else "from sample.core import price\n")
        + regression,
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "tool-owned fixed fixture and regression")
    fixed = git(repo, "rev-parse", "HEAD")
    prepare_contract(
        repo,
        buggy=buggy,
        fixed=fixed,
        contract_id="price.v1",
        target="sample:price" if reexport else "sample.core:price",
        import_root=import_root,
        test_ref="tests/test_price.py",
        test_function="test_price",
        output=workspace / "prep",
        cwd=workspace,
    )
    (repo / "contracts").mkdir()
    (repo / "contracts/price.v1.json").write_bytes((workspace / "prep/contract.json").read_bytes())
    git(repo, "add", "contracts/price.v1.json")
    git(repo, "commit", "-m", "NOT upstream: tool-owned assertion-head fixture")
    head = git(repo, "rev-parse", "HEAD")
    value = bind_contract(
        repo, head, "contracts/price.v1.json", output=workspace / "bind", cwd=workspace
    )
    assert value["capture_input_status"] == "review_required"
    return repo
