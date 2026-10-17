# Security Policy

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Preferred channel: GitHub's **Private vulnerability reporting / Security Advisory** on this
repository. If that is unavailable, open a *minimal* public issue that only asks the
maintainer for a private channel — do not include the details in it.

Please do not publish, before the maintainer has had reasonable time to investigate:

- customer files or reproduced source text
- credentials, access tokens, private paths or machine identifiers
- details that are directly exploitable

**There is currently no public security response SLA.**

## What this project does

CounterGuard verifies that previously fixed defects have not regressed. It runs real tests
against declared contracts and produces evidence artifacts with content digests.

Because it **executes code** and **reads repositories**, its own security posture matters.
The full detail lives in two documents — this file is only the entry point:

- **[docs/security-model.md](docs/security-model.md)** — assets, trust assumptions, and the
  concrete controls and limits for repository inspection (W3-A) and container execution (W3-B)
- **[docs/attack-surface-checklist.md](docs/attack-surface-checklist.md)** — a per-item list of
  what has been tested, what is partially covered, and **what is not covered at all**
  (A01–A11), plus the still-open requirements for untrusted repositories (W01–W04)

## Threat model (summary)

- **Assumed attacker capability**: can modify the record copies that are being verified.
- **Not assumed**: can simultaneously control the trusted source, all raw logs, the verifier
  itself, and its runtime environment.
- **Digests are not signatures.** They provide consistency and provenance linking. They are
  not author authentication, and they do not independently prove creation time or host
  identity. An attacker who can rewrite the source, the raw logs, all associated records *and*
  their digests is outside the current trust boundary.
- **Documented limits are not an OS sandbox.** The Docker runner applies non-root execution,
  read-only mounts, network isolation, capability removal and resource/log limits — but these
  are deliberate, documented limits, not a general-purpose sandbox for arbitrary Python.

## Currently open items

These are known, documented gaps. They are listed here rather than omitted, because an honest
scope is more useful than a false guarantee.

| ID | Open item | Blocks |
|---|---|---|
| W01 | The reviewed Docker profiles have recorded isolation tests; kernel/daemon compromise and arbitrary malicious pytest interference remain outside that evidence | Broader isolation claims |
| W02 | Bounded committed-object reads and path/history checks exist; comprehensive fuzzing and concurrent filesystem proofs remain open | Unsupported Git layouts |
| W03 | Independent literal contracts support reviewed source-only closures; native config, fixtures/plugins and target dependency installation remain unsupported | Native test-suite compatibility |
| W04 | Local immutable state and explicit Shadow/Active policy are implemented; identity, signatures/rollback resistance and remote authority remain open | Automated authorization of external contributions |

Only inputs admitted to a reviewed profile execute, exclusively in Docker. Unknown or
blocked inputs are refused; there is no local execution fallback for repository code.

## Supported scope

Recorded checks use local Python tooling and the pinned Linux Docker images. No claim is made about
an untested cross-platform matrix, general malicious-repository isolation, signature-based authentication,
general-purpose redaction, live-model stability, or program equivalence.

See [docs/known-limitations.md](docs/known-limitations.md) for the full statement of scope and
the [historical verification boundary](docs/known-limitations.md).
