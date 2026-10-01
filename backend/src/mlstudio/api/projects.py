from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from mlstudio.db.session import get_session
from mlstudio.models import Project, utc_now
from mlstudio.profile_schemas import ProfileResponse
from mlstudio.schemas import (
    DatasetPatch,
    DatasetResponse,
    ProjectCreate,
    ProjectPatch,
    ProjectResponse,
)
from mlstudio.services import datasets
from mlstudio.services.profiles import read_profile
from mlstudio.services.project_deletion import delete_project
from mlstudio.services.source import DomainError

router = APIRouter(prefix="/projects", tags=["projects"])
Database = Annotated[Session, Depends(get_session)]


def get_project(project_id: str, session: Database) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise DomainError("Project not found.", 404)
    return project


CurrentProject = Annotated[Project, Depends(get_project)]


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(body: ProjectCreate, session: Database):
    project = Project(**body.model_dump())
    session.add(project)
    session.commit()
    return project


@router.get("", response_model=list[ProjectResponse])
def list_projects(session: Database):
    return session.scalars(select(Project).order_by(Project.updated_at.desc(), Project.id)).all()


@router.get("/{project_id}", response_model=ProjectResponse)
def retrieve_project(project: CurrentProject):
    return project


@router.delete("/{project_id}", status_code=204)
def remove_project(
    project_id: str, revision: Annotated[int, Query(ge=1)], session: Database, request: Request
):
    delete_project(session, project_id, revision, request.app.state.settings)
    return Response(status_code=204)


@router.get("/{project_id}/dataset/profile", response_model=ProfileResponse)
def profile(
    project: CurrentProject,
    session: Database,
    request: Request,
    dataset_id: str,
    revision: Annotated[int, Query(ge=1)],
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return read_profile(
        session, project.id, dataset_id, revision, offset, request.app.state.settings
    )


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(body: ProjectPatch, project: CurrentProject, session: Database):
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(project, key, value)
    if changes:
        project.updated_at = utc_now()
    session.commit()
    return project


@router.post("/{project_id}/dataset", response_model=DatasetResponse, status_code=201)
def upload_dataset(
    project: CurrentProject,
    session: Database,
    request: Request,
    file: UploadFile,
    expected_dataset_id: Annotated[str | None, Form()] = None,
):
    return datasets.ingest(session, project, file, expected_dataset_id, request.app.state.settings)


@router.get("/{project_id}/dataset", response_model=DatasetResponse)
def retrieve_dataset(project: CurrentProject, session: Database, request: Request):
    return datasets.read_dataset(session, project, request.app.state.settings)


@router.patch("/{project_id}/dataset", response_model=DatasetResponse)
def configure_dataset(
    body: DatasetPatch, project: CurrentProject, session: Database, request: Request
):
    return datasets.configure(session, project, body, request.app.state.settings)
