from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Every value can be overridden with a CODEATLAS_* variable."""

    backend_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parents[1])
    data_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("CODEATLAS_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data"))
        ).resolve()
    )
    allowed_repo_root: Path | None = field(
        default_factory=lambda: (
            Path(value).resolve() if (value := os.getenv("CODEATLAS_ALLOWED_REPO_ROOT", "").strip()) else None
        )
    )
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: _csv(
            "CODEATLAS_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        )
    )
    max_file_bytes: int = field(default_factory=lambda: int(os.getenv("CODEATLAS_MAX_FILE_BYTES", "1000000")))
    max_files: int = field(default_factory=lambda: int(os.getenv("CODEATLAS_MAX_FILES", "10000")))
    max_total_bytes: int = field(
        default_factory=lambda: int(os.getenv("CODEATLAS_MAX_TOTAL_BYTES", "50000000"))
    )
    chunk_lines: int = field(default_factory=lambda: int(os.getenv("CODEATLAS_CHUNK_LINES", "120")))
    chunk_overlap_lines: int = field(default_factory=lambda: int(os.getenv("CODEATLAS_CHUNK_OVERLAP_LINES", "12")))
    local_embedding_dimensions: int = field(
        default_factory=lambda: int(os.getenv("CODEATLAS_LOCAL_EMBEDDING_DIMENSIONS", "384"))
    )
    embedding_provider: str = field(
        default_factory=lambda: os.getenv("CODEATLAS_EMBEDDING_PROVIDER", "local").lower()
    )
    embedding_model: str = field(
        default_factory=lambda: os.getenv("CODEATLAS_EMBEDDING_MODEL", "text-embedding-3-small")
    )
    answer_provider: str = field(default_factory=lambda: os.getenv("CODEATLAS_ANSWER_PROVIDER", "local").lower())
    answer_model: str = field(default_factory=lambda: os.getenv("CODEATLAS_ANSWER_MODEL", "gpt-5.4-mini"))
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY") or None)

    @property
    def database_path(self) -> Path:
        return self.data_dir / "codeatlas.db"

    @property
    def cloned_repos_dir(self) -> Path:
        return self.data_dir / "repositories"

    @property
    def demo_repo_path(self) -> Path:
        return self.backend_dir / "demo_repository"

    def prepare(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cloned_repos_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
