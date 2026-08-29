from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, settings
from .database import Database
from .embeddings import build_embedder
from .generation import AnswerGenerator
from .indexing import Indexer
from .retrieval import Retriever
from .schemas import (
    AskRequest,
    AskResponse,
    FileContent,
    FileItem,
    HealthResponse,
    Project,
    ProjectCreate,
    SearchRequest,
    SearchResponse,
)


def create_app(config: Settings = settings) -> FastAPI:
    config.prepare()
    database = Database(config.database_path)
    embedder = build_embedder(config)
    indexer = Indexer(database, config, embedder)
    retriever = Retriever(database, embedder)
    generator = AnswerGenerator(config)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        database.initialize()
        yield

    app = FastAPI(
        title="CodeAtlas API",
        version="0.1.0",
        description="Index repositories, retrieve code-aware evidence, and answer with citations.",
        lifespan=lifespan,
    )
    app.state.config = config
    app.state.database = database
    app.state.indexer = indexer
    app.state.retriever = retriever
    app.state.generator = generator
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> dict:
        return {
            "status": "ok",
            "database": str(config.database_path),
            "embedding_provider": embedder.provider,
            "answer_provider": generator.mode,
            "openai_configured": bool(config.openai_api_key),
        }

    @app.get("/api/projects", response_model=list[Project])
    def projects() -> list[dict]:
        return indexer.list_projects()

    @app.get("/api/projects/{project_id}", response_model=Project)
    def project(project_id: str) -> dict:
        result = indexer.get_project(project_id)
        if not result:
            raise HTTPException(status_code=404, detail="Project not found")
        return result

    @app.post("/api/projects", response_model=Project, status_code=201)
    async def create_project(payload: ProjectCreate) -> dict:
        try:
            return await run_in_threadpool(indexer.create_project, payload.source, payload.name)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/projects/demo", response_model=Project, status_code=201)
    async def create_demo() -> dict:
        try:
            return await run_in_threadpool(indexer.create_demo_project)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/projects/{project_id}/index", response_model=Project)
    async def reindex(project_id: str) -> dict:
        try:
            return await run_in_threadpool(indexer.index_project, project_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Project not found") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.delete("/api/projects/{project_id}", status_code=204)
    def delete_project(project_id: str) -> Response:
        if not indexer.delete_project(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        return Response(status_code=204)

    @app.get("/api/projects/{project_id}/files", response_model=list[FileItem])
    def files(
        project_id: str,
        q: str = Query(default="", max_length=200),
        limit: int = Query(default=500, ge=1, le=2000),
    ) -> list[dict]:
        if not indexer.get_project(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        return indexer.list_files(project_id, q, limit)

    @app.get("/api/projects/{project_id}/file", response_model=FileContent)
    def file_content(project_id: str, path: str = Query(min_length=1, max_length=1000)) -> dict:
        result = indexer.get_file(project_id, path)
        if not result:
            raise HTTPException(status_code=404, detail="File not found")
        return result

    @app.post("/api/projects/{project_id}/search", response_model=SearchResponse)
    async def search(project_id: str, payload: SearchRequest) -> dict:
        if not indexer.get_project(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        chunks, elapsed = await run_in_threadpool(retriever.search, project_id, payload.query, payload.top_k)
        return {
            "query": payload.query,
            "citations": [chunk.citation(index) for index, chunk in enumerate(chunks, start=1)],
            "elapsed_ms": elapsed,
        }

    @app.post("/api/projects/{project_id}/ask", response_model=AskResponse)
    async def ask(project_id: str, payload: AskRequest) -> dict:
        if not indexer.get_project(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        chunks, retrieval_ms = await run_in_threadpool(
            retriever.search, project_id, payload.question, payload.top_k
        )
        answer, confidence, mode, generation_ms = await run_in_threadpool(
            generator.answer, payload.question, chunks
        )
        return {
            "question": payload.question,
            "answer": answer,
            "citations": [chunk.citation(index) for index, chunk in enumerate(chunks, start=1)],
            "confidence": confidence,
            "answer_mode": mode,
            "elapsed_ms": retrieval_ms + generation_ms,
        }

    return app


app = create_app()

