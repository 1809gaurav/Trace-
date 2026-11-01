"""Case and evidence persistence services."""

import asyncio
import hashlib
import os
import re
import shutil
import threading
import uuid
from pathlib import Path, PurePosixPath

import aiofiles
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import Settings
from api.db.models import Case, EvidenceImage, utc_now
from api.errors import APIError
from api.services.audit import record_audit
from api.services.custody_service import append_entry

CHUNK_SIZE = 1024 * 1024
_upload_locks: dict[str, asyncio.Lock] = {}
_upload_locks_guard = threading.Lock()


def _lock_for_case(case_id: str) -> asyncio.Lock:
    with _upload_locks_guard:
        return _upload_locks.setdefault(case_id, asyncio.Lock())


def create_case(session: Session, title: str) -> Case:
    """Create a case record."""
    case = Case(title=title.strip() or "Untitled case")
    session.add(case)
    session.flush()
    record_audit(session, "case_created", case.id, {"title": case.title})
    session.commit()
    return case


def get_case(session: Session, case_id: str) -> Case:
    """Return a live case or raise a not-found API error."""
    case = session.scalar(select(Case).where(Case.id == case_id, Case.deleted_at.is_(None)))
    if case is None:
        raise APIError(404, "case_not_found", "We could not find that case.")
    return case


def case_image(session: Session, case_id: str) -> EvidenceImage | None:
    """Return the newest uploaded evidence image for a case."""
    return session.scalar(
        select(EvidenceImage).where(EvidenceImage.case_id == case_id).order_by(EvidenceImage.uploaded_at.desc()).limit(1)
    )


def soft_delete_case(session: Session, case_id: str) -> None:
    """Soft-delete a case while retaining its evidence files."""
    case = get_case(session, case_id)
    case.deleted_at = utc_now()
    case.status = "cancelled"
    record_audit(session, "case_deleted", case.id, {"evidence_retained": True})
    session.commit()


def _safe_filename(value: str) -> str:
    normalized = value.replace("\\", "/")
    name = PurePosixPath(normalized).name
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    return cleaned[:180] or "evidence-image.bin"


async def upload_evidence(
    session: Session,
    settings: Settings,
    case_id: str,
    upload: UploadFile,
    expected_sha256: str | None,
) -> EvidenceImage:
    """Serialize uploads per case and stream bytes into protected storage."""
    async with _lock_for_case(case_id):
        return await _upload_evidence(session, settings, case_id, upload, expected_sha256)


async def _upload_evidence(
    session: Session,
    settings: Settings,
    case_id: str,
    upload: UploadFile,
    expected_sha256: str | None,
) -> EvidenceImage:
    """Stream, hash, and lock an evidence image without buffering it in memory."""
    case = get_case(session, case_id)
    case_dir = (settings.data_dir / "evidence" / case_id).resolve()
    root = settings.data_dir.resolve()
    if not case_dir.is_relative_to(root):
        raise APIError(400, "invalid_path", "The evidence destination is not valid.")
    case_dir.mkdir(parents=True, exist_ok=True)
    free_space = shutil.disk_usage(case_dir).free
    expected_size = getattr(upload, "size", None)
    if free_space < (expected_size if isinstance(expected_size, int) else CHUNK_SIZE):
        raise APIError(507, "insufficient_space", "There is not enough free storage to receive this image.")

    temporary_path = case_dir / f".{uuid.uuid4().hex}.upload"
    final_path: Path | None = None
    digest = hashlib.sha256()
    size = 0
    committed = False
    try:
        async with aiofiles.open(temporary_path, "wb") as destination:
            while chunk := await upload.read(CHUNK_SIZE):
                size += len(chunk)
                if size > settings.max_upload_size:
                    raise APIError(413, "upload_too_large", "This image is larger than the allowed upload size.")
                digest.update(chunk)
                await destination.write(chunk)
        if size == 0:
            raise APIError(400, "empty_upload", "The selected image is empty.")
        fingerprint = digest.hexdigest()
        if expected_sha256 and fingerprint.lower() != expected_sha256.strip().lower():
            raise APIError(400, "hash_mismatch", "The image hash does not match the value provided.")

        filename = _safe_filename(upload.filename or "evidence-image.bin")
        final_path = case_dir / f"{uuid.uuid4().hex}_{filename}"
        os.replace(temporary_path, final_path)
        try:
            final_path.chmod(0o444)
            locked = True
        except OSError:
            locked = False

        image = EvidenceImage(
            case_id=case.id,
            original_filename=filename,
            stored_path=str(final_path),
            size_bytes=size,
            sha256=fingerprint,
            read_only_locked=locked,
        )
        session.add(image)
        case.status = "uploaded"
        session.flush()
        append_entry(
            session,
            case.id,
            "EVIDENCE_RECEIVED",
            {"filename": filename, "size_bytes": size, "sha256": fingerprint},
        )
        record_audit(session, "evidence_uploaded", case.id, {"filename": filename, "size_bytes": size})
        session.commit()
        committed = True
        return image
    finally:
        if not committed:
            session.rollback()
            temporary_path.unlink(missing_ok=True)
            if final_path and final_path.exists():
                final_path.chmod(0o600)
                final_path.unlink()
        await upload.close()
