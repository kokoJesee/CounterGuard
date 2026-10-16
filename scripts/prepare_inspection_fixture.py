"""Create a new two-commit trusted fixture; never initialize an untrusted repository."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare(output: Path) -> dict[str, str]:
    output = output.resolve()
    if not output.is_relative_to(ROOT) or output == ROOT:
        raise ValueError("Fixture output must stay below the source workspace")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a new empty fixture directory; historical repositories are preserved")
    source = ROOT / "tests/fixtures/repos/sample_project"
    output.mkdir(parents=True, exist_ok=True)
    executable = shutil.which("git")
    if executable is None:
        raise OSError("Git is required")
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)

    def git(*args):
        result = subprocess.run(
            [executable, "-c", "core.hooksPath=", "-c", "commit.gpgsign=false", *args],
            cwd=output,
            env=environment,
            capture_output=True,
            check=True,
        )
        return result.stdout.decode("utf-8").strip()

    shutil.copytree(
        source / "base", output, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__")
    )
    git("init", "-b", "main")
    git("config", "user.name", "CounterGuard inspection fixture")
    git("config", "user.email", "fixture@example.invalid")
    git("add", ".")
    git("commit", "-m", "fixture base")
    base = git("rev-parse", "HEAD")
    shutil.copytree(
        source / "head", output, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__")
    )
    git("add", ".")
    git("commit", "-m", "fixture changed source")
    return {
        "repository": output.relative_to(ROOT).as_posix(),
        "base": base,
        "head": git("rev-parse", "HEAD"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output)))
