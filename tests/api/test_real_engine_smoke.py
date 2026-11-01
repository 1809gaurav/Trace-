import hashlib
import json
import time

from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app
from testgen.make_image import generate


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def test_real_engine_api_smoke_preserves_evidence_and_download_hashes(tmp_path):
    fixture_root = tmp_path / "fixtures"
    generate(fixture_root, seed=1337, only=["demo_mixed"])
    scenario_dir = fixture_root / "demo_mixed"
    image_path = scenario_dir / "disk.img"
    ground_truth = json.loads((scenario_dir / "ground_truth.json").read_text(encoding="utf-8"))
    source_hash = _sha256(image_path)
    settings = Settings(
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{(tmp_path / 'trace.db').as_posix()}",
        auth_mode="none",
        engine_mode="real",
        demo_mode=True,
        job_timeout=240,
    )

    with TestClient(create_app(settings)) as client:
        case_response = client.post("/api/cases", json={"title": "Real engine smoke test"})
        case_response.raise_for_status()
        case_id = case_response.json()["id"]
        with image_path.open("rb") as image_stream:
            upload = client.post(
                f"/api/cases/{case_id}/upload",
                files={"file": ("disk.img", image_stream, "application/octet-stream")},
            )
        upload.raise_for_status()
        truth_response = client.post(
            f"/api/cases/{case_id}/ground-truth",
            json={"ground_truth": ground_truth},
        )
        truth_response.raise_for_status()
        run_response = client.post(f"/api/cases/{case_id}/runs")
        run_response.raise_for_status()
        run_id = run_response.json()["run"]["id"]

        deadline = time.monotonic() + 250
        while time.monotonic() < deadline:
            runs = client.get(f"/api/cases/{case_id}/runs").json()["runs"]
            run = next(item for item in runs if item["id"] == run_id)
            if run["status"] in {"completed", "failed", "cancelled", "interrupted"}:
                break
            time.sleep(0.25)
        else:
            raise TimeoutError("The real engine API run did not finish in time.")
        assert run["status"] == "completed", run["error_message"]

        results_response = client.get(
            f"/api/cases/{case_id}/results",
            params={"run_id": run_id},
        )
        results_response.raise_for_status()
        files = results_response.json()["files"]
        assert files
        for item in files:
            download = client.get(
                f"/api/cases/{case_id}/files/{item['id']}/content",
                params={"run_id": run_id},
            )
            download.raise_for_status()
            assert len(download.content) == item["size_bytes"]
            assert hashlib.sha256(download.content).hexdigest() == item["sha256"]
            if item["type"] in {"jpeg", "png"}:
                preview = client.get(
                    f"/api/cases/{case_id}/files/{item['id']}/preview",
                    params={"run_id": run_id},
                )
                preview.raise_for_status()
                assert preview.headers["content-type"].startswith("image/")
                assert hashlib.sha256(preview.content).hexdigest() == item["sha256"]

        first_offset = files[0]["offsets"][0]["start"]
        hex_response = client.get(
            f"/api/cases/{case_id}/files/{files[0]['id']}/hex",
            params={"offset": first_offset, "length": 32},
        )
        hex_response.raise_for_status()
        with image_path.open("rb") as image_stream:
            image_stream.seek(first_offset)
            source_bytes = image_stream.read(32)
        assert hex_response.json()["hex"] == " ".join(f"{byte:02x}" for byte in source_bytes)

        score_response = client.get(
            f"/api/cases/{case_id}/score",
            params={"run_id": run_id},
        )
        score_response.raise_for_status()
        score = score_response.json()
        assert score["expected"] == 15
        assert score["image_integrity_ok"] is True
        deleted_ids = {
            entry["id"] for entry in ground_truth["files"]
            if entry["state"] in {"deleted_contiguous", "deleted_fragmented", "dvr_deleted"}
        }
        deleted_results = [
            item for item in score["per_file"] if item["ground_truth_id"] in deleted_ids
        ]
        assert sum(item["status"] in {"exact", "partial"} for item in deleted_results) >= 0.8 * len(deleted_ids)
        assert _sha256(image_path) == source_hash
