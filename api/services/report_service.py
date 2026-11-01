"""Build Trace HTML and PDF reports and persist report provenance."""

import hashlib
import io
import base64
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import Settings
from api.db.models import Case, CustodyEntry, EvidenceImage, RecoveredFile, Report, Run, Score
from api.errors import APIError
from api.services.audit import record_audit
from api.services.custody_service import append_entry, verify_entries
from api.services.results import choose_run

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "report" / "templates"


def report_context(session: Session, case: Case, settings: Settings, run_id: str | None = None) -> dict[str, object]:
    """Assemble data for HTML and PDF report rendering."""
    run = choose_run(session, case.id, run_id)
    evidence = session.scalar(
        select(EvidenceImage).where(EvidenceImage.case_id == case.id).order_by(EvidenceImage.uploaded_at.desc()).limit(1)
    )
    files = list(session.scalars(
        select(RecoveredFile).where(RecoveredFile.case_id == case.id, RecoveredFile.run_id == run.id)
    ).all())
    custody = list(session.scalars(
        select(CustodyEntry).where(CustodyEntry.case_id == case.id).order_by(CustodyEntry.idx)
    ).all())
    verification = verify_entries(custody)
    score = session.scalar(select(Score).where(Score.run_id == run.id))
    return {
        "case": case,
        "run": run,
        "evidence": evidence,
        "files": files,
        "custody": custody,
        "verification": verification,
        "score": score.payload if score else None,
        "version": settings.app_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report_css": (TEMPLATE_DIR / "report.css").read_text(encoding="utf-8"),
        "logo_data": _logo_data_uri(),
    }


def render_html(context: dict[str, object]) -> str:
    """Render the report template to HTML."""
    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    return environment.get_template("report.html").render(**context)


def generate_report(session: Session, settings: Settings, case: Case, run_id: str | None = None) -> Report:
    """Generate a PDF, store its hash, and append its custody record."""
    context = report_context(session, case, settings, run_id)
    run = context["run"]
    html_content = render_html(context)
    pdf_content, engine = _render_pdf(context, html_content, settings.report_engine)
    report_dir = (settings.data_dir / "reports" / case.id).resolve()
    if not report_dir.is_relative_to(settings.data_dir.resolve()):
        raise APIError(400, "invalid_path", "The report destination is not valid.")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{run.id}.pdf"
    report_path.write_bytes(pdf_content)
    digest = hashlib.sha256(pdf_content).hexdigest()
    row = Report(
        case_id=case.id,
        run_id=run.id,
        path=str(report_path),
        sha256=digest,
        chain_ok_at_generation=bool(context["verification"]["ok"]),
        report_engine=engine,
    )
    session.add(row)
    session.flush()
    append_entry(
        session,
        case.id,
        "REPORT_GENERATED",
        {"report_sha256": digest, "chain_ok_at_generation": row.chain_ok_at_generation, "report_engine": engine},
        run.id,
    )
    record_audit(session, "report_generated", case.id, {"report_sha256": digest, "report_engine": engine})
    session.commit()
    session.refresh(row)
    return row


def _logo_data_uri() -> str | None:
    """Return a data URI for the frontend logo when the asset is available."""
    logo_path = Path(__file__).resolve().parents[2] / "src" / "assets" / "logo.svg"
    if not logo_path.is_file():
        return None
    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _render_pdf(context: dict[str, object], html_content: str, preference: str) -> tuple[bytes, str]:
    if preference in {"auto", "weasyprint"}:
        try:
            from weasyprint import HTML
        except ImportError:
            if preference == "weasyprint":
                raise RuntimeError("WeasyPrint is not installed; choose REPORT_ENGINE=auto or reportlab.")
        else:
            return HTML(string=html_content, base_url=str(TEMPLATE_DIR)).write_pdf(), "weasyprint"
    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    styles = getSampleStyleSheet()
    title = styles["Title"]
    title.textColor = colors.HexColor("#1F3D2B")
    heading = styles["Heading2"]
    heading.textColor = colors.HexColor("#1F3D2B")
    body = styles["BodyText"]
    story = []
    if context["run"].engine_mode == "fake":
        story.extend([
            Paragraph("SYNTHETIC DEMONSTRATION — no evidence recovery was performed.", heading),
            Spacer(1, 5 * mm),
        ])
    story.extend([Paragraph("Trace — Evidence recovery report", title), Spacer(1, 5 * mm)])
    case = context["case"]
    evidence = context["evidence"]
    synthetic = context["run"].engine_mode == "fake"
    story.extend([
        Paragraph("Case information", heading),
        Paragraph(f"Case ID: {case.id}<br/>Case name: {case.title}", body),
        Paragraph("Evidence", heading),
        Paragraph(
            f"{evidence.original_filename} · {evidence.size_bytes} bytes · SHA-256 {evidence.sha256}"
            if evidence else "No evidence image is attached.",
            body,
        ),
        Paragraph("Recovery summary", heading),
    ])
    if synthetic:
        story.append(Paragraph("Synthetic demonstration outputs; no evidence recovery was performed.", body))
        rows = [["Name", "Type", "Class", "Size", "SHA-256", "Reason"]]
    else:
        story.append(Paragraph(f"{len(context['files'])} results. Confidence is a comparative estimate, not a guarantee.", body))
        rows = [["Name", "Type", "Class", "Confidence", "Size", "SHA-256", "Reason"]]
    for file in context["files"]:
        row = [
            Paragraph(str(file.name or file.public_id), body),
            file.type,
            file.classification,
            str(file.size_bytes),
            Paragraph(file.sha256, body),
            Paragraph(file.reason, body),
        ]
        if not synthetic:
            row.insert(3, f"{file.confidence:.0%}")
        rows.append(row)
    widths = [30 * mm, 15 * mm, 20 * mm, 15 * mm, 35 * mm, 45 * mm]
    if not synthetic:
        widths = [25 * mm, 12 * mm, 18 * mm, 18 * mm, 15 * mm, 35 * mm, 45 * mm]
    table = Table(rows, repeatRows=1, colWidths=widths)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FFFFFF")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1F3D2B")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#6F806E")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
    ]))
    story.extend([Spacer(1, 4 * mm), table, Paragraph("Custody and verification", heading)])
    verify_result = context["verification"]
    story.append(Paragraph(f"Chain verification: {verify_result['ok']} — {verify_result['reason']}", body))
    for entry in context["custody"]:
        story.append(Paragraph(f"{entry.idx} · {entry.time} · {entry.step} · {entry.hash[:12]}", body))
    if context["score"]:
        story.extend([Paragraph("Synthetic benchmark only", heading), Paragraph(str(context["score"]), body)])
    story.extend([
        Paragraph("Limitations and assumptions", heading),
        Paragraph("Recovery can be incomplete. Reconstructed files may contain missing or altered content. This report is a court-ready format, not a legal certification.", body),
        Spacer(1, 3 * mm),
        Paragraph(f"Trace {context['version']} · {context['generated_at']} · Engine mode: {context['run'].engine_mode}", body),
    ])
    document.build(story)
    return buffer.getvalue(), "reportlab"
