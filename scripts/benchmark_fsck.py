"""Measure W3-A's exact fsck profile on bounded synthetic and current repositories."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
import zlib
from pathlib import Path


def _object(repo: Path, kind: bytes, body: bytes) -> str:
    raw = kind + b" " + str(len(body)).encode("ascii") + b"\0" + body
    oid = hashlib.sha1(raw, usedforsecurity=False).hexdigest()
    destination = repo / "objects" / oid[:2] / oid[2:]
    destination.parent.mkdir(exist_ok=True)
    if not destination.exists():
        destination.write_bytes(zlib.compress(raw))
    return oid


def _synthetic_repo(path: Path, blobs: int) -> tuple[str, str]:
    path.mkdir()
    (path / "objects").mkdir()
    (path / "refs/heads").mkdir(parents=True)
    (path / "config").write_text(
        "[core]\nrepositoryformatversion = 0\nbare = true\n", encoding="ascii"
    )
    tree = bytearray()
    for index in range(blobs):
        oid = _object(path, b"blob", f"fixture-{index:08d}\n".encode("ascii"))
        tree.extend(f"100644 file-{index:08d}.txt\0".encode("ascii"))
        tree.extend(bytes.fromhex(oid))
    tree_oid = _object(path, b"tree", bytes(tree))
    identity = b"CounterGuard <fixture@example.invalid> 946684800 +0000"
    base_body = b"tree " + tree_oid.encode() + b"\nauthor " + identity + b"\ncommitter "
    base_body += identity + b"\n\nbase\n"
    base = _object(path, b"commit", base_body)
    head_body = b"tree " + tree_oid.encode() + b"\nparent " + base.encode() + b"\nauthor "
    head_body += identity + b"\ncommitter " + identity + b"\n\nhead\n"
    head = _object(path, b"commit", head_body)
    (path / "refs/heads/main").write_text(head + "\n", encoding="ascii")
    (path / "HEAD").write_text("ref: refs/heads/main\n", encoding="ascii")
    return base, head


def _git_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "LANG"}
    }
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_COUNT": "0",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
    )
    return environment


def _argv(git: str, gitdir: Path, *args: str) -> list[str]:
    return [
        git,
        "--no-pager",
        "--no-replace-objects",
        "--no-optional-locks",
        f"--git-dir={gitdir}",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "gc.auto=0",
        "-c",
        "core.commitGraph=false",
        *args,
    ]


def _measure(git: str, gitdir: Path, base: str, head: str, repeats: int) -> list[float]:
    values = []
    for _ in range(repeats):
        started = time.perf_counter()
        subprocess.run(
            _argv(
                git,
                gitdir,
                "fsck",
                "--full",
                "--strict",
                "--no-reflogs",
                "--no-dangling",
                base,
                head,
            ),
            env=_git_environment(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
            check=True,
            shell=False,
        )
        values.append(round((time.perf_counter() - started) * 1000, 2))
    return values


def _summary(values: list[float]) -> dict[str, object]:
    ordered = sorted(values)
    p95_index = max(0, min(len(ordered) - 1, round(0.95 * len(ordered) + 0.5) - 1))
    return {
        "runs_ms": values,
        "min_ms": min(values),
        "median_ms": ordered[len(ordered) // 2],
        "p95_ms": ordered[p95_index],
        "max_ms": max(values),
        "under_w3a_process_limit": max(values) < 5000,
    }


def _current_repository(git: str, root: Path, repeats: int) -> dict[str, object]:
    gitdir = root / ".git"
    base = subprocess.run(
        _argv(git, gitdir, "rev-parse", "HEAD^"),
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
        env=_git_environment(),
    ).stdout.strip()
    head = subprocess.run(
        _argv(git, gitdir, "rev-parse", "HEAD"),
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
        env=_git_environment(),
    ).stdout.strip()
    count = subprocess.run(
        _argv(git, gitdir, "count-objects", "-v"),
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
        env=_git_environment(),
    ).stdout
    metrics = {
        key: int(value)
        for line in count.splitlines()
        for key, value in [line.split(": ", 1)]
        if value.isdigit()
    }
    return {"storage": metrics, "fsck": _summary(_measure(git, gitdir, base, head, repeats))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--object-counts", type=int, nargs="+", default=[1000, 5000, 10000, 16000])
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("refusing to overwrite an existing benchmark result")
    if args.repeats < 3 or any(value < 1 or value > 16000 for value in args.object_counts):
        raise SystemExit("use at least three repeats and 1..16000 synthetic blobs")
    git = shutil.which("git")
    if git is None:
        raise SystemExit("git is unavailable")
    git_version = subprocess.run(
        [git, "--version"], capture_output=True, text=True, check=True, timeout=5
    ).stdout.strip()
    root = Path(__file__).resolve().parents[1]
    rows = []
    with tempfile.TemporaryDirectory(prefix="eg-fsck-") as temporary:
        temporary_root = Path(temporary)
        for count in args.object_counts:
            gitdir = temporary_root / f"loose-{count}.git"
            base, head = _synthetic_repo(gitdir, count)
            loose = _summary(_measure(git, gitdir, base, head, args.repeats))
            subprocess.run(
                _argv(git, gitdir, "gc", "--prune=now"),
                env=_git_environment(),
                capture_output=True,
                timeout=30,
                check=True,
            )
            packed = _summary(_measure(git, gitdir, base, head, args.repeats))
            rows.append(
                {
                    "reachable_object_count": count + 3,
                    "requested_blob_count": count,
                    "loose": loose,
                    "packed": packed,
                }
            )
    result = {
        "schema_version": "fsck-benchmark.v1",
        "measurement_date": "2026-10-15",
        "git_version": git_version,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "profile": "fsck --full --strict --no-reflogs --no-dangling <base> <head>",
        "w3a_single_process_limit_ms": 5000,
        "repeats": args.repeats,
        "current_repository": _current_repository(git, root, args.repeats),
        "synthetic": rows,
        "interpretation": (
            "Object count alone is not a timeout predictor; loose versus packed storage and host "
            "filesystem cache materially change the result. Admit pilots by local preflight margin."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
