# Samjho — build contract

**Product:** a study companion for CBSE Class 10 (India). A student picks a subject and chapter,
asks questions and gets answers **cited to their own copy of the book** (chapter, section, page),
works through interactive concept animations, and is quizzed on what they got wrong.

**Name:** `samjho` (समझो, "understand") — rename freely, but pick one before the repo goes public.

**Owner:** Aditya Singh (`aditya0si`). Local repo: `C:/Users/oliad/Desktop/samjho`.

---

## 1. The constraint that shapes everything

NCERT's terms of use, quoted from `ncert.nic.in/textbook.php`:

> "republication of NCERT textbooks by any other individual or agency is strictly prohibited …
> No agency or individual may make electronic or print copies of these books and redistribute them
> in any form whatsoever. Use of these online books as a part of digital content packages or
> software is also strictly prohibited. No website or online service is permitted to host these
> online textbooks."

**Therefore the architecture is split:**

| Layer | Rights | Ships where |
|---|---|---|
| Textbook text (the corpus) | the student's own copy | **never** in the repo, never on a public server. Ingested locally into a gitignored `corpus/` directory, or uploaded by a signed-in user into their own tenant |
| Chapter/section structure, learning outcomes | factual metadata | `data/syllabus/` — shipped, sourced from public CBSE/NCERT syllabus documents |
| Concept animations, explainers, quiz generators | ours | shipped, mapped to syllabus outcomes |
| Demo corpus for the public site | permissive licence only (OpenStax CC BY, or our own writing) | `data/demo-corpus/` with the licence recorded per source |

**Required artifact:** `docs/adr/ADR-001-licensing-boundary.md` explaining the constraint, the design
response, and what the deployment does and does not serve. This ADR is a deliverable, not decoration:
it is the part a reviewer reads to judge engineering judgement.

**Forbidden:** committing NCERT PDFs or extracted text, serving book text from the public API,
"downloading the books for the user" as a server-side fetch, or presenting generated prose as
quotations from the book.

## 2. Scope for v1

- Subjects: **Science and Mathematics, Class 10** (deeply done). The ingestion path must be
  subject-agnostic — Social Science, English, Hindi come later as configuration, not as code.
- A student can: pick subject → chapter → section; ask questions; see cited answers with page
  references into their own copy; run interactive concept animations; take a generated quiz and see
  which concepts they missed.
- A teacher can: ingest a PDF once and share the resulting question bank with a class code (v1:
  stubbed to a single tenant with a note, not faked as multi-tenant).

## 3. Architecture

```
PDF ──▶ ingest ──▶ sections ──▶ chunks ──▶ embeddings ──▶ Postgres (pgvector + FTS)
                                                              │
                          question ──▶ retrieve (hybrid + rerank) ──▶ answer with citations
                                                              │
                                             refusal path when the corpus does not cover it
```

- **Ingestion:** PyMuPDF text extraction with page-accurate provenance. NCERT PDFs extract cleanly
  (verified: Maths ch1 9pp ≈1.6k chars/page; Science ch1 16pp ≈2.0k chars/page; no empty pages).
  Known defect to handle explicitly: **math symbols degrade** (`3√2` → `3 2`) because radicals are
  positioned glyphs. Mitigation in v1: mark math-heavy pages (`data-math-heavy="true"`), keep them
  retrievable but answer maths questions at the reasoning/section level and cite the page rather
  than reproducing a formula as if the text layer were faithful. Say this in the README.
  Deduplicate the repeated-label artifacts NCERT PDFs carry (`Activity 1.7` appears 5× on one page).
- **Chunking:** by section, ~700–1000 characters with overlap, each chunk carrying
  `{subject, chapter_no, chapter_title, section_no, section_title, page_start, page_end, text}`.
  Never split a chunk across chapters.
- **Retrieval:** hybrid — pgvector cosine over `bge-small-en-v1.5` (384-dim, local, free) fused with
  Postgres full-text search, then a local cross-encoder rerank. Fusion weights live in config.
- **Answering:** provider-agnostic LLM client. Free-tier default, configurable via env. The prompt
  must force: answer only from retrieved context; cite `[Ch 4 §4.2 p.57]`; if the context does not
  support an answer, refuse and say which chapter would cover it.
- **Eval gate (CI):** `evals/golden/*.jsonl` per subject — question, expected section, expected
  answer facts. Gate on Hit@4 and MRR against thresholds recorded in the repo. **Refusal set**:
  out-of-corpus questions (Class 12 topics, other boards) that must be refused; measure refusal
  precision and recall. A gate that can fail is mandatory; no `continue-on-error`.
- **Web:** Next.js (App Router) — syllabus map, chapter view with sections, chat panel with citation
  chips that deep-link to `[chapter, section, page]`, animation host, quiz view, progress page.
- **API:** FastAPI — `/subjects`, `/chapters`, `/ask`, `/quiz`, `/progress`, `/health`, `/metrics`.

## 4. Concept animations (our IP, mapped to syllabus outcomes)

Interactive first, video second. Each animation is a single self-contained component, keyboard
reachable, with `prefers-reduced-motion` respected, and a one-line "what you should notice" caption
plus a "try this" prompt that changes the parameters.

**Science (Class 10):**
1. Reflection and refraction at a plane/curved surface — draggable ray, live angle readouts.
2. Ohm's law circuit — sliders for V, R; live current, V–I graph drawn as you change values.
3. Magnetic field lines around a current-carrying conductor — field strength by distance.
4. Carbon compounds — 3D ball-and-stick (Three.js) for the first four alkanes/functional groups.
5. Human eye and lens defects — focal-length simulation, myopia/hypermetropia correction.
6. Chemical reaction types — balance the equation interactively, with a live atom count.

**Mathematics (Class 10):**
7. Trigonometric ratios on the unit circle — dragging the angle, sine/cosine traces.
8. Quadratic polynomials — a, b, c sliders, roots and vertex updating live.
9. Circles and tangents — tangent length from an external point, theorem visualised.
10. Similar triangles and the basic proportionality theorem — drag the parallel line.
11. Probability — simulate coin/dice trials, watch the relative frequency converge.

Use p5.js or hand-written canvas for the interactive sims and Three.js only where 3D earns it.
Where a derivation is better watched than touched, a Manim-rendered explainer is acceptable, but it
must be generated from a committed script (never a hand-drawn asset).

## 5. Data contract

- `data/syllabus/class10.json` — subjects → books → chapters → sections, with learning outcomes.
  Factual structure only, no book text.
- `corpus/` — the student's own PDFs and extracted text. **Gitignored. Never committed.**
- `evals/golden/science.jsonl`, `evals/golden/maths.jsonl` — golden QA with expected section/page.
- `evals/refusals.jsonl` — questions that must be refused.
- `data/demo-corpus/` — permissively licensed text with a `SOURCES.md` recording, per file, the
  source URL, licence, and retrieval date.

## 6. Rules every builder follows

- **No fabricated content.** No invented quotations from a book, no made-up page numbers, no
  fabricated eval scores. If a number is not measured, it does not appear.
- **Refusal is a feature.** A study bot that invents an answer teaches a student something wrong.
  Every answer path must be able to say "not in your material".
- **Tests and the eval gate run in CI and can fail.** No `continue-on-error`, no `|| true` on test
  steps, no deselection to get green, no deleting tests.
- **Free-tier only.** Local embeddings, free LLM tier with a documented key, no paid service in the
  default path. The app must run with zero external API keys using the demo corpus + a local model
  fallback path that honestly degrades to retrieval-only answers.
- **Accessible:** keyboard reachable, visible focus, ≥4.5:1 contrast, reduced-motion honoured.
- **Honest README:** what works, what does not, measured numbers only, and the licensing boundary
  stated plainly.

## 7. Deliverables

```
samjho/
├── docs/{PLAN.md,adr/ADR-001-licensing-boundary.md}
├── data/{syllabus/,demo-corpus/}
├── evals/{golden/,refusals.jsonl}
├── ingest/        # PDF → sections → chunks → embeddings, with provenance
├── api/           # FastAPI service + retrieval + answer + quiz
├── web/           # Next.js site + the 11 concept animations
├── infra/         # docker compose (postgres+pgvector, api, web)
├── tests/         # pytest: ingestion, retrieval, refusal, API contract
└── .github/workflows/{ci.yml,eval.yml}
```

Success for v1: a student can ingest their Class 10 Science book, ask "why does the silver chloride
turn grey in sunlight", get an answer citing the right chapter/section/page, then take a 5-question
quiz on that chapter — with the eval gate green in CI and the refusal path measured.
