from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from mlstudio.api.health import router
from mlstudio.api.projects import router as projects_router
from mlstudio.api.upload_limit import UploadLimitMiddleware
from mlstudio.core.config import Settings
from mlstudio.db.session import create_database_engine
from mlstudio.services.source import DomainError


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_database_engine(settings)
        app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        try:
            yield
        finally:
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
