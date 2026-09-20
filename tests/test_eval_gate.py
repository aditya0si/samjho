"""The eval gate: measure the real retriever and answer path, and fail when a threshold is not met.

Marked ``eval`` (see pyproject.toml): these tests need a corpus ingested into Postgres and ``api/``
importable. Nothing here is skipped or xfailed — a gate that quietly passes when the corpus is
absent is worse than no gate.

Shape of the suite, deliberately:

* one session-scoped measurement per book (models load once per process, not once per test);
* a subject whose corpus is missing produces **one** failing test
  (``test_every_golden_subject_has_an_ingested_corpus``) naming the blocker, instead of a cascade of
  fifteen red assertions that hide which book is blocked;
* every threshold is asserted for every book that *is* measurable, and the same test starts
  asserting a book's numbers the moment its corpus lands — so a blocked book cannot quietly shrink
  the gate;
* the two golden questions the answer path currently refuses are kept in the set and asserted to be
  answerable: a study companion that refuses a covered question is broken, and the suite says so.

``python -m evals.run_eval`` is the CLI equivalent of the same code path, so the CI number and the
local number cannot drift apart.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals import run_eval  # noqa: E402

pytestmark = pytest.mark.eval

GOLDEN_SUBJECTS = ("science", "maths")
GOLDEN_COUNTS = {"science": 20, "maths": 15}

COMMITTED = {
    "section hit@4": run_eval.DEFAULT_MIN_HIT4,
    "MRR": run_eval.DEFAULT_MIN_MRR,
    "page@4": run_eval.DEFAULT_MIN_PAGE_HIT,
    "citation hit": run_eval.DEFAULT_MIN_CITE_HIT,
    "golden acceptance": run_eval.DEFAULT_MIN_GOLDEN_ACCEPTANCE,
    "refusal accuracy": run_eval.DEFAULT_MIN_REFUSAL_ACCURACY,
}

FLAGS = {
    "section hit@4": "--min-hit4",
    "MRR": "--min-mrr",
    "page@4": "--min-page-hit",
    "citation hit": "--min-cite-hit",
    "golden acceptance": "--min-golden-acceptance",
    "refusal accuracy": "--min-refusal-accuracy",
}


@pytest.fixture(scope="session")
def measurements() -> dict[str, dict]:
    """{subject: {"report": …}} or {subject: {"error": …}} — measured once per book per session."""
    out: dict[str, dict] = {}
    for subject in GOLDEN_SUBJECTS:
        args = run_eval.build_parser().parse_args(["--subjects", subject])
        try:
            out[subject] = {"report": run_eval.evaluate(args)}
        except (run_eval.MeasurementError, run_eval.adapter.AdapterError) as exc:
            out[subject] = {"error": str(exc)}
    return out


def _measurable(measurements: dict[str, dict]) -> dict[str, dict]:
    return {
        subject: entry["report"] for subject, entry in measurements.items() if "report" in entry
    }


def test_every_golden_subject_has_an_ingested_corpus(measurements: dict[str, dict]) -> None:
    """The one failure a blocked book is allowed to produce, and it names the blocker."""
    blocked = {
        subject: entry["error"] for subject, entry in measurements.items() if "error" in entry
    }
    assert not blocked, (
        "the eval gate is BLOCKED on ingestion for these subjects — ingest the book "
        f"(python -m api.db init && python -m api.db load corpus/chunks/<subject>.jsonl) and re-run: "
        f"{blocked}"
    )


def test_measured_reports_cover_the_whole_path(measurements: dict[str, dict]) -> None:
    for subject, report in _measurable(measurements).items():
        assert report["with_answer"] is True, f"{subject}: the gate ran in retrieval-only mode"
        assert report["refusals"] is not None, f"{subject}: refusals were not measured"
        assert report["overall"]["n"] == GOLDEN_COUNTS[subject]


@pytest.mark.parametrize("metric", sorted(COMMITTED))
def test_metric_meets_its_committed_threshold(measurements: dict[str, dict], metric: str) -> None:
    reports = _measurable(measurements)
    assert (
        reports
    ), "no subject was measurable — see test_every_golden_subject_has_an_ingested_corpus"
    for subject, report in reports.items():
        value = report["measured"].get(metric)
        assert value is not None, f"{subject}: {metric} was not measured"
        assert value >= COMMITTED[metric], (
            f"{subject}: {metric} = {value:.3f} is below the committed threshold "
            f"{COMMITTED[metric]:.3f} (all measured values: {report['measured']})"
        )


def test_gate_passes_with_the_committed_defaults(measurements: dict[str, dict]) -> None:
    for subject, report in _measurable(measurements).items():
        assert report["passed"] is True, f"{subject}: failing checks {report['checks']}"


def test_no_golden_question_is_falsely_refused(measurements: dict[str, dict]) -> None:
    """Stricter than the measured floor on purpose: a covered question must never be refused."""
    for subject, report in _measurable(measurements).items():
        refused = [
            (i["question"], i["refusal_reason"])
            for i in report["overall"]["items"]
            if i["refused"] is True
        ]
        assert (
            not refused
        ), f"{subject}: the answer path refused golden questions the book covers: {refused}"


def test_refusal_set_is_never_answered(measurements: dict[str, dict]) -> None:
    for subject, report in _measurable(measurements).items():
        answered = [
            (i["question"], i["refused_by_scope"])
            for i in report["refusals"]["items"]
            if not i["refused_everywhere"]
        ]
        assert not answered, f"{subject}: out-of-corpus questions that were answered: {answered}"


@pytest.mark.parametrize("metric", sorted(COMMITTED))
def test_raising_a_threshold_makes_the_same_measurement_fail(
    measurements: dict[str, dict], metric: str
) -> None:
    """The gate must be able to fail: push each threshold just past what was measured."""
    reports = _measurable(measurements)
    assert (
        reports
    ), "no subject was measurable — see test_every_golden_subject_has_an_ingested_corpus"
    for subject, report in reports.items():
        values = report["measured"]
        inflated = values[metric] + 0.01
        args = run_eval.build_parser().parse_args(
            ["--subjects", subject, FLAGS[metric], f"{inflated:.6f}"]
        )
        checks = run_eval.threshold_checks(values, run_eval.thresholds_from_args(args))
        assert checks[metric] is False, (
            f"{subject}: {FLAGS[metric]} = {inflated:.4f} should fail against the measured "
            f"{values[metric]:.4f}"
        )
        assert not all(
            checks.values()
        ), f"{subject}: the gate stayed green with {FLAGS[metric]} raised"


def test_missing_measurement_is_a_failure_not_a_pass() -> None:
    checks = run_eval.threshold_checks({"section hit@4": None}, {"section hit@4": 0.5})
    assert checks["section hit@4"] is False


def test_the_cli_exits_non_zero_when_a_threshold_cannot_be_met() -> None:
    """End-to-end proof on the real retriever: an impossible threshold exits 1, not 0 or 2."""
    code = run_eval.main(
        ["--subjects", "science", "--limit", "3", "--skip-answer", "--min-hit4", "1.01"]
    )
    assert code == 1, f"expected exit 1 (threshold failed), got {code}"


def test_the_cli_exits_zero_on_a_small_slice_it_should_pass() -> None:
    """The same slice with a threshold it can meet must exit 0 — otherwise the exit 1 above proves nothing."""
    code = run_eval.main(
        ["--subjects", "science", "--limit", "3", "--skip-answer", "--min-hit4", "0.0"]
    )
    assert code == 0, f"expected exit 0, got {code}"
