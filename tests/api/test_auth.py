from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app


def test_api_key_mode_protects_cases_and_keeps_health_public(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{(tmp_path / 'apikey.db').as_posix()}",
        auth_mode="apikey",
        api_key="test-key",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").status_code == 200
        denied = client.get("/api/cases")
        allowed = client.get("/api/cases", headers={"X-API-Key": "test-key"})
        assert denied.status_code == 401
        assert allowed.status_code == 200


def test_jwt_login_uses_seeded_demo_user(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{(tmp_path / 'jwt.db').as_posix()}",
        auth_mode="jwt",
        jwt_secret="test-secret-at-least-thirty-two-characters",
        demo_username="investigator",
        demo_password="correct horse battery staple",
    )
    with TestClient(create_app(settings)) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": "investigator", "password": "correct horse battery staple"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        allowed = client.get("/api/cases", headers={"Authorization": f"Bearer {token}"})
        assert allowed.status_code == 200
        assert client.get("/api/cases").status_code == 401
