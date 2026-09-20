# `api/` — retrieval and answering service

FastAPI service that turns a student question into a cited answer, or into an explicit refusal.
Interfaces are frozen in `docs/CONTRACTS.md` sections 2–4.

## Modules

| file | what it is |
|---|---|
| `config.py` | all settings, matching `.env.example`; every one has a working default |
| `db.py` | schema + migrations, the two search arms, quiz history, and the JSONL→embeddings loader |
| `embed.py` | local `BAAI/bge-small-en-v1.5` (384-dim) and the `ms-marco-MiniLM-L-6-v2` cross-encoder |
| `retriever.py` | hybrid retrieval: cosine + full-text, RRF fusion (`FTS_WEIGHT`), cross-encoder rerank |
| `answer.py` | cited answers, and refusal as a first-class result |
| `quiz.py` | quiz questions from one chapter's chunks, each with its section and a marking key |
| `syllabus.py` | reads `data/syllabus/class10.json`; serves structure only, never book text |
| `progress.py` | per-chapter quiz history store (`GET /progress/{student_id}`) |
| `main.py` | the FastAPI app and its response models |

## Run it

```bash
# 1. a database (pgvector)
docker run -d --name samjho-pg -e POSTGRES_PASSWORD=samjho -e POSTGRES_USER=samjho \
  -e POSTGRES_DB=samjho -p 5439:5432 pgvector/pgvector:pg16
export DATABASE_URL=postgresql://samjho:samjho@localhost:5439/samjho

# 2. schema (the app also applies migrations at startup when a database is reachable)
python -m api.db init

# 3. the student's own corpus: corpus/chunks/<subject>.jsonl, produced by ingest/
python -m api.db load corpus/chunks/science.jsonl

# 4. serve
uvicorn api.main:app --port 8000
```

With no database, no corpus and no LLM key the service still starts and serves `/health`,
`/subjects` and `/chapters/...`; `/ask` returns `refused: true` with `refusal_reason: "no_corpus"`.

## Answer paths

`provider` in the response always names the path that ran:

* **`retrieval-only`** (default, no key needed) — quotes the retrieved sections word for word and
  cites them. It never paraphrases, because a paraphrase with no model behind it is a fabrication.
* **a provider name** — `ANSWER_PROVIDER` + `LLM_BASE_URL` + `LLM_MODEL` are all set. The prompt
  forces citations from the retrieved passages only, and any `[Ch …]` marker the model produces
  that is not one of the retrieved labels is stripped before the response goes out
  (`stripped_citations` counts them). If the call fails, the response degrades to retrieval-only
  and sets `degraded: true` + `provider_error` rather than inventing anything.

Refusals are decided **before** any model is called, from two bands calibrated on measured
distributions (20 golden science questions vs the 15-question refusal set, against a 937-chunk
Class 10 Science corpus — the numbers and margins are in `api/config.py`):

```
answer iff  top_score >= REFUSAL_CONFIDENT_SCORE (0.95)
        or (top_score >= REFUSAL_MIN_SCORE (0.05) and overlap >= REFUSAL_MIN_OVERLAP (0.40))
```

* **confident band** — the reranker is sure. Answered with no lexical requirement, because a
  student's paraphrase may share few words with the book's wording; refusing that is the failure a
  study companion must not have.
* **weak band** — the reranker is unsure, so the question's own words must appear in the retrieved
  text. This is the guard against a plausible-looking passage that does not answer the question.
* **below the floor** — `refusal_reason: "below_threshold"`.

Measured on that corpus: golden answered 20/20, refusal-set questions wrongly answered 0/15. The
old single threshold of 0.35 answered 19/20 and wrongly answered 1/15 — it refused a legitimate
"why do fried snacks go rancid" question while answering an out-of-syllabus one. A refusal can
never contain invented prose: no model is called once the evidence check fails.

A refusal on a non-empty corpus also carries `closest`: up to three distinct sections the corpus
*does* hold near the question, each with its honest score, and the same list is appended to
`refusal_detail`. It is a pointer, never an answer — `citations` stays empty and the answer text is
the fixed refusal sentence.

## Retrieval quality (measured, 937-chunk Class 10 Science corpus)

| metric | value |
|---|---|
| section Hit@4 (20 golden science questions) | 18/20 = 0.900 |
| MRR | 0.754 |
| golden answered (not refused) | 20/20 |
| refusal-set questions refused | 15/15 |

Widening the candidate pool does not move Hit@4: measured 0.900 at 24 candidates, 0.900 at 40 and
0.900 at 60 (MRR 0.754 / 0.779 / 0.779). The two remaining misses are ranking failures — the
reranker prefers §2.4.4 over §2.3.1 for the pH question and §3.2.4 over §3.2.5 for the reactivity
question — not recall failures, so `RETRIEVAL_CANDIDATES` stays at 24 rather than paying 1.7x the
rerank cost for +0.025 MRR. The eval gate in `evals/` is the instrument that should decide if that
trade ever changes.

## Known limitation: the thresholds do not transfer to maths

The science-calibrated thresholds are **not** valid for the maths corpus, and this is measured, not
suspected. Against a 500-chunk maths corpus, the same 15-question refusal set and the 15 maths
golden questions produce:

| question | score | overlap | rule says | should be |
|---|---|---|---|---|
| "Explain why the square root of 2 cannot be written as a fraction…" (golden) | 0.7995 | 0.22 | **refused** | answered |
| "Solve 2x + 3y = 8 … using determinants (Cramer's rule)" (refusal) | 0.9073 | 0.20 | **refused** (since the confident line moved to 0.95) | refused |
| "Find the derivative of tan(x²+1)" (refusal) | 0.7604 | 0.50 | **answered** | refused |
| "In the ICSE Class 10 Mathematics syllabus, state the factor theorem…" (refusal) | 0.1629 | 0.60 | **answered** | refused |

**Maths refusal accuracy is 13/15 = 0.867**, against a committed bar of 0.800 — one question of real
margin, where before the confident-line move it was 12/15 = 0.800, i.e. no margin at all. The
product bar this project states in `docs/PLAN.md` ("a study bot that invents an answer teaches a
student something wrong") is 1.000; at 1.000 the gate **fails on maths**, and the two questions still
leaking are the named cause.

**What was fixed, and what was deliberately not fitted.** Moving the *global* confident line from
0.90 to 0.95 refuses the Cramer's-rule question, and it is a two-sided measured margin rather than a
fitted number: highest maths refusal 0.9073 < 0.95 < lowest maths golden 0.9589 (and < 0.9688 for
science). A golden question that drifts into the weak band still passes on its lexical overlap
(golden minimum 0.50 > 0.40), so the move cannot over-refuse a question that was being answered.

Two candidates were measured and rejected, and stay rejected:

* *An overlap floor above 0.60 for the maths weak band.* It would catch the other two leaks, but **no
  maths golden question needs the weak band at all** (the only maths golden below 0.95 is the √2
  question at overlap 0.22, already over-refused), so there is no golden-side measurement to bound
  that floor. Choosing 0.65 would be fitting the refusal set — the failure mode this calibration is
  supposed to avoid.
* *A subject-vocabulary scope guard.* Measured: the science paraphrase case ("fried snacks … smell
  and taste unpleasant" → `fried`, `snacks`, `unpleasant` are absent from the science corpus) has
  0.75 vocabulary coverage, while the maths false answers sit at 0.60, 0.75 and 0.80. Any floor that
  catches them refuses the legitimate science question; "refuse if any term is missing" refuses it
  too.

What would fix the remaining two is a different instrument, not a different number: a syllabus-scope
check (does this question's topic appear in the subject's syllabus structure at all — a classifier,
not a lexical rule) or a reranker that is better on maths phrasing, plus more refusal questions so
the thresholds have a distribution rather than 15 points to fit. `evals/` already holds the
instrument that would measure either.

## Configuration

Every value has a working default; the only one that matters for retrieval is `DATABASE_URL`.
The full list is in `.env.example` (owned by the docs/infra builder) plus these:

| env var | default | why |
|---|---|---|
| `TORCH_THREADS` | `4` | intra-op threads for local inference. Measured on this host on real ~800-char chunks: a single query encode is 64–130 ms at 1–4 threads but ~1700 ms at torch's default 10; reranking 24 pairs is 10.1 s at 1 thread and 5.1 s at 4. Raise it for bulk ingest on an idle machine. |
| `REFUSAL_MIN_SCORE` | `0.05` | weak-band score floor (was `0.35`, which over-refused). |
| `REFUSAL_CONFIDENT_SCORE` | `0.95` | score above which lexical support is not required (was `0.90`, which answered an off-syllabus maths question scoring 0.9073). |
| `REFUSAL_MIN_OVERLAP` | `0.40` | lexical support required in the weak band. |
| `RERANK_CANDIDATES` | `0` (all) | caps how many fused candidates the cross-encoder sees; 0 keeps ranking quality untouched. |
| `QUOTE_MIN_RATIO` | `0.5` | a passage is only quoted in a retrieval-only answer if its score is at least this fraction of the best one. |

> These three refusal values live in more than one place — the field defaults in `api/config.py`,
> `.env.example`, `infra/docker-compose.yml`, and the hermeticity pin in `tests/conftest.py` — and a
> stale copy silently shadows the others. `.env` beats the field default, and the conftest pin beats
> both, so a mismatch shows up as a *different measurement* rather than an error. They were
> reconciled together; if you move one, move all four and re-run
> `python -m evals.run_eval --subjects all`.

## Tests

```bash
pytest -m unit          # no database, no model download
pytest -m integration   # needs Postgres + pgvector; downloads the two models on first run
```

`tests/test_retrieval_integration.py` loads `tests/fixtures/synthetic_chunks.jsonl` (six
hand-written chunks, two synthetic subjects) into subjects prefixed `fixture-` and deletes them
afterwards, so a real corpus in the same database is untouched.

## Docker

```bash
docker build -f api/Dockerfile -t samjho-api .
```

The two models are baked in at build time so the running container needs no network. The image
carries the API code and the syllabus structure only — never textbook text (`corpus/` is a mount).
