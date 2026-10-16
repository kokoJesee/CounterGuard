# Tests

CounterGuard uses pytest for unit and integration tests and Ruff for linting. Run these from the repository root after `uv sync`.

```powershell
uv run pytest -m "not slow" -q
uv run ruff check .
```

The quick command selects tests marked for routine feedback. It does not replace the full suite. Before a release or major change, run:

```powershell
uv run pytest -q --durations=20
```

Integration and end-to-end tests, tests that depend on expensive pipeline setup, and tests that start real subprocesses are classified as slow. To run that group alone:

```powershell
uv run pytest -m slow -q --durations=20
```

Docker tests require Docker Desktop or a compatible Linux engine and the image profile documented in [Docker execution](docker-execution.md). Run the fixed-runner attack fixtures with:

```powershell
uv run pytest -m docker tests/integration/test_docker_runner.py -q
```

Pytest does not hide slow tests by default; `uv run pytest -q` runs the full collected suite. The published test-tier records are historical snapshots. See [selected results](results/README.md) for their scope and limits.
