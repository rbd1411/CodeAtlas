from __future__ import annotations

import json
import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass

from .database import Database
from .embeddings import Embedder, cosine_similarity, tokenize


@dataclass(frozen=True)
class RankedChunk:
    id: str
    file_path: str
    language: str
    symbol: str | None
    kind: str
    start_line: int
    end_line: int
    content: str
    score: float

    def citation(self, number: int) -> dict:
        excerpt_lines = self.content.splitlines()[:18]
        return {
            "number": number,
            "chunk_id": self.id,
            "file_path": self.file_path,
            "language": self.language,
            "symbol": self.symbol,
            "kind": self.kind,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "excerpt": "\n".join(excerpt_lines),
            "score": round(self.score, 4),
        }


class Retriever:
    def __init__(self, database: Database, embedder: Embedder):
        self.database = database
        self.embedder = embedder

    def search(self, project_id: str, query: str, top_k: int = 8) -> tuple[list[RankedChunk], int]:
        started = time.perf_counter()
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM chunks WHERE project_id = ?", (project_id,)
            ).fetchall()
        if not rows:
            return [], int((time.perf_counter() - started) * 1000)

        query_embedding = self.embedder.embed([query])[0]
        query_tokens = tokenize(query)
        document_tokens = [tokenize(row["content"] + " " + (row["symbol"] or "") + " " + row["file_path"]) for row in rows]
        lexical = self._bm25(query_tokens, document_tokens)
        max_lexical = max(lexical, default=0.0) or 1.0
        path_terms = set(re.findall(r"[A-Za-z0-9_.\-/]+", query.lower()))

        ranked: list[RankedChunk] = []
        for index, row in enumerate(rows):
            vector_score = max(0.0, cosine_similarity(query_embedding, json.loads(row["embedding"])))
            lexical_score = lexical[index] / max_lexical
            metadata = f"{row['file_path']} {row['symbol'] or ''}".lower()
            metadata_score = 1.0 if any(term and term in metadata for term in path_terms) else 0.0
            final_score = 0.62 * vector_score + 0.32 * lexical_score + 0.06 * metadata_score
            ranked.append(
                RankedChunk(
                    id=row["id"],
                    file_path=row["file_path"],
                    language=row["language"],
                    symbol=row["symbol"],
                    kind=row["kind"],
                    start_line=row["start_line"],
                    end_line=row["end_line"],
                    content=row["content"],
                    score=final_score,
                )
            )
        ranked.sort(key=lambda item: item.score, reverse=True)

        # Prevent a single large file from crowding out all other evidence.
        diverse: list[RankedChunk] = []
        per_file: defaultdict[str, int] = defaultdict(int)
        for item in ranked:
            if per_file[item.file_path] >= 3:
                continue
            diverse.append(item)
            per_file[item.file_path] += 1
            if len(diverse) >= top_k:
                break
        return diverse, int((time.perf_counter() - started) * 1000)

    @staticmethod
    def _bm25(query: list[str], documents: list[list[str]], k1: float = 1.5, b: float = 0.75) -> list[float]:
        if not documents or not query:
            return [0.0] * len(documents)
        average_length = sum(map(len, documents)) / len(documents) or 1.0
        frequencies = [Counter(document) for document in documents]
        document_frequency = Counter()
        for document in documents:
            document_frequency.update(set(document))
        scores: list[float] = []
        for document, counts in zip(documents, frequencies):
            score = 0.0
            for token in set(query):
                frequency = counts[token]
                if not frequency:
                    continue
                containing = document_frequency[token]
                inverse_document_frequency = math.log(1 + (len(documents) - containing + 0.5) / (containing + 0.5))
                denominator = frequency + k1 * (1 - b + b * len(document) / average_length)
                score += inverse_document_frequency * frequency * (k1 + 1) / denominator
            scores.append(score)
        return scores
