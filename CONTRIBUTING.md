# Contributing to CounterGuard

Thanks for your interest. This document covers what contributions are welcome, the
development workflow, and the **project-specific rules** that keep the evidence chain
trustworthy.

## What is welcome

| Type | Notes |
|---|---|
| Bug reports | Always welcome — please include reproduction steps |
| Documentation fixes | Always welcome |
| New benchmark scenarios | Welcome — see "evidence requirements" below |
| Cross-platform / packaging fixes | Welcome |
| New runtime dependencies | ⚠️ Open an issue first |
| Changes to core protocols | ⚠️ Open an issue first |
| Changes to frozen benchmark data or evaluation criteria | ❌ Not accepted in place — see rule 1 |

## Development setup

```powershell
uv sync
uv run pytest -m "not slow" -q      # fast tier: no real child processes
uv run ruff check .
```

Before opening a pull request, run the complete suite once:

```powershell
uv run pytest -q --durations=20
```

**Test tiers**: integration/e2e tests, heavy prepared fixtures and real child processes are
marked `slow`. The fast tier *rejects* unmarked real process launches during fixture setup,
execution and teardown — so every new test that spawns a process must declare itself `slow`.
Definitions and timing evidence are in [docs/testing.md](docs/testing.md).

## Project-specific rules

These are not generic guidelines. They come from how this project actually works, and they
exist because the value of the project is the trustworthiness of its evidence.

### 1. Frozen assets are never edited in place

These files define the current experiment. They must not be modified to make results look
better:

- `experiments/scope_v1.json`
- `benchmarks/splits/scope_v1.json`
- `benchmarks/context/scope_v1.json`
- the labeled samples under `benchmarks/`

To change the criteria, create a **new protocol version** (e.g. `scope_v2`) in a new
directory. The original stays intact.

### 2. Semantic changes require a new version, never an in-place overwrite

If a stored artifact's meaning changes, publish a new `schema_version` or a new versioned
directory. Historical records keep their bytes and digests. New runs of the same input are
read-only audits.

### 3. Failures must be preserved and explained

If an experiment fails, keep the raw result, package it, and explain it. Do not re-run until
it looks better, and do not delete failing artifacts. A reported failure with its evidence is
more valuable than a silent success.

### 4. Every claim needs a reproducible check

A change in behavior must state how to verify it — a command, a test, or an artifact
comparison. "It works now" is not verifiable.

### 5. Do not overwrite published artifacts

New runs use new IDs and new output directories. Do not modify or re-sign historical
manifests to match a newer code state; use a new workspace instead.

## Pull request checklist

- [ ] **Purpose** — what problem does this solve?
- [ ] **Impact** — which artifact layers must be re-materialized?
      (contract / evidence / guard / feature / scope / replay / evaluation)
- [ ] **Verification** — which commands or tests prove it works?
- [ ] **Not done** — what was deliberately left out, and why?
- [ ] Frozen assets untouched, or a new version was created
- [ ] `uv run ruff check .` passes

## Reporting issues

Please include:

1. **Reproduction** — the exact commands you ran
2. **Expected** — what you expected to happen
3. **Actual** — what happened instead, including the exit code
   (see the exit-code table in [README.md](README.md))
4. **Environment** — OS, Python version, and whether Docker is available

If the report involves a security issue, follow [SECURITY.md](SECURITY.md) instead of
opening a public issue.

## License

By contributing, you agree that your contributions are licensed under
[Apache-2.0](LICENSE).
