import asyncio
import hashlib
import tracemalloc
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from api.config import Settings
from api.db.models import Case
from api.db.session import create_database_engine, create_session_factory
from api.services.cases import upload_evidence
from api.services.importer import validate_real_dependencies


def test_initial_migration_creates_database_schema(tmp_path):
    database_path = tmp_path / "empty.db"
    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "api" / "db" / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert {"cases", "evidence_images", "runs", "custody_entries", "audit_log"} <= tables
    assert "users" not in tables


class GeneratedUpload:
    filename = "../../outside.img"

    def __init__(self, total_bytes: int):
        self.remaining = total_bytes
        self.digest = hashlib.sha256()

    async def read(self, size: int) -> bytes:
        count = min(size, self.remaining)
        if count == 0:
            return b""
        chunk = b"x" * count
        self.digest.update(chunk)
        self.remaining -= count
        return chunk

    async def close(self) -> None:
        return None


def test_128_mib_upload_is_chunked_and_filename_is_sanitized(tmp_path):
    size = 128 * 1024 * 1024
    settings = Settings(
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{(tmp_path / 'upload.db').as_posix()}",
        max_upload_size=size + 1024,
    )
    settings.data_dir.mkdir(parents=True)
    engine = create_database_engine(settings.resolved_database_url)
    from api.db.base import Base
    from api.db import models as _models

    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    upload = GeneratedUpload(size)
    with factory() as session:
        case = Case(title="Streaming test")
        session.add(case)
        session.commit()
        tracemalloc.start()
        image = asyncio.run(upload_evidence(session, settings, case.id, upload, None))
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert image.size_bytes == size
        assert image.sha256 == upload.digest.hexdigest()
        assert image.original_filename == "outside.img"
        assert peak < 16 * 1024 * 1024
    engine.dispose()


def test_real_engine_dependencies_are_available_after_project_merge():
    validate_real_dependencies()
