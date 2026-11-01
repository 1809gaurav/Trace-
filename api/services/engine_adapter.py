"""Adapters for the optional external engine and deterministic fake mode."""

import json
import hashlib
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from api.services.importer import validate_engine_outputs, validate_real_dependencies

@dataclass(frozen=True)
class RunOutput:
    """Paths emitted by a completed engine invocation."""

    results_path: Path
    custody_path: Path
    files: list[dict[str, object]]


FAKE_FILES: list[dict[str, object]] = [
    {"public_id": "f-001", "name": "garage_cam_01.jpg", "type": "jpeg", "stage": "Camera JPEG recovered", "classification": "intact", "confidence": 0.97, "reason": "The original frame header and file structure match the stored image.", "offsets": [{"start": 3200, "end": 65920}], "size_bytes": 89218},
    {"public_id": "f-002", "name": "entry_door_nav.png", "type": "png", "stage": "PNG chain still complete", "classification": "intact", "confidence": 0.95, "reason": "The capture remained in place and the image blocks still line up.", "offsets": [{"start": 15432, "end": 48720}], "size_bytes": 110204},
    {"public_id": "f-003", "name": "warehouse_floor.pdf", "type": "pdf", "stage": "PDF structure found", "classification": "partial", "confidence": 0.72, "reason": "Most pages are present, but the last section was damaged.", "offsets": [{"start": 56172, "end": 67844}], "size_bytes": 74312},
    {"public_id": "f-004", "name": "lane_3_footage.mp4", "type": "mp4", "stage": "Header and index recovered", "classification": "carved", "confidence": 0.81, "reason": "The header is intact, but several frames were split and reassembled.", "offsets": [{"start": 417600, "end": 661440}], "size_bytes": 1004212},
    {"public_id": "f-005", "name": "shelf_interior.jpg", "type": "jpeg", "stage": "Fragments matched into one file", "classification": "reconstructed", "confidence": 0.86, "reason": "Fragments were stitched together without changing the core image.", "offsets": [{"start": 2000, "end": 21400}, {"start": 82200, "end": 97800}], "size_bytes": 51721},
]

FAKE_STAGES = [
    ("reading", "Looking at the drive and checking the write history."),
    ("scanning", "Finding deleted files in the unallocated space."),
    ("isolating", "Isolating likely evidence from raw data."),
    ("reconstructing", "Reassembling fragments where sectors are damaged."),
    ("verifying", "Checking and labelling recovered files."),
]


def run_fake(
    image_path: Path,
    output_dir: Path,
    on_event: Callable[[str, str, str, dict[str, object]], None],
    cancelled: threading.Event,
    timeout: int,
    step_seconds: float,
) -> RunOutput:
    """Replay a clearly synthetic run and write JSON artifacts."""
    del image_path
    output_dir.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    for index, (stage, message) in enumerate(FAKE_STAGES):
        if cancelled.wait(step_seconds):
            raise InterruptedError("Recovery was cancelled.")
        if time.monotonic() - start > timeout:
            raise TimeoutError("The recovery job exceeded its time limit.")
        found = min(len(FAKE_FILES), index + 1)
        on_event("stage", stage, message, {"found_so_far": found})
        if found > 0:
            on_event(
                "file_found",
                stage,
                f"Found {FAKE_FILES[found - 1]['name']}.",
                {"found_so_far": found, "public_id": FAKE_FILES[found - 1]["public_id"]},
            )
    files: list[dict[str, object]] = []
    artifact_dir = output_dir / "recovered"
    artifact_dir.mkdir(exist_ok=True)
    for item in FAKE_FILES:
        content = f"SYNTHETIC DEMO OUTPUT - not recovered evidence: {item['name']}".encode("ascii")
        artifact_path = artifact_dir / str(item["public_id"])
        artifact_path.write_bytes(content)
        files.append({
            **item,
            "source": "synthetic-demo",
            "output_path": str(artifact_path),
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "warnings": ["Synthetic sample output; not recovered from the uploaded evidence."],
        })
    results_path = output_dir / "results.json"
    custody_path = output_dir / "custody.json"
    results_path.write_text(json.dumps({"files": files}, indent=2), encoding="utf-8")
    custody_path.write_text(json.dumps({"entries": []}, indent=2), encoding="utf-8")
    return RunOutput(results_path, custody_path, files)


def run_real(
    image_path: Path,
    output_dir: Path,
    on_event: Callable[[str, str, str, dict[str, object]], None],
    cancelled: threading.Event,
    timeout: int,
) -> RunOutput:
    """Invoke Agent B's CLI without exposing ground-truth data."""
    validate_real_dependencies()
    results_path = output_dir / "results.json"
    custody_path = output_dir / "custody.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, "-m", "engine.pipeline",
        "--image", str(image_path), "--out", str(output_dir),
        "--results", str(results_path), "--custody", str(custody_path),
        "--progress", "jsonl",
    ]
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creation_flags,
        start_new_session=os.name != "nt",
        bufsize=1,
    )
    output_lines: queue.Queue[str | None] = queue.Queue()
    stderr_tail: deque[str] = deque(maxlen=256)

    def read_stdout() -> None:
        if process.stdout is None:
            output_lines.put(None)
            return
        for line in process.stdout:
            output_lines.put(line)
        output_lines.put(None)

    def read_stderr() -> None:
        if process.stderr is None:
            return
        while chunk := process.stderr.read(4096):
            stderr_tail.append(chunk)

    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    deadline = time.monotonic() + timeout
    stdout_done = False
    files: list[dict[str, object]] = []
    while not stdout_done or process.poll() is None:
        if cancelled.is_set():
            _terminate_process(process)
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            raise InterruptedError("Recovery was cancelled.")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _terminate_process(process)
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            raise TimeoutError("The recovery job exceeded its time limit.")
        try:
            line = output_lines.get(timeout=min(0.25, remaining))
        except queue.Empty:
            continue
        if line is None:
            stdout_done = True
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            on_event(
                str(event.get("type", "progress")),
                str(event.get("stage", "")),
                str(event.get("message", "")),
                event,
            )
    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)
    stderr = "".join(stderr_tail)
    if process.returncode:
        raise RuntimeError(f"The recovery engine stopped unexpectedly. {stderr[-2000:]}")
    if not results_path.is_file() or not custody_path.is_file():
        raise RuntimeError("The recovery engine did not produce both required result files.")
    content, _custody = validate_engine_outputs(results_path, custody_path)
    files = content.get("files", []) if isinstance(content, dict) else []
    return RunOutput(results_path, custody_path, files if isinstance(files, list) else [])


def _terminate_process(process: subprocess.Popen[str]) -> None:
    """Request termination of the engine process group, then ensure it exits."""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
