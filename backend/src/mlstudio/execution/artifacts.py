"""Managed execution bytes and ordered, recoverable filesystem publication."""

import hashlib
import json
import os
import stat
from pathlib import Path
from uuid import UUID

from mlstudio.execution.schemas import Artifact


def canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def safe_path(home: Path, relative: str) -> Path:
    path = home / relative
    if (
        Path(relative).is_absolute()
        or path.absolute() != path.resolve()
        or not path.resolve().is_relative_to(home.resolve())
    ):
        raise ValueError("Unsafe managed artifact path.")
    current = path
    while current != home:
        if current.is_symlink() or current.is_junction():
            raise ValueError("Unsafe managed artifact link.")
        current = current.parent
    return path


def run_directory(home: Path, project_id: str, run_id: str) -> Path:
    return safe_path(home, f"projects/{UUID(project_id)}/runs/{UUID(run_id)}")


def regular(path: Path, limit: int) -> int:
    if path.resolve() != path.absolute() or path.is_symlink() or path.is_junction():
        raise ValueError("Artifact is redirected.")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise ValueError("Artifact is not a bounded regular file.")
    return info.st_size


def bounded_read(path: Path, limit: int) -> bytes:
    regular(path, limit)
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Artifact exceeds its bound.")
    return data


def reference(home: Path, path: Path, limit: int) -> dict:
    size = regular(path, limit)
    with path.open("rb") as stream:
        checksum = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
    if path.stat().st_size != size:
        raise ValueError("Artifact changed during inspection.")
    return Artifact(
        path=path.relative_to(home).as_posix(), sha256=checksum, size_bytes=size
    ).model_dump()


def verify(home: Path, artifact: dict) -> Path:
    ref = Artifact.model_validate(artifact)
    path = safe_path(home, ref.path)
    if reference(home, path, ref.size_bytes) != ref.model_dump():
        raise ValueError("Artifact integrity check failed.")
    return path


def sync_directory(path: Path) -> None:
    # Windows does not expose directory fsync through Python. File flush + same-volume
    # rename is used there; no cross-filesystem atomicity is claimed.
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if bounded_read(path, len(data)) != data:
        raise ValueError("Package read-back failed.")


def write_evidence(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    if temporary.exists():
        regular(temporary, 1024 * 1024)
        temporary.unlink()
    write_new(temporary, canonical(value))
    temporary.replace(path)
    sync_directory(path.parent)


def strict_json(data: bytes):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate JSON key.")
            result[key] = value
        return result

    def invalid(_value):
        raise ValueError("Nonfinite JSON constant.")

    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)
