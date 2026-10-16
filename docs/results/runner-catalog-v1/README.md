# Reviewed runner profiles

The catalog contains two exact images, each backed by a build lock and a fresh
run of the original four Docker attack fixtures. The source Dockerfile was not
modified; the validators image uses its existing `PYTEST_VERSION=9.0.3` build arg.

| Runner ID | Profile | Build | Isolation attacks |
|---|---|---|---|
| root-pytest8 | Root imports, pytest 8.4.2 | [Receipt](root-build.json) | [4 passed, no skip](root-attacks.json) |
| validators-pytest9 | Reviewed validators src profile, pytest 9.0.3 | [Receipt](validators-build.json) | [4 passed, no skip](validators-attacks.json) |

Image archives, full package inventories and raw test logs remain local. Their
digests and references in the published receipts preserve what was checked;
the receipts do not claim that the archives are publicly downloadable.

Use [runner discovery](../../runners.md) to distinguish reviewed provenance from
current local image availability. These checks cover the fixed Docker profile,
not arbitrary plugins, package installation, host or daemon compromise, or CI
identity and permissions.
