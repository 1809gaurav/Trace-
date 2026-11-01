"""Custody log, verification, and non-destructive tamper demonstration."""

import copy
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from sqlalchemy import select

from api.db.models import CustodyEntry
from api.errors import APIError
from api.schemas_api import TamperDemoRequest
from api.services.audit import record_audit
from api.services.cases import get_case
from api.services.custody_service import custody_payload, verify_entries

router = APIRouter(prefix="/api/cases/{case_id}", tags=["custody"])


@router.get("/custody")
def custody(case_id: str, request: Request) -> dict[str, object]:
    """Return immutable custody entries in sequence order."""
    with request.app.state.session_factory() as session:
        get_case(session, case_id)
        entries = session.scalars(
            select(CustodyEntry).where(CustodyEntry.case_id == case_id).order_by(CustodyEntry.idx)
        ).all()
        return {"case_id": case_id, "entries": [custody_payload(item) for item in entries]}


@router.get("/verify")
def verify(case_id: str, request: Request) -> dict[str, object]:
    """Verify the chain and log the check without appending a custody entry."""
    with request.app.state.session_factory() as session:
        get_case(session, case_id)
        entries = list(session.scalars(
            select(CustodyEntry).where(CustodyEntry.case_id == case_id).order_by(CustodyEntry.idx)
        ).all())
        result = verify_entries(entries)
        record_audit(session, "chain_verified", case_id, result)
        session.commit()
        return {**result, "checked_at": datetime.now(timezone.utc).isoformat()}


@router.post("/tamper-demo")
def tamper_demo(case_id: str, request: Request, body: TamperDemoRequest) -> dict[str, object]:
    """Change only an in-memory copy and demonstrate a failed verification."""
    index = body.index
    with request.app.state.session_factory() as session:
        get_case(session, case_id)
        stored = list(session.scalars(
            select(CustodyEntry).where(CustodyEntry.case_id == case_id).order_by(CustodyEntry.idx)
        ).all())
        if index > len(stored):
            raise APIError(404, "entry_not_found", "We could not find that custody entry.")
        changed = [copy.copy(entry) for entry in stored]
        changed[index - 1].details = {**changed[index - 1].details, "demo_altered": True}
        result = verify_entries(changed)
        record_audit(session, "tamper_demo", case_id, {"index": index, "stored_data_changed": False})
        session.commit()
        return {
            "entries": [custody_payload(item) for item in changed],
            "verify": result,
            "stored_data_changed": False,
        }
