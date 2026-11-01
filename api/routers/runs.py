"""Recovery run lifecycle, event replay, and WebSocket streaming."""

import asyncio

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from api.db.models import Run, RunEvent
from api.errors import APIError
from api.services.cases import get_case
from api.security import decode_access_token
from api.services.jobs import add_event

router = APIRouter(prefix="/api/cases/{case_id}", tags=["runs"])
ws_router = APIRouter(prefix="/api/ws/cases", tags=["runs"])


@router.post("/runs", status_code=202)
def start_run(case_id: str, request: Request) -> dict[str, object]:
    """Queue a recovery run for the case's latest uploaded evidence."""
    run = request.app.state.jobs.start(case_id)
    return {"run": _run_json(run)}


@router.get("/runs")
def list_runs(case_id: str, request: Request) -> dict[str, object]:
    """Return runs newest first."""
    with request.app.state.session_factory() as session:
        get_case(session, case_id)
        runs = session.scalars(select(Run).where(Run.case_id == case_id).order_by(Run.started_at.desc())).all()
        return {"runs": [_run_json(run) for run in runs]}


@router.post("/runs/{run_id}/cancel", status_code=202)
def cancel_run(case_id: str, run_id: str, request: Request) -> dict[str, str]:
    """Request cancellation of an active run."""
    request.app.state.jobs.cancel(run_id, case_id)
    return {"status": "cancelled"}


@router.get("/runs/{run_id}/events")
def replay_events(
    case_id: str,
    run_id: str,
    request: Request,
    after_seq: int = Query(default=0, ge=0),
) -> dict[str, object]:
    """Replay persisted events after the provided sequence number."""
    with request.app.state.session_factory() as session:
        _require_run(session, case_id, run_id)
        events = session.scalars(
            select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.seq > after_seq).order_by(RunEvent.seq)
        ).all()
        return {"events": [_event_json(item) for item in events]}


@ws_router.websocket("/{case_id}")
async def case_events(websocket: WebSocket, case_id: str, after_seq: int = 0) -> None:
    """Stream persisted events and reconnect-safe replay for a case's latest run."""
    settings = websocket.app.state.settings
    origin = websocket.headers.get("origin")
    scheme = "https" if websocket.url.scheme == "wss" else "http"
    same_origin = origin == f"{scheme}://{websocket.headers.get('host', '')}"
    if origin and origin not in settings.cors_origins and not same_origin:
        await websocket.close(code=1008, reason="Origin is not allowed")
        return
    if settings.auth_mode == "apikey":
        import hmac

        supplied_key = websocket.headers.get("x-api-key", websocket.query_params.get("api_key", ""))
        if not hmac.compare_digest(supplied_key, settings.api_key or ""):
            await websocket.close(code=1008, reason="A valid API key is required")
            return
    elif settings.auth_mode == "jwt":
        authorization = websocket.headers.get("authorization", "")
        token = authorization[7:] if authorization.startswith("Bearer ") else websocket.query_params.get("token", "")
        try:
            decode_access_token(token, settings)
        except APIError:
            await websocket.close(code=1008, reason="Sign in to continue")
            return
    await websocket.accept(headers=[(b"x-trace-engine", settings.engine_mode.encode("ascii"))])
    last_sent = max(0, after_seq)
    idle_seconds = 0
    try:
        while idle_seconds < 20:
            with websocket.app.state.session_factory() as session:
                run = session.scalar(
                    select(Run).where(Run.case_id == case_id).order_by(Run.started_at.desc()).limit(1)
                )
                if run is None:
                    await websocket.send_json({"type": "error", "message": "No recovery run is available.", "seq": last_sent})
                    return
                events = session.scalars(
                    select(RunEvent)
                    .where(RunEvent.run_id == run.id, RunEvent.seq > last_sent)
                    .order_by(RunEvent.seq)
                ).all()
                run_status = run.status
                for event in events:
                    await websocket.send_json(_event_json(event))
                    last_sent = event.seq
            if run_status in {"completed", "failed", "cancelled", "interrupted"} and not events:
                return
            if events:
                idle_seconds = 0
            else:
                idle_seconds += 1
                if idle_seconds % 15 == 0:
                    await websocket.send_json({"type": "heartbeat", "seq": last_sent})
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return


def _require_run(session, case_id: str, run_id: str) -> Run:
    run = session.scalar(select(Run).where(Run.id == run_id, Run.case_id == case_id))
    if run is None:
        raise APIError(404, "run_not_found", "We could not find that recovery run.")
    return run


def _run_json(run: Run) -> dict[str, object]:
    return {
        "id": run.id,
        "case_id": run.case_id,
        "status": run.status,
        "engine_mode": run.engine_mode,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "integrity_ok": run.integrity_ok,
        "error_message": run.error_message,
    }


def _event_json(event: RunEvent) -> dict[str, object]:
    return {
        "seq": event.seq,
        "type": event.type,
        "stage": event.stage,
        "message": event.message,
        "found_so_far": event.payload.get("found_so_far", 0),
        "payload": event.payload,
    }
