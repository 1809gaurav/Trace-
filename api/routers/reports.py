"""HTML preview and downloadable PDF report routes."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select

from api.db.models import Report
from api.errors import APIError
from api.services.cases import get_case
from api.services.audit import record_audit
from api.services.report_service import generate_report, render_html, report_context

router = APIRouter(prefix="/api/cases/{case_id}/report", tags=["reports"])


@router.post("", status_code=201)
def post_report(case_id: str, request: Request, run_id: str | None = None) -> dict[str, object]:
    """Generate and persist a report for the latest or selected run."""
    with request.app.state.session_factory() as session:
        case = get_case(session, case_id)
        report = generate_report(session, request.app.state.settings, case, run_id)
        return {
            "id": report.id,
            "case_id": report.case_id,
            "run_id": report.run_id,
            "sha256": report.sha256,
            "generated_at": report.generated_at.isoformat(),
            "chain_ok_at_generation": report.chain_ok_at_generation,
            "report_engine": report.report_engine,
        }


@router.get("")
def get_report(case_id: str, request: Request) -> FileResponse:
    """Download the latest case report as a PDF attachment."""
    with request.app.state.session_factory() as session:
        get_case(session, case_id)
        report = session.scalar(
            select(Report).where(Report.case_id == case_id).order_by(Report.generated_at.desc()).limit(1)
        )
        if report is None:
            case = get_case(session, case_id)
            report = generate_report(session, request.app.state.settings, case)
        record_audit(session, "report_downloaded", case_id, {"report_sha256": report.sha256})
        session.commit()
        path = _safe_report_path(request, report.path)
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.get("/preview", response_class=HTMLResponse)
def report_preview(case_id: str, request: Request) -> HTMLResponse:
    """Return a live HTML report preview."""
    with request.app.state.session_factory() as session:
        case = get_case(session, case_id)
        html = render_html(report_context(session, case, request.app.state.settings))
    return HTMLResponse(html)


def _safe_report_path(request: Request, value: str) -> Path:
    path = Path(value).resolve()
    if not path.is_relative_to(request.app.state.settings.data_dir.resolve()) or not path.is_file():
        raise APIError(404, "report_not_found", "The report file is not available.")
    return path
