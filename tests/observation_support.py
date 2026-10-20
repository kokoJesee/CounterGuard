"""Independent tool-owned eight-case histories, never external project substitutes."""

from counterguard.bootstrap_binding import bind_contract, prepare_contract
from counterguard.standalone_capture import ZERO, _seal
from counterguard.study_data import inspect_source, inspect_target, make_call_map, persist
from counterguard.study_models import StdoutWitnessCase, StudyCaseMap, StudyWitness
from counterguard.study_observation import StudyObservationSession, issue_observation_review
from counterguard.study_observation_models import StudyObservationPlan
from tests.repository_support import git


def commit(repo, message):
    git(repo, "add", ".")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def init(repo):
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "CounterGuard fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")


def rgb_history(workspace):
    repo = workspace / "source-repo"
    init(repo)
    (repo / "fixture_source").mkdir()
    (repo / "fixture_source/__init__.py").write_text("from .core import paint\n")
    (repo / "pyproject.toml").write_text(
        '[project]\nname="fixture-source"\ndependencies=[]\nrequires-python=">=3.12"\n'
    )
    prefix = (
        "import os\n"
        "def paint(text, color=None, on_color=None, force_color=False):\n"
        " if os.environ.get('COUNTERGUARD_CONTRACT') != 'cg_control/contract.json':\n"
        "  raise RuntimeError('Docker only fixture')\n"
    )
    (repo / "fixture_source/core.py").write_text(prefix + " return text\n")
    buggy = commit(repo, "tool-owned buggy RGB fixture")
    (repo / "fixture_source/core.py").write_text(
        prefix + " for rgb in (color, on_color):\n"
        "  if rgb is not None and (len(rgb) != 3 or any(v < 0 or v > 255 for v in rgb)):\n"
        "   raise ValueError('fixture RGB rejection')\n return text\n"
    )
    (repo / "tests").mkdir()
    (repo / "tests/conftest.py").write_text("raise RuntimeError('must not load')\n")
    (repo / "tests/test_paint.py").write_text(
        "import pytest\nfrom fixture_source import paint\n"
        "@pytest.mark.parametrize('rgb', [(-1,0,0), (0,0,256), (0,0), (0,0,0,0)])\n"
        "def test_paint(rgb):\n"
        " with pytest.raises(ValueError, match='fixture RGB rejection'):\n"
        "  paint('text', color=rgb, force_color=True)\n"
        " with pytest.raises(ValueError, match='fixture RGB rejection'):\n"
        "  paint('text', on_color=rgb, force_color=True)\n"
    )
    fixed = commit(repo, "tool-owned fixed RGB fixture and regression")
    prepare_contract(
        repo,
        buggy=buggy,
        fixed=fixed,
        contract_id="fixture.rgb.v1",
        target="fixture_source:paint",
        import_root=".",
        test_ref="tests/test_paint.py",
        test_function="test_paint",
        output=workspace / "prep",
        cwd=workspace,
    )
    (repo / "contracts").mkdir()
    (repo / "contracts/rgb.json").write_bytes((workspace / "prep/contract.json").read_bytes())
    head = commit(repo, "NOT upstream: tool-owned assertion head")
    binding = bind_contract(
        repo, head, "contracts/rgb.json", output=workspace / "bind", cwd=workspace
    )
    assert binding["capture_input_status"] == "review_required"
    return repo


def prepare_observation(source_repo, workspace):
    source, _, facts = inspect_source(source_repo, workspace, "g/guard.json", source_id="source")
    contract = facts[-1]
    assert len(source.case_ids) == len(contract.cases) == 8
    target_repo = workspace / "target-repo"
    init(target_repo)
    (target_repo / "fixture_target").mkdir()
    (target_repo / "fixture_target/__init__.py").write_text("from .core import emit\n")
    (target_repo / "fixture_target/core.py").write_text(
        "import os\ndef emit(text, fore_rgb=None, back_rgb=None):\n"
        " if os.environ.get('COUNTERGUARD_CONTRACT') != 'cg_control/contract.json':\n"
        "  raise RuntimeError('Docker only fixture')\n"
        " if 'FORCE_COLOR' in os.environ: raise RuntimeError('host environment leaked')\n"
        " rgb = fore_rgb if fore_rgb is not None else back_rgb\n"
        " r, g, b = rgb\n"
        " r, g, b = (max(0, min(255, v)) for v in (r, g, b))\n"
        " code = '38' if fore_rgb is not None else '48'\n"
        " print(f'\\x1b[{code};2;{r};{g};{b}m{text}')\n"
    )
    (target_repo / "pyproject.toml").write_text(
        '[project]\nname="fixture-target"\ndependencies=[]\nrequires-python=">=3.12"\n'
    )
    (target_repo / "LICENSE").write_text("CounterGuard tool-owned fixture\n")
    (target_repo / "README.md").write_text("Tool-owned RGB output fixture, no external labels.\n")
    (target_repo / "conftest.py").write_text("raise RuntimeError('must not load')\n")
    revision = commit(target_repo, "tool-owned independent output fixture")
    target, _ = inspect_target(
        target_repo,
        revision,
        target_id="target",
        module="fixture_target",
        symbol="emit",
        import_root=".",
        profile="static-reexport-v2",
        license_ref="LICENSE",
    )
    rows, own = [], []
    for case in contract.cases:
        kwargs = {k.name: k.literal for k in case.keyword_args}
        key = "color" if "color" in kwargs else "on_color"
        name = "fore_rgb" if key == "color" else "back_rgb"
        rows.append(
            StudyCaseMap(
                case_id=case.case_id,
                source_assertion_digest=case.assertion_digest,
                keyword_renames={key: name},
                source_only_keywords=("force_color",),
            )
        )
        rgb = tuple(v.value for v in kwargs[key].items)
        if len(rgb) == 3:
            # Independent fixture goldens for the two literal inputs, no target invocation.
            expected = {
                ("color", (-1, 0, 0)): "\x1b[38;2;0;0;0mtext\n",
                ("color", (0, 0, 256)): "\x1b[38;2;0;0;255mtext\n",
                ("on_color", (-1, 0, 0)): "\x1b[48;2;0;0;0mtext\n",
                ("on_color", (0, 0, 256)): "\x1b[48;2;0;0;255mtext\n",
            }[key, rgb]
            own.append(StdoutWitnessCase(case_id=case.case_id, stdout=expected))
    mapping = make_call_map(source, target, contract, map_id="map", cases=rows)
    witness = _seal(
        StudyWitness(
            target_digest=target.artifact_digest,
            map_digest=mapping.artifact_digest,
            basis_refs=("README.md",),
            cases=tuple(sorted(own, key=lambda c: c.case_id)),
            artifact_digest=ZERO,
        )
    )
    assert len(witness.cases) == 4
    for ref, record in (("s", source), ("t", target), ("m", mapping), ("w", witness)):
        persist(workspace / (ref + ".json"), record)
    plan = _seal(
        StudyObservationPlan(
            source_ref="s.json",
            target_ref="t.json",
            map_ref="m.json",
            witness_ref="w.json",
            review_ref="external-review.json",
            artifact_digest=ZERO,
        )
    )
    review = issue_observation_review(
        source_repo,
        target_repo,
        workspace,
        plan,
        output_ref=plan.review_ref,
        review_id="observation",
        operator="tool-owned qualification reviewer",
        reason="Review source cases and independent stdout subset under external purpose",
        source_interface="value_return",
        target_interface="stdout_write",
    )
    return StudyObservationSession(
        source_repo, target_repo, workspace, review.artifact_digest
    ), plan
