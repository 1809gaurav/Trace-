"""Recovered result filtering and benchmark score endpoints."""

from collections import Counter

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from api.db.models import RecoveredFile
from api.errors import APIError
from api.services.results import case_for_results, choose_run, file_payload, score_payload

router = APIRouter(prefix="/api/cases/{case_id}", tags=["results"])
SORTS = {"confidence_desc", "confidence_asc", "offset", "name"}


@router.get("/results")
def results(
    case_id: str,
    request: Request,
    classification: str | None = None,
    type: str | None = None,
    q: str | None = None,
    sort: str = "confidence_desc",
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    run_id: str | None = None,
) -> dict[str, object]:
    """Return filtered files in a results document with summary counts."""
    if sort not in SORTS:
        raise APIError(422, "invalid_sort", "Choose a supported results sort order.")
    with request.app.state.session_factory() as session:
        case_for_results(session, case_id)
        run = choose_run(session, case_id, run_id)
        statement = select(RecoveredFile).where(RecoveredFile.case_id == case_id, RecoveredFile.run_id == run.id)
        if classification:
            statement = statement.where(RecoveredFile.classification == classification)
        if type:
            statement = statement.where(RecoveredFile.type == type)
        files = list(session.scalars(statement).all())
        if q:
            needle = q.casefold()
            files = [file for file in files if needle in (file.name or "").casefold()]
        if sort == "confidence_desc":
            files.sort(key=lambda file: file.confidence, reverse=True)
        elif sort == "confidence_asc":
            files.sort(key=lambda file: file.confidence)
        elif sort == "name":
            files.sort(key=lambda file: (file.name or "").casefold())
        else:
            files.sort(key=lambda file: file.offsets[0].get("start", 0) if file.offsets else 0)
        summary = Counter(file.classification for file in files)
        return {
            "case_id": case_id,
            "run_id": run.id,
            "engine_mode": run.engine_mode,
            "files": [file_payload(file) for file in files[offset:offset + limit]],
            "summary": {"total": len(files), "by_classification": dict(summary)},
            "limit": limit,
            "offset": offset,
        }


@router.get("/score")
def score(case_id: str, request: Request, run_id: str | None = None) -> dict[str, object]:
    """Return benchmark-only quality metrics for an eligible run."""
    with request.app.state.session_factory() as session:
        case_for_results(session, case_id)
        run = choose_run(session, case_id, run_id)
        return score_payload(session, run)
