"""Build only trusted, task-owned Git fixtures; inspection never runs their code."""

import os
import shutil
import subprocess
from pathlib import Path


def git(root: Path, *args: str) -> str:
    executable = shutil.which("git")
    assert executable
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    result = subprocess.run(
        [executable, "-c", "core.hooksPath=", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        env=environment,
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8").strip()


def sample_repository(root: Path) -> tuple[str, str]:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "EvidenceGuard fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    (root / "src").mkdir()
    (root / "contracts").mkdir()
    (root / "src/pricing.py").write_text("def price(x):\n    return x\n", encoding="utf-8")
    (root / "contracts/price.json").write_text('{"declared":"fixture"}\n', encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    before = git(root, "rev-parse", "HEAD")
    (root / "src/pricing.py").write_text(
        "raise RuntimeError('must never import')\n", encoding="utf-8"
    )
    git(root, "add", ".")
    git(root, "commit", "-m", "change")
    return before, git(root, "rev-parse", "HEAD")
