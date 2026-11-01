"""Case-scoped recovered file details, preview, download, and hex views."""

import html
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from api.errors import APIError
from api.services.cases import case_image
from api.services.results import case_for_results, file_payload, find_file

router = APIRouter(prefix="/api/cases/{case_id}/files/{public_id}", tags=["files"])


@router.get("")
def file_detail(case_id: str, public_id: str, request: Request, run_id: str | None = None) -> dict[str, object]:
    """Return technical metadata for one recovered file."""
    with request.app.state.session_factory() as session:
        case_for_results(session, case_id)
        return file_payload(find_file(session, case_id, public_id, run_id))


@router.get("/content")
def file_content(
    case_id: str,
    public_id: str,
    request: Request,
    range_header: str | None = None,
    run_id: str | None = None,
) -> Response:
    """Stream an authorized recovered output and honor a single byte range."""
    with request.app.state.session_factory() as session:
        file = find_file(session, case_id, public_id, run_id)
        path = _safe_output_path(request, file.output_path)
        name = file.name or f"{public_id}.bin"
        media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        total_size = path.stat().st_size
    range_value = request.headers.get("range") or range_header
    start, end = 0, total_size - 1
    status_code = 200
    headers = {"Accept-Ranges": "bytes", "Content-Disposition": f'attachment; filename="{_header_filename(name)}"'}
    if range_value:
        start, end = _parse_range(range_value, total_size)
        status_code = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
    headers["Content-Length"] = str(end - start + 1)

    def chunks():
        with path.open("rb") as stream:
            stream.seek(start)
            remaining = end - start + 1
            while remaining:
                data = stream.read(min(1024 * 1024, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    return StreamingResponse(chunks(), status_code=status_code, media_type=media_type, headers=headers)


@router.get("/preview")
def file_preview(case_id: str, public_id: str, request: Request, run_id: str | None = None) -> Response:
    """Return an image inline or an inert generated preview for other formats."""
    with request.app.state.session_factory() as session:
        file = find_file(session, case_id, public_id, run_id)
        path = _safe_output_path(request, file.output_path, required=False)
        if path and file.type in {"jpeg", "png"} and file.source != "synthetic-demo":
            return FileResponse(
                path,
                media_type="image/jpeg" if file.type == "jpeg" else "image/png",
                headers={"Content-Disposition": "inline"},
            )
        label = html.escape(file.name or "Recovered file")
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="100%" height="100%" fill="#F6F0E1"/><text x="50%" y="50%" text-anchor="middle" fill="#1F3D2B" font-size="24">{label}</text></svg>'
        return Response(svg, media_type="image/svg+xml")


@router.get("/hex")
def evidence_hex(
    case_id: str,
    public_id: str,
    request: Request,
    offset: int = Query(default=0, ge=0),
    length: int = Query(default=128, ge=1, le=512),
) -> dict[str, object]:
    """Return a bounded hexadecimal view of the original evidence bytes."""
    with request.app.state.session_factory() as session:
        case_for_results(session, case_id)
        find_file(session, case_id, public_id)
        image = case_image(session, case_id)
        if image is None:
            raise APIError(404, "evidence_not_found", "The source evidence image is no longer available.")
        image_path = _safe_data_path(request, image.stored_path)
        size = image_path.stat().st_size
        if offset > size or offset + length > size:
            raise APIError(416, "range_not_satisfiable", "The requested byte range is outside the evidence image.")
    with image_path.open("rb") as stream:
        stream.seek(offset)
        content = stream.read(length)
    return {
        "offset": offset,
        "length": len(content),
        "hex": " ".join(f"{byte:02x}" for byte in content),
        "ascii": "".join(chr(byte) if 32 <= byte < 127 else "." for byte in content),
    }


def _safe_output_path(request: Request, value: str | None, required: bool = True) -> Path | None:
    """Resolve a database-owned output path strictly below the data directory."""
    if not value:
        if required:
            raise APIError(404, "file_content_missing", "The recovered file content is not available.")
        return None
    path = Path(value).resolve()
    root = request.app.state.settings.data_dir.resolve()
    if not path.is_relative_to(root) or not path.is_file():
        if required:
            raise APIError(404, "file_content_missing", "The recovered file content is not available.")
        return None
    return path


def _safe_data_path(request: Request, value: str) -> Path:
    path = Path(value).resolve()
    if not path.is_relative_to(request.app.state.settings.data_dir.resolve()) or not path.is_file():
        raise APIError(404, "evidence_not_found", "The source evidence image is not available.")
    return path


def _parse_range(value: str, total_size: int) -> tuple[int, int]:
    if not value.startswith("bytes=") or "," in value:
        raise APIError(416, "range_not_satisfiable", "Only one valid byte range can be requested.")
    parts = value[6:].split("-", maxsplit=1)
    try:
        if not parts[0]:
            suffix_length = int(parts[1])
            if suffix_length <= 0:
                raise ValueError("The suffix length must be positive.")
            start = max(0, total_size - suffix_length)
            end = total_size - 1
        else:
            start = int(parts[0])
            end = int(parts[1]) if parts[1] else total_size - 1
    except (ValueError, IndexError) as error:
        raise APIError(416, "range_not_satisfiable", "The requested byte range is not valid.") from error
    if total_size <= 0 or start < 0 or end < start or start >= total_size:
        raise APIError(416, "range_not_satisfiable", "The requested byte range is outside the recovered file.")
    return start, min(end, total_size - 1)


def _header_filename(value: str) -> str:
    return "".join(char for char in value if char.isalnum() or char in "._- ")[:180] or "recovered-file.bin"
