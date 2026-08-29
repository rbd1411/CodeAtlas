from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pathspec

from .chunking import CodeChunk, chunk_source, detect_language
from .config import Settings
from .database import Database, row_to_project
from .embeddings import Embedder


DEFAULT_IGNORE_RULES = """
.git/
.hg/
.svn/
.idea/
.vscode/
node_modules/
.next/
dist/
build/
coverage/
.coverage
.pytest_cache/
.mypy_cache/
.ruff_cache/
.tox/
.venv/
venv/
__pycache__/
*.pyc
*.pyo
*.class
*.o
*.obj
*.so
*.dll
*.dylib
*.exe
*.min.js
*.map
*.lock
package-lock.json
pnpm-lock.yaml
yarn.lock
poetry.lock
uv.lock
.env
.env.*
!.env.example
*.pem
*.key
*.p12
*.pfx
id_rsa*
secrets.*
credentials.*
*.sqlite
*.sqlite3
*.db
data/
""".strip().splitlines()

GITHUB_PATTERN = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?$")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _git_branch(repo_path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.stdout.strip() or "detached"
    except (OSError, subprocess.SubprocessError):
        return "working tree"


def _display_name(source: str) -> str:
    clean = source.rstrip("/\\")
    name = Path(clean[:-4] if clean.endswith(".git") else clean).name
    return name or "repository"


class Indexer:
    def __init__(self, database: Database, config: Settings, embedder: Embedder):
        self.database = database
        self.config = config
        self.embedder = embedder

    def list_projects(self) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [row_to_project(row) for row in rows]

    def get_project(self, project_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return row_to_project(row) if row else None

    def get_project_record(self, project_id: str):
        with self.database.connect() as connection:
            return connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()

    def create_project(self, source: str, name: str | None = None, *, source_type: str | None = None) -> dict:
        source = source.strip()
        resolved_type = source_type or ("github" if source.startswith("https://github.com/") else "local")
        if resolved_type == "github":
            source_path = self._clone_public_github(source)
        else:
            source_path = self._validate_local_path(Path(source))
        canonical = str(source_path.resolve())
        with self.database.connect() as connection:
            existing = connection.execute("SELECT id FROM projects WHERE source_path = ?", (canonical,)).fetchone()
        if existing:
            return self.index_project(existing["id"])

        project_id = uuid.uuid4().hex[:12]
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    id, name, source, source_path, source_type, branch, status,
                    embedding_provider, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'created', ?, ?)
                """,
                (
                    project_id,
                    (name or _display_name(source))[:100],
                    source,
                    canonical,
                    resolved_type,
                    _git_branch(source_path),
                    self.embedder.provider,
                    now,
                ),
            )
        return self.index_project(project_id)

    def create_demo_project(self) -> dict:
        if not self.config.demo_repo_path.exists():
            raise ValueError("The bundled demo repository is missing")
        return self.create_project(str(self.config.demo_repo_path), "TinyShop API", source_type="demo")

    def delete_project(self, project_id: str) -> bool:
        record = self.get_project_record(project_id)
        if not record:
            return False
        with self.database.connect() as connection:
            connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        # Only remove repositories that CodeAtlas cloned into its managed data directory.
        if record["source_type"] == "github":
            path = Path(record["source_path"]).resolve()
            managed_root = self.config.cloned_repos_dir.resolve()
            if path != managed_root and managed_root in path.parents:
                shutil.rmtree(path, ignore_errors=True)
        return True

    def index_project(self, project_id: str) -> dict:
        record = self.get_project_record(project_id)
        if not record:
            raise KeyError(project_id)
        repo_path = self._validate_local_path(
            Path(record["source_path"]), enforce_allowed_root=record["source_type"] == "local"
        )
        with self.database.connect() as connection:
            connection.execute("UPDATE projects SET status = 'indexing' WHERE id = ?", (project_id,))

        try:
            files = list(self._scan(repo_path))
            all_chunks: list[tuple[CodeChunk, str]] = []
            file_records: list[tuple[str, str, str, str, int]] = []
            edges: list[tuple[str, str, str]] = []
            for relative_path, language, content in files:
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                file_records.append((relative_path, language, content_hash, content, len(content.splitlines())))
                for chunk in chunk_source(
                    relative_path,
                    language,
                    content,
                    chunk_lines=self.config.chunk_lines,
                    overlap=self.config.chunk_overlap_lines,
                ):
                    embedding_text = (
                        f"file: {chunk.file_path}\nlanguage: {chunk.language}\n"
                        f"symbol: {chunk.symbol or 'module'}\n{chunk.content}"
                    )
                    all_chunks.append((chunk, embedding_text))
                edges.extend(self._extract_edges(relative_path, language, content))

            embeddings = self.embedder.embed([embedding_text for _, embedding_text in all_chunks])
            chunk_rows = []
            for (chunk, _), embedding in zip(all_chunks, embeddings):
                identity = (
                    f"{project_id}:{chunk.file_path}:{chunk.start_line}:{chunk.end_line}:"
                    f"{chunk.symbol or ''}:{chunk.content}"
                )
                chunk_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
                chunk_rows.append(
                    (
                        chunk_id,
                        project_id,
                        chunk.file_path,
                        chunk.language,
                        chunk.symbol,
                        chunk.kind,
                        chunk.start_line,
                        chunk.end_line,
                        chunk.content,
                        json.dumps(embedding, separators=(",", ":")),
                    )
                )

            symbol_count = sum(1 for chunk, _ in all_chunks if chunk.symbol)
            with self.database.connect() as connection:
                connection.execute("DELETE FROM edges WHERE project_id = ?", (project_id,))
                connection.execute("DELETE FROM chunks WHERE project_id = ?", (project_id,))
                connection.execute("DELETE FROM files WHERE project_id = ?", (project_id,))
                connection.executemany(
                    """
                    INSERT INTO files (project_id, path, language, content_hash, content, lines)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [(project_id, *row) for row in file_records],
                )
                connection.executemany(
                    """
                    INSERT INTO chunks (
                        id, project_id, file_path, language, symbol, kind,
                        start_line, end_line, content, embedding
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    chunk_rows,
                )
                connection.executemany(
                    "INSERT INTO edges (project_id, source_path, target_ref, kind) VALUES (?, ?, ?, ?)",
                    [(project_id, *edge) for edge in edges],
                )
                connection.execute(
                    """
                    UPDATE projects
                    SET status = 'ready', indexed_at = ?, branch = ?, file_count = ?,
                        symbol_count = ?, chunk_count = ?, embedding_provider = ?
                    WHERE id = ?
                    """,
                    (
                        utc_now(),
                        _git_branch(repo_path),
                        len(file_records),
                        symbol_count,
                        len(chunk_rows),
                        self.embedder.provider,
                        project_id,
                    ),
                )
        except Exception:
            with self.database.connect() as connection:
                connection.execute("UPDATE projects SET status = 'failed' WHERE id = ?", (project_id,))
            raise
        project = self.get_project(project_id)
        if not project:
            raise RuntimeError("Project disappeared after indexing")
        return project

    def list_files(self, project_id: str, query: str = "", limit: int = 500) -> list[dict]:
        pattern = f"%{query}%"
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT path, language, lines FROM files
                WHERE project_id = ? AND path LIKE ?
                ORDER BY path LIMIT ?
                """,
                (project_id, pattern, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_file(self, project_id: str, path: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT path, language, lines, content FROM files WHERE project_id = ? AND path = ?",
                (project_id, path),
            ).fetchone()
        return dict(row) if row else None

    def _validate_local_path(self, path: Path, *, enforce_allowed_root: bool = True) -> Path:
        resolved = path.expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise ValueError(f"Repository directory does not exist: {resolved}")
        allowed = self.config.allowed_repo_root
        if enforce_allowed_root and allowed and resolved != allowed and allowed not in resolved.parents:
            raise ValueError(f"Repository must be inside CODEATLAS_ALLOWED_REPO_ROOT ({allowed})")
        return resolved

    def _clone_public_github(self, url: str) -> Path:
        if not GITHUB_PATTERN.fullmatch(url):
            raise ValueError("Only public https://github.com/owner/repository URLs are accepted")
        target = self.config.cloned_repos_dir / uuid.uuid4().hex[:12]
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "--", url, str(target)],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise ValueError(f"Could not run git clone: {error}") from error
        if result.returncode != 0:
            shutil.rmtree(target, ignore_errors=True)
            message = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "git clone failed"
            raise ValueError(message)
        return target.resolve()

    def _scan(self, root: Path):
        rules = list(DEFAULT_IGNORE_RULES)
        gitignore = root / ".gitignore"
        if gitignore.exists():
            rules.extend(gitignore.read_text(encoding="utf-8", errors="replace").splitlines())
        spec = pathspec.GitIgnoreSpec.from_lines(rules)
        count = 0
        total_bytes = 0
        for directory, names, filenames in os.walk(root):
            current = Path(directory)
            relative_directory = current.relative_to(root)
            names[:] = [
                name
                for name in names
                if not (current / name).is_symlink()
                and not spec.match_file((relative_directory / name).as_posix() + "/")
            ]
            for filename in filenames:
                path = current / filename
                relative = path.relative_to(root).as_posix()
                if path.is_symlink() or spec.match_file(relative):
                    continue
                language = detect_language(path)
                if not language:
                    continue
                try:
                    if path.stat().st_size > self.config.max_file_bytes:
                        continue
                    raw = path.read_bytes()
                except OSError:
                    continue
                if b"\x00" in raw[:8192]:
                    continue
                total_bytes += len(raw)
                if total_bytes > self.config.max_total_bytes:
                    raise ValueError(
                        "Repository exceeds CODEATLAS_MAX_TOTAL_BYTES "
                        f"({self.config.max_total_bytes}); narrow the scope"
                    )
                content = raw.decode("utf-8", errors="replace")
                count += 1
                if count > self.config.max_files:
                    raise ValueError(
                        f"Repository exceeds CODEATLAS_MAX_FILES ({self.config.max_files}); narrow the scope"
                    )
                yield relative, language, content

    @staticmethod
    def _extract_edges(path: str, language: str, content: str) -> list[tuple[str, str, str]]:
        targets: set[str] = set()
        if language == "python":
            targets.update(re.findall(r"^\s*from\s+([\w.]+)\s+import", content, re.MULTILINE))
            targets.update(re.findall(r"^\s*import\s+([\w.]+)", content, re.MULTILINE))
        elif language in {"javascript", "typescript"}:
            targets.update(re.findall(r"(?:from\s+|require\s*\(\s*)['\"]([^'\"]+)", content))
        elif language == "go":
            targets.update(re.findall(r"^\s*\"([^\"]+)\"\s*$", content, re.MULTILINE))
        elif language in {"java", "kotlin"}:
            targets.update(re.findall(r"^\s*import\s+([\w.]+)", content, re.MULTILINE))
        return [(path, target, "imports") for target in sorted(targets)]
