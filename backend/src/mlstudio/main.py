import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from mlstudio.api.code_drafts import router as code_drafts_router
from mlstudio.api.health import router
from mlstudio.api.projects import router as projects_router
from mlstudio.api.runs import router as runs_router
from mlstudio.api.upload_limit import UploadLimitMiddleware
from mlstudio.core.config import Settings
from mlstudio.db.session import create_database_engine
from mlstudio.execution.coordinator import Coordinator
from mlstudio.services.source import DomainError


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_database_engine(settings)
        app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        app.state.execution = Coordinator(settings, app.state.session_factory)
        app.state.execution.startup()
        try:
            yield
        finally:
            app.state.execution.close()
            engine.dispose()

    app = FastAPI(title=settings.app_name, version=version("mlstudio"), lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(UploadLimitMiddleware, max_bytes=settings.max_csv_upload_bytes + 1024 * 1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(router, prefix=settings.api_prefix)
    app.include_router(projects_router, prefix=settings.api_prefix)
    app.include_router(runs_router, prefix=settings.api_prefix)
    app.include_router(code_drafts_router, prefix=settings.api_prefix)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, error):
        # Rejected numeric inputs may contain inf/NaN (including JSON 1e309).
        # Preserve validation locations/messages without making the 422 itself
        # invalid JSON. This never coerces or accepts the rejected configuration.
        errors = error.errors()
        if "/code-drafts" in _request.url.path:
            errors = [
                {key: value for key, value in item.items() if key not in ("input", "ctx")}
                for item in errors
            ]
        detail = jsonable_encoder(
            errors, custom_encoder={float: lambda v: v if math.isfinite(v) else None}
        )
        return JSONResponse({"detail": detail}, status_code=422)

    @app.exception_handler(DomainError)
    async def domain_error(_request, error):
        return JSONResponse({"detail": error.message}, status_code=error.status_code)

    @app.exception_handler(StaleDataError)
    async def stale_error(_request, _error):
        return JSONResponse({"detail": "Project changed. Reload and try again."}, status_code=409)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_request, _error):
        return JSONResponse(
            {"detail": "Database operation failed. Check migrations and retry."}, status_code=503
        )

    @app.exception_handler(OSError)
    async def storage_error(_request, _error):
        return JSONResponse(
            {"detail": "Managed storage is unavailable. Check workspace access."}, status_code=503
        )

    return app
