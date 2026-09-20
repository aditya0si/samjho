#!/usr/bin/env python
"""samjho eval gate — section Hit@4, MRR, page coverage and refusal correctness.

Run from the repository root with the venv active::

    python -m evals.run_eval                    # the gate (exit 0 pass / 1 below threshold / 2 cannot measure)
    python -m evals.run_eval -v                 # per-question detail
    python -m evals.run_eval --skip-answer      # retrieval metrics only (diagnostic; refusal not enforced)
    python -m evals.run_eval --min-hit4 0.99    # deliberately fail the gate (used to prove it can fail)

What is measured, exactly:

* ``hit@4``      at least one of the first four retrieved chunks carries an expected ``section_no``
                 (exact match — ``"1.2.2"`` does not satisfy ``"1.2"``).
* ``MRR``        mean of 1/rank of the first correct chunk over the whole returned list.
* ``page@4``     at least one of the first four chunks covers an expected page
                 (``page_start <= p <= page_end``).
* ``cite_hit``   the answer path's citation set contains an expected section — this is what the
                 student actually sees, so it is measured separately from retrieval.
* ``accepted``   share of golden questions the answer path did *not* refuse (a false refusal is a
                 failure of the same severity as a hallucinated answer).
* ``refusal``    share of refusal-set questions the answer path refuses in *every* scope tried.

Thresholds are CLI flags whose committed defaults are measured values, not aspirations — see
``evals/README.md`` for the command and the measurement each default comes from.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import functools
import json
import re
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals import adapter  # noqa: E402
from evals.metrics import (  # noqa: E402
    accuracy,
    hit_at_k,
    mean,
    page_hit,
    page_overlap_hit,
    rank_of_first_hit,
    reciprocal_rank,
)

EVALS_DIR = Path(__file__).resolve().parent
GOLDEN_DIR = EVALS_DIR / "golden"
REFUSALS_PATH = EVALS_DIR / "refusals.jsonl"
SYLLABUS_PATH = REPO_ROOT / "data" / "syllabus" / "class10.json"

# --- committed thresholds ---------------------------------------------------------------------
# Measured against the real corpus (ingest/ built it: 937 Science chunks covering all 13 chapters
# and 500 Maths chunks covering all 14) with api.retriever.search + api.answer.answer_question,
# provider "retrieval-only", chapter scope, top_k 6:
#
#     DATABASE_URL=postgresql://… python -m evals.run_eval --subjects all -v
#
#   run 1  hit@4 0.943  MRR 0.806  page@4 …     citation hit 0.886  acceptance 0.971  refusals 0.800
#   run 2  hit@4 0.943  MRR 0.806  page@4 0.971  citation hit 0.857  acceptance 0.943  refusals 0.867
#
# (run 1 predates the page-span fix, so its page@4 is not comparable.) Retrieval is not bit-stable
# across runs — Postgres returns ties in a different order — so one question can flip either way
# (1/35 = 0.029). Each default below is therefore the *worst* value observed, rounded down to the
# nearest 0.05, which leaves room for two flipped questions on every metric:
#
#   hit@4 0.90 = 32/35   MRR 0.75 (worst observed 0.806)
#   page@4 0.90 = 32/35  citation hit 0.80 = 28/35   acceptance 0.90 = 32/35
#   refusal accuracy 0.80 = 12/15 — the worst run observed *before* the confident band moved from
#                      0.90 to 0.95. That move refused the Cramer's-rule leak, so the measured value
#                      is now 0.867 = 13/15 and this floor carries one question of real headroom.
#                      Raising it to 0.85 is defensible only after a re-measure confirms 13/15 is
#                      stable across runs; it is not raised on a single run.
#
# Do not raise a default without re-measuring, and do not lower one to make a red run green.
DEFAULT_MIN_HIT4 = 0.90
DEFAULT_MIN_MRR = 0.75
DEFAULT_MIN_PAGE_HIT = 0.90
DEFAULT_MIN_CITE_HIT = 0.80
DEFAULT_MIN_GOLDEN_ACCEPTANCE = 0.90
DEFAULT_MIN_REFUSAL_ACCURACY = 0.80

GOLDEN_FILES = {"science": GOLDEN_DIR / "science.jsonl", "maths": GOLDEN_DIR / "maths.jsonl"}
REFUSAL_REASONS = {"out_of_syllabus", "other_board", "not_course_material"}


class MeasurementError(RuntimeError):
    """The harness could not obtain a number (missing api/, missing corpus, contract violation)."""


# --- input -------------------------------------------------------------------------------------


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MeasurementError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise MeasurementError(f"{path}:{lineno}: each line must be a JSON object")
        rows.append(obj)
    if not rows:
        raise MeasurementError(f"{path}: no questions found")
    return rows


def validate_golden(rows: list[dict[str, Any]], path: Path) -> None:
    required = {
        "question",
        "subject",
        "chapter_no",
        "expected_sections",
        "expected_pages",
        "why",
    }
    for i, row in enumerate(rows, start=1):
        missing = required - set(row)
        if missing:
            raise MeasurementError(f"{path}:{i}: missing keys {sorted(missing)}")
        if not isinstance(row["expected_sections"], list) or not row["expected_sections"]:
            raise MeasurementError(f"{path}:{i}: expected_sections must be a non-empty list")
        if not isinstance(row["expected_pages"], list) or not row["expected_pages"]:
            raise MeasurementError(f"{path}:{i}: expected_pages must be a non-empty list")
        if not isinstance(row["chapter_no"], int):
            raise MeasurementError(f"{path}:{i}: chapter_no must be an integer")


def validate_refusals(rows: list[dict[str, Any]], path: Path) -> None:
    for i, row in enumerate(rows, start=1):
        if set(row) != {"question", "reason"}:
            raise MeasurementError(
                f"{path}:{i}: expected exactly {{question, reason}}, got {sorted(row)}"
            )
        if row["reason"] not in REFUSAL_REASONS:
            raise MeasurementError(
                f"{path}:{i}: reason {row['reason']!r} not one of {sorted(REFUSAL_REASONS)}"
            )


# --- calling the real api/ ---------------------------------------------------------------------


@dataclass
class CallBudget:
    """Wall-clock guard so a hung answer path cannot hang CI forever."""

    timeout_s: float = 120.0
    executor: concurrent.futures.ThreadPoolExecutor = field(
        default_factory=lambda: concurrent.futures.ThreadPoolExecutor(max_workers=1)
    )

    def call(self, fn, **kwargs):
        if self.timeout_s <= 0:
            return fn(**kwargs)
        future = self.executor.submit(fn, **kwargs)
        try:
            return future.result(timeout=self.timeout_s)
        except concurrent.futures.TimeoutError as exc:
            raise MeasurementError(
                f"call exceeded {self.timeout_s:g}s and was abandoned: {kwargs.get('question')!r}"
            ) from exc


# --- evaluation --------------------------------------------------------------------------------


@dataclass
class GoldenResult:
    subject: str
    question: str
    chapter_no: int
    expected_sections: list[str]
    expected_pages: list[int]
    ranked_sections: list[str | None]
    ranked_pages: list[tuple[int | None, int | None]]
    rank: int | None
    hit1: bool
    hit4: bool
    rr: float
    page4: bool
    page_start4: bool
    citation_sections: list[str | None] | None = None
    cite_hit: bool | None = None
    refused: bool | None = None
    refusal_reason: str | None = None
    provider: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "question": self.question,
            "chapter_no": self.chapter_no,
            "expected_sections": self.expected_sections,
            "expected_pages": self.expected_pages,
            "ranked_sections": self.ranked_sections,
            "ranked_pages": [list(p) for p in self.ranked_pages],
            "rank_of_first_hit": self.rank,
            "hit@1": self.hit1,
            "hit@4": self.hit4,
            "reciprocal_rank": self.rr,
            "page@4": self.page4,
            "page_start@4": self.page_start4,
            "citation_sections": self.citation_sections,
            "cite_hit": self.cite_hit,
            "refused": self.refused,
            "refusal_reason": self.refusal_reason,
            "provider": self.provider,
        }


@dataclass
class RefusalResult:
    question: str
    reason: str
    refused_by_scope: dict[str, bool | None]
    refusal_reason_by_scope: dict[str, str | None] = field(default_factory=dict)

    def _vacuous(self, scope: str) -> bool:
        """Refused because the subject has no corpus at all — not evidence of good judgement."""
        return self.refused_by_scope.get(scope) is True and (
            self.refusal_reason_by_scope.get(scope) == "no_corpus"
        )

    @property
    def measurable_scopes(self) -> list[str]:
        return [
            scope
            for scope in self.refused_by_scope
            if not self._vacuous(scope) and self.refused_by_scope[scope] is not None
        ]

    @property
    def refused_everywhere(self) -> bool:
        """Correct only when every scope that could actually answer refused to."""
        scopes = self.measurable_scopes
        return bool(scopes) and all(self.refused_by_scope[scope] is True for scope in scopes)

    @property
    def vacuous_scopes(self) -> list[str]:
        return [scope for scope in self.refused_by_scope if self._vacuous(scope)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "reason": self.reason,
            "refused_by_scope": self.refused_by_scope,
            "refusal_reason_by_scope": self.refusal_reason_by_scope,
            "vacuous_scopes": self.vacuous_scopes,
            "measurable_scopes": self.measurable_scopes,
            "refused_everywhere": self.refused_everywhere,
        }


@functools.lru_cache(maxsize=1)
def section_spans(path: Path = SYLLABUS_PATH) -> dict[tuple[str, int, str], tuple[int, int]]:
    """``(subject, chapter_no, section_no) -> (first_page, last_page)`` from the syllabus.

    A section runs from its own start page to the page before the next section starts; the last
    section of a chapter runs to the chapter's final page. These are the chapter-relative page
    numbers the syllabus and the chunk records both use.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    spans: dict[tuple[str, int, str], tuple[int, int]] = {}
    for subject in data["subjects"]:
        for chapter in subject["chapters"]:
            sections = sorted(
                [s for s in chapter.get("sections", []) if s.get("page") is not None],
                key=lambda s: (int(s["page"]), str(s.get("no"))),
            )
            last_page = int(chapter.get("pages") or 0)
            for i, section in enumerate(sections):
                start = int(section["page"])
                end = int(sections[i + 1]["page"]) - 1 if i + 1 < len(sections) else last_page
                spans[(subject["id"], int(chapter["no"]), str(section["no"]))] = (
                    start,
                    max(end, start),
                )
    return spans


def _search(**kwargs: Any) -> list[dict[str, Any]]:
    """adapter.search, with any non-adapter failure reported as 'cannot measure', not as a score."""
    try:
        return adapter.search(**kwargs)
    except adapter.AdapterError:
        raise
    except Exception as exc:  # noqa: BLE001 - the message is the measurement's only evidence
        raise MeasurementError(
            f"retriever failed on {kwargs.get('question')!r}: {type(exc).__name__}: {exc}"
        ) from exc


def _answer(**kwargs: Any) -> dict[str, Any]:
    try:
        return adapter.answer(**kwargs)
    except adapter.AdapterError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise MeasurementError(
            f"answer path failed on {kwargs.get('question')!r}: {type(exc).__name__}: {exc}"
        ) from exc


def evaluate_golden(
    subject: str,
    rows: list[dict[str, Any]],
    *,
    top_k: int,
    scope: str,
    with_answer: bool,
    budget: CallBudget,
    verbose: bool = False,
    limit: int | None = None,
) -> list[GoldenResult]:
    results: list[GoldenResult] = []
    for i, row in enumerate(rows, start=1):
        if limit is not None and i > limit:
            break
        chapter_no = row["chapter_no"] if scope == "chapter" else None
        hits = _search(
            question=row["question"],
            subject=row["subject"],
            chapter_no=chapter_no,
            top_k=top_k,
        )
        if not hits:
            raise MeasurementError(
                f"{subject}: retriever returned nothing for {row['question']!r} — "
                "is the corpus ingested? (corpus/chunks/*.jsonl, ingest + DB)"
            )
        expected_sections = [str(s) for s in row["expected_sections"]]
        expected_pages = [int(p) for p in row["expected_pages"]]
        spans = section_spans()
        expected_spans = [
            spans.get((subject, row["chapter_no"], section), (page, page))
            for section, page in zip(expected_sections, expected_pages, strict=True)
        ]
        rank = rank_of_first_hit(hits, expected_sections)

        result = GoldenResult(
            subject=subject,
            question=row["question"],
            chapter_no=row["chapter_no"],
            expected_sections=expected_sections,
            expected_pages=expected_pages,
            ranked_sections=[h.get("section_no") for h in hits],
            ranked_pages=[(h.get("page_start"), h.get("page_end")) for h in hits],
            rank=rank,
            hit1=hit_at_k(hits, expected_sections, k=1),
            hit4=hit_at_k(hits, expected_sections, k=4),
            rr=reciprocal_rank(hits, expected_sections),
            page4=page_overlap_hit(hits, expected_spans, k=4),
            page_start4=page_hit(hits, expected_pages, k=4),
        )

        if with_answer:
            payload = budget.call(
                _answer,
                question=row["question"],
                subject=row["subject"],
                chapter_no=chapter_no,
                top_k=top_k,
            )
            if payload["refused"] is None:
                raise MeasurementError(
                    f"{subject}: answer path returned no `refused` flag for {row['question']!r} "
                    f"(keys seen: {payload['keys']}) — the answer contract is not satisfied"
                )
            citation_sections = [c.get("section_no") for c in payload["citations"]]
            result.citation_sections = citation_sections
            result.cite_hit = any(
                str(s) in expected_sections for s in citation_sections if s is not None
            )
            result.refused = payload["refused"]
            result.refusal_reason = payload["refusal_reason"]
            result.provider = payload["provider"]

        results.append(result)
        if verbose:
            mark = "HIT " if result.hit4 else "MISS"
            print(
                f"    {mark} rank={result.rank} expected={expected_sections} "
                f"got={result.ranked_sections[:4]} pages={result.ranked_pages[:4]} "
                f"page@4={result.page4} pgstart={result.page_start4} "
                f"cite={result.cite_hit} refused={result.refused}"
            )
            print(f"         {row['question']}")
    return results


def evaluate_refusals(
    rows: list[dict[str, Any]],
    *,
    subjects: list[str],
    top_k: int,
    budget: CallBudget,
    verbose: bool = False,
) -> list[RefusalResult]:
    results: list[RefusalResult] = []
    for row in rows:
        by_scope: dict[str, bool | None] = {}
        reason_by_scope: dict[str, str | None] = {}
        for subject in subjects:
            payload = budget.call(
                _answer,
                question=row["question"],
                subject=subject,
                chapter_no=None,
                top_k=top_k,
            )
            by_scope[subject] = payload["refused"]
            reason_by_scope[subject] = payload["refusal_reason"]
        result = RefusalResult(row["question"], row["reason"], by_scope, reason_by_scope)
        results.append(result)
        if verbose:
            print(f"    refused={by_scope} reasons={reason_by_scope} {row['question']!r}")
    return results


def _subject_summary(results: list[GoldenResult]) -> dict[str, Any]:
    with_answer = [r for r in results if r.cite_hit is not None]
    return {
        "n": len(results),
        "hit@1": accuracy(r.hit1 for r in results),
        "hit@4": accuracy(r.hit4 for r in results),
        "mrr": mean(r.rr for r in results),
        "page@4": accuracy(r.page4 for r in results),
        "page_start@4": accuracy(r.page_start4 for r in results),
        "cite_hit": accuracy(bool(r.cite_hit) for r in with_answer) if with_answer else None,
        "accepted": (accuracy(r.refused is False for r in with_answer) if with_answer else None),
        "items": [r.to_dict() for r in results],
    }


def thresholds_from_args(args: argparse.Namespace) -> dict[str, float]:
    """The thresholds this run enforces, in the same key space as the measured values."""
    thresholds = {
        "section hit@4": args.min_hit4,
        "MRR": args.min_mrr,
        "page@4": args.min_page_hit,
    }
    if not args.skip_answer:
        thresholds["citation hit"] = args.min_cite_hit
        thresholds["golden acceptance"] = args.min_golden_acceptance
        thresholds["refusal accuracy"] = args.min_refusal_accuracy
    return thresholds


def threshold_checks(measured: dict[str, float | None], thresholds: dict[str, float]) -> dict[str, bool]:
    """Compare measured values against thresholds. A missing measurement is a failure, never a pass.

    `measured` is typed to allow None because a metric that could not be measured is exactly the
    case this function exists to catch — an unmeasured subject must not read as a pass.
    """
    checks: dict[str, bool] = {}
    for name, threshold in thresholds.items():
        value = measured.get(name)
        checks[name] = value is not None and value >= threshold
    return checks


def parse_subjects(value: str) -> list[str]:
    """`all`, `science,maths`, or `science maths` — the spellings a caller will actually try.

    An unknown subject is a clear one-line error rather than an argparse usage wall, because the
    obvious way to ask for two subjects (`--subjects science,maths`) used to be rejected by
    `choices=` and left the whole gate unmeasured.
    """
    if value.strip().lower() == "all":
        return list(GOLDEN_FILES)
    requested = [s for s in re.split(r"[,\s]+", value.strip()) if s]
    if not requested:
        raise SystemExit("--subjects was empty; pass 'all' or e.g. 'science,maths'")
    unknown = [s for s in requested if s not in GOLDEN_FILES]
    if unknown:
        raise SystemExit(
            f"unknown subject(s) {unknown}; known subjects are {sorted(GOLDEN_FILES)} (or 'all')"
        )
    return requested


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    """Run the whole harness and return a JSON-serialisable report."""
    budget = CallBudget(timeout_s=args.answer_timeout)
    subjects = parse_subjects(args.subjects)
    golden: dict[str, list[GoldenResult]] = {}
    with_answer = not args.skip_answer

    for subject in subjects:
        path = GOLDEN_FILES[subject]
        rows = load_jsonl(path)
        validate_golden(rows, path)
        if args.verbose:
            print(f"\n[{subject}] {path.name}: {len(rows)} questions, scope={args.scope}")
        golden[subject] = evaluate_golden(
            subject,
            rows,
            top_k=args.top_k,
            scope=args.scope,
            with_answer=with_answer,
            budget=budget,
            verbose=args.verbose,
            limit=args.limit,
        )

    all_items = [item for items in golden.values() for item in items]
    per_subject = {subject: _subject_summary(items) for subject, items in golden.items()}
    overall = _subject_summary(all_items)

    refusals: list[RefusalResult] = []
    refusal_subjects = [s.strip() for s in args.refusal_subjects.split(",") if s.strip()]
    if with_answer:
        refusal_rows = load_jsonl(REFUSALS_PATH)
        validate_refusals(refusal_rows, REFUSALS_PATH)
        if args.verbose:
            print(
                f"\n[refusals] {REFUSALS_PATH.name}: {len(refusal_rows)} questions, "
                f"scopes={refusal_subjects}"
            )
        refusals = evaluate_refusals(
            refusal_rows,
            subjects=refusal_subjects,
            top_k=args.top_k,
            budget=budget,
            verbose=args.verbose,
        )

    refusal_block: dict[str, Any] | None = None
    if with_answer:
        unknown = [r for r in refusals if any(v is None for v in r.refused_by_scope.values())]
        if unknown:
            raise MeasurementError(
                "answer path returned no `refused` flag for "
                f"{len(unknown)} refusal question(s), e.g. {unknown[0].question!r}"
            )
        judged = [r for r in refusals if r.measurable_scopes]
        refusal_block = {
            "n": len(refusals),
            "scopes": refusal_subjects,
            "judged": len(judged),
            "accuracy": accuracy(r.refused_everywhere for r in judged) if judged else None,
            "per_scope": {
                scope: (
                    accuracy(
                        r.refused_by_scope.get(scope) is True
                        for r in refusals
                        if scope in r.measurable_scopes
                    )
                    if any(scope in r.measurable_scopes for r in refusals)
                    else None
                )
                for scope in refusal_subjects
            },
            "vacuous_refusals_per_scope": {
                scope: sum(1 for r in refusals if scope in r.vacuous_scopes)
                for scope in refusal_subjects
            },
            "unjudged": [r.question for r in refusals if not r.measurable_scopes],
            "by_reason": {
                reason: accuracy(r.refused_everywhere for r in judged if r.reason == reason)
                for reason in sorted({r.reason for r in refusals})
            },
            "items": [r.to_dict() for r in refusals],
        }

    measured = {
        "section hit@4": overall["hit@4"],
        "MRR": overall["mrr"],
        "page@4": overall["page@4"],
    }
    if with_answer:
        measured["citation hit"] = overall["cite_hit"]
        measured["golden acceptance"] = overall["accepted"]
        measured["refusal accuracy"] = refusal_block["accuracy"] if refusal_block else None

    thresholds = thresholds_from_args(args)
    checks = threshold_checks(measured, thresholds)

    report = {
        "scope": args.scope,
        "top_k": args.top_k,
        "with_answer": with_answer,
        "providers_seen": sorted({r.provider for r in all_items if r.provider}),
        "per_subject": per_subject,
        "overall": overall,
        "refusals": refusal_block,
        "measured": measured,
        "thresholds": thresholds,
        "checks": checks,
        "passed": all(checks.values()),
    }
    return report


# --- presentation ------------------------------------------------------------------------------


def _fmt(value: float | None, digits: int = 3) -> str:
    return "  n/a" if value is None else f"{value:.{digits}f}"


def print_report(report: dict[str, Any], *, verbose: bool = False) -> None:
    print("")
    print("samjho eval gate")
    print(f"  retriever : {report['retriever']}")
    print(f"  answer    : {report['answer']}")
    print(f"  provider  : {', '.join(report['providers_seen']) or 'not recorded'}")
    print(
        f"  scope     : {report['scope']}   top_k: {report['top_k']}   "
        f"hit@4 measured on the first 4 of the returned list"
    )
    print("")
    header = (
        f"{'subject':<10}{'n':>4}{'hit@1':>8}{'hit@4':>8}{'MRR':>8}"
        f"{'page@4':>8}{'pgstart':>9}{'cite_hit':>10}{'accepted':>10}"
    )
    print(header)
    print("-" * len(header))
    for subject in ("science", "maths"):
        if subject not in report["per_subject"]:
            continue
        s = report["per_subject"][subject]
        print(
            f"{subject:<10}{s['n']:>4}{_fmt(s['hit@1']):>8}{_fmt(s['hit@4']):>8}{_fmt(s['mrr']):>8}"
            f"{_fmt(s['page@4']):>8}{_fmt(s['page_start@4']):>9}{_fmt(s['cite_hit']):>10}"
            f"{_fmt(s['accepted']):>10}"
        )
    o = report["overall"]
    print(
        f"{'ALL':<10}{o['n']:>4}{_fmt(o['hit@1']):>8}{_fmt(o['hit@4']):>8}{_fmt(o['mrr']):>8}"
        f"{_fmt(o['page@4']):>8}{_fmt(o['page_start@4']):>9}{_fmt(o['cite_hit']):>10}"
        f"{_fmt(o['accepted']):>10}"
    )
    print(
        "  page@4 = citation overlaps the expected section's pages (gated); "
        "pgstart = citation covers the page the golden line names (diagnostic)"
    )

    refusals = report["refusals"]
    print("")
    if refusals is None:
        print("refusals: NOT MEASURED (--skip-answer)")
    else:
        print(
            f"refusals: {refusals['n']} questions x {len(refusals['scopes'])} scope(s) "
            f"{refusals['scopes']} — judged {refusals['judged']}, refused everywhere it could "
            f"answer: {_fmt(refusals['accuracy'])}"
        )
        for scope, value in refusals["per_scope"].items():
            vacuous = refusals["vacuous_refusals_per_scope"][scope]
            note = f"  ({vacuous} vacuous: that subject has no corpus)" if vacuous else ""
            print(f"          refused with subject={scope:<8}: {_fmt(value)}{note}")
        for reason, value in refusals["by_reason"].items():
            print(f"          {reason:<20}: {_fmt(value)}")
        if refusals["unjudged"]:
            print(
                f"          unjudged (no corpus in any scope): {len(refusals['unjudged'])} question(s)"
            )
        missed = [
            r for r in refusals["items"] if r["measurable_scopes"] and not r["refused_everywhere"]
        ]
        if missed:
            print("          answered instead of refused:")
            for item in missed:
                print(
                    f"            - {item['question']!r} ({item['reason']}) "
                    f"refused={item['refused_by_scope']} reason={item['refusal_reason_by_scope']}"
                )

    print("")
    print(f"{'metric':<20}{'measured':>10}{'threshold':>12}   result")
    print("-" * 54)
    for name, value in report["measured"].items():
        verdict = "PASS" if report["checks"][name] else "FAIL"
        print(f"{name:<20}{_fmt(value):>10}{_fmt(report['thresholds'][name]):>12}   {verdict}")
    print("")
    print("GATE PASSED" if report["passed"] else "GATE FAILED")


def _adapter_signatures() -> tuple[str, str]:
    retriever = answer_path = "api/ not importable"
    try:
        retriever = adapter.describe("api.retriever", adapter.SEARCH_ATTRS)
    except adapter.AdapterError as exc:
        retriever = f"unavailable: {exc}"
    try:
        answer_path = adapter.describe("api.answer", adapter.ANSWER_ATTRS)
    except adapter.AdapterError as exc:
        answer_path = f"unavailable: {exc}"
    return retriever, answer_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals.run_eval",
        description="Measure samjho's retrieval and refusal quality against the golden sets and "
        "fail when a threshold is not met.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--subjects",
        default="all",
        help="comma- or space-separated subject ids (e.g. 'science,maths' or 'science maths'), "
        "or 'all'",
    )
    parser.add_argument("--top-k", type=int, default=6, help="retrieved list length")
    parser.add_argument(
        "--scope",
        choices=["chapter", "subject"],
        default="chapter",
        help="retrieval scope: 'chapter' matches what POST /ask does, 'subject' searches the whole subject",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="only the first N questions per subject"
    )
    parser.add_argument(
        "--skip-answer",
        action="store_true",
        help="retrieval metrics only; refusal and acceptance are not measured",
    )
    parser.add_argument(
        "--refusal-subjects",
        default="science,maths",
        help="comma-separated subjects a refusal question must be refused under",
    )
    parser.add_argument(
        "--answer-timeout",
        type=float,
        default=120.0,
        help="seconds allowed per answer call (0 disables the guard)",
    )
    parser.add_argument("--min-hit4", type=float, default=DEFAULT_MIN_HIT4)
    parser.add_argument("--min-mrr", type=float, default=DEFAULT_MIN_MRR)
    parser.add_argument("--min-page-hit", type=float, default=DEFAULT_MIN_PAGE_HIT)
    parser.add_argument("--min-cite-hit", type=float, default=DEFAULT_MIN_CITE_HIT)
    parser.add_argument(
        "--min-golden-acceptance", type=float, default=DEFAULT_MIN_GOLDEN_ACCEPTANCE
    )
    parser.add_argument("--min-refusal-accuracy", type=float, default=DEFAULT_MIN_REFUSAL_ACCURACY)
    parser.add_argument("--emit-json", type=Path, default=None, help="write the full report here")
    parser.add_argument("-v", "--verbose", action="store_true", help="per-question detail")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    retriever_sig, answer_sig = _adapter_signatures()
    try:
        report = evaluate(args)
    except adapter.AdapterError as exc:
        print(f"CANNOT MEASURE — api/ is not usable: {exc}", file=sys.stderr)
        return 2
    except MeasurementError as exc:
        print(f"CANNOT MEASURE — {exc}", file=sys.stderr)
        return 2
    except Exception:  # noqa: BLE001 - report, never swallow
        print("CANNOT MEASURE — unexpected failure while running the harness:", file=sys.stderr)
        traceback.print_exc()
        return 2

    report["retriever"] = retriever_sig
    report["answer"] = answer_sig
    print_report(report, verbose=args.verbose)
    if args.emit_json is not None:
        args.emit_json.parent.mkdir(parents=True, exist_ok=True)
        args.emit_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"report written to {args.emit_json}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
