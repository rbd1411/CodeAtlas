from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    source: str = Field(min_length=1, max_length=2048, description="Local directory or public GitHub URL")
    name: str | None = Field(default=None, min_length=1, max_length=100)


class Project(BaseModel):
    id: str
    name: str
    source: str
    source_type: Literal["local", "github", "demo"]
    branch: str
    status: str
    indexed_at: str | None
    created_at: str
    file_count: int
    symbol_count: int
    chunk_count: int
    embedding_provider: str


class FileItem(BaseModel):
    path: str
    language: str
    lines: int


class FileContent(FileItem):
    content: str


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=20)


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    top_k: int = Field(default=8, ge=3, le=16)


class Citation(BaseModel):
    number: int
    chunk_id: str
    file_path: str
    language: str
    symbol: str | None
    kind: str
    start_line: int
    end_line: int
    excerpt: str
    score: float


class SearchResponse(BaseModel):
    query: str
    citations: list[Citation]
    elapsed_ms: int


class AskResponse(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    confidence: Literal["high", "medium", "low"]
    answer_mode: Literal["openai", "local-extractive"]
    elapsed_ms: int


class HealthResponse(BaseModel):
    status: str
    database: str
    embedding_provider: str
    answer_provider: str
    openai_configured: bool

