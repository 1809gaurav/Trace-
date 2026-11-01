import hashlib
import io
import time

from fastapi.testclient import TestClient
from pypdf import PdfReader

from api.config import Settings
from api.main import create_app


def make_client(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{(tmp_path / 'trace.db').as_posix()}",
        engine_mode="fake",
        demo_mode=True,
        fake_step_seconds=0.01,
    )
    return TestClient(create_app(settings))


def create_uploaded_case(client):
    created = client.post("/api/cases", json={"title": "Test case"})
    assert created.status_code == 201
    case_id = created.json()["id"]
    content = b"not-a-real-disk-image"
    uploaded = client.post(
        f"/api/cases/{case_id}/upload",
        files={"file": ("sample.img", content, "application/octet-stream")},
        headers={"X-Expected-SHA256": hashlib.sha256(content).hexdigest()},
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["locked"] is True
    return case_id, content


def wait_for_run(client, case_id, run_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/cases/{case_id}/runs")
        runs = response.json()["runs"]
        run = next(run for run in runs if run["id"] == run_id)
        if run["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            return run
        time.sleep(0.02)
    raise AssertionError("Fake recovery run did not finish in time")


def test_health_and_case_upload_contract(tmp_path):
    with make_client(tmp_path) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["db_ok"] is True

        case_id, content = create_uploaded_case(client)
        case = client.get(f"/api/cases/{case_id}")
        assert case.status_code == 200
        image = case.json()["image"]
        assert image["sha256"] == hashlib.sha256(content).hexdigest()
        assert image["size_bytes"] == len(content)


def test_fake_run_results_score_and_event_replay(tmp_path):
    with make_client(tmp_path) as client:
        case_id, _ = create_uploaded_case(client)
        response = client.post(f"/api/cases/{case_id}/runs")
        assert response.status_code == 202
        run_id = response.json()["run"]["id"]
        assert response.headers["x-trace-engine"] == "fake"

        run = wait_for_run(client, case_id, run_id)
        assert run["status"] == "completed"
        assert run["engine_mode"] == "fake"
        results = client.get(f"/api/cases/{case_id}/results")
        assert results.status_code == 200
        assert results.json()["files"]
        assert {"id", "name", "type", "stage", "classification", "confidence", "size_bytes", "sha256"} <= set(results.json()["files"][0])
        score = client.get(f"/api/cases/{case_id}/score")
        assert score.status_code == 200

        replay = client.get(f"/api/cases/{case_id}/runs/{run_id}/events?after_seq=1")
        assert replay.status_code == 200
        assert all(event["seq"] > 1 for event in replay.json()["events"])
        with client.websocket_connect(
            f"/api/ws/cases/{case_id}?after_seq=0",
            headers={"origin": "http://testserver"},
        ) as websocket:
            first_stream = []
            while True:
                event = websocket.receive_json()
                first_stream.append(event)
                if event["type"] == "done":
                    break
        assert first_stream[0]["seq"] == 1
        with client.websocket_connect(f"/api/ws/cases/{case_id}?after_seq=4") as websocket:
            resumed = []
            while True:
                event = websocket.receive_json()
                resumed.append(event)
                if event["type"] == "done":
                    break
        assert resumed[0]["seq"] > 4


def test_tamper_demo_does_not_change_persisted_custody(tmp_path):
    with make_client(tmp_path) as client:
        case_id, _ = create_uploaded_case(client)
        before = client.get(f"/api/cases/{case_id}/custody").json()["entries"]
        tamper = client.post(
            f"/api/cases/{case_id}/tamper-demo",
            json={"index": 1},
        )
        after = client.get(f"/api/cases/{case_id}/custody").json()["entries"]
        assert tamper.status_code == 200
        assert tamper.json()["verify"]["ok"] is False
        assert after == before


def test_upload_rejects_empty_and_expected_hash_mismatch(tmp_path):
    with make_client(tmp_path) as client:
        case_response = client.post("/api/cases", json={"title": "Upload checks"})
        case_id = case_response.json()["id"]
        empty = client.post(
            f"/api/cases/{case_id}/upload",
            files={"file": ("empty.img", b"", "application/octet-stream")},
        )
        mismatch = client.post(
            f"/api/cases/{case_id}/upload",
            files={"file": ("sample.img", b"sample", "application/octet-stream")},
            headers={"X-Expected-SHA256": "0" * 64},
        )
        assert empty.status_code == 400
        assert mismatch.status_code == 400
        assert empty.json()["error"]["code"] == "empty_upload"
        assert mismatch.json()["error"]["code"] == "hash_mismatch"


def test_report_pdf_is_hashed_and_added_to_custody(tmp_path):
    with make_client(tmp_path) as client:
        case_id, _ = create_uploaded_case(client)
        run_response = client.post(f"/api/cases/{case_id}/runs")
        run_id = run_response.json()["run"]["id"]
        assert wait_for_run(client, case_id, run_id)["status"] == "completed"

        report = client.post(f"/api/cases/{case_id}/report")
        assert report.status_code == 201
        assert len(report.json()["sha256"]) == 64
        assert report.json()["report_engine"] == "reportlab"
        pdf = client.get(f"/api/cases/{case_id}/report")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF-")
        parsed_pdf = PdfReader(io.BytesIO(pdf.content))
        assert len(parsed_pdf.pages) > 0
        pdf_text = "\n".join(page.extract_text() or "" for page in parsed_pdf.pages)
        assert "Test case" in pdf_text
        assert "SYNTHETIC" not in pdf_text
        chain = client.get(f"/api/cases/{case_id}/custody").json()["entries"]
        assert chain[-1]["step"] == "REPORT_GENERATED"
        assert client.get(f"/api/cases/{case_id}/verify").json()["ok"] is True


def test_soft_delete_keeps_the_evidence_file(tmp_path):
    with make_client(tmp_path) as client:
        case_id, _ = create_uploaded_case(client)
        image_path = client.get(f"/api/cases/{case_id}").json()["image"]["path"]
        deleted = client.delete(f"/api/cases/{case_id}")
        assert deleted.status_code == 204
        assert client.get(f"/api/cases/{case_id}").status_code == 404
        from pathlib import Path

        assert Path(image_path).is_file()


def test_cancel_run_and_hex_view_are_bounded(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{(tmp_path / 'cancel.db').as_posix()}",
        engine_mode="fake",
        fake_step_seconds=0.3,
    )
    with TestClient(create_app(settings)) as client:
        case_id, content = create_uploaded_case(client)
        first_run = client.post(f"/api/cases/{case_id}/runs").json()["run"]
        assert wait_for_run(client, case_id, first_run["id"])["status"] == "completed"
        hex_view = client.get(
            f"/api/cases/{case_id}/files/f-001/hex",
            params={"offset": 0, "length": len(content)},
        )
        assert hex_view.status_code == 200
        assert hex_view.json()["length"] == len(content)
        outside = client.get(
            f"/api/cases/{case_id}/files/f-001/hex",
            params={"offset": len(content), "length": 1},
        )
        assert outside.status_code == 416

        run = client.post(f"/api/cases/{case_id}/runs").json()["run"]
        cancelled = client.post(f"/api/cases/{case_id}/runs/{run['id']}/cancel")
        assert cancelled.status_code == 202
        events = client.get(f"/api/cases/{case_id}/runs/{run['id']}/events").json()["events"]
        sequences = [event["seq"] for event in events]
        assert sequences == sorted(set(sequences))
