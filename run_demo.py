"""Migrate, optionally seed and pre-run a case, then start Trace."""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from api.config import Settings
from api.db.base import Base
from api.db import models as _models
from api.db.models import Case, EvidenceImage
from api.db.session import create_database_engine, create_session_factory
from api.main import create_app
from api.services.audit import record_audit
from api.services.custody_service import append_entry
from api.services.jobs import JobManager

PROJECT_ROOT = Path(__file__).resolve().parent
DEMO_IMAGE = PROJECT_ROOT / "testdata" / "demo_mixed" / "disk.img"
GROUND_TRUTH = PROJECT_ROOT / "testdata" / "demo_mixed" / "ground_truth.json"
SAFE_DATA_CHILDREN = {"evidence", "runs", "reports", "trace.db", "trace.db-shm", "trace.db-wal"}


def _safe_reset(data_dir: Path) -> None:
    """Remove only known demo-data children below the configured data directory."""
    root = data_dir.resolve()
    if root == Path(root.anchor) or root == PROJECT_ROOT.resolve() or not root.is_relative_to(PROJECT_ROOT.resolve()):
        raise ValueError("Refusing to reset a data directory outside the project data area.")
    root.mkdir(parents=True, exist_ok=True)
    for name in SAFE_DATA_CHILDREN:
        target = (root / name).resolve()
        if not target.is_relative_to(root) or not target.exists():
            continue
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()


def _database_settings(settings: Settings) -> None:
    """Apply the configured database URL to Alembic."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", settings.resolved_database_url.replace("%", "%%"))
    command.upgrade(config, "head")


def _seed_demo_case(settings: Settings, create_synthetic: bool) -> str | None:
    """Seed a real sample when present, or an explicitly synthetic demo image."""
    source = DEMO_IMAGE if DEMO_IMAGE.is_file() else None
    title = "Trace demo sample"
    if source is None and create_synthetic:
        title = "Synthetic demo image (not real evidence)"
    elif source is None:
        return None

    image_dir = settings.data_dir / "evidence"
    image_dir.mkdir(parents=True, exist_ok=True)
    engine = create_database_engine(settings.resolved_database_url)
    factory = create_session_factory(engine)
    try:
        with factory() as session:
            existing = session.scalar(select(Case).where(Case.title == title, Case.deleted_at.is_(None)))
            if existing is not None:
                latest = session.scalar(select(EvidenceImage).where(EvidenceImage.case_id == existing.id).limit(1))
                if latest and Path(latest.stored_path).is_file():
                    return existing.id
            case = Case(title=title, status="uploaded")
            session.add(case)
            session.flush()
            case_dir = image_dir / case.id
            case_dir.mkdir(parents=True, exist_ok=True)
            filename = source.name if source else "synthetic-demo.img"
            destination = case_dir / filename
            digest = hashlib.sha256()
            size = 0
            with destination.open("wb") as target:
                if source:
                    with source.open("rb") as input_file:
                        while chunk := input_file.read(1024 * 1024):
                            digest.update(chunk)
                            target.write(chunk)
                            size += len(chunk)
                else:
                    sample = b"TRACE SYNTHETIC DEMO IMAGE - not recovered evidence\n"
                    digest.update(sample)
                    target.write(sample)
                    size = len(sample)
            try:
                destination.chmod(0o444)
                locked = True
            except OSError:
                locked = False
            session.add(EvidenceImage(
                case_id=case.id,
                original_filename=filename,
                stored_path=str(destination.resolve()),
                size_bytes=size,
                sha256=digest.hexdigest(),
                read_only_locked=locked,
            ))
            append_entry(
                session,
                case.id,
                "EVIDENCE_RECEIVED",
                {"filename": filename, "size_bytes": size, "sha256": digest.hexdigest()},
            )
            if settings.demo_mode and GROUND_TRUTH.is_file():
                import json

                case.ground_truth = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
            elif settings.demo_mode and source is None:
                case.ground_truth = {"synthetic": True, "expected_count": 15}
            record_audit(session, "demo_seeded", case.id, {"synthetic": source is None})
            session.commit()
            return case.id
    finally:
        engine.dispose()


def _prerun(settings: Settings, case_id: str) -> None:
    """Run one demo recovery and wait for its persisted terminal status."""
    engine = create_database_engine(settings.resolved_database_url)
    factory = create_session_factory(engine)
    manager = JobManager(factory, settings)
    try:
        run = manager.start(case_id)
        deadline = time.monotonic() + settings.job_timeout + 10
        while time.monotonic() < deadline:
            with factory() as session:
                refreshed = session.get(_models.Run, run.id)
                if refreshed and refreshed.status in {"completed", "failed", "cancelled", "interrupted"}:
                    if refreshed.status != "completed":
                        raise RuntimeError(refreshed.error_message or f"Demo run ended as {refreshed.status}.")
                    print(f"Pre-run completed ({refreshed.engine_mode} engine, run {refreshed.id}).")
                    return
            time.sleep(0.25)
        raise TimeoutError("The pre-run did not finish before the configured timeout.")
    finally:
        manager.shutdown()
        engine.dispose()


def main() -> None:
    """Run the Trace API and optionally build the frontend."""
    parser = argparse.ArgumentParser(description="Run Trace API and frontend.")
    parser.add_argument("--reset", action="store_true", help="Safely clear Trace demo data under DATA_DIR.")
    parser.add_argument("--prerun", action="store_true", help="Seed and finish a demo recovery before starting.")
    parser.add_argument("--reload", action="store_true", help="Enable Uvicorn reload for development.")
    args = parser.parse_args()

    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if args.reset:
        _safe_reset(settings.data_dir)
    _database_settings(settings)
    case_id = _seed_demo_case(settings, create_synthetic=args.prerun)
    if args.prerun:
        if case_id is None:
            raise RuntimeError("No demo image could be seeded.")
        _prerun(settings, case_id)

    build_environment = os.environ.copy()
    build_environment["VITE_API_URL"] = "/api"
    build_environment["VITE_USE_MOCK"] = "false"
    build_command = ["npm", "run", "build"]
    if os.name == "nt":
        build_command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", "npm.cmd run build"]
    subprocess.run(build_command, cwd=PROJECT_ROOT, env=build_environment, check=True)
    settings.serve_frontend = True
    os.environ["SERVE_FRONTEND"] = "true"
    print("Trace is available at http://127.0.0.1:8000")
    if settings.engine_mode == "fake":
        print("Demo mode: responses identify the fake engine; outputs are synthetic.")
    if args.reload:
        uvicorn.run("api.asgi:app", host="127.0.0.1", port=8000, reload=True)
    else:
        uvicorn.run(create_app(settings, initialize_db=False), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
