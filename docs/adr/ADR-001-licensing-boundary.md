# ADR-001 — The licensing boundary

- **Status:** accepted
- **Date:** 2026-09-20
- **Owner:** docs/infra builder (`docs/**`, `infra/**`, `.github/**`, `README.md`, `LICENSE`)
- **Related:** `docs/PLAN.md` §1 and §7, `docs/CONTRACTS.md` §0 and §7, `docs/ARCHITECTURE.md`,
  `LICENSE` (NOTICE section), `.github/workflows/ci.yml` job `licensing-guard`

## Context

Samjho answers a student's questions from a CBSE Class 10 textbook and cites the chapter, section and
page in *their own copy of that book*. The books in question are published by NCERT, and NCERT's
terms of use restrict copying and hosting them. That constraint, not a technical one, is what decides
where the textbook text is allowed to exist.

NCERT's terms, quoted as recorded in `docs/PLAN.md` §1 (which cites `ncert.nic.in/textbook.php`; the
ellipsis is in that record, so this is a partial quotation):

> "republication of NCERT textbooks by any other individual or agency is strictly prohibited …
> No agency or individual may make electronic or print copies of these books and redistribute them
> in any form whatsoever. Use of these online books as a part of digital content packages or
> software is also strictly prohibited. No website or online service is permitted to host these
> online textbooks."

**Provenance of that quotation.** It is reproduced from our own planning record, `docs/PLAN.md` §1.
On 2026-09-20 the build machine could not reach `ncert.nic.in` (TCP/TLS connect timeout), so the
wording has *not* been re-verified against the live page during this build. Anyone who publishes a
samjho instance publicly should read the current terms at the source first, and re-read them if they
are ever revised.

## The constraint in engineering language

Taking the quoted sentences at face value, and without reading more or less into them than they say:

1. **"republication … strictly prohibited"** — book text must not appear in any artefact we
   distribute: not in the git repository, not in a container image, not in a release asset, not on a
   public web page.
2. **"may make electronic or print copies … and redistribute them in any form"** — we must not hand
   the file, or any extracted copy of its text, to a second party, which includes the next user of an
   instance we operate.
3. **"use of these online books as a part of digital content packages or software is … prohibited"** —
   the books must not be an input to the *shipped product*. This closes the obvious workaround: a
   pre-built chunk store or embedding index is a derivative of the book, so shipping one is still
   redistribution in a different form, not a legitimate technical trick.
4. **"No website or online service is permitted to host these online textbooks"** — no samjho-operated
   service may serve the books, directly or as a proxy that fetches them on the user's behalf.

In one sentence: **the textbook text is data that the student already owns and keeps; samjho is
software that runs on it locally, and what we distribute is the software, the syllabus skeleton, and
our own explanatory material.**

## Decision — the architecture that responds to it

| Layer | Whose rights | Where it lives | What enforces it |
|---|---|---|---|
| Textbook text (the corpus) | the student's own copy (or their school's) | `corpus/` on the machine that owns the book; gitignored; bind-mounted into the compose `api` container | `.gitignore` (`corpus/`, `*.pdf`), the `licensing-guard` CI job, and the rule that `corpus/` is never inside a build context or an image |
| Chapter/section structure, page anchors, learning outcomes | factual metadata from public CBSE/NCERT syllabus documents | `data/syllabus/class10.json`, shipped | the generator emits headings and page numbers only — `ingest/extract_structure.py` has no code path that writes a paragraph |
| Concept animations, explainers, quiz generators, our prose | ours | `web/components/animations/**`, `api/**`, `web/app/**`, shipped under MIT | — |
| Demo corpus for any public/demo deployment | third-party text under its own open licence, or our own writing | `data/demo-corpus/`, with source URL, licence and retrieval date recorded per file in `SOURCES.md` | review rule; demo-corpus files are one of two narrow exemptions in the licensing guard |

Design consequences, in order of how much they constrain the product:

- **Ingestion runs where the book is.** PDF to chunks to embeddings to Postgres is a local pipeline
  invoked by whoever holds the copy; it writes `corpus/` on that machine. No samjho-controlled server
  is in that path. (Contract: `docs/CONTRACTS.md` §2. Implementation status: see
  `docs/ARCHITECTURE.md` "What is not built".)
- **Only structure is shippable.** The syllabus generator finds headings by font metrics (a heading
  is a line set above body size, not a line that matches a regex) and records heading text plus a page
  anchor. It is deliberately incapable of emitting prose.
- **Answers are generated, cited, and labelled as ours.** An answer is prose the model wrote from the
  student's own retrieved chunks, with citations into that copy; it is never presented as a quotation
  from the book.
- **The corpus never enters an image.** Compose bind-mounts the host directory; nothing is baked in.
- **We never fetch a textbook for the user.** There is no server-side "download this book/chapter"
  code path, and there must not be one. That is a design invariant of this project, not a
  not-yet-implemented feature. The one fetcher in the tree, `scripts/fetch_demo_corpus.py`, targets
  openly licensed Wikipedia articles for `data/demo-corpus/` only; it must never be pointed at
  `ncert.nic.in` or any other textbook source, and a change that does so is a re-open trigger below.
- **Retrieval-only is the default answer path.** With no provider configured, samjho answers from
  retrieved text without any network call. If the operator configures a hosted LLM, the retrieved
  chunks travel to that provider — an outbound copy of the student's text and a decision that belongs
  to the operator, which is why the default is local and why the trade-off is written down in
  `.env.example` and the README.

## What the deployment does NOT serve

These are the verification points for a reviewer of an instance:

- No textbook PDFs, and no text extracted from one, anywhere in the image, the image history, or the
  repository.
- No endpoint that fetches from `ncert.nic.in` or any third party on a user's behalf.
- No corpus shared between users. v1 is single-tenant by design; the planned teacher/class-code
  feature is stubbed in the open rather than faked as a multi-tenant service (`docs/PLAN.md` §2).
- No pre-built index of a textbook offered as a download.
- No generated prose presented as a quotation from the book, and no invented page numbers.
- Any public/demo deployment answers only from `data/demo-corpus/`.

## Residual risks

Listed plainly, because a boundary that is described as airtight when it is not is worse than one
with its seams visible.

1. **A user can ingest material they have no right to.** Samjho cannot verify who owns a PDF dropped
   into `corpus/`. The software is neutral infrastructure; responsibility sits with whoever runs it.
   We state the expectation in the README and in the ingest CLI's own output, and we ship no crawler.
2. **Derived artefacts remain derivative.** Chunk text, embeddings and a reranker index are
   transformations of the book, not new works. Our reading is that producing them locally, for the
   owner of the copy, for private study, is not redistribution — but that is an engineering reading,
   not a legal conclusion, and it does not license shipping or sharing those artefacts.
3. **Excerpt display.** Citation chips and short supporting snippets put fragments of the book on
   screen. For the owner's copy on the owner's machine that is use of material they already have. Any
   feature that displays longer passages, or shares them with someone who does not own the book,
   moves toward republication and needs its own decision (see the re-open triggers below).
4. **The demo corpus is committed, so the repository does redistribute that text.** It is Wikipedia
   material under **CC BY-SA 4.0** — attribution is repeated in each file header and recorded per file
   (URL, licence, retrieval date, sha256) in `data/demo-corpus/SOURCES.md`. CC BY-SA is a share-alike
   licence, not the same as CC BY: it permits redistribution with attribution, and it attaches its
   share-alike condition to modified versions of that text. It applies to those files, not to the
   project's own code. Keep the attribution intact and keep the licence record current when files are
   re-fetched.
5. **Extraction fidelity.** NCERT PDFs extract with defects: radicals degrade (`3√2` becomes `3 2`
   because they are positioned glyphs) and some headings carry a duplicated text layer fragment.
   A confidently wrong answer is a teaching hazard, so math-heavy pages are marked and answered at
   reasoning/section level with a page citation, never as a reconstructed formula.
6. **Hosted model providers.** If `ANSWER_PROVIDER` points at a hosted endpoint, retrieved book text
   leaves the machine. The retrieval-only default exists precisely because that is a real
   consequence, not a performance choice.
7. **Multi-tenancy later.** "One shared corpus, many students" becomes a redistribution channel the
   moment the second user is not the owner of the copy. Re-open this ADR before building it.
8. **This is not legal advice.** This ADR records an engineering reading of publicly published terms,
   written by engineers, so that the architecture is defensible and the intent is legible. It is not a
   legal opinion, it does not claim to be correct about the law, and it should not be quoted as one.
   Get qualified counsel before any commercial or at-scale public deployment.

## Enforcement — the parts that actually bite

- **`.gitignore`** ignores `corpus/` (the whole directory, which is where PDFs and extracted chunks
  live) and `*.pdf`, with narrow exceptions for `data/demo-corpus/**` and `tests/fixtures/**`.
  Extracted `.txt` is deliberately *not* ignored globally — that would silently exclude files like
  `requirements.txt` — so extracted text is caught by the guard instead.
- **CI job `licensing-guard`** (`.github/workflows/ci.yml`) fails the build if `git ls-files` lists
  any `*.pdf` outside `data/demo-corpus/` and `tests/fixtures/`, any path under `corpus/`, or any
  `*.txt` outside those two directories. It exists because `git add -f` defeats `.gitignore`; the
  guard makes that mistake a red build rather than a silent commit. No `continue-on-error`. Its
  behaviour was exercised on 2026-09-20 against synthetic `git ls-files` output: it exits 1 for a
  committed PDF, a `corpus/` path and an extracted `.txt`, and 0 for a clean tree, for the
  licence-documented demo corpus, and for a near-miss name like `docs/corpus-notes.md`.
  The two exemptions are deliberate and narrow — they exist because `docs/CONTRACTS.md` §0 sanctions
  synthetic fixtures and openly licensed demo text — and they are the guard's known soft spot: it
  cannot tell a synthetic fixture from a copied page, so a reviewer still has to look.
- **Review rule, not mechanisable:** a commit that adds text under `data/demo-corpus/` must add that
  file's source URL, licence and retrieval date to `data/demo-corpus/SOURCES.md` (in place, with a
  sha256 per file). A commit that adds bulk text of unstated origin should be assumed to be textbook
  text until the author shows otherwise.
- **Re-open this ADR** before any change that (a) moves book text off the machine holding the copy,
  (b) shares one corpus between users, (c) displays passages beyond short supporting snippets, or
  (d) points any fetcher in this repository at a textbook source.

## Consequences

- **The product is harder to demo.** A fresh clone shows a syllabus-driven UI with no answers until
  the operator supplies their own book. Accepted deliberately; the alternative is distributing
  someone else's book.
- **Embeddings and reranking run locally** (`BAAI/bge-small-en-v1.5`, a MiniLM cross-encoder). That is
  also what the free-tier rule requires, and the models download on first use by the operator.
- **Eval fixtures must be ours.** We author the golden questions; the files must not contain book
  paragraphs pasted in as "expected answers". Expected section/page references are factual metadata
  and are fine.
- **The guard is a release blocker.** A failure here stops the build; it is not a lint warning to be
  waved through.
