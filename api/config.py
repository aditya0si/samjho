"""Runtime configuration for the samjho API.

Every value has a working default, because the app must start and serve `/health` and
`/subjects` with no LLM key and an empty corpus — that is a supported state, not a broken one
(docs/PLAN.md section 6, docs/CONTRACTS.md section 0). Only `DATABASE_URL` matters for the
retrieval endpoints, and even that degrades to a clear "no corpus" answer rather than a crash.

Names match `.env.example` exactly so a single `.env` configures the whole repo.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- database ---------------------------------------------------------------
    database_url: str = "postgresql://samjho:samjho@localhost:5432/samjho"
    db_connect_timeout_s: int = 5

    # --- corpus (the student's own copy; never shipped, never public) -----------
    corpus_dir: str = "./corpus"
    syllabus_path: str = str(REPO_ROOT / "data" / "syllabus" / "class10.json")

    # --- embeddings / reranking (local, free, no key) ---------------------------
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    embedding_device: str = "cpu"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_enabled: bool = True
    # Intra-op threads for local model inference. Measured on the development host (16-core
    # Windows, CPU-only, loaded), on real ~800-character chunks:
    #     threads:   1      2      4      8
    #     query:    64ms   75ms  130ms  120ms   (single short input — flat, thread overhead)
    #     rerank24: 10.1s  6.7s  5.1s   4.4s    (24 long pairs — the dominant cost)
    # 4 is the compromise: the rerank halves against 1 thread and the query is still negligible.
    # Raise it for bulk ingest on an idle machine.
    torch_threads: int = 4
    # How many of the fused candidates the cross-encoder sees. 0 = all of them (the default, so
    # ranking quality is not traded for latency by surprise). Set it to bound the rerank cost on a
    # slow machine; the eval gate is what should justify a non-zero value.
    rerank_candidates: int = 0
    # A passage is quoted in a retrieval-only answer only if its score is at least this fraction of
    # the best passage's score. The cross-encoder separates cleanly (0.9999 vs 0.0045 on the real
    # corpus), so this keeps irrelevant passages out of an answer that claims to be quoting the book.
    quote_min_ratio: float = 0.5

    # --- answer provider --------------------------------------------------------
    answer_provider: str = ""  # "" -> retrieval-only answers, no network at all
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""
    llm_timeout_s: float = 45.0
    llm_max_tokens: int = 700

    # --- retrieval tuning -------------------------------------------------------
    fts_weight: float = 0.4  # reciprocal-rank fusion weight for the full-text arm
    retrieval_candidates: int = 24
    retrieval_top_k: int = 6
    # --- refusal thresholds, calibrated on measured distributions -----------------
    # Measured against a 937-chunk Class 10 Science corpus (a snapshot of the real ingest, so the
    # numbers are reproducible) over the 20 golden science questions and the 15 refusal-set
    # questions in evals/:
    #     golden  top scores: 17 of 20 >= 0.9688, then 0.5146, 0.4577, 0.0970
    #     refusal top scores: 0.4359, 0.0655, 0.0259, 0.0069, then <= 0.0012
    #     golden  lexical overlap: min 0.50
    #     refusal lexical overlap: 0.20, 0.25, 0.30 above the score floor (up to 0.67 below it)
    # A single absolute threshold cannot separate those: the old REFUSAL_MIN_SCORE=0.35 refused
    # the 0.0970 golden question (a legitimate "why do fried snacks go rancid" question) and
    # simultaneously *answered* the 0.4359 refusal question. Two signals, each with a measured
    # margin, separate them: a confident band the reranker only enters for real matches, and a
    # weak band that additionally requires lexical support.
    #   answer iff  top >= REFUSAL_CONFIDENT_SCORE (0.95)
    #           or (top >= REFUSAL_MIN_SCORE (0.05) and overlap >= REFUSAL_MIN_OVERLAP (0.40))
    # Margins: highest refusal 0.4359 < 0.95 < lowest confident golden 0.9688;
    #          0.0259 < 0.05 < 0.0970;  0.30 < 0.40 < 0.50.
    # The confident line is 0.95, not 0.90, because the maths refusal set showed the reranker can be
    # confidently wrong: "Solve 2x + 3y = 8 and x - y = 1 using determinants (Cramer's rule)" — a
    # Class 12 topic — scored 0.9073 with only 0.20 lexical overlap and was answered out of a Class
    # 10 book. Moving the line sends that case to the weak band, where its 0.20 overlap is refused,
    # while every confident golden question scores >= 0.9688 and is untouched. A golden question that
    # does drift into the weak band still passes on its lexical overlap (golden minimum 0.50).
    # Result on the science snapshot: golden answered 20/20, refusals wrongly answered 0/15; maths
    # refusal accuracy 12/15 -> 13/15 against the committed 0.80 bar. The eval gate (evals/) is the
    # instrument that re-checks all of this.
    refusal_min_score: float = 0.05
    refusal_confident_score: float = 0.95
    refusal_min_overlap: float = 0.40
    rrf_k: int = 60

    # --- http -------------------------------------------------------------------
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def chunks_dir(self) -> Path:
        return Path(self.corpus_dir) / "chunks"

    @property
    def provider_configured(self) -> bool:
        """True only when a provider *and* everything needed to call it are set."""
        return bool(self.answer_provider.strip() and self.llm_base_url.strip() and self.llm_model.strip())

    @property
    def provider_name(self) -> str:
        return self.answer_provider.strip() if self.provider_configured else "retrieval-only"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Tests flip env vars; the cached Settings object has to go with them."""
    get_settings.cache_clear()
