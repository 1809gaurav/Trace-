"""Queries for recovered output, scoring, and safe file lookup."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import Case, RecoveredFile, Run, Score
from api.errors import APIError


def choose_run(session: Session, case_id: str, run_id: str | None = None) -> Run:
    """Select an explicitly requested or newest completed run."""
    statement = select(Run).where(Run.case_id == case_id)
    if run_id:
        statement = statement.where(Run.id == run_id)
    else:
        statement = statement.where(Run.status == "completed").order_by(Run.finished_at.desc())
    run = session.scalar(statement.limit(1))
    if run is None:
        raise APIError(404, "results_not_ready", "There are no completed recovery results for this case yet.")
    return run


def file_payload(file: RecoveredFile) -> dict[str, object]:
    """Serialize a recovered file in the documented snake_case API shape."""
    return {
        "id": file.public_id,
        "name": file.name,
        "type": file.type,
        "source": file.source,
        "stage": file.stage,
        "classification": file.classification,
        "confidence": file.confidence,
        "reason": file.reason,
        "offsets": file.offsets,
        "size_bytes": file.size_bytes,
        "sha256": file.sha256,
        "timestamps": file.timestamps,
        "metadata": file.metadata_json,
        "warnings": file.warnings,
    }


def find_file(session: Session, case_id: str, public_id: str, run_id: str | None = None) -> RecoveredFile:
    """Find a file belonging to this case, never by client-provided path."""
    run = choose_run(session, case_id, run_id)
    file = session.scalar(
        select(RecoveredFile).where(
            RecoveredFile.case_id == case_id,
            RecoveredFile.run_id == run.id,
            RecoveredFile.public_id == public_id,
        )
    )
    if file is None:
        raise APIError(404, "file_not_found", "We could not find that recovered file.")
    return file


def case_for_results(session: Session, case_id: str) -> Case:
    """Confirm a case exists before looking up its output."""
    case = session.get(Case, case_id)
    if case is None or case.deleted_at is not None:
        raise APIError(404, "case_not_found", "We could not find that case.")
    return case


def score_payload(session: Session, run: Run) -> dict[str, object]:
    """Return a stored synthetic benchmark score, if available."""
    case = session.get(Case, run.case_id)
    if case is None or case.ground_truth is None:
        raise APIError(404, "no_ground_truth", "Scoring is not available for real evidence without benchmark data.")
    score = session.scalar(select(Score).where(Score.run_id == run.id))
    if score is None:
        raise APIError(503, "scorer_unavailable", "Benchmark data is attached, but the scoring module is not available.")
    return {**score.payload, "ground_truth_source": score.ground_truth_source, "engine_mode": run.engine_mode}
