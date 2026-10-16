"""Read committed Git data through disposable, configuration-free metadata."""

import hashlib
import os
import re
import stat
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Literal

from evidenceguard.digests import digest_bytes
from evidenceguard.models import Digest, FrozenModel
from evidenceguard.project_config import RepositoryPath, reject_links, repository_path

GIT_TIMEOUT = 5.0
OUTPUT_LIMIT = 2 * 1024 * 1024
BLOB_LIMIT = 1024 * 1024
METADATA_LIMIT = 16384
_OID = re.compile(r"^[0-9a-f]{40}$")
_REVISION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*(?:[~^][0-9]{0,5})*$")
_REF = re.compile(r"^refs/(?:heads|tags)/[A-Za-z0-9][A-Za-z0-9_./-]*$")


class RepositoryProblem(Exception):
    def __init__(self, code: str, *, rejected: bool = False):
        super().__init__(code)
        self.code, self.rejected = code, rejected


class FileChange(FrozenModel):
    path: RepositoryPath
    kind: Literal["A", "M", "D", "T"]
    old_mode: str
    new_mode: str


class FilePin(FrozenModel):
    revision: Literal["base", "head"]
    path: RepositoryPath
    object_id: str
    content_digest: Digest


class RepositorySnapshot(FrozenModel):
    schema_version: Literal["repository-snapshot.v1"] = "repository-snapshot.v1"
    status: Literal["ready", "unknown", "rejected"]
    reason_codes: tuple[str, ...] = ()
    base_commit: str | None = None
    head_commit: str | None = None
    shallow: bool = False
    git_version: str | None = None
    changes: tuple[FileChange, ...] = ()
    files: tuple[FilePin, ...] = ()


def validate_revision(value: str) -> str:
    if len(value) > 160 or not _REVISION.fullmatch(value) or ".." in value or "//" in value:
        raise ValueError("Use a commit ID, HEAD, branch/tag name and optional ~N/^N ancestry")
    return value


def _read(path: Path, limit: int = 1024 * 1024) -> bytes:
    reject_links(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
        raise RepositoryProblem("linked_or_special_metadata", rejected=True)
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise RepositoryProblem("repository_budget_exceeded")
    return data


def _walk(directory: Path):
    reject_links(directory)
    if not directory.exists():
        return
    pending, count = [directory], 0
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                count += 1
                if count > METADATA_LIMIT:
                    raise RepositoryProblem("repository_budget_exceeded")
                path = Path(entry.path)
                reject_links(path)
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    if len(path.relative_to(directory).parts) > 8:
                        raise RepositoryProblem("repository_budget_exceeded")
                    pending.append(path)
                elif not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
                    raise RepositoryProblem("linked_or_special_metadata", rejected=True)
                else:
                    yield path


def _metadata(gitdir: Path) -> dict[str, bytes]:
    reject_links(gitdir)
    if not gitdir.is_dir():
        raise RepositoryProblem("unsupported_git_layout")
    if (gitdir / "commondir").exists() or (gitdir / "reftable").exists():
        raise RepositoryProblem("unsupported_git_layout")
    result = {"HEAD": _read(gitdir / "HEAD", 1024)}
    for name in ("packed-refs", "shallow"):
        reject_links(gitdir / name)
        if (gitdir / name).exists():
            result[name] = _read(gitdir / name)
    for area in ("heads", "tags"):
        for path in _walk(gitdir / "refs" / area):
            ref = path.relative_to(gitdir).as_posix()
            if not _REF.fullmatch(ref) or ".." in ref or ref.endswith(".lock"):
                raise RepositoryProblem("unsupported_reference")
            result[ref] = _read(path, 1024)
    if sum(map(len, result.values())) > 2 * 1024 * 1024:
        raise RepositoryProblem("repository_budget_exceeded")
    return result


def _prepare_metadata(files: dict[str, bytes], destination: Path) -> None:
    (destination / "objects").mkdir()
    (destination / "refs/heads").mkdir(parents=True)
    (destination / "refs/tags").mkdir()
    (destination / "config").write_bytes(b"[core]\nrepositoryformatversion = 0\nbare = true\n")
    refs = {}
    for line in files.get("packed-refs", b"").splitlines():
        if line.startswith((b"#", b"^")):
            continue
        try:
            oid, ref = line.decode("ascii").split(" ", 1)
        except (ValueError, UnicodeError) as error:
            raise RepositoryProblem("unsupported_reference") from error
        if not _OID.fullmatch(oid):
            raise RepositoryProblem("unsupported_object_format")
        if _REF.fullmatch(ref) and ".." not in ref:
            refs[ref] = (oid + "\n").encode()
    refs.update({key: value for key, value in files.items() if key.startswith("refs/")})
    if len(refs) > 2048:
        raise RepositoryProblem("repository_budget_exceeded")
    for ref, value in {"HEAD": files["HEAD"], **refs}.items():
        if ref != "HEAD":
            repository_path(ref)
        try:
            text = value.decode("ascii").strip()
        except UnicodeError as error:
            raise RepositoryProblem("unsupported_reference") from error
        if re.fullmatch(r"[0-9a-f]{64}", text):
            raise RepositoryProblem("unsupported_object_format")
        if not _OID.fullmatch(text) and not (
            text.startswith("ref: ") and _REF.fullmatch(text[5:]) and ".." not in text
        ):
            raise RepositoryProblem("unsupported_reference")
        path = destination / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((text + "\n").encode())
    if "shallow" in files:
        if not all(_OID.fullmatch(line.decode("ascii")) for line in files["shallow"].splitlines()):
            raise RepositoryProblem("unsupported_object_format")
        (destination / "shallow").write_bytes(files["shallow"])


def _executable() -> str:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory or not Path(directory).is_absolute():
            continue
        path = Path(directory) / ("git.exe" if os.name == "nt" else "git")
        if path.is_file():
            return str(path.resolve())
    raise RepositoryProblem("git_unavailable")


def _git(
    gitdir: Path, objects: Path, *args: str, limit: int = OUTPUT_LIMIT, deadline: float
) -> bytes:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RepositoryProblem("inspection_timeout")
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
            "GIT_OBJECT_DIRECTORY": str(objects),
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ALLOW_PROTOCOL": "",
            "GIT_LITERAL_PATHSPECS": "1",
            "GIT_ATTR_NOSYSTEM": "1",
            "LC_ALL": "C",
        }
    )
    argv = [
        _executable(),
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
        "-c",
        "core.attributesFile=" + os.devnull,
        "-c",
        "protocol.allow=never",
        *args,
    ]
    buffers = [bytearray(), bytearray()]
    overflow = threading.Event()
    with subprocess.Popen(
        argv,
        cwd=gitdir,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    ) as process:

        def consume(stream, index, maximum):
            while chunk := stream.read(8192):
                if len(buffers[index]) + len(chunk) > maximum:
                    overflow.set()
                    process.kill()
                    return
                buffers[index].extend(chunk)

        threads = [
            threading.Thread(target=consume, args=(stream, index, cap), daemon=True)
            for index, stream, cap in ((0, process.stdout, limit), (1, process.stderr, 65536))
        ]
        for thread in threads:
            thread.start()
        try:
            process.wait(timeout=min(GIT_TIMEOUT, remaining))
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.wait()
            raise RepositoryProblem("git_timeout") from error
        finally:
            for thread in threads:
                thread.join(timeout=1)
        if overflow.is_set():
            raise RepositoryProblem("git_output_limit")
        if process.returncode:
            raise RepositoryProblem("git_read_failed")
    return bytes(buffers[0])


def _check_mode(mode: str) -> None:
    if mode == "120000":
        raise RepositoryProblem("symbolic_tree_entry", rejected=True)
    if mode not in {"000000", "100644", "100755"}:
        raise RepositoryProblem("submodule_or_nonfile_entry")


def read_repository(
    repo: str | Path, base: str, head: str, paths: tuple[str, ...] = ()
) -> RepositorySnapshot:
    """Resolve two committed snapshots without loading original config or working-tree code."""
    validate_revision(base)
    validate_revision(head)
    paths = tuple(sorted({repository_path(p) for p in paths}))
    if len(paths) > 2048:
        raise ValueError("At most 2048 explicitly mapped files may be inspected")
    commits, shallow, git_version = {}, False, None
    deadline = time.monotonic() + 30
    try:
        root = Path(repo).absolute()
        reject_links(root)
        if not root.is_dir():
            raise RepositoryProblem("repository_unavailable")
        gitdir = root / ".git"
        before = _metadata(gitdir)
        shallow = "shallow" in before
        objects = gitdir / "objects"
        total_size = 0
        for path in _walk(objects):
            if path.name in {"alternates", "http-alternates"}:
                raise RepositoryProblem("external_object_store", rejected=True)
            total_size += path.stat().st_size
            if total_size > 128 * 1024 * 1024:
                raise RepositoryProblem("repository_budget_exceeded")
        for ref in paths:
            reject_links(root / ref)
        with tempfile.TemporaryDirectory(prefix="eg-git-") as temporary:
            isolated = Path(temporary)
            _prepare_metadata(before, isolated)

            def read_git(*args, **kwargs):
                return _git(isolated, objects, *args, deadline=deadline, **kwargs)

            git_version = read_git("--version").decode("ascii").strip()
            for role, revision in (("base", base), ("head", head)):
                try:
                    value = (
                        read_git(
                            "rev-parse", "--verify", "--end-of-options", revision + "^{commit}"
                        )
                        .decode("ascii")
                        .strip()
                    )
                except RepositoryProblem as error:
                    if error.code != "git_read_failed":
                        raise
                    raise RepositoryProblem(
                        "shallow_history_insufficient" if shallow else "missing_" + role + "_commit"
                    ) from error
                if not _OID.fullmatch(value):
                    raise RepositoryProblem("unsupported_object_format")
                commits[role] = value
            try:
                read_git(
                    "fsck",
                    "--full",
                    "--strict",
                    "--no-reflogs",
                    "--no-dangling",
                    commits["base"],
                    commits["head"],
                )
            except RepositoryProblem as error:
                if error.code == "git_read_failed":
                    raise RepositoryProblem("git_object_integrity", rejected=True) from error
                raise
            raw = read_git(
                "diff-tree",
                "--no-commit-id",
                "--raw",
                "--no-abbrev",
                "--no-renames",
                "--no-ext-diff",
                "--no-textconv",
                "-r",
                "-z",
                commits["base"],
                commits["head"],
                "--",
            )
            pieces, changes = raw.split(b"\0"), []
            if pieces[-1] != b"" or (len(pieces) - 1) % 2:
                raise RepositoryProblem("invalid_git_output")
            for index in range(0, len(pieces) - 1, 2):
                header = pieces[index].decode("ascii").split()
                if len(header) != 5 or not header[0].startswith(":") or header[4] not in "AMDT":
                    raise RepositoryProblem("invalid_git_output")
                old_mode, new_mode = header[0][1:], header[1]
                _check_mode(old_mode)
                _check_mode(new_mode)
                changes.append(
                    FileChange(
                        path=repository_path(pieces[index + 1].decode("utf-8")),
                        kind=header[4],
                        old_mode=old_mode,
                        new_mode=new_mode,
                    )
                )
            pins, cache, size = [], {}, 0
            for role in ("base", "head"):
                for start in range(0, len(paths), 32):
                    entries = read_git(
                        "ls-tree",
                        "-z",
                        "--full-tree",
                        commits[role],
                        "--",
                        *paths[start : start + 32],
                    )
                    for entry in entries.split(b"\0"):
                        if not entry:
                            continue
                        header, path = entry.split(b"\t", 1)
                        mode, kind, oid = header.decode("ascii").split()
                        _check_mode(mode)
                        ref = repository_path(path.decode("utf-8"))
                        if kind != "blob" or ref not in paths or not _OID.fullmatch(oid):
                            raise RepositoryProblem("invalid_git_output")
                        if oid not in cache:
                            length = int(read_git("cat-file", "-s", oid))
                            if length > BLOB_LIMIT or size + length > 8 * BLOB_LIMIT:
                                raise RepositoryProblem("blob_budget_exceeded")
                            body = read_git("cat-file", "blob", oid, limit=BLOB_LIMIT)
                            header = b"blob " + str(len(body)).encode("ascii") + b"\0"
                            if (
                                len(body) != length
                                or hashlib.sha1(header + body, usedforsecurity=False).hexdigest()
                                != oid
                            ):
                                raise RepositoryProblem("git_object_integrity", rejected=True)
                            cache[oid], size = digest_bytes(body), size + len(body)
                        pins.append(
                            FilePin(
                                revision=role, path=ref, object_id=oid, content_digest=cache[oid]
                            )
                        )
        if before != _metadata(gitdir):
            raise RepositoryProblem("repository_changed_during_inspection")
        return RepositorySnapshot(
            status="ready",
            base_commit=commits["base"],
            head_commit=commits["head"],
            shallow=shallow,
            git_version=git_version,
            changes=tuple(sorted(changes, key=lambda row: row.path)),
            files=tuple(sorted(pins, key=lambda row: (row.revision, row.path))),
        )
    except RepositoryProblem as error:
        code, rejected = error.code, error.rejected
    except (ValueError, UnicodeError):
        code, rejected = "unsafe_repository_path_or_metadata", True
    except OSError:
        code, rejected = "repository_unavailable", False
    return RepositorySnapshot(
        status="rejected" if rejected else "unknown",
        reason_codes=(code,),
        base_commit=commits.get("base"),
        head_commit=commits.get("head"),
        shallow=shallow,
        git_version=git_version,
    )


def read_committed_files(
    repo: str | Path,
    revision: str,
) -> tuple[str, dict[str, bytes], tuple[FilePin, ...]]:
    """Read a bounded complete tree for static preflight, never the dirty working tree."""
    snapshot = read_repository(repo, revision, revision)
    if snapshot.status != "ready":
        raise RepositoryProblem(snapshot.reason_codes[0], rejected=snapshot.status == "rejected")
    gitdir = Path(repo).absolute() / ".git"
    before = _metadata(gitdir)
    objects = gitdir / "objects"
    deadline = time.monotonic() + 30
    files, pins, total = {}, [], 0
    with tempfile.TemporaryDirectory(prefix="eg-tree-") as temporary:
        isolated = Path(temporary)
        _prepare_metadata(before, isolated)
        entries = _git(
            isolated,
            objects,
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            snapshot.head_commit,
            deadline=deadline,
        )
        for entry in entries.split(b"\0"):
            if not entry:
                continue
            if len(files) >= 2048:
                raise RepositoryProblem("repository_budget_exceeded")
            header, raw_ref = entry.split(b"\t", 1)
            mode, kind, oid = header.decode("ascii").split()
            _check_mode(mode)
            ref = repository_path(raw_ref.decode("utf-8"))
            if kind != "blob" or not _OID.fullmatch(oid) or ref in files:
                raise RepositoryProblem("invalid_git_output", rejected=True)
            body = _git(
                isolated, objects, "cat-file", "blob", oid, deadline=deadline, limit=BLOB_LIMIT
            )
            total += len(body)
            if total > 8 * BLOB_LIMIT:
                raise RepositoryProblem("blob_budget_exceeded")
            blob = b"blob " + str(len(body)).encode("ascii") + b"\0" + body
            if hashlib.sha1(blob, usedforsecurity=False).hexdigest() != oid:
                raise RepositoryProblem("git_object_integrity", rejected=True)
            files[ref] = body
            pins.append(
                FilePin(revision="head", path=ref, object_id=oid, content_digest=digest_bytes(body))
            )
    if before != _metadata(gitdir):
        raise RepositoryProblem("repository_changed_during_inspection")
    return snapshot.head_commit, files, tuple(sorted(pins, key=lambda pin: pin.path))
