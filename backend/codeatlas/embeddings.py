from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

from openai import OpenAI

from .config import Settings


TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+|[^\w\s]", re.UNICODE)


def tokenize(text: str) -> list[str]:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return [token.lower() for token in TOKEN_PATTERN.findall(expanded)]


def normalize(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    return [value / magnitude for value in vector] if magnitude else vector


class Embedder(ABC):
    provider: str

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class LocalHashEmbedder(Embedder):
    """Deterministic feature-hashing embeddings: private, offline, and dependency-light."""

    provider = "local"

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = tokenize(text)
        features = tokens + [f"{left}::{right}" for left, right in zip(tokens, tokens[1:])]
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            number = int.from_bytes(digest, "little")
            index = number % self.dimensions
            sign = 1.0 if number & 1 else -1.0
            vector[index] += sign
        return normalize(vector)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]


class OpenAIEmbedder(Embedder):
    provider = "openai"

    def __init__(self, api_key: str, model: str):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for offset in range(0, len(texts), 128):
            batch = texts[offset : offset + 128]
            response = self.client.embeddings.create(model=self.model, input=batch)
            vectors.extend(item.embedding for item in sorted(response.data, key=lambda item: item.index))
        return vectors


def build_embedder(config: Settings) -> Embedder:
    if config.embedding_provider == "openai":
        if not config.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when CODEATLAS_EMBEDDING_PROVIDER=openai")
        return OpenAIEmbedder(config.openai_api_key, config.embedding_model)
    if config.embedding_provider != "local":
        raise RuntimeError(f"Unsupported embedding provider: {config.embedding_provider}")
    return LocalHashEmbedder(config.local_embedding_dimensions)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))
