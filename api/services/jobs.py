"""Background run scheduling, event persistence, and restart recovery."""

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from api.config import Settings
from api.db.models import Case, EvidenceImage, RecoveredFile, Run, RunEvent, Score, utc_now
from api.errors import APIError
from api.services.audit import record_audit
from api.services.cases import case_image, get_case
from api.services.custody_service import append_entry
from api.services.engine_adapter import run_fake, run_real
from scorer.score import score_case


class OutputIntegrityError(RuntimeError):
    """Raised when an engine output disagrees with its recorded digest or size."""


def add_event(
    session: Session,
    run_id: str,
    event_type: str,
    stage: str,
    message: str,
    payload: dict[str, object],
) -> RunEvent:
    """Persist the next monotonically sequenced run event."""
    latest = session.scalar(select(RunEvent.seq).where(RunEvent.run_id == run_id).order_by(RunEvent.seq.desc()).limit(1))
    event = RunEvent(
        run_id=run_id,
        seq=(latest or 0) + 1,
        type=event_type,
        stage=stage,
        message=message,
        payload=payload,
    )
    session.add(event)
    return event


class JobManager:
    """Submit background jobs and expose cooperative cancellation."""

    def __init__(self, factory: sessionmaker[Session], settings: Settings):
        self.factory = factory
        self.settings = settings
        self.executor = ThreadPoolExecutor(max_workers=settings.max_concurrent_jobs, thread_name_prefix="trace-run")
        self.cancel_flags: dict[str, threading.Event] = {}
        self.lock = threading.Lock()
        self.event_lock = threading.Lock()

    def start(self, case_id: str) -> Run:
        """Create a queued run and submit it to the worker pool."""
        if self.settings.engine_mode == "fake" and not self.settings.demo_mode:
            raise APIError(
                409,
                "demo_mode_required",
                "Synthetic recovery is available only when DEMO_MODE=true.",
            )
        with self.factory() as session:
            case = get_case(session, case_id)
            image = case_image(session, case_id)
            if image is None:
                raise APIError(409, "evidence_required", "Upload an evidence image before starting recovery.")
            image_path = Path(image.stored_path)
            run = Run(case_id=case.id, status="queued", engine_mode=self.settings.engine_mode, image_sha256_before=image.sha256)
            session.add(run)
            session.flush()
            case.status = "running"
            add_event(session, run.id, "stage", "queued", "Recovery is queued.", {"found_so_far": 0})
            record_audit(session, "run_started", case.id, {"run_id": run.id, "engine_mode": run.engine_mode})
            session.commit()
            session.refresh(run)
            run_id = run.id
        cancel_flag = threading.Event()
        with self.lock:
            self.cancel_flags[run_id] = cancel_flag
        self.executor.submit(self._execute, run_id, case_id, image, image_path, cancel_flag)
        return run

    def cancel(self, run_id: str, case_id: str) -> None:
        """Request cooperative cancellation for an active run."""
        with self.lock:
            flag = self.cancel_flags.get(run_id)
        with self.event_lock:
            with self.factory() as session:
                run = session.scalar(select(Run).where(Run.id == run_id, Run.case_id == case_id))
                if run is None:
                    raise APIError(404, "run_not_found", "We could not find that recovery run.")
                if run.status not in {"queued", "running"}:
                    raise APIError(409, "run_not_active", "That recovery run is no longer active.")
                if flag is not None:
                    flag.set()
                run.status = "cancelled"
                run.finished_at = utc_now()
                add_event(session, run.id, "error", "cancelled", "Recovery was cancelled.", {"found_so_far": 0})
                record_audit(session, "run_cancelled", case_id, {"run_id": run_id})
                session.commit()

    def _execute(self, run_id: str, case_id: str, image: EvidenceImage, image_path: Path, cancelled: threading.Event) -> None:
        started = time.monotonic()
        output_dir = (self.settings.data_dir / "runs" / run_id).resolve()
        with self.event_lock:
            with self.factory() as session:
                run = session.get(Run, run_id)
                if run is None or run.status in {"cancelled", "failed", "completed", "interrupted"}:
                    return
                run.status = "running"
                run.started_at = utc_now()
                session.commit()

        def emit(event_type: str, stage: str, message: str, payload: dict[str, object]) -> None:
            with self.event_lock:
                if cancelled.is_set():
                    return
                with self.factory() as event_session:
                    add_event(event_session, run_id, event_type, stage, message, payload)
                    event_session.commit()

        try:
            adapter = run_fake if self.settings.engine_mode == "fake" else run_real
            if self.settings.engine_mode == "fake":
                output = adapter(image_path, output_dir, emit, cancelled, self.settings.job_timeout, self.settings.fake_step_seconds)
            else:
                output = adapter(image_path, output_dir, emit, cancelled, self.settings.job_timeout)
            after_hash = _sha256_file(image_path)
            if after_hash != image.sha256:
                raise RuntimeError("The stored evidence image changed after upload; this run cannot be trusted.")
            validated_files = _validate_output_files(output.files, output_dir, self.settings.data_dir)
            benchmark_payload: dict[str, object] | None = None
            if self.settings.demo_mode and self.settings.engine_mode == "real":
                with self.factory() as score_session:
                    case_for_score = score_session.get(Case, case_id)
                    ground_truth = case_for_score.ground_truth if case_for_score else None
                if ground_truth is not None:
                    results_data = json.loads(output.results_path.read_text(encoding="utf-8"))
                    benchmark = score_case(ground_truth, results_data, output_dir, image_path)
                    benchmark_payload = benchmark.model_dump(mode="json")
                    if not benchmark.image_integrity_ok:
                        raise RuntimeError("The scorer rejected the evidence image integrity check.")
            with self.event_lock:
                with self.factory() as session:
                    run = session.get(Run, run_id)
                    case = session.get(Case, case_id)
                    if run is None or case is None:
                        return
                    if cancelled.is_set():
                        run.status = "cancelled"
                        run.finished_at = utc_now()
                        session.commit()
                        return
                    for item in validated_files:
                        session.add(RecoveredFile(
                            run_id=run.id,
                            case_id=case.id,
                            public_id=str(item["id"]),
                            name=str(item["name"]) if item.get("name") is not None else None,
                            type=str(item["type"]),
                            source=str(item["source"]),
                            stage=str(item["stage"]),
                            classification=str(item["classification"]),
                            confidence=float(item["confidence"]),
                            reason=str(item["reason"]),
                            offsets=item["offsets"],
                            size_bytes=int(item["size_bytes"]),
                            sha256=str(item["sha256"]),
                            output_path=str(item["output_path"]),
                            timestamps=item["timestamps"],
                            metadata_json=item["metadata"],
                            warnings=item["warnings"],
                        ))
                    run.status = "completed"
                    run.finished_at = utc_now()
                    run.image_sha256_after = after_hash
                    run.integrity_ok = True
                    run.engine_version = "fake-demo" if run.engine_mode == "fake" else "external"
                    case.status = "completed"
                    if run.engine_mode == "real":
                        append_entry(session, case.id, "RECOVERY_COMPLETED", {"run_id": run.id, "files_found": len(validated_files)}, run.id)
                    record_audit(session, "run_completed", case.id, {"run_id": run.id, "duration_seconds": round(time.monotonic() - started, 3)})
                    if benchmark_payload is not None:
                        session.add(Score(
                            run_id=run.id,
                            payload=benchmark_payload,
                            ground_truth_source="synthetic-benchmark",
                        ))
                    completion = (
                        "Synthetic demonstration complete; no evidence recovery was performed."
                        if run.engine_mode == "fake"
                        else "Recovery complete. The evidence set is ready for review."
                    )
                    add_event(session, run.id, "done", "done", completion, {"found_so_far": len(validated_files), "percent": 100})
                    session.commit()
        except InterruptedError as error:
            self._finish_error(run_id, case_id, "cancelled", str(error))
        except OutputIntegrityError as error:
            self._finish_error(run_id, case_id, "failed", str(error), integrity_ok=False)
        except APIError as error:
            self._finish_error(run_id, case_id, "failed", error.message)
        except (OSError, ValueError, RuntimeError, TimeoutError, json.JSONDecodeError) as error:
            self._finish_error(run_id, case_id, "failed", str(error))
        except SQLAlchemyError as error:
            self._finish_error(run_id, case_id, "failed", f"The run could not be saved: {error}")
        finally:
            with self.lock:
                self.cancel_flags.pop(run_id, None)

    def _finish_error(
        self,
        run_id: str,
        case_id: str,
        status: str,
        message: str,
        *,
        integrity_ok: bool | None = None,
    ) -> None:
        with self.event_lock:
            with self.factory() as session:
                run = session.get(Run, run_id)
                if run is None or run.status in {"completed", "failed", "cancelled", "interrupted"}:
                    return
                run.status = status
                run.error_message = message
                run.finished_at = utc_now()
                if integrity_ok is not None:
                    run.integrity_ok = integrity_ok
                elif "evidence image changed" in message:
                    run.integrity_ok = False
                case = session.get(Case, case_id)
                if case is not None:
                    case.status = status
                add_event(session, run.id, "error", status, message, {"found_so_far": 0})
                record_audit(session, f"run_{status}", case_id, {"run_id": run_id, "message": message})
                session.commit()

    def shutdown(self) -> None:
        """Stop the worker pool during application shutdown."""
        self.executor.shutdown(wait=False, cancel_futures=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        while chunk := file_obj.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_output_files(
    files: list[dict[str, object]],
    output_dir: Path,
    data_dir: Path,
) -> list[dict[str, object]]:
    """Validate engine IDs, paths, sizes, and hashes before persisting results."""
    run_root = output_dir.resolve()
    data_root = data_dir.resolve()
    if not run_root.is_relative_to(data_root):
        raise ValueError("The recovery output directory is outside DATA_DIR.")
    validated: list[dict[str, object]] = []
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("The recovery engine returned an invalid file record.")
        public_id = item.get("id")
        requested_path = item.get("output_path")
        expected_hash = item.get("sha256")
        size_bytes = item.get("size_bytes")
        if not isinstance(public_id, str) or not public_id:
            raise ValueError("The recovery engine returned a file without an ID.")
        required_fields = {
            "type",
            "source",
            "stage",
            "classification",
            "confidence",
            "reason",
            "offsets",
            "timestamps",
            "metadata",
            "warnings",
        }
        missing_fields = required_fields.difference(item)
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(f"Recovered file {public_id} is missing required fields: {missing}.")
        if not isinstance(requested_path, str) or not requested_path:
            raise ValueError(f"Recovered file {public_id} has no output path.")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            raise ValueError(f"Recovered file {public_id} has an invalid SHA-256.")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
            raise ValueError(f"Recovered file {public_id} has an invalid size.")
        path = Path(requested_path)
        resolved = (path if path.is_absolute() else run_root / path).resolve()
        if not resolved.is_relative_to(run_root) or not resolved.is_file():
            raise ValueError(f"Recovered file {public_id} is outside this run or is missing.")
        if resolved.stat().st_size != size_bytes:
            raise OutputIntegrityError(f"Recovered file {public_id} has a size mismatch.")
        if _sha256_file(resolved) != expected_hash:
            raise OutputIntegrityError(f"Recovered file {public_id} failed its SHA-256 check.")
        validated.append({**item, "output_path": str(resolved)})
    return validated


def recover_interrupted_runs(factory: sessionmaker[Session]) -> None:
    """Mark runs left active by a prior server process as interrupted."""
    with factory() as session:
        runs = list(session.scalars(select(Run).where(Run.status.in_(("running", "queued")))))
        for run in runs:
            run.status = "interrupted"
            run.finished_at = utc_now()
            case = session.get(Case, run.case_id)
            if case is not None:
                case.status = "interrupted"
            record_audit(session, "run_interrupted", run.case_id, {"run_id": run.id})
        session.commit()
