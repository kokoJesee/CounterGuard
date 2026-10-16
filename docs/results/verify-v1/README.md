# Repository verification results

The [selected acceptance summary](acceptance.json) records the root-import
verification profile and local Guard lifecycle. It is a new summary of actual
test reports; it does not replace or re-sign the original reports or raw logs.
The implementation source digests identify the tested package bytes.

Final checks:

- `uv run pytest -m "not slow" -q`: **588 passed, 200 deselected**, 25.72 s.
- `uv run pytest tests/e2e/test_verify.py tests/integration/test_registry_cli.py -q`:
  **2 passed**, 25.30 s, with an explicit reviewed runner image and no Docker skip.
- `uv run ruff check .`: passed.
- The full suite was not run; it remains a delivery acceptance check.

The actual test commands also supplied a task-owned `--basetemp` directory.
Its workstation path and raw logs are intentionally local. The Windows sandbox
denied immutable-file hard links and Docker named-pipe access, so the checks ran
outside that sandbox without weakening the product's publication or Docker policy.

The real Git/Docker test captures trusted project fixtures first, then forbids
the local executor for all repository verification calls. A known regression
produces a recorded violation with exit 0 in Shadow and exit 1 in Active.
Two independent Active replays have identical counts and decision digests, with
distinct run IDs. A later, unreviewed source snapshot returns unknown with no run.

The summary includes selected row decisions and the original report digests.
It omits raw source workspaces, Registry actor records and process logs; the
summary alone is not an independently portable provenance bundle.

This result does not validate learned Scope generalization, the validators
`guard.v2` / `src` profile through the new generic entry, authenticated state
transitions, CI permissions, signatures or a general public-log export format.
See [verify](../../verify.md) and [Guard lifecycle](../../guard-lifecycle.md).
