# samjho

**A study companion for CBSE Class 10 that answers from *your own copy* of the textbook** — with
citations to the chapter, section and page you can turn to — plus interactive concept animations and
a quiz that follows up on what you got wrong.

समझो — "understand".

Built for a Class 10 student working through NCERT Science and Mathematics, and for a teacher who
wants to ingest a book once and share the resulting question bank (that part is a v1 stub, described
honestly below).

---

## The licensing boundary, up front

**samjho does not ship, host or serve textbook text, and it never will.** NCERT's terms of use prohibit
republication of their textbooks and prohibit using them as part of a digital content package or
software, so a study app built on those books has to be split in two:

| | |
|---|---|
| **You bring** | your own copy of the textbook. It stays on your machine, in a gitignored `corpus/` directory. Ingestion is local. Nothing is uploaded, nothing is redistributed. |
| **This repo ships** | the software (MIT), the syllabus skeleton — chapter and section headings with page anchors, which is factual metadata — our own content (the concept animations, explainers and quizzes), and a small demo corpus of openly licensed Wikipedia text under CC BY-SA 4.0 with its sources recorded per file. |

So the app is useful the moment *you* supply a book, and empty of answers until then. That is the
design, not a missing feature. Full reasoning, including the residual risks we cannot engineer away:
[`docs/adr/ADR-001-licensing-boundary.md`](docs/adr/ADR-001-licensing-boundary.md). A CI job fails the
build if a textbook PDF or extracted corpus text is ever committed, so the boundary is enforced by the
pipeline and not just by good intentions.

Two consequences worth knowing before you start:

- **Default answers make no network calls.** With no LLM provider configured, samjho answers
  retrieval-only, from your own chunks, and quotes them. If you configure a hosted provider, your
  retrieved textbook text is sent to that provider — your call, and the one setting that moves book
  text off your machine.
- **Maths pages extract imperfectly.** Radicals are positioned glyphs in these PDFs, so `3√2` comes out
  of the text layer as `3 2`. Pages like that are flagged `math_heavy`; maths answers reason at section
  level and cite the page rather than reproducing a formula the text layer may have mangled. Don't trust
  a formula samjho quotes back at you.

## Status

Snapshot taken **2026-09-20**. Everything in the table below was measured on this machine today, by the
commands named in it — nothing is inherited from a plan document. The repository is being built by
several people in parallel, so treat this as a timestamped reading, not a permanent claim.

### What runs today

| Thing | State | Evidence (2026-09-20) |
|---|---|---|
| Structure extraction — `ingest/extract_structure.py` | **works** | Run against two synthetic 3-page PDFs authored for the test: found both numbered headings per fixture with their page anchors, marked absent chapters `missing`, exited 0 (it exits 1 when nothing parses). It writes headings and page numbers only — no prose. |
| Ingestion — `ingest/` (PDF → page text → section chunks) | **works, measured on the real books** | `python -m ingest.cli --pdf-dir … --repair-titles --text-dir data/demo-corpus` over the 27 chapter PDFs: 27/27 chapters, 434 pages, 206 sections, **1074 chunks** (593 Science + 411 Maths + 70 demo), every id unique; an independent pass over the written JSONL reported 0 structural problems. `guard_output_path()` refuses to write book text anywhere except `corpus/`. |
| Section titles | **15 repaired, 0 flagged** | The duplicate-text-layer defect was found on 15 titles under a stated rule; 13 were repaired from the chapter's own vocabulary, and the last two (§2.1, §12.2) were rebuilt from the heading's own span cluster and checked against the PDF's glyphs rather than guessed. A re-run reports `fragmented titles found: 0`. |
| Syllabus skeleton — `data/syllabus/class10.json` | **shipped** | Science: 13 chapters / 150 sections. Mathematics: 14 chapters / 56 sections. All chapters `status: ok`. Counted from the committed file. |
| Retrieval — `api/retriever.py` | **runs, measured** | Hybrid pgvector cosine + Postgres full-text, RRF fusion, cross-encoder rerank. Warm search p50 66–72 ms / p95 82–93 ms; the database phase alone is p95 10–30 ms. `pytest -m integration` → 28 passed, three consecutive runs. |
| Answer + refusal — `api/answer.py` | **runs, verified end to end** | Live against the loaded corpus: an in-syllabus question returns a cited answer (`Ch 1 §1.3.2 p.13`, "…they become rancid and their smell and taste change"), an off-syllabus maths question is refused as `not_in_corpus` **and names the closest sections**, and a nonsense question is refused as `below_threshold`. Both retrieval arms contribute (`vector_candidates: 24`, `fts_candidates: 24`). |
| Eval gate — `evals/` | **PASSES** | `python -m evals.run_eval --subjects all` → hit@4 **0.943** (≥0.90), MRR **0.806** (≥0.75), page@4 **0.971** (≥0.90), citation hit **0.886** (≥0.80), golden acceptance **0.971** (≥0.90), refusal accuracy **0.867** (≥0.80) → `GATE PASSED`. It fails correctly too: `--min-hit4 0.99` → FAIL (exit 1); unreachable database → CANNOT MEASURE (exit 2). |
| Web app — `web/` | **typechecks, builds, audits clean** | `npx tsc --noEmit` exit 0; `npm run build` exit 0 (6 routes); `npm audit --audit-level=high` → **0 vulnerabilities**; `node scripts/contrast-check.mjs` → 32/32 pairs pass. |
| Concept animations — 11 canvas components | **draw and respond** | Each measured in a headless browser: non-uniform pixels (14 of 16 luminance buckets), a control changes the canvas hash, and reduced motion freezes the frame. Readouts were asserted against the physics, not merely rendered: I = 2.000 A = 8/4, B = 40 µT = 0.2·10/0.05, C₄H₁₀ with 13 single bonds, PT = 4 exactly. |
| Unit tests — `uv run pytest -m unit` | **green** | Exit 0 in ~2 s; 148 passed. |
| Lint — `uv run ruff check .` | **green** | `All checks passed!` |
| Typecheck — `uv run mypy .` | **green** | `Success: no issues found in 32 source files`. |
| API image — `api/Dockerfile` | **builds, verified in-container** | `samjho-api:dev` built and run in three states: no database (503 on `/ask`, while `/health` and `/subjects` still serve), empty corpus (`refused`/`no_corpus`, 5 ms), real corpus (cited answer, ~1.0 s with the models pre-warmed). |
| Web image — `web/Dockerfile` | **builds and serves** | `samjho-web:dev` built from Next's standalone output and run: `HTTP 200` in 1 s, rendering the app's honest "The samjho API is not answering… This is a setup problem, not a missing feature" state while no API was reachable. |
| Licensing guard | **enforced** | `corpus/` and `*.pdf` are gitignored; `git add -A --dry-run` stages 126 files, none from `corpus/`; a repo-wide search for book prose finds it only inside the ignored `corpus/`. |
| Deployment file — `infra/docker-compose.yml` | **parses** | `docker compose -f infra/docker-compose.yml config` and `… config --quiet` both exit 0 with no `.env` present; `--env-file` overrides verified (`FTS_WEIGHT=0.55`, `API_PORT=8123`). |
| CI workflows | **valid, never run on GitHub** | Both files parse as YAML; all 17 `run:` blocks pass `bash -n` (GNU bash 5.2); the licensing guard was exercised against synthetic file lists and returns the right exit code in all 12 cases (see the ADR). |

Every gate CI runs passes locally on this machine — lint, typecheck, unit tests, integration tests
against a real Postgres + pgvector, the web typecheck and build, the licensing guard, and the compose
parse. The workflows themselves have **never executed on GitHub**, and the eval job cannot run there at
all: its golden sets need the textbook corpus, which licensing forbids in CI. `eval.yml` says so at the
top and documents the one-line fix (a self-hosted runner).

### What is not built

- **Multi-tenancy.** v1 is deliberately single-tenant; the teacher/class-code flow is an open stub, not
  a faked service.
- **Deployment.** Nothing is deployed: no remote, no host, no live URL. `infra/` plus the two images are
  what a deployment would use, and both images have been built and run locally.
- **A real browser pass.** The web app's degraded states and the 11 animations were verified headlessly
  (server-rendered markup, CDP pixel measurements). Typing, clicking, hydration and tab order in a real
  browser have not been exercised, and there has been no screen-reader or axe run.
- **The hosted-LLM answer path.** With no provider key configured, every number above is retrieval-only.
  `ANSWER_PROVIDER` is wired and degrades honestly, but it has never been run against a live provider.
- **Two known maths false answers**, named and kept red in `evals/` rather than smoothed over: "Find the
  derivative of tan(x²+1)…" and the ICSE factor-theorem question are still answered from a topically
  adjacent passage. [`api/README.md`](api/README.md) records the measurements and why the threshold that
  would have hidden them was deliberately not fitted.

## Quickstart

Two ways in. The **host path** is the one that has been run on this machine end to end; the **compose
path** is what a deployment uses — both images build and each has been run individually, but the stack
itself has not been brought up here.

### Host path (verified)

```bash
cp .env.example .env            # every value has a default; none is required

# 1. a Postgres with pgvector (any instance; .env.example defaults to localhost:5432)
docker run -d --name samjho-pg -e POSTGRES_PASSWORD=samjho -e POSTGRES_USER=samjho \
    -e POSTGRES_DB=samjho -p 5439:5432 pgvector/pgvector:pg16
export DATABASE_URL=postgresql://samjho:samjho@localhost:5439/samjho

# 2. your own textbook PDFs, named NCERT-style (corpus/pdfs/jesc101.pdf = Science ch 1, jemh101.pdf …).
#    No textbook handy? Skip to the demo-corpus line — it needs none.
mkdir -p corpus/pdfs && cp ~/your-copy/jesc1*.pdf corpus/pdfs/
uv run --with pymupdf python -m ingest.cli --pdf-dir corpus/pdfs --repair-titles
uv run --with pymupdf python -m ingest.cli --text-dir data/demo-corpus   # demo corpus, CC BY-SA 4.0

# 3. load the chunks. Embeddings are computed locally: no key, no network, no cost.
python -m api.db init
python -m api.db load corpus/chunks/*.jsonl
python -m api.db status     # → {"migrations": [1, 2], "chunks": 1437, "subjects": ["maths", "science"]}

# 4. serve
python -m uvicorn api.main:app --port 8000        # API
cd web && npm install && npm run dev              # web on :3000
```

### Compose path

```bash
docker compose --env-file .env -f infra/docker-compose.yml up --build -d
docker compose --env-file .env -f infra/docker-compose.yml exec api \
    python -m api.db load /corpus/chunks/science.jsonl /corpus/chunks/maths.jsonl
```

`postgres` is deliberately not published to the host — only `api` needs to reach it — which is why the
loader runs inside the api container against the read-only `/corpus` bind mount. Uncomment the `ports:`
block on `postgres` if you would rather load from the host.

With the API down, the web app shows its explicit "The samjho API is not answering … This is a setup
problem, not a missing feature" state rather than an empty page (`web/components/CorpusNotice.tsx`,
required by `docs/CONTRACTS.md` §5) — verified in the built web image.

## `POST /ask` — the contract, with an example that is *not* measured output

`api/` implements this contract, but no question has been asked through it on this machine, so there is
no real output to show. The shape below is the documented interface from
[`docs/CONTRACTS.md`](docs/CONTRACTS.md) §3 with illustrative values: **treat it as what the API
promises, not as something samjho produced.**

```http
POST /ask
{ "subject": "science", "chapter_no": 1, "question": "why does silver chloride turn grey in sunlight", "top_k": 6 }
```

```jsonc
{
  "answer": "…prose written from your retrieved chunks, citing [Ch 1 §1.2 p.6]…",
  "citations": [
    { "chapter_no": 1, "section_no": "1.2", "page_start": 6, "page_end": 6,
      "chapter_title": "Chemical Reactions and Equations", "section_title": "…", "score": 0.83 }
  ],
  "refused": false,
  "refusal_reason": null,          // "not_in_corpus" | "no_corpus" | "below_threshold"
  "retrieval": { "mode": "hybrid", "candidates": 24, "reranked": 6, "took_ms": 142 },
  "provider": "retrieval-only"     // which answer path actually ran; never lies about it
}
```

Refusal is a first-class answer, not an error. Ask about a Class 12 topic and the correct response is
`"refused": true` with `refusal_reason: "not_in_corpus"` — because a study companion that invents an
answer teaches you something wrong. In the implementation the refusal decision is made *before* any
model is called, and the eval suite measures how often it refuses correctly.

## How it works

```
your PDFs ──▶ ingest (local) ──▶ chunks + embeddings ──▶ Postgres (pgvector + full-text)
                                                              │
                    question ──▶ hybrid retrieval + rerank ──▶ answer with citations
                                                              │
                                              refusal when your corpus doesn't cover it
```

Retrieval is hybrid — pgvector cosine over a local `bge-small-en-v1.5` embedding, fused with Postgres
full-text search by reciprocal-rank fusion, then reranked by a local cross-encoder — so exact terms
(chemical names, theorem names) and paraphrases both work, and every result carries the ranks that
produced it. The answer path has three modes (written answer, retrieval-only, refusal) and always
reports which one ran. Component-by-component detail, including what is built and what is not:
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Repository layout

```
docs/       PLAN.md, CONTRACTS.md, ARCHITECTURE.md, adr/ADR-001-licensing-boundary.md
data/       syllabus/class10.json (shipped structure), demo-corpus/ (Wikipedia, CC BY-SA 4.0 + SOURCES.md)
ingest/     structure extraction (works) — PDF → chunks: not built yet
api/        FastAPI: retrieval, answer/refusal, quiz, progress, health, metrics
web/        Next.js App Router site + all 11 concept animations + registries
evals/      golden sets, refusal set, harness, metrics
tests/      unit / integration / eval suites, synthetic fixtures
infra/      docker-compose.yml — postgres + api + web
.github/    ci.yml (incl. the licensing guard), eval.yml
scripts/    fetch_demo_corpus.py — re-fetches the openly licensed demo text
```

## Development

```bash
uv sync --extra dev
uv run ruff check .          # lint
uv run mypy .                # typecheck
uv run pytest -m unit        # fast tests (no database, no model download)
uv run pytest -m integration # needs Postgres + pgvector, downloads the local models
uv run pytest -m eval        # the golden-set gate; needs a corpus ingested, so run it where the book is
uv run python -m evals.run_eval --subjects all   # the same measurement, printed as a table
docker compose -f infra/docker-compose.yml config # validate the deployment file
cd web && npm run typecheck && npm run build      # and npm run check:contrast for the a11y check
```

See [`docs/PLAN.md`](docs/PLAN.md) §6 for the rules every contributor here follows — no fabricated
content or numbers, refusal as a feature, tests and the eval gate must be able to fail, free-tier only,
accessible by default, and the licensing boundary stated plainly.

## Licensing

The code, the animations, our own prose and the syllabus structure are MIT — see [`LICENSE`](LICENSE).
Textbook content is **not** included and remains the property of its rights holders; the NOTICE at the
bottom of `LICENSE` says so explicitly. Text under `data/demo-corpus/` keeps its own licence (Wikipedia,
CC BY-SA 4.0), recorded per file with source URL, retrieval date and hash in
`data/demo-corpus/SOURCES.md`, with attribution repeated in each file's header.
