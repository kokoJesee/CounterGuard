# CounterGuard

CounterGuard turns verified bug evidence into reusable regression guards with explicit
applicability boundaries.

> English · [中文](README.zh-CN.md)

## The problem

AI-generated and AI-edited code has a structural gap: **it does not know what you fixed three
months ago.** The same defect can therefore be reintroduced repeatedly, and "someone remembers"
was never a reliable mechanism.

CounterGuard makes every fix a permanent check — and the check **knows when it should apply**.
Rules are not global; each guard's applicability boundary is learned from confirmed
counterexamples.

## Install

```powershell
uv sync
uv run counterguard --help

uv build
python -m pip install "dist/counterguard-0.1.0-py3-none-any.whl[runner]"
```

The wheel provides the CLI and library. Executing tests requires the `runner` extra, which
declares the pytest dependency. Without pytest, execution fails **before creating any output**
with exit `3` and a `counterguard[runner]` installation hint.

The offline Demo additionally needs the source distribution's `examples/`, `benchmarks/`,
`experiments/` and contract tests — these are not bundled in the library wheel.

## Quick start

```powershell
uv run counterguard demo --scenario examples/demo/mvp.yaml --workspace artifacts/quickstart-v1
```

One command runs the full pipeline from clean inputs and writes `report.json` and `report.md`.
Repeating it performs a read-only audit and re-renders existing records.

```powershell
uv run counterguard demo --workspace artifacts/quickstart-v1 --format markdown
uv run counterguard demo --workspace artifacts/quickstart-v1 --verify-only
```

**Note**: although the scenario is named `mvp.yaml`, it currently requires **JSON syntax**.
YAML indentation, comments and anchors are unsupported. The
[quickstart](docs/quickstart.md) includes valid input plus a real missing-contract `unknown`
replay.

The default Demo uses recorded proposals and trusted local fixtures — no network, no live
model. **It is not a sandbox for arbitrary Python.**

## Three states are kept separate

This is the core design: **applicability, execution outcome and final verdict are three
independent quantities.**

| Dimension | Values |
|---|---|
| `scope_decision` | `applicable` / `inapplicable` / `unknown` |
| `execution_outcome` | `not_run` / `pass` / `fail` / `error` / `timeout` |
| `final_verdict` | `pass` / `violation` / `skipped` / `inconclusive` |

**Inapplicable and unknown never start pytest** — they produce `not_run` + `skipped`.
Infrastructure failures produce `inconclusive`. A skipped target never becomes a pass.

Reports also show the minimal failed cases, the initial/refined rules, per-clause comparison
results, and source links. See [the CLI contract](docs/cli.md).

## How it works

Four steps, each of which produces a versioned, digest-bound artifact:

1. **Capture** — only a real buggy failure followed by a fixed pass counts as reproducible
   Evidence. Contract, test and target digests, structured case results and raw logs are all
   recorded.
2. **Compile** — the failed cases become an independent minimal Guard, self-checked against the
   fixed target before publication.
3. **Learn the boundary** — the guard's applicability is fitted from confirmed counterexamples.
   The solver receives only a `FeatureVector` plus a strict applicability bool; provenance,
   identity fields and leaking subclasses are rejected.
4. **Replay** — applicability is decided **before** pytest starts. Skipped rows keep `run=null`.

## Frozen benchmark

15 labeled scenarios: **9 training + 6 holdout**. Each guard has applicable and inapplicable
examples in both splits, and the holdout implementations use code shapes absent from training.

Scope features deliberately exclude contract IDs, paths, module names, target names, expected
outputs and oracle values — a rule cannot work by memorizing answers. One target is
**inapplicable while violating its own contract**, proving applicability cannot be inferred
from target correctness.

### Membership discount guard

Source contract: `membership_discount` final-price at version `v1`.

- members pay 80% of the original amount; non-members pay the original amount
- two decimal places, **half-up rounding**; negative amounts rejected

The compiled Guard retains **only the two member-price cases that failed on the source bug**.

### Query-limit validation guard

Source contract: default 20, accepting only ASCII decimal digit strings from 1 through 100.
Signed, padded, Unicode-digit, malformed and out-of-range input is rejected.

The compiled Guard retains **only the zero-rejection assertion**.

## Scope learning

```powershell
uv run counterguard scope learn --protocol experiments/scope_v1.json --phase initial --output artifacts/.../initial
uv run counterguard scope learn --protocol experiments/scope_v1.json --phase refined --output artifacts/.../refined
```

Both **initial** rules learn `contract_version == v1`. Adding the two frozen legal
counterexamples and refitting produces **version AND interface** rules:
`final_price` for discount, `query_parameter` for input-limit.

On all nine training rows:

| Phase | TP | FP | TN | FN |
|---|---:|---:|---:|---:|
| initial | 4 | 2 | 3 | 0 |
| **refined** | **4** | **0** | **5** | **0** |

Search space is recorded as `predicate_count` / `combination_count` — 8/92 for discount,
10/175 for input-limit. Twenty input permutations preserve the learned rule and digest.
**Holdout never enters fitting.**

## Replay and evaluation

```powershell
uv run counterguard benchmark replay --protocol experiments/scope_v1.json --phase refined --split train
uv run counterguard experiment evaluate --protocol experiments/scope_v1.json --split holdout --fitted artifacts/experiments/scope-v1/fitted --output artifacts/experiments/scope-v1/final
```

Training replay expects exit `1` because two applicable targets really violate their guards:
**2 pass, 2 violation, 5 skipped**, with exactly **4 pytest processes started**. Every skipped
row has `run=null`.

Four methods on the frozen holdout:

| Method | TP / FP / TN / FN | False-application rate | Bug recall |
|---|---|---:|---:|
| always | 2 / 4 / 0 / 0 | 1.0 | 1/1 |
| fixed interface | 2 / 2 / 2 / 0 | 0.5 | 1/1 |
| learned initial | 2 / 2 / 2 / 0 | 0.5 | 1/1 |
| **learned refined** | **2 / 0 / 4 / 0** | **0.0** | **1/1** |

**Refined corrected 2 false applications, retained 2 applicable cases, and added no FP/FN.**
The query guard has no held-out bug, so its Bug recall is reported as `null` rather than 100%.

The frozen confusion policy counts unknown as a negative prediction while also reporting its
rate and decision coverage. Raw results retain unknown.

> `evaluate` exiting 0 means **the experiment met its frozen acceptance**, not that every guard
> passed. These six labels are already public, so this is engineering validation rather than a
> blind benchmark.

`replay verify` audits current inputs **without executing pytest**. A successful audit means the
record is complete — **not that the recorded verdict was pass**.

## CLI and exit codes

`capture`, `compile`, `learn`, `replay run` and `evaluate` accept
`--format text|json|markdown`. Explicit formats wrap the original payload in
`command-report.v1`; without `--format` the original JSON shape is preserved. Formatting does
not change exit codes.

| Code | Meaning |
|---|---|
| `0` | reproduced Evidence / acceptance met |
| `1` | completed but not reproduced; or an applicable guard confirmed a violation |
| `2` | invalid input |
| `3` | execution failure (including missing pytest metadata) |
| `4` | insufficient information (`unknown`); or learning refused to generalize |
| `5` | artifact integrity failure |

Pytest exit codes 2–5, missing or ambiguous case results, and timeouts **cannot count as a
reproduced bug**.

## Development

The source checkout also provides [repository verification](docs/verify.md) and an
[append-only Guard lifecycle](docs/guard-lifecycle.md). `verify` replays reviewed
Shadow/Active Guards in Docker, with separate unknown, skipped, and execution-error
results. Its current scope is known source snapshots under the root-import profile;
the reviewed validators profile additionally supports src imports and pytest9.
Use `counterguard runner list` to discover reviewed image IDs and their sources,
then select a stable `--runner-id`. Other projects must meet the explicit
[admission conditions](docs/project-admission.md).

The [onboarding checklist](docs/onboarding.md) assigns responsibility for contracts,
bug/fix sources and initial Scope. `preflight --profile minimal-python --import-root src`
classifies static no-install/no-plugin candidates without authorizing execution.
The [CI example and Summary export](docs/github-actions.md) currently cover trusted tool
fixtures; generic project onboarding and live GitHub platform acceptance remain open.

```powershell
uv run pytest -m "not slow" -q      # fast tier: seconds
uv run ruff check .
uv run pytest -q --durations=20      # complete suite, once before delivery
```

Integration/e2e tests, heavy fixtures and real child processes are marked `slow`. **The fast
tier rejects unmarked real process launches during fixture setup, execution and teardown** — so
any new test that spawns a process must declare itself `slow`. See [testing.md](docs/testing.md).

## Project layout

```text
src/counterguard/     implementation and CLI
tests/                unit, integration and e2e suites
schemas/              JSON Schema for every artifact
benchmarks/           frozen labeled samples, splits and module context
examples/             demo scenario, contracts and implementations
experiments/          frozen experiment protocol
containers/           restricted Docker runner
docs/                 architecture, data contracts, CLI, security model, known limits
```

Runtime artifacts under `artifacts/` and distributions under `dist/` are excluded from Git.

## Security and limitations

Because CounterGuard executes code and reads repositories, its own security posture matters:

- **[docs/security-model.md](docs/security-model.md)** — assets, trust assumptions, and the
  concrete controls for repository inspection and container execution
- **[docs/attack-surface-checklist.md](docs/attack-surface-checklist.md)** — per-item status of
  what is tested, partially covered, and **not covered at all**
- **[docs/known-limitations.md](docs/known-limitations.md)** — the current scope statement and
  the historical verification boundary

Current releases are validated on local Python environments only. No claim is made about
cross-platform behavior, malicious-repository isolation, signature-based authentication or
program equivalence.

## License

[Apache-2.0](LICENSE)
