# CodeAtlas architecture

This document is the deeper technical companion to the root README.

## Component boundaries

| Component | Owns | Does not own |
|---|---|---|
| Web app | Repository selection, questions, answer/evidence presentation | Filesystem access, model keys, retrieval |
| FastAPI app | HTTP contracts, validation, CORS, service coordination | Parsing or ranking algorithms |
| Indexer | Source acquisition, safety checks, scanning, chunk persistence | Query ranking or answer prose |
| Chunker | Language detection, symbol boundaries, line provenance | Storage or embeddings |
| Embedder | Local/OpenAI text-to-vector conversion | Ranking policy |
| Retriever | BM25, cosine similarity, metadata boost, diversity | Answer generation |
| Generator | Evidence-only answer construction | Repository scanning |
| SQLite | Project snapshots, source text, chunks, vectors, edges | Authorization or distributed search |

These boundaries make provider replacement straightforward. A vector database can replace JSON embeddings without changing the UI or chunker; Tree-sitter can replace heuristic parsing without changing the API.

## Indexing sequence

```text
POST /api/projects
  → classify local path or GitHub URL
  → validate boundary or clone shallow copy
  → set project.status = indexing
  → compile built-in rules + .gitignore
  → walk supported non-symlink text files within limits
  → detect each language
  → create structure-aware chunks with source lines
  → extract import edges
  → embed metadata-prefixed chunks in batches
  → replace project file/chunk/edge snapshot transactionally
  → update counts, branch, provider, time, and ready status
```

If indexing raises, the project status becomes `failed` and the existing request receives the error. Re-indexing currently replaces the project snapshot; chunk IDs are content-and-location derived.

## Query sequence

```text
POST /api/projects/{id}/ask
  → validate project and question
  → embed question
  → load project chunks
  → calculate cosine score
  → tokenize question and corpus
  → calculate BM25 score
  → calculate path/symbol metadata match
  → weighted score fusion
  → sort and cap each file at three chunks
  → construct numbered citations
  → local extraction OR OpenAI evidence prompt
  → return answer, citations, mode, confidence, and elapsed time
```

## Data integrity

SQLite foreign keys cascade project deletion into files, chunks, and edges. Index writes are made in one transaction after scanning and embedding have completed, so the visible project snapshot does not contain half of a new index. The status update to `indexing` happens first to make lifecycle state explicit.

## Threat model

Repository content is untrusted. The primary threats are unintended file access, secret ingestion, prompt injection, resource exhaustion, and unauthorized repository access.

Implemented mitigations include path resolution, optional allowed-root enforcement, public-GitHub-only URL validation, no shell expansion for Git, symlink exclusion, secret/binary/generated ignore rules, resource limits, CORS restriction, and an evidence prompt that explicitly treats code as data.

The current system is single-user and local-first. Authentication and multi-tenant authorization are outside its security boundary. See the README for production controls.

## Scaling path

| Current design | Scaling replacement | Trigger |
|---|---|---|
| Synchronous indexing | Queue + isolated worker | Index requests exceed normal HTTP duration |
| SQLite JSON vectors | pgvector or vector service | Tens/hundreds of thousands of chunks or multiple users |
| Full re-index | Git-blob incremental index | Repositories change frequently |
| In-process BM25 | PostgreSQL FTS/OpenSearch | Corpus no longer fits comfortably in one process |
| Heuristic parsing | Tree-sitter | More languages or precise nested-symbol analysis |
| Stored import edges only | Graph expansion/reranking | Change-impact and call-flow questions become primary |
| One-shot response | Server-sent events | Model latency needs progressive UI feedback |

## Evaluation plan

Create a small versioned dataset with repository snapshots and questions grouped by intent:

- symbol location;
- architectural overview;
- request/control flow;
- error behavior;
- tests covering a feature;
- configuration discovery;
- multi-file relationship; and
- intentionally unanswerable questions.

Measure retrieval recall@k, mean reciprocal rank, citation precision, answer faithfulness, abstention accuracy, latency, tokens, and cost. Compare vector-only, BM25-only, hybrid, metadata-boosted, reranked, and graph-expanded variants.

