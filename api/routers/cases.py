"""Case creation, listing, soft deletion, and streamed evidence upload."""

from fastapi import APIRouter, File, Header, Request, UploadFile
from pydantic import ValidationError
from sqlalchemy import select

from api.db.models import Case, EvidenceImage, Run
from api.errors import APIError
from api.schemas_api import CaseCreateRequest, GroundTruthRequest
from api.services.cases import case_image, create_case, get_case, soft_delete_case, upload_evidence

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _image_json(image: EvidenceImage) -> dict[str, object]:
    return {
        "id": image.id,
        "path": image.stored_path,
        "original_filename": image.original_filename,
        "size_bytes": image.size_bytes,
        "sha256": image.sha256,
        "read_only_locked": image.read_only_locked,
        "uploaded_at": image.uploaded_at.isoformat(),
    }


@router.post("", status_code=201)
def post_case(request: Request, body: CaseCreateRequest) -> dict[str, object]:
    """Create a new evidence case."""
    with request.app.state.session_factory() as session:
        case = create_case(session, body.title)
        return {"id": case.id, "title": case.title, "status": case.status, "created_at": case.created_at.isoformat()}


@router.get("")
def list_cases(request: Request, limit: int = 20) -> dict[str, object]:
    """List the most recently updated live cases."""
    if limit < 1 or limit > 100:
        raise APIError(422, "invalid_limit", "Choose a page size between 1 and 100.")
    with request.app.state.session_factory() as session:
        cases = session.scalars(
            select(Case).where(Case.deleted_at.is_(None)).order_by(Case.updated_at.desc()).limit(limit)
        ).all()
        return {"cases": [_case_json(item) for item in cases]}


@router.get("/{case_id}")
def get_case_route(case_id: str, request: Request) -> dict[str, object]:
    """Return one case and its latest uploaded image."""
    with request.app.state.session_factory() as session:
        case = get_case(session, case_id)
        image = case_image(session, case.id)
        return {**_case_json(case), "image": _image_json(image) if image else None}


@router.delete("/{case_id}", status_code=204)
def delete_case(case_id: str, request: Request) -> None:
    """Soft-delete a case without deleting stored evidence."""
    with request.app.state.session_factory() as session:
        soft_delete_case(session, case_id)
    return None


@router.post("/{case_id}/upload", status_code=201)
async def upload_route(
    case_id: str,
    request: Request,
    file: UploadFile = File(...),
    expected_sha256: str | None = Header(default=None, alias="X-Expected-SHA256"),
) -> dict[str, object]:
    """Stream an evidence image into protected storage."""
    with request.app.state.session_factory() as session:
        image = await upload_evidence(session, request.app.state.settings, case_id, file, expected_sha256)
        return {
            "image": {
                "path": image.stored_path,
                "sha256": image.sha256,
                "size_bytes": image.size_bytes,
                "original_filename": image.original_filename,
            },
            "locked": image.read_only_locked,
        }


@router.post("/{case_id}/ground-truth", status_code=201)
def attach_ground_truth(case_id: str, request: Request, body: GroundTruthRequest) -> dict[str, object]:
    """Attach benchmark-only metadata to a demo case."""
    settings = request.app.state.settings
    if not settings.demo_mode:
        raise APIError(403, "demo_mode_disabled", "Benchmark data is disabled for this server.")
    with request.app.state.session_factory() as session:
        case = get_case(session, case_id)
        case.ground_truth = body.ground_truth
        session.commit()
    return {"case_id": case_id, "ground_truth_attached": True}


def _case_json(case: Case) -> dict[str, object]:
    return {
        "id": case.id,
        "title": case.title,
        "status": case.status,
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
    }
