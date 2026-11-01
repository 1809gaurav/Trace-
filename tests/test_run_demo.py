import os
import stat

import run_demo


def test_safe_reset_removes_read_only_evidence(tmp_path, monkeypatch):
    project = tmp_path / "project"
    data = project / "data"
    evidence = data / "evidence" / "case" / "disk.img"
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(b"evidence")
    evidence.chmod(os.stat(evidence).st_mode & ~stat.S_IWRITE)
    monkeypatch.setattr(run_demo, "PROJECT_ROOT", project)

    run_demo._safe_reset(data)

    assert data.exists()
    assert not evidence.exists()
