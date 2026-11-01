"""Health and version endpoints."""

from fastapi import APIRouter, Request
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    """Check database connectivity and data-directory writability."""
    database_ok = False
    try:
        with request.app.state.session_factory() as session:
            session.execute(text("SELECT 1"))
        database_ok = True
    except SQLAlchemyError as error:
        request.app.state.logger.error("health_database_failed", extra={"error": str(error)})
    probe = request.app.state.settings.data_dir / ".trace-healthcheck"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        data_writable = True
    except OSError as error:
        request.app.state.logger.error("health_data_dir_failed", extra={"error": str(error)})
        data_writable = False
    return {
        "db_ok": database_ok,
        "data_dir_writable": data_writable,
        "engine_importable": request.app.state.settings.engine_mode == "fake" or (
            Path(__file__).resolve().parents[2] / "engine" / "pipeline.py"
        ).is_file(),
        "version": request.app.state.settings.app_version,
    }


@router.get("/version")
def version(request: Request) -> dict[str, str]:
    """Return the Trace API version."""
    return {"version": request.app.state.settings.app_version}
