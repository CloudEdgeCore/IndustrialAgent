"""Embedding 提供者：OpenAI-compatible 优先，未配置时使用确定性本地实现。

确定性实现基于特征哈希（feature hashing），对词元重叠敏感、完全可复现，
用于离线开发与测试；生产环境配置 EMBEDDING_BASE_URL 后自动切换。
"""

import hashlib
import re
from typing import Protocol

import httpx
import numpy as np

from tools.settings import settings

_ASCII_WORD_RE = re.compile(r"[a-z0-9_]+")
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_BATCH_SIZE = 32


class EmbeddingProvider(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def tokenize(text: str) -> list[str]:
    """粗粒度分词：ASCII 词 + 中文字符 bigram（无需分词器，检索召回友好）。"""
    lowered = text.lower()
    words = _ASCII_WORD_RE.findall(lowered)
    chinese = _CHINESE_RE.findall(lowered)
    bigrams = ["".join(pair) for pair in zip(chinese, chinese[1:], strict=False)]
    if len(chinese) == 1:
        bigrams.append(chinese[0])
    return words + bigrams


class DeterministicEmbedding:
    """特征哈希 embedding：同文本恒等，词元重叠越相似度越高。"""

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = np.zeros(self.dim, dtype=float)
        for token in tokenize(text):
            digest = hashlib.md5(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        return vector.tolist()


class OpenAICompatibleEmbedding:
    def __init__(self, base_url: str, api_key: str, model: str, dim: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start : start + _BATCH_SIZE]
            response = httpx.post(
                f"{self.base_url}/embeddings",
                json={"model": self.model, "input": batch},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60.0,
            )
            response.raise_for_status()
            items = sorted(response.json()["data"], key=lambda item: item["index"])
            vectors.extend(item["embedding"] for item in items)
        if vectors and len(vectors[0]) != self.dim:
            raise ValueError(
                f"Embedding 维度不匹配: 模型返回 {len(vectors[0])}，期望 {self.dim}"
                "（需迁移调整 EMBEDDING_DIM 与 document_chunks.embedding）"
            )
        return vectors


def get_embedding_provider() -> EmbeddingProvider:
    if settings.embedding_base_url:
        return OpenAICompatibleEmbedding(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key or "",
            model=settings.embedding_model,
            dim=settings.embedding_dim,
        )
    return DeterministicEmbedding(dim=settings.embedding_dim)
