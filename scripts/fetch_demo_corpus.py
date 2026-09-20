#!/usr/bin/env python3
"""Fetch the demo corpus: openly licensed text that the PUBLIC deployment is allowed to serve.

Why this exists: the product's real corpus is the student's own textbook, which cannot be
redistributed (see docs/adr/ADR-001-licensing-boundary.md). A public demo therefore needs a corpus
whose licence permits redistribution. Wikimedia article extracts are CC BY-SA 4.0, so they can ship
in this repository with attribution — which is what this script records, per file.

Every fetch writes:
  data/demo-corpus/<slug>.txt   the article's plain text, trimmed, with an attribution header
and rebuilds:
  data/demo-corpus/SOURCES.md   the table of source URL, licence, retrieval date and checksum

Run:  python scripts/fetch_demo_corpus.py
The script is idempotent; re-running refreshes the text and the date. It refuses to write anything
if the API response is not the shape it expects, so a partial or error page can never enter the
corpus silently.

Topics are chosen to line up with the Class 10 concepts the animations cover, so the demo can answer
questions about the same ideas a student is studying.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://en.wikipedia.org/w/api.php"
LICENCE = "CC BY-SA 4.0"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "demo-corpus"

# slug -> (Wikipedia article, CBSE Class 10 hook)
TOPICS: dict[str, tuple[str, str]] = {
    "reflection-of-light": ("Reflection (physics)", "Science Ch 9 — Light: reflection"),
    "refraction": ("Refraction", "Science Ch 9 — Light: refraction"),
    "electric-current": ("Electric current", "Science Ch 11 — Electricity"),
    "ohms-law": ("Ohm's law", "Science Ch 11 — Electricity: Ohm's law"),
    "magnetic-field": ("Magnetic field", "Science Ch 12 — Magnetic effects of current"),
    "chemical-reaction": ("Chemical reaction", "Science Ch 1 — Chemical reactions and equations"),
    "acid-base-reaction": ("Acid–base reaction", "Science Ch 2 — Acids, bases and salts"),
    "human-eye": ("Human eye", "Science Ch 10 — The human eye and the colourful world"),
    "photoreceptor-cell": ("Photoreceptor cell", "Science Ch 10 — the eye: rods and cones"),
    "trigonometric-functions": ("Trigonometric functions", "Maths Ch 8 — Introduction to trigonometry"),
    "quadratic-equation": ("Quadratic equation", "Maths Ch 4 — Quadratic equations"),
    "circle": ("Circle", "Maths Ch 10 — Circles and tangents"),
    "similar-triangles": ("Similarity (geometry)", "Maths Ch 6 — Triangles"),
    "probability-theory": ("Probability theory", "Maths Ch 14 — Probability"),
}

MAX_CHARS = 4200  # enough for several retrieval chunks per article, small enough to review


def fetch_extract(title: str) -> str:
    query = urllib.parse.urlencode(
        {"action": "query", "prop": "extracts", "explaintext": "1", "redirects": "1",
         "format": "json", "titles": title}
    )
    request = urllib.request.Request(
        f"{API}?{query}", headers={"User-Agent": "samjho-demo-corpus/0.1 (educational demo corpus)"}
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))

    pages = payload.get("query", {}).get("pages", {})
    if not pages:
        raise RuntimeError(f"no pages in response for {title!r}")
    page = next(iter(pages.values()))
    if "missing" in page:
        raise RuntimeError(f"article not found: {title!r}")
    text = page.get("extract", "")
    if len(text) < 500:
        raise RuntimeError(f"extract suspiciously short for {title!r}: {len(text)} chars")

    # Trim at a paragraph boundary near the cap so the file never ends mid-sentence.
    if len(text) > MAX_CHARS:
        cut = text.rfind("\n\n", 0, MAX_CHARS)
        text = text[: cut if cut > 800 else MAX_CHARS].rstrip() + "\n"
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Drop sections that are not prose about the topic.
    text = re.split(r"\n== (?:See also|References|External links|Notes|Further reading) ==", text)[0]
    return text.strip() + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    rows, failures = [], []

    for slug, (title, hook) in TOPICS.items():
        try:
            body = fetch_extract(title)
        except Exception as exc:
            failures.append((slug, f"{type(exc).__name__}: {exc}"))
            continue
        url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        header = (
            f"# source: {url}\n"
            f"# licence: {LICENCE}\n"
            f"# retrieved: {today}\n"
            f"# note: extracted from the Wikipedia article named above and redistributed under "
            f"{LICENCE}. This file is the DEMO corpus — it is not textbook content, and the "
            f"product's real corpus is supplied by the student.\n"
            f"# class10 hook: {hook}\n"
        )
        text = header + "\n" + body
        (OUT_DIR / f"{slug}.txt").write_text(text, encoding="utf-8")
        rows.append({
            "slug": slug,
            "title": title,
            "url": url,
            "licence": LICENCE,
            "retrieved": today,
            "chars": len(body),
            "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()[:16],
            "hook": hook,
        })
        print(f"  {slug:24} {len(body):6d} chars  <- {title}")

    sources = [
        "# Demo corpus — sources and licences",
        "",
        "This directory holds the demo corpus: openly licensed text the **public** deployment may",
        "serve. It exists because the product's real corpus is a student's own textbook, which",
        "cannot be redistributed (see `docs/adr/ADR-001-licensing-boundary.md`).",
        "",
        f"All text below is from Wikipedia, licensed **{LICENCE}**, retrieved {today}.",
        "Attribution is repeated in each file's header. Re-fetch with `python scripts/fetch_demo_corpus.py`.",
        "",
        "| file | article | licence | retrieved | chars | sha256 |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        sources.append(
            f"| `{row['slug']}.txt` | [{row['title']}]({row['url']}) | {row['licence']} | "
            f"{row['retrieved']} | {row['chars']} | `{row['sha256']}` |"
        )
    sources += [
        "",
        "## What this corpus is not",
        "",
        "- It is **not** NCERT textbook content, and it is not a substitute for the student's own",
        "  copy of their book. Coverage is partial and the wording is not the syllabus wording.",
        "- It is **not** aligned page-by-page to any book; the Class 10 hooks above are for orientation.",
        "",
    ]
    (OUT_DIR / "SOURCES.md").write_text("\n".join(sources), encoding="utf-8")

    print(f"\nwrote {len(rows)} files + SOURCES.md to {OUT_DIR}")
    for slug, why in failures:
        print(f"  FAILED {slug}: {why}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
