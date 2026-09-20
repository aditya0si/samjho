"""Local embeddings — `BAAI/bge-small-en-v1.5`, 384 dimensions, no API key.

Two properties this module has to keep:

1. **Query-time offline.** Once the model is in the HuggingFace cache the loader tries
   `local_files_only=True` first, so an answering request never depends on the network.
2. **One model per process.** Loading is lazy and locked: importing this module costs nothing,
   which is what lets `api.main` start (and serve `/health`, `/subjects`) on a machine that has
   never downloaded a model.

Passages are embedded bare; queries get the instruction prefix bge-small-en-v1.5 was trained
with. Mixing the two would quietly cost recall, so both directions live here rather than in the
callers.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence

from .config import get_settings

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_embed_lock = threading.Lock()
_rerank_lock = threading.Lock()
_torch_configured = False
_embedder = None
_reranker = None


def _configure_torch() -> None:
    """Cap intra-op threads before the first model runs.

    Measured on the development host (16-core Windows, CPU-only, loaded), on real ~800-character
    chunks: a single query encode took ~1700 ms at torch's default 10 threads and 64-130 ms at
    1-4; reranking 24 long pairs took 10.1 s at 1 thread and 5.1 s at 4. Short inputs make thread
    launch/sync the dominant cost, long batches want threads, so the default is 4 and
    `TORCH_THREADS` raises it for bulk ingest.
    """
    global _torch_configured
    if _torch_configured:
        return
    import torch

    torch.set_num_threads(max(1, int(get_settings().torch_threads)))
    _torch_configured = True


def _load_sentence_transformer(name: str, device: str):
    from sentence_transformers import SentenceTransformer

    _configure_torch()
    # Cached-first: the normal path after the first run never touches the network.
    try:
        return SentenceTransformer(name, device=device, local_files_only=True)
    except Exception:
        return SentenceTransformer(name, device=device)


def _load_cross_encoder(name: str, device: str):
    from sentence_transformers import CrossEncoder

    _configure_torch()
    try:
        return CrossEncoder(name, device=device, local_files_only=True)
    except Exception:
        return CrossEncoder(name, device=device)


def get_embedder():
    """Lazy singleton. Raises only when the model is genuinely unavailable."""
    global _embedder
    if _embedder is None:
        with _embed_lock:
            if _embedder is None:
                settings = get_settings()
                _embedder = _load_sentence_transformer(
                    settings.embedding_model, settings.embedding_device
                )
    return _embedder


def get_reranker():
    """Lazy singleton cross-encoder, or None when reranking is switched off."""
    global _reranker
    settings = get_settings()
    if not settings.reranker_enabled:
        return None
    if _reranker is None:
        with _rerank_lock:
            if _reranker is None:
                _reranker = _load_cross_encoder(settings.reranker_model, settings.embedding_device)
    return _reranker


def model_loaded() -> bool:
    """True when the embedding model is already in memory (used by /health, and by unit tests
    that must not trigger a download)."""
    return _embedder is not None


def reranker_loaded() -> bool:
    return _reranker is not None


def unload() -> None:
    """Drop the in-memory models. Tests use this to prove lazy loading; nothing else should."""
    global _embedder, _reranker
    with _embed_lock, _rerank_lock:
        _embedder = None
        _reranker = None


def embed_passages(texts: Sequence[str]) -> list[list[float]]:
    """Embed corpus chunks. Normalised, so cosine distance and dot product agree."""
    if not texts:
        return []
    vectors = get_embedder().encode(
        list(texts),
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return [[float(x) for x in row] for row in vectors]


def embed_query(question: str) -> list[float]:
    """Embed a student question with the retrieval instruction prefix."""
    text = question.strip()
    if not text:
        raise ValueError("cannot embed an empty question")
    return embed_passages([QUERY_PREFIX + text])[0]


def embedding_dim() -> int:
    """The dimension the configured model actually produces, not what config claims."""
    return int(get_embedder().get_sentence_embedding_dimension())


def rerank_scores(question: str, passages: Sequence[str]) -> list[float]:
    """Cross-encoder logits for (question, passage) pairs. Higher is better, unbounded."""
    if not passages:
        return []
    reranker = get_reranker()
    if reranker is None:
        return []
    pairs = [(question.strip(), p) for p in passages]
    raw = reranker.predict(pairs, show_progress_bar=False)
    return [float(x) for x in raw]


def prefetch() -> dict[str, str]:
    """Download/verify both models. Used by the Docker build so the runtime stays offline."""
    settings = get_settings()
    embedder = get_embedder()
    out = {
        "embedding_model": settings.embedding_model,
        "embedding_dim": str(embedder.get_sentence_embedding_dimension()),
    }
    if settings.reranker_enabled:
        get_reranker()
        out["reranker_model"] = settings.reranker_model
    return out


if __name__ == "__main__":  # pragma: no cover - build-time helper
    import json

    print(json.dumps(prefetch(), indent=2))
