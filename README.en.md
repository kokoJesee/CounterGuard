# CounterGuard

Fixed bugs should stay fixed.

A while back you patched a boundary case. Today an AI assistant edits the same file. It has no idea that patch ever happened, so the same check goes missing again.

CounterGuard takes a different approach: every confirmed fix is compiled into a small check that can be replayed later. The check also knows which code it belongs to, so it stays out of unrelated modules.

> [中文](README.md) · English

The public release is [v0.5.0 Beta](https://github.com/kokoJesee/CounterGuard/releases/tag/v0.5.0). It ships a wheel, an sdist, two hashed dependency lists, the reviewed runner archive and a SHA256SUMS file. Installation details are in the [Beta guide](docs/beta-release.md). Nothing has been published to PyPI.

## Install

```powershell
uv sync
uv run counterguard --help
```

Or install from a build:

```powershell
uv build
python -m pip install "dist/counterguard-0.5.0-py3-none-any.whl[runner]"
```

The wheel gives you the CLI and the library. Running tests needs the `runner` extra, which pulls in pytest. Without pytest the command exits `3` before writing anything and tells you to install `counterguard[runner]`.

The offline demo also needs `examples/`, `benchmarks/`, `experiments/` and the contract tests from the source tree. Those are not part of the wheel.

## Run the demo

```powershell
uv run counterguard demo --scenario examples/demo/mvp.yaml --workspace artifacts/quickstart-v1
```

That single command goes through capture, compile, scope learning and replay, then writes `report.json` and `report.md`. Run it again against the same workspace and it only audits the records and re-renders the report.

The scenario file is called `mvp.yaml`, but the parser only accepts a JSON subset. Indentation, comments and anchors are not supported. The [quickstart](docs/quickstart.md) has valid input plus a real missing-contract case that ends in `unknown`.

The demo uses recorded proposals and local fixtures. No network, no model calls. It is a demo, not a sandbox for arbitrary Python.

## Three states, kept apart

Running a guard can produce three different answers, and CounterGuard records them separately:

| Field | Values | What it means |
|---|---|---|
| `scope_decision` | `applicable` / `inapplicable` / `unknown` | whether this guard is meant for this target |
| `execution_outcome` | `not_run` / `pass` / `fail` / `error` / `timeout` | whether pytest ran, and what it did |
| `final_verdict` | `pass` / `violation` / `skipped` / `inconclusive` | the conclusion a person reads |

Inapplicable and unknown targets never start pytest; they are recorded as `not_run` plus `skipped`. Infrastructure problems become `inconclusive`. A skipped row is never turned into a pass.

Reports also carry the minimal failed cases, the initial and refined rules, clause-by-clause comparisons and source links. Field definitions live in the [CLI contract](docs/cli.md).

## How it works

1. **Capture.** The same cases run against the buggy and the fixed revision. Only a real failure followed by a real pass counts as reproducible evidence. Raw logs, case results and source digests are kept.
2. **Compile.** The failing cases become a Guard that contains nothing else, and that Guard has to pass on the fixed target before it is published.
3. **Learn the boundary.** Which targets a guard should apply to is fitted from confirmed counterexamples. The learner only sees a `FeatureVector` and an applicability boolean. Paths, names, expected values and anything else that would leak the answer stay out of training.
4. **Replay.** Applicability is decided first. Only then does pytest run, and skipped rows keep `run = null`.

## The frozen 15 samples

`benchmarks/` holds 15 labeled targets: 9 for training, 6 held out. Two guards cover them:

- **Membership discount** (`membership_discount` v1 final-price). Members pay 80% of the original amount, two decimal places, half-up rounding, negative amounts rejected. The compiled guard keeps only the two member-price cases that failed on the source bug.
- **Query limit** (`input-limit` v1). Default 20, accepting only ASCII decimal strings from 1 to 100. Signed, zero-padded, Unicode-digit, malformed and out-of-range input is rejected. The guard keeps a single assertion: reject zero.

Scope features deliberately exclude contract IDs, paths, module names, target names and expected output. The holdout set also contains a target that is inapplicable while violating its own contract, which is there to keep "should this run" separate from "is this correct".

### What the learner found

In the initial phase both rules learn `contract_version == v1`. Add the two frozen legal counterexamples and refit, and the rules become version plus interface: `final_price` for discount, `query_parameter` for query limit.

On the 9 training rows:

| Phase | TP | FP | TN | FN |
|---|---:|---:|---:|---:|
| initial | 4 | 2 | 3 | 0 |
| refined | 4 | 0 | 5 | 0 |

The search space is reported as 8/92 and 10/175 candidate combinations. Twenty input shuffles produce the same rule and digest. Holdout never enters fitting.

```powershell
uv run counterguard scope learn --protocol experiments/scope_v1.json --phase initial --output artifacts/.../initial
uv run counterguard scope learn --protocol experiments/scope_v1.json --phase refined --output artifacts/.../refined
```

## Four methods on the holdout set

```powershell
uv run counterguard benchmark replay --protocol experiments/scope_v1.json --phase refined --split train
uv run counterguard experiment evaluate --protocol experiments/scope_v1.json --split holdout --fitted artifacts/experiments/scope-v1/fitted --output artifacts/experiments/scope-v1/final
```

Training replay is expected to exit `1`: two applicable targets really do violate their guards. That run gives 2 passes, 2 violations and 5 skips, with exactly 4 pytest processes started.

On the 6 held-out targets:

| Method | TP / FP / TN / FN | False-application rate | Bug recall |
|---|---|---:|---:|
| always | 2 / 4 / 0 / 0 | 1.0 | 1/1 |
| fixed interface | 2 / 2 / 2 / 0 | 0.5 | 1/1 |
| learned initial | 2 / 2 / 2 / 0 | 0.5 | 1/1 |
| learned refined | 2 / 0 / 4 / 0 | 0.0 | 1/1 |

Refined removed both false applications, kept both applicable targets and added no FP or FN. The query guard has no held-out bug, so its bug recall is reported as `null` rather than 100%.

Under the frozen policy, unknown counts as a negative prediction, but its rate and decision coverage are reported separately, and raw results keep `unknown`.

An `evaluate` exit code of 0 means the experiment met its frozen acceptance criteria, not that every guard passed. These six labels are public, so this is engineering validation, not a blind benchmark.

`replay verify` audits the current inputs without executing pytest. A clean audit means the record is complete. It does not mean the recorded verdict was `pass`.

## Exit codes

`capture`, `compile`, `learn`, `replay run` and `evaluate` all accept `--format text|json|markdown`. An explicit format wraps the original payload in `command-report.v1`; without it, the original JSON shape is kept. Formatting never changes the exit code.

| Code | Meaning |
|---|---|
| `0` | reproduced evidence, or acceptance met |
| `1` | completed but not reproduced; or an applicable guard confirmed a violation |
| `2` | invalid input |
| `3` | execution failure, including missing pytest metadata |
| `4` | not enough information (`unknown`); or learning refused to generalize |
| `5` | artifact integrity failure |

Pytest's own exit codes 2–5, missing or ambiguous case results, and timeouts never count as a reproduced bug.

## More docs

- [Repository verification (`verify`)](docs/verify.md) and [guard lifecycle](docs/guard-lifecycle.md)
- [Read-only console](console/README.md): export the local Registry and run artifacts, then browse guards, replay records and scope decisions in a browser
- [Admission conditions](docs/project-admission.md), [onboarding checklist](docs/onboarding.md) and [roadmap](docs/roadmap.md)
- [Contract drafts](docs/contract-drafts.md) and [CI example with Summary export](docs/github-actions.md)
- The boltons trial: [a real attempt that stopped at admission](docs/results/onboarding-boltons-v1/README.md)

Where the project stands: reviewed local snapshots and the fixed validators profile can run the whole chain end to end. A brand-new project can take the restricted onboarding path, but its Scope stays an exact snapshot and does not generalize to later source changes. Details are in [the admission boundary](docs/standalone-guards.md).

## Development

```powershell
uv run pytest -m "not slow" -q      # fast tier, no real subprocesses
uv run ruff check .
uv run pytest -q --durations=20      # full suite, once before shipping
```

Integration tests, e2e flows, heavy fixtures and real child processes are marked `slow`. The fast tier rejects unmarked real processes during setup, execution and teardown, so any new test that starts a process has to declare itself `slow`. The rules are in [testing.md](docs/testing.md).

## Layout

```text
src/counterguard/     implementation and CLI
tests/                unit, integration and e2e suites
schemas/              JSON Schema for every artifact
benchmarks/           frozen labeled samples, splits and module context
examples/             demo scenario, contracts and implementations
experiments/          frozen experiment protocol
containers/           restricted Docker runner
console/              read-only console for guards, replays and scope
docs/                 architecture, data contracts, CLI, security model, known limits
```

Runtime artifacts under `artifacts/` and distributions under `dist/` stay out of Git.

## Security

CounterGuard reads repositories and executes code, so its own boundaries are documented separately:

- [security-model.md](docs/security-model.md): assets, trust assumptions, repository inspection and container controls
- [attack-surface-checklist.md](docs/attack-surface-checklist.md): tested, partially covered and not covered at all, item by item
- [known-limitations.md](docs/known-limitations.md): the current scope and the historical verification boundary

Verification so far ran on local Python tooling and a pinned Linux Docker image. None of it is a cross-platform guarantee, malicious-repository isolation, signature-based authentication or a proof of program equivalence.

## License

[Apache-2.0](LICENSE)
