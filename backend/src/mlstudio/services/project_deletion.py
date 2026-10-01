"""Permanent deletion with a reversible filesystem rename before database commit."""

import shutil
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import Session

from mlstudio.core.config import Settings
from mlstudio.models import Dataset, Project, utc_now
from mlstudio.services.source import DomainError


def checked_directory(root: Path, area: str, project_id: str) -> Path:
    path = root / area / project_id
    if path.resolve() != path.absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise DomainError("Project storage location is unsafe; deletion was not performed.", 409)
    return path


def check_tree(path: Path) -> None:
    if not path.exists():
        return
    # Never follow junctions/symlinks into data owned outside this Project.
    if not path.is_dir() or path.is_symlink() or path.is_junction():
        raise DomainError("Project storage contains an unsafe filesystem link.", 409)
    for child in path.iterdir():
        if child.is_symlink() or child.is_junction():
            raise DomainError("Project storage contains an unsafe filesystem link.", 409)
        if child.is_dir():
            check_tree(child)


def delete_project(session: Session, project_id: str, revision: int, settings: Settings) -> None:
    try:
        project_id = str(UUID(project_id))
    except ValueError:
        raise DomainError("Project not found.", 404) from None
    original = checked_directory(settings.home, "projects", project_id)
    pending = checked_directory(settings.home, ".deleting", project_id)
    project = session.get(Project, project_id)
    if project is None:
        if not pending.exists():
            raise DomainError("Project not found.", 404)
        # Retry a purge that failed after metadata was successfully removed.
        check_tree(pending)
        try:
            shutil.rmtree(pending)
        except FileNotFoundError:
            pass  # Another cleanup request already removed the staged directory.
        except OSError:
            raise DomainError(
                "Project metadata is deleted; managed file cleanup failed. Retry deletion.", 503
            ) from None
        return
    if project.revision != revision:
        raise DomainError("Project changed. Reload before confirming deletion.", 409)
    moved = False
    try:
        # Acquire the revision-guarded write lock BEFORE inspecting/recovering
        # staging. Otherwise another live deletion's rename looks like a crash.
        project.updated_at = utc_now()
        session.flush()
        check_tree(original)
        check_tree(pending)
        if pending.exists():
            if original.exists():
                raise DomainError(
                    "Project deletion storage is inconsistent; deletion was stopped.", 409
                )
            pending.rename(original)
        project.target_column = None
        project.active_dataset_id = None
        session.flush()  # Check revision and acquire the database write lock.
        session.execute(delete(Dataset).where(Dataset.project_id == project.id))
        session.delete(project)
        session.flush()
        if original.exists():
            pending.parent.mkdir(exist_ok=True)
            original.rename(pending)
            moved = True
        session.commit()
    except Exception:
        session.rollback()
        if moved:
            pending.rename(original)
        raise
    if moved:
        try:
            shutil.rmtree(pending)
        except FileNotFoundError:
            pass  # A concurrent post-commit retry completed the same cleanup.
        except OSError:
            raise DomainError(
                "Project metadata is deleted; managed file cleanup failed. Retry deletion.", 503
            ) from None
