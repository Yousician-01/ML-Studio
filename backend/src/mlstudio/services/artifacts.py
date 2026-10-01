import hashlib
from pathlib import Path
from uuid import UUID

from mlstudio.services.source import DomainError


def source_path(home: Path, project_id: str, dataset_id: str) -> Path:
    # IDs are generated internally; validation also protects corrupted metadata.
    try:
        project_id, dataset_id = str(UUID(project_id)), str(UUID(dataset_id))
    except ValueError:
        raise DomainError("Invalid managed artifact identity.", 409) from None
    owner = home / "projects" / project_id / "datasets" / dataset_id
    result = (owner / "source.csv").resolve()
    if not result.is_relative_to(home.resolve()) or result.parent != owner.absolute():
        raise DomainError("Managed artifact location is invalid.", 409)
    return result


def fingerprint(path: Path) -> str:
    with path.open("rb") as stream:
        return "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


def verified_source(home: Path, dataset) -> Path:
    path = source_path(home, dataset.project_id, dataset.id)
    expected_reference = path.relative_to(home).as_posix()
    if dataset.source_relative_path != expected_reference:
        raise DomainError("Managed source reference is invalid.", 409)
    if not path.is_file():
        raise DomainError("Managed source is missing. Dataset metadata has been preserved.", 409)
    if fingerprint(path) != dataset.fingerprint:
        raise DomainError(
            "Managed source integrity check failed. Dataset metadata has been preserved.", 409
        )
    return path
