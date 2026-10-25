# CounterGuard

Fixed bugs should stay fixed.

CounterGuard is a regression guard tool for Python. It compiles a confirmed fix (old revision fails, new revision passes) into the smallest check that reproduces the failure, then learns from confirmed counterexamples which code that check should apply to.

> v0.5.0 Beta · Apache-2.0 · [中文](README.md) · Not on PyPI

## Installation

```powershell
uv sync
uv run counterguard --help
```

To run tests, install the wheel with the `runner` extra:

```powershell
uv build
python -m pip install "dist/counterguard-0.5.0-py3-none-any.whl[runner]"
```

## Quickstart

```powershell
uv run counterguard demo --scenario examples/demo/mvp.yaml --workspace artifacts/quickstart-v1
```

Output:

```text
demo accepted: true
Replay executions: 4
verdict_counts: {"pass": 2, "skipped_inapplicable": 2, "violation": 2}
```

Run it again with `--verify-only` to audit the existing records without starting pytest.

The demo runs offline against the bundled example and local fixtures, with no model calls. The scenario file is called `mvp.yaml`, but only a JSON subset is supported; valid input is in the [quickstart](docs/quickstart.md).

## How it works

1. **Capture.** The same cases run against the old and new revisions. Only an old failure followed by a new pass counts as evidence.
2. **Compile.** The failing cases become a Guard, which is self-checked against the new revision.
3. **Learn the boundary.** Applicability is trained on confirmed counterexamples. Paths, names and expected values never enter the features.
4. **Replay.** Applicability is decided first, then pytest runs.

Results are recorded in three layers: `scope_decision` (applicable / inapplicable / unknown), `execution_outcome` (not run / pass / fail / error / timeout) and `final_verdict` (pass / violation / skipped / inconclusive). Inapplicable and unknown targets never start pytest, and a skip never counts as a pass.

## Results

15 labeled targets (9 training / 6 holdout) and two guards: membership discount and query limit.

With the two confirmed counterexamples added, false applications on the holdout set drop from 2 to 0, while both applicable targets are kept. The labels are public, so this is engineering validation. Numbers and reproduction commands are in the [evaluation notes](docs/evaluation.md).

## Console

```powershell
python console/tools/export_console_data.py --root .
start console/index.html
```

A static page showing guards, replay records, scope decisions and alerts. Exported data contains local paths and is excluded by `.gitignore`. More in the [console docs](console/README.md).

![Console overview](console/shots/01-overview-real.png)

## Limitations

- Supports Python 3.12+, pytest 8.4, root or `src/` layouts and projects with no runtime dependencies;
- repository code only runs inside a reviewed Docker image, not as a general sandbox;
- a new project's Scope is an exact snapshot and does not generalize to later changes;
- not published to PyPI yet.

## Documentation

- [CLI and exit codes](docs/cli.md)
- [Repository verification](docs/verify.md), [guard lifecycle](docs/guard-lifecycle.md)
- [Admission conditions](docs/project-admission.md), [roadmap](docs/roadmap.md), [boltons trial](docs/results/onboarding-boltons-v1/README.md)
- [Security model](docs/security-model.md), [known limitations](docs/known-limitations.md)

## Development

```powershell
uv run pytest -m "not slow" -q
uv run ruff check .
```

Tests that start real processes must be marked `slow`; see [testing.md](docs/testing.md).

## License

[Apache-2.0](LICENSE)
