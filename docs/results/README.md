# Published result records

This directory contains selected results that help reviewers understand and reproduce the project. It is not a complete archive of local execution logs.

Raw execution logs that contained workstation paths, and raw Registry event snapshots that included an individual operator label, were removed from public history during the privacy cleanup. Their JSON was not edited and reissued as if it were an original digest-bound record. Use the commands in [Testing](../testing.md), [Docker execution](../docker-execution.md), and the pilot reports to reproduce supported checks.

The privacy cleanup rewrote the Git commit history. Commit IDs embedded in older result records describe the pre-cleanup history and may not resolve in the current public `main`; the contents and recorded artifact digests were left unchanged. These digests provide integrity checks, not signatures or identity proof.
