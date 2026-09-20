# Interface contracts — do not change these without telling the parent agent

Seven builders work in this repository at once. Each owns a directory; nobody edits another
builder's files. These are the seams between them, frozen up front so parallel work composes.

## 0. Ground rules

- **Never commit textbook text or PDFs.** `corpus/` is gitignored. Test fixtures must be
  synthetic PDFs/text you author yourself (a 2-page PDF you generate with PyMuPDF is fine).
- **No fabricated data.** If a number is not measured, it does not appear. Eval scores come from
  the runner's output.
- **CI must be able to fail.** No `continue-on-error`, `|| true`, deselection or skips on test steps.
- Free tier only: local embeddings (`BAAI/bge-small-en-v1.5`, 384-dim), local cross-encoder
  reranker, LLM provider configurable by env with a retrieval-only fallback when no key is set.

## 1. Syllabus structure — `data/syllabus/class10.json` (exists, owned by ingest)

```jsonc
{
  "board": "CBSE", "class": 10,
  "subjects": [
    { "id": "science", "name": "Science", "book_code": "jesc1",
      "chapters": [
        { "no": 1, "title": "Chemical Reactions and Equations", "pages": 16, "status": "ok",
          "sections": [ { "no": "1.1", "title": "Chemical Equations", "page": 2 }, ... ] }
      ] }
  ]
}
```
Section titles for a minority of all-caps parent headings are still mangled by the source PDF's
duplicate text layer (e.g. `CHEMICAL EQUA AL EQUATIONS`). Repairing them is an explicit task for the
ingest builder; the marker for "this title needs review" is the presence of a repeated fragment.

## 2. Chunk record — produced by ingest, consumed by retrieval

JSONL, one object per line, written to `corpus/chunks/<subject>.jsonl` (gitignored):

```jsonc
{
  "id": "science-1-1.1-2",              // subject-chapter-section-page
  "subject": "science",
  "chapter_no": 1,
  "chapter_title": "Chemical Reactions and Equations",
  "section_no": "1.1",
  "section_title": "Chemical Equations",
  "page_start": 2, "page_end": 3,
  "math_heavy": false,                   // true when the page is mostly equations/figures
  "text": "…"                            // the only field that contains book text
}
```
Chunks never span chapters. Target 700–1000 chars with 15% overlap, splitting on sentence
boundaries where possible.

## 3. Retrieval + answer contract — owned by `api/`

```jsonc
// POST /ask  { "subject": "science", "chapter_no": 1, "question": "…", "top_k": 6 }
{
  "answer": "…",                        // prose, citing [Ch 1 §1.1 p.2]
  "citations": [ { "chapter_no": 1, "section_no": "1.1", "page_start": 2, "page_end": 3,
                   "chapter_title": "…", "section_title": "…", "score": 0.83 } ],
  "refused": false,
  "refusal_reason": null,               // "not_in_corpus" | "no_corpus" | "below_threshold"
  "retrieval": { "mode": "hybrid", "candidates": 24, "reranked": 6, "took_ms": 142 },
  "provider": "retrieval-only"          // which answer path ran; never lies about it
}
```
Refusal is a first-class result: if the retrieved context does not support an answer, the API must
return `refused: true` with a reason and no invented prose.

## 4. Other API endpoints (owned by `api/`)

- `GET /health` → `{ "status": "ok", "corpus_chunks": 1234, "provider": "…" }`
- `GET /metrics` → Prometheus text
- `GET /subjects` → the syllabus structure minus any textbook text
- `GET /chapters/{subject}/{no}` → sections + whether that chapter is ingested
- `POST /quiz` `{ subject, chapter_no, count }` → questions generated only from that chapter's
  retrieved chunks, each with the section it came from and a marking key
- `GET /progress/{student_id}` → per-chapter quiz history (SQLite or Postgres table)

## 5. Web app — owned by `web/`

- Reads `NEXT_PUBLIC_API_URL`; must render the syllabus and a clear "corpus not ingested yet" state
  when the API has no chunks, rather than an empty page.
- Citation chips are links to `/subject/[subject]/chapter/[no]#section-[section_no]`.
- Chat panel: streaming optional; a plain request/response is acceptable if it shows a spinner and
  never blocks the page.
- No network fonts, no CDN scripts. System font stack. `prefers-reduced-motion` honoured.

## 6. Animation components — owned by `web/components/animations/`

Each concept is one self-contained client component with this exact signature:

```tsx
export type ConceptAnimationProps = { className?: string };
export default function ReflectionRefraction({ className }: ConceptAnimationProps) { … }
```

Rules: interactive (at least one control that changes the drawing), keyboard reachable, canvas or
SVG drawn in-code (no CDN, no image files), a one-line "What to notice" caption and a "Try this"
prompt, `prefers-reduced-motion` respected, and no dependency outside React + the browser.

Registries: `web/components/animations/registry-science.ts` (science builder) and
`registry-maths.ts` (maths builder) export `{ conceptId, title, chapterRef, Component }[]`. The web
builder imports both registries and renders them on the chapter page — that is the only file the web
builder reads from your directory, so keep the export shape exactly as above.

## 7. Ownership map

| Path | Owner |
|---|---|
| `ingest/**`, `tests/test_ingest*`, `data/syllabus/**` | ingest builder |
| `api/**`, `evals/**`, `tests/test_retrieval*`, `tests/test_api*` | retrieval/API builder |
| `web/app/**`, `web/lib/**`, `web/components/*` (except animations) | web builder |
| `web/components/animations/{reflection-*,ohm-*,magnetic-*,carbon-*,eye-*,reaction-*}` | science-animation builder |
| `web/components/animations/{trig-*,quadratic-*,tangent-*,similar-*,probability-*}`, `registry-maths.ts` | maths-animation builder |
| `docs/**`, `infra/**`, `.github/workflows/**`, `README.md`, `LICENSE` | docs/infra builder |
