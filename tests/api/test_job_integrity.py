import hashlib

import pytest

from api.services.jobs import OutputIntegrityError, _validate_output_files


def _record(path, content: bytes) -> dict[str, object]:
    return {
        "id": "f-001",
        "name": "sample.jpg",
        "type": "jpeg",
        "source": "carver",
        "stage": "carving",
        "classification": "carved",
        "confidence": 0.6,
        "reason": "Validated fixture output.",
        "offsets": [{"start": 0, "end": len(content)}],
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "output_path": str(path),
        "timestamps": {},
        "metadata": {},
        "warnings": [],
    }


def test_engine_output_path_and_digest_are_validated(tmp_path):
    data_dir = tmp_path / "data"
    run_dir = data_dir / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    content = b"fixture output"
    path = run_dir / "sample.jpg"
    path.write_bytes(content)

    validated = _validate_output_files([_record(path, content)], run_dir, data_dir)

    assert validated[0]["output_path"] == str(path.resolve())

    path.write_bytes(b"tampered data!")
    with pytest.raises(OutputIntegrityError, match="SHA-256 check"):
        _validate_output_files([_record(path, content)], run_dir, data_dir)


def test_engine_output_cannot_escape_data_directory(tmp_path):
    data_dir = tmp_path / "data"
    run_dir = data_dir / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"fixture output")

    with pytest.raises(ValueError, match="outside this run"):
        _validate_output_files([_record(outside, b"fixture output")], run_dir, data_dir)


def test_engine_output_requires_engine_file_id(tmp_path):
    data_dir = tmp_path / "data"
    run_dir = data_dir / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    path = run_dir / "sample.jpg"
    path.write_bytes(b"fixture output")
    record = _record(path, b"fixture output")
    del record["id"]

    with pytest.raises(ValueError, match="without an ID"):
        _validate_output_files([record], run_dir, data_dir)


def test_engine_output_requires_persisted_metadata_fields(tmp_path):
    data_dir = tmp_path / "data"
    run_dir = data_dir / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    path = run_dir / "sample.jpg"
    path.write_bytes(b"fixture output")
    record = _record(path, b"fixture output")
    del record["timestamps"]

    with pytest.raises(ValueError, match="missing required fields: timestamps"):
        _validate_output_files([record], run_dir, data_dir)
