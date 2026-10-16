# Unified validators verification

The [selected acceptance summary](acceptance.json) records actual Docker capture,
minimal compilation and two independent calls through the unified `verify` entry.
It covers the fixed validators owner head and MAC cases, not arbitrary projects
or learned Scope generalization. Original records remain in new local namespaces.

- Existing owner head: `a7565a59962bf9c784cd1c6dc4ad8df0ee0effd5`.
- No owner commit was created or rewritten. The historical `evidenceguard.yaml`
  and the contract were read from that head; upstream files remain unchanged.
- Buggy/fixed capture: exits **1 / 0**, ten cases each. Two LF cases fail on buggy;
  only those cases enter the Guard, whose head self-check passes.
- Both unified replays: **one Guard, one execution, one pass**, exit **0**.
  Run IDs differ; counts and decision digests agree.
- Independent audit: **1 passed in 95.10 s**, rebuilding authorization from
  committed sources, current Registry state, runner review and raw JUnit/logs.

Validation commands used a task-owned local `--basetemp` directory:

```powershell
uv run pytest -m "not slow" -q
uv run pytest tests/e2e/test_verify.py tests/integration/test_registry_cli.py -q
# With COUNTERGUARD_PILOT_MANIFEST and COUNTERGUARD_VERIFY_REPORTS explicitly set:
uv run pytest tests/integration/test_repository_verify_live.py -q
uv run ruff check .
```

Given the retained local owner clone and the newly captured Registry/source chain,
repeat verification in a fresh output namespace with the frozen manifest values:

```powershell
$reviewedPilot = Get-Content integrations/pilot/manifest-v6.yaml -Raw | ConvertFrom-Json
uv run counterguard verify --repo $reviewedPilot.repository_ref --base $reviewedPilot.base_sha --head $reviewedPilot.head_sha --config $reviewedPilot.config_ref --registry $reviewedPilot.registry_root_ref --runner-id validators-pytest9 --output artifacts/verify/validators-new-check
```

The output directory must not already exist. The manifest is a record of local
inputs, not a download service for the owner clone or source artifacts.

The fast tier passed **605**, with **201 deselected**, in 29.11 s. The root-profile
integration checks passed **2** in 28.35 s. Both reviewed runner images separately
passed the four original Docker isolation fixtures without skips; their receipts
are in [runner provenance](../runner-catalog-v1/README.md). The full suite was not run.

The basic wheel was installed in an isolated environment outside the project and
successfully queried the offline catalog. The wheel includes the catalog. A first
local source build exposed that untracked personal documentation can enter an
sdist; it was not published. The local guide was moved outside the repository and
the source distribution rebuilt in a fresh directory, with its absence checked.

The owner head is still local-only. Clean remote CI reproduction requires its
publication or a trusted artifact-transfer route; neither was invented here.
Full provenance validation remains slow. General repository capture/compile,
learned-scope bindings, dependency installation, plugins, CI identities and a
public-log export format remain outside this acceptance scope.

Source and evidence are bound to the actual package digests recorded in the
summary. The implementation archive truthfully records an uncommitted working
tree during capture; no synthetic Git commit or time was used as evidence.
