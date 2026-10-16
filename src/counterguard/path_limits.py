"""Portable path budgets including atomic temporary files and pytest caches."""

from pathlib import Path, PurePath

PATH_BUDGET = 240
PLACEHOLDER_ID = "0" * 32


def path_units(path: PurePath) -> int:
    absolute = path if path.is_absolute() else Path.cwd() / path
    return len(str(absolute).encode("utf-16-le")) // 2


def require_paths(*paths: PurePath) -> None:
    for path in paths:
        units = path_units(path)
        if units > PATH_BUDGET:
            raise ValueError(
                f"Artifact path exceeds {PATH_BUDGET} UTF-16 units ({units}); "
                "choose a shorter workspace/output directory or identity"
            )


def require_publication(path: PurePath) -> None:
    require_paths(path, path.parent / f".{path.name}.{PLACEHOLDER_ID}.tmp")


def require_run_directory(directory: PurePath) -> None:
    require_paths(
        *(directory / name for name in ("pytest.ini", "stdout.txt", "stderr.txt", "junit.xml")),
        directory / ".pytest_cache/v/cache/lastfailed",
    )


def require_replay_directory(directory: PurePath) -> None:
    require_publication(directory / "result.json")
    require_publication(directory / "feature.json")
    require_run_directory(directory / "runs" / f"run_{PLACEHOLDER_ID}")


def require_evaluation_directory(directory: PurePath) -> None:
    for name in (
        "manifest.json",
        "predictions.jsonl",
        "metrics.json",
        "replays.jsonl",
        "source-checks.jsonl",
        "paired-refinement.json",
        "report.md",
        "failure.json",
    ):
        require_publication(directory / name)
    require_replay_directory(directory / "runtime/replays" / f"rpl_{PLACEHOLDER_ID}")
