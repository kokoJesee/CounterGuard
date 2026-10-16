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
| W01 | File / network / CPU / memory / PID / descendant-process isolation for untrusted targets | Running unknown repositories |
| W02 | Git base/head, shallow clone, submodule and repository-link boundaries | — |
| W03 | Real-project plugin / conftest / dependency-install handling | Repositories whose tests need fixtures |
| W04 | Registry permissions and state, CI credentials, public report supply chain | CI integration |

Until W01 and W03 are closed with recorded evidence, **untrusted repositories are not executed
at all** — the tool refuses rather than falling back to local execution.

## Supported scope

Current releases are validated on **local Python environments** only. No claim is made about
cross-platform behavior, malicious-repository isolation, signature-based authentication,
general-purpose redaction, live-model stability, or program equivalence.

See [docs/known-limitations.md](docs/known-limitations.md) for the full statement of scope and
the [historical verification boundary](docs/known-limitations.md).
