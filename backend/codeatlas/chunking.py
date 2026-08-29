from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".sql": "sql",
    ".sh": "shell",
    ".ps1": "powershell",
    ".md": "markdown",
    ".mdx": "markdown",
    ".rst": "documentation",
    ".txt": "text",
    ".toml": "config",
    ".yaml": "config",
    ".yml": "config",
    ".json": "config",
    ".xml": "config",
    ".ini": "config",
    ".cfg": "config",
    ".env.example": "config",
    ".dockerfile": "docker",
}


@dataclass(frozen=True)
class CodeChunk:
    file_path: str
    language: str
    symbol: str | None
    kind: str
    start_line: int
    end_line: int
    content: str


def detect_language(path: Path) -> str | None:
    name = path.name.lower()
    if name == "dockerfile" or name.startswith("dockerfile."):
        return "docker"
    if name == "makefile":
        return "makefile"
    if name.endswith(".env.example"):
        return "config"
    return LANGUAGES.get(path.suffix.lower())


def _windows(
    *,
    lines: list[str],
    file_path: str,
    language: str,
    start: int,
    end: int,
    symbol: str | None,
    kind: str,
    chunk_lines: int,
    overlap: int,
) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []
    cursor = max(1, start)
    end = min(end, len(lines))
    step = max(1, chunk_lines - overlap)
    while cursor <= end:
        window_end = min(end, cursor + chunk_lines - 1)
        content = "\n".join(lines[cursor - 1 : window_end]).strip()
        if content:
            chunks.append(
                CodeChunk(
                    file_path=file_path,
                    language=language,
                    symbol=symbol,
                    kind=kind,
                    start_line=cursor,
                    end_line=window_end,
                    content=content,
                )
            )
        if window_end == end:
            break
        cursor += step
    return chunks


def _python_chunks(
    file_path: str, content: str, chunk_lines: int, overlap: int
) -> list[CodeChunk]:
    lines = content.splitlines()
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return _windows(
            lines=lines,
            file_path=file_path,
            language="python",
            start=1,
            end=len(lines),
            symbol=None,
            kind="module",
            chunk_lines=chunk_lines,
            overlap=overlap,
        )

    chunks: list[CodeChunk] = []
    covered = [False] * (len(lines) + 1)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start, end = node.lineno, getattr(node, "end_lineno", node.lineno)
            chunks.extend(
                _windows(
                    lines=lines,
                    file_path=file_path,
                    language="python",
                    start=start,
                    end=end,
                    symbol=node.name,
                    kind="function",
                    chunk_lines=chunk_lines,
                    overlap=overlap,
                )
            )
            for number in range(start, end + 1):
                covered[number] = True
        elif isinstance(node, ast.ClassDef):
            class_end = getattr(node, "end_lineno", node.lineno)
            method_nodes = [
                child
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            first_method = min((method.lineno for method in method_nodes), default=class_end + 1)
            chunks.extend(
                _windows(
                    lines=lines,
                    file_path=file_path,
                    language="python",
                    start=node.lineno,
                    end=max(node.lineno, first_method - 1),
                    symbol=node.name,
                    kind="class",
                    chunk_lines=chunk_lines,
                    overlap=overlap,
                )
            )
            for method in method_nodes:
                chunks.extend(
                    _windows(
                        lines=lines,
                        file_path=file_path,
                        language="python",
                        start=method.lineno,
                        end=getattr(method, "end_lineno", method.lineno),
                        symbol=f"{node.name}.{method.name}",
                        kind="method",
                        chunk_lines=chunk_lines,
                        overlap=overlap,
                    )
                )
            for number in range(node.lineno, class_end + 1):
                covered[number] = True

    # Preserve imports, constants, module docstrings, and other top-level code.
    cursor = 1
    while cursor <= len(lines):
        while cursor <= len(lines) and covered[cursor]:
            cursor += 1
        start = cursor
        while cursor <= len(lines) and not covered[cursor]:
            cursor += 1
        if start < cursor and "\n".join(lines[start - 1 : cursor - 1]).strip():
            chunks.extend(
                _windows(
                    lines=lines,
                    file_path=file_path,
                    language="python",
                    start=start,
                    end=cursor - 1,
                    symbol=None,
                    kind="module",
                    chunk_lines=chunk_lines,
                    overlap=overlap,
                )
            )
    return sorted(chunks, key=lambda item: (item.start_line, item.end_line, item.symbol or ""))


SYMBOL_PATTERNS = {
    "javascript": re.compile(
        r"^\s*(?:export\s+)?(?:default\s+)?(?:(?:async\s+)?function\s+([A-Za-z_$][\w$]*)|class\s+([A-Za-z_$][\w$]*)|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\()"
    ),
    "typescript": re.compile(
        r"^\s*(?:export\s+)?(?:default\s+)?(?:(?:async\s+)?function\s+([A-Za-z_$][\w$]*)|class\s+([A-Za-z_$][\w$]*)|interface\s+([A-Za-z_$][\w$]*)|type\s+([A-Za-z_$][\w$]*)|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\()"
    ),
    "java": re.compile(r"^\s*(?:(?:public|private|protected|static|final|abstract)\s+)*(?:class|interface|enum|record)\s+([A-Za-z_]\w*)|^\s*(?:(?:public|private|protected|static|final|synchronized)\s+)+[\w<>, ?\[\]]+\s+([A-Za-z_]\w*)\s*\("),
    "go": re.compile(r"^\s*(?:func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)|type\s+([A-Za-z_]\w*)\s+(?:struct|interface))"),
    "rust": re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:fn|struct|enum|trait|impl)\s+([A-Za-z_]\w*)"),
}


def _heuristic_symbol_chunks(
    file_path: str, language: str, content: str, chunk_lines: int, overlap: int
) -> list[CodeChunk]:
    lines = content.splitlines()
    pattern = SYMBOL_PATTERNS.get(language)
    if not pattern:
        return _windows(
            lines=lines,
            file_path=file_path,
            language=language,
            start=1,
            end=len(lines),
            symbol=None,
            kind="section",
            chunk_lines=chunk_lines,
            overlap=overlap,
        )
    starts: list[tuple[int, str]] = []
    for number, line in enumerate(lines, start=1):
        if match := pattern.search(line):
            symbol = next((group for group in match.groups() if group), "anonymous")
            starts.append((number, symbol))
    if not starts:
        return _windows(
            lines=lines,
            file_path=file_path,
            language=language,
            start=1,
            end=len(lines),
            symbol=None,
            kind="module",
            chunk_lines=chunk_lines,
            overlap=overlap,
        )

    chunks: list[CodeChunk] = []
    if starts[0][0] > 1:
        chunks.extend(
            _windows(
                lines=lines,
                file_path=file_path,
                language=language,
                start=1,
                end=starts[0][0] - 1,
                symbol=None,
                kind="module",
                chunk_lines=chunk_lines,
                overlap=overlap,
            )
        )
    for index, (start, symbol) in enumerate(starts):
        end = starts[index + 1][0] - 1 if index + 1 < len(starts) else len(lines)
        chunks.extend(
            _windows(
                lines=lines,
                file_path=file_path,
                language=language,
                start=start,
                end=end,
                symbol=symbol,
                kind="symbol",
                chunk_lines=chunk_lines,
                overlap=overlap,
            )
        )
    return chunks


def _markdown_chunks(
    file_path: str, content: str, chunk_lines: int, overlap: int
) -> list[CodeChunk]:
    lines = content.splitlines()
    headings = [
        (number, match.group(2).strip())
        for number, line in enumerate(lines, start=1)
        if (match := re.match(r"^(#{1,6})\s+(.+)$", line))
    ]
    if not headings:
        return _windows(
            lines=lines,
            file_path=file_path,
            language="markdown",
            start=1,
            end=len(lines),
            symbol=None,
            kind="documentation",
            chunk_lines=chunk_lines,
            overlap=overlap,
        )
    chunks: list[CodeChunk] = []
    if headings[0][0] > 1:
        chunks.extend(
            _windows(
                lines=lines,
                file_path=file_path,
                language="markdown",
                start=1,
                end=headings[0][0] - 1,
                symbol=None,
                kind="documentation",
                chunk_lines=chunk_lines,
                overlap=overlap,
            )
        )
    for index, (start, heading) in enumerate(headings):
        end = headings[index + 1][0] - 1 if index + 1 < len(headings) else len(lines)
        chunks.extend(
            _windows(
                lines=lines,
                file_path=file_path,
                language="markdown",
                start=start,
                end=end,
                symbol=heading,
                kind="documentation",
                chunk_lines=chunk_lines,
                overlap=overlap,
            )
        )
    return chunks


def chunk_source(
    file_path: str,
    language: str,
    content: str,
    *,
    chunk_lines: int = 120,
    overlap: int = 12,
) -> list[CodeChunk]:
    if not content.strip():
        return []
    if language == "python":
        return _python_chunks(file_path, content, chunk_lines, overlap)
    if language == "markdown":
        return _markdown_chunks(file_path, content, chunk_lines, overlap)
    return _heuristic_symbol_chunks(file_path, language, content, chunk_lines, overlap)

