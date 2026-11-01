"""Trace FastAPI application factory."""

import hmac
import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from starlette.staticfiles import StaticFiles

from api.config import Settings
from api.db.base import Base
from api.db import models as _models
from api.db.session import create_database_engine, create_session_factory
from api.errors import APIError
from api.routers import auth, cases, custody, files, health, results, reports, runs
from api.security import decode_access_token, hash_password
from api.services.audit import current_actor
from api.services.jobs import JobManager, recover_interrupted_runs
from api.db.models import User


class JsonLineFormatter(logging.Formatter):
    """Render structured logs as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "method": getattr(record, "method", None),
            "path": getattr(record, "path", None),
            "status_code": getattr(record, "status_code", None),
        }, ensure_ascii=True)


def create_app(settings: Settings | None = None, initialize_db: bool = True) -> FastAPI:
    """Construct an independently configurable Trace API application."""
    app_settings = settings or Settings()
    if app_settings.auth_mode == "apikey" and not app_settings.api_key:
        raise ValueError("API_KEY must be configured when AUTH_MODE=apikey.")
    if app_settings.auth_mode == "jwt" and not (
        app_settings.jwt_secret and app_settings.demo_username and app_settings.demo_password
    ):
        raise ValueError("JWT_SECRET, DEMO_USERNAME, and DEMO_PASSWORD are required when AUTH_MODE=jwt.")
    app_settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_database_engine(app_settings.resolved_database_url)
    factory = create_session_factory(engine)
    logger = logging.getLogger("trace.api")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLineFormatter())
        logger.addHandler(handler)
    logger.propagate = False
    if initialize_db:
        tables = [table for table in Base.metadata.sorted_tables if table.name != "users"]
        Base.metadata.create_all(engine, tables=tables)
        if app_settings.auth_mode == "jwt":
            User.__table__.create(engine, checkfirst=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        recover_interrupted_runs(factory)
        if app_settings.auth_mode == "jwt":
            User.__table__.create(engine, checkfirst=True)
            with factory() as session:
                seeded = session.scalar(select(User).where(User.username == app_settings.demo_username))
                if seeded is None:
                    session.add(User(
                        username=app_settings.demo_username or "",
                        password_hash=hash_password(app_settings.demo_password or ""),
                    ))
                    session.commit()
        app.state.jobs = JobManager(factory, app_settings)
        yield
        app.state.jobs.shutdown()
        engine.dispose()

    app = FastAPI(title="Trace API", version=app_settings.app_version, lifespan=lifespan)
    app.state.settings = app_settings
    app.state.engine = engine
    app.state.session_factory = factory
    app.state.logger = logger
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(cases.router)
    app.include_router(auth.router)
    app.include_router(runs.router)
    app.include_router(runs.ws_router)
    app.include_router(results.router)
    app.include_router(files.router)
    app.include_router(custody.router)
    app.include_router(reports.router)
    app.include_router(health.router)

    @app.middleware("http")
    async def trace_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        actor = "local-demo"
        protected = request.url.path.startswith("/api/") and request.url.path not in {
            "/api/health", "/api/version", "/api/auth/login",
        } and request.method != "OPTIONS"
        if protected and app_settings.auth_mode == "apikey":
            supplied = request.headers.get("X-API-Key", "")
            if not hmac.compare_digest(supplied, app_settings.api_key or ""):
                response = JSONResponse(
                    status_code=401,
                    content={"error": {"code": "unauthorized", "message": "A valid API key is required.", "details": None}},
                )
                response.headers["X-Request-ID"] = request_id
                response.headers["X-Trace-Engine"] = app_settings.engine_mode
                response.headers["X-Content-Type-Options"] = "nosniff"
                return response
            actor = "api-key"
        elif protected and app_settings.auth_mode == "jwt":
            authorization = request.headers.get("Authorization", "")
            if not authorization.startswith("Bearer "):
                response = JSONResponse(
                    status_code=401,
                    content={"error": {"code": "unauthorized", "message": "Sign in to continue.", "details": None}},
                )
                response.headers["X-Request-ID"] = request_id
                response.headers["X-Trace-Engine"] = app_settings.engine_mode
                response.headers["X-Content-Type-Options"] = "nosniff"
                return response
            try:
                actor = decode_access_token(authorization[7:], app_settings)
            except APIError as error:
                response = JSONResponse(
                    status_code=error.status_code,
                    content={"error": {"code": error.code, "message": error.message, "details": error.details}},
                )
                response.headers["X-Request-ID"] = request_id
                response.headers["X-Trace-Engine"] = app_settings.engine_mode
                response.headers["X-Content-Type-Options"] = "nosniff"
                return response
        if (
            request.url.path.startswith("/api/")
            and not request.url.path.endswith("/upload")
            and request.method in {"POST", "PUT", "PATCH"}
        ):
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    request_size = int(content_length)
                except ValueError:
                    request_size = app_settings.max_request_size + 1
                if request_size < 0 or request_size > app_settings.max_request_size:
                    response = JSONResponse(
                        status_code=413,
                        content={"error": {
                            "code": "request_too_large",
                            "message": "This request is larger than the allowed size.",
                            "details": None,
                        }},
                    )
                    response.headers["X-Request-ID"] = request_id
                    response.headers["X-Trace-Engine"] = app_settings.engine_mode
                    response.headers["X-Content-Type-Options"] = "nosniff"
                    return response
        request.state.actor = actor
        actor_token = current_actor.set(actor)
        try:
            response = await call_next(request)
        finally:
            current_actor.reset(actor_token)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Trace-Engine"] = app_settings.engine_mode
        logger.info(
            "http_request",
            extra={"request_id": request_id, "method": request.method, "path": request.url.path, "status_code": response.status_code},
        )
        return response

    @app.exception_handler(APIError)
    async def api_error_handler(_request: Request, error: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message, "details": error.details}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "invalid_request", "message": "Some information is missing or invalid.", "details": error.errors()}},
        )

    if app_settings.serve_frontend:
        _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Serve the existing Vite build with history fallback when present."""
    build_dir = Path(__file__).resolve().parents[1] / "dist"
    if not (build_dir / "index.html").is_file():
        raise RuntimeError("SERVE_FRONTEND is enabled, but the Vite dist/index.html build is missing.")
    app.mount("/assets", StaticFiles(directory=build_dir / "assets"), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend_fallback(full_path: str):
        candidate = (build_dir / full_path).resolve()
        if candidate.is_relative_to(build_dir.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(build_dir / "index.html")
