from pathlib import Path

from fastapi.testclient import TestClient

from codeatlas.app import create_app
from codeatlas.config import Settings


def make_repository(root: Path) -> Path:
    repository = root / "sample-repo"
    repository.mkdir()
    (repository / "auth.py").write_text(
        """class AuthService:\n"
        "    def validate_token(self, token):\n"
        "        if token == 'expired':\n"
        "            raise TokenExpiredError()\n"
        "        return decode_jwt(token)\n"
        """,
        encoding="utf-8",
    )
    (repository / ".env").write_text("SECRET=should-not-be-indexed", encoding="utf-8")
    (repository / "README.md").write_text("# Authentication\nTokens are validated in AuthService.", encoding="utf-8")
    return repository


def test_index_search_and_grounded_answer(tmp_path):
    repository = make_repository(tmp_path)
    config = Settings(data_dir=tmp_path / "data", allowed_repo_root=tmp_path)
    app = create_app(config)
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["answer_provider"] == "local-extractive"

        created = client.post("/api/projects", json={"source": str(repository)})
        assert created.status_code == 201
        project = created.json()
        assert project["file_count"] == 2
        assert project["chunk_count"] >= 2

        files = client.get(f"/api/projects/{project['id']}/files").json()
        assert {item["path"] for item in files} == {"README.md", "auth.py"}

        result = client.post(
            f"/api/projects/{project['id']}/ask",
            json={"question": "Where is token expiration validated?"},
        )
        assert result.status_code == 200
        payload = result.json()
        assert payload["citations"]
        assert payload["citations"][0]["file_path"] == "auth.py"
        assert "[1]" in payload["answer"]


def test_rejects_paths_outside_allowed_root(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    config = Settings(data_dir=tmp_path / "data", allowed_repo_root=allowed)
    with TestClient(create_app(config)) as client:
        response = client.post("/api/projects", json={"source": str(outside)})
    assert response.status_code == 400
    assert "CODEATLAS_ALLOWED_REPO_ROOT" in response.json()["detail"]
