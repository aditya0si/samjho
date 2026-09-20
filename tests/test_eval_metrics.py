"""Unit tests for the eval metric functions — hand-computed expected values, no api/ needed.

The ranked list below is fixed, so every number asserted here can be worked out on paper:

    rank 1: section 9.1      rank 3: section 11.4
    rank 2: section 9.3      rank 4: section 2.2      rank 5: section 1.1
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals import adapter, run_eval  # noqa: E402
from evals.metrics import (  # noqa: E402
    accuracy,
    hit_at_k,
    mean,
    page_hit,
    page_overlap_hit,
    rank_of_first_hit,
    ranked_sections,
    reciprocal_rank,
)

RANKED = [
    {"section_no": "9.1", "page_start": 1, "page_end": 2},
    {"section_no": "9.3", "page_start": 12, "page_end": 14},
    {"section_no": "11.4", "page_start": 5, "page_end": 6},
    {"section_no": "2.2", "page_start": 2, "page_end": 4},
    {"section_no": "1.1", "page_start": 2, "page_end": 2},
]


@pytest.mark.unit
def test_ranked_sections_reads_dicts_and_objects():
    assert ranked_sections(RANKED) == ["9.1", "9.3", "11.4", "2.2", "1.1"]
    objects = [SimpleNamespace(section_no="9.1"), SimpleNamespace(section_no=11)]
    assert ranked_sections(objects) == ["9.1", "11"]


@pytest.mark.unit
def test_rank_of_first_hit_is_one_based():
    assert rank_of_first_hit(RANKED, ["9.1"]) == 1
    assert rank_of_first_hit(RANKED, ["11.4"]) == 3
    assert rank_of_first_hit(RANKED, ["1.1"]) == 5
    assert rank_of_first_hit(RANKED, ["9.2"]) is None


@pytest.mark.unit
def test_section_matching_is_exact_not_prefix():
    # "9.1" must not satisfy a question that asked for "9.1.1" and vice versa
    assert rank_of_first_hit(RANKED, ["9.1.1"]) is None
    assert rank_of_first_hit([{"section_no": "9.1.1"}], ["9.1"]) is None
    assert rank_of_first_hit([{"section_no": "9.1.1"}], ["9.1.1"]) == 1


@pytest.mark.unit
def test_hit_at_k_boundary():
    assert hit_at_k(RANKED, ["11.4"], k=4) is True
    assert hit_at_k(RANKED, ["11.4"], k=2) is False
    assert hit_at_k(RANKED, ["2.2"], k=4) is True
    assert hit_at_k(RANKED, ["1.1"], k=4) is False
    assert hit_at_k(RANKED, ["1.1"], k=5) is True


@pytest.mark.unit
def test_reciprocal_rank_values():
    assert reciprocal_rank(RANKED, ["9.1"]) == pytest.approx(1.0)
    assert reciprocal_rank(RANKED, ["9.3"]) == pytest.approx(0.5)
    assert reciprocal_rank(RANKED, ["11.4"]) == pytest.approx(1 / 3)
    assert reciprocal_rank(RANKED, ["1.1"]) == pytest.approx(0.2)
    assert reciprocal_rank(RANKED, ["12.1"]) == 0.0


@pytest.mark.unit
def test_mean_mrr_over_a_fixed_list_is_hand_computable():
    # (1/3 + 1/5 + 1/1) / 3 = (0.3333 + 0.2 + 1.0) / 3
    value = mean(reciprocal_rank(RANKED, [expected]) for expected in ("11.4", "1.1", "9.1"))
    assert value == pytest.approx((1 / 3 + 0.2 + 1.0) / 3)
    assert value == pytest.approx(0.511111, abs=1e-5)


@pytest.mark.unit
def test_hit4_accuracy_over_the_same_list_is_hand_computable():
    flags = [hit_at_k(RANKED, [expected], k=4) for expected in ("11.4", "1.1", "9.1")]
    assert flags == [True, False, True]
    assert accuracy(flags) == pytest.approx(2 / 3)


@pytest.mark.unit
def test_expected_sections_accept_any_of_the_listed_sections():
    assert hit_at_k(RANKED, ["9.2.1", "9.2.2", "9.1"], k=4) is True
    assert hit_at_k(RANKED, ["9.2.1", "9.2.2"], k=4) is False


@pytest.mark.unit
def test_page_hit_uses_the_citation_page_range():
    assert page_hit(RANKED, [12], k=4) is True  # inside 9.3's 12-14
    assert page_hit(RANKED, [11], k=4) is False  # 9.3 starts at 12, 9.1 covers 1-2
    assert page_hit(RANKED, [1], k=1) is True
    assert page_hit(RANKED, [5], k=2) is False  # 11.4 is at rank 3
    assert page_hit(RANKED, [5], k=4) is True


@pytest.mark.unit
def test_page_hit_with_only_a_start_page_or_reversed_range():
    assert page_hit([{"page_start": 7}], [7]) is True
    assert page_hit([{"page_start": 7}], [8]) is False
    assert page_hit([{"page_start": 9, "page_end": 4}], [6]) is True  # reversed range still counts


@pytest.mark.unit
def test_section_hit_and_page_hit_are_independent():
    # right page, wrong section: page@4 passes, hit@4 fails
    chunk = [{"section_no": "9.2", "page_start": 1, "page_end": 3}]
    assert page_hit(chunk, [2]) is True
    assert hit_at_k(chunk, ["9.1"], k=4) is False


@pytest.mark.unit
def test_page_overlap_hit_accepts_a_citation_inside_the_sections_pages():
    """A section that spans pages 8-9 is satisfied by a chunk from either page."""
    chunk_p8 = [{"section_no": "1.2.2", "page_start": 8, "page_end": 8}]
    chunk_p9 = [{"section_no": "1.2.2", "page_start": 9, "page_end": 9}]
    chunk_8_9 = [{"section_no": "1.2.2", "page_start": 8, "page_end": 9}]
    for chunk in (chunk_p8, chunk_p9, chunk_8_9):
        assert page_overlap_hit(chunk, [(8, 9)]) is True
    assert (
        page_overlap_hit([{"section_no": "1.2.3", "page_start": 10, "page_end": 10}], [(8, 9)])
        is False
    )
    assert page_overlap_hit([{"page_start": 3, "page_end": 4}], [(8, 9)]) is False
    # k still applies: the correct chunk at rank 5 does not count at k=4
    ranked = [{"page_start": 1, "page_end": 1}] * 4 + [{"page_start": 8, "page_end": 8}]
    assert page_overlap_hit(ranked, [(8, 9)], k=4) is False
    assert page_overlap_hit(ranked, [(8, 9)], k=5) is True
    with pytest.raises(ValueError):
        page_overlap_hit(ranked, [], k=4)


@pytest.mark.unit
def test_section_spans_come_from_the_syllabus():
    spans = run_eval.section_spans()
    assert spans[("science", 1, "1.2.2")] == (8, 9)  # next section starts on page 10
    assert spans[("science", 1, "1.3.2")] == (13, 16)  # last section runs to the chapter's end
    assert spans[("maths", 1, "1.3")] == (6, 8)
    assert spans[("maths", 1, "1.4")] == (9, 9)


@pytest.mark.unit
def test_metric_guards_reject_impossible_arguments():
    with pytest.raises(ValueError):
        hit_at_k(RANKED, ["9.1"], k=0)
    with pytest.raises(ValueError):
        reciprocal_rank(RANKED, [])
    with pytest.raises(ValueError):
        page_hit(RANKED, [], k=4)
    assert mean([]) == 0.0
    assert accuracy([]) == 0.0


# --- adapter: normalisation and signature binding (no api/ import required) ---------------------


@pytest.mark.unit
def test_normalize_hits_accepts_the_shapes_the_api_might_return():
    flat = [{"section_no": "1.1", "page_start": 2, "page_end": 3}]
    assert adapter.normalize_hits(flat) == flat
    assert adapter.normalize_hits({"results": flat}) == flat
    assert adapter.normalize_hits({"chunks": flat}) == flat
    assert adapter.normalize_hits((flat, {"took_ms": 5})) == flat
    nested = adapter.normalize_hits([{"chunk": {"section_no": "1.1"}, "score": 0.8}])
    assert nested == [{"section_no": "1.1", "score": 0.8}]
    assert adapter.normalize_hits(None) == []


@pytest.mark.unit
def test_normalize_answer_flags_and_citations():
    payload = adapter.normalize_answer(
        {
            "answer": "prose",
            "refused": False,
            "citations": [{"section_no": "1.2", "page_start": 6, "page_end": 7}],
            "provider": "retrieval-only",
        }
    )
    assert payload["refused"] is False
    assert payload["citations"][0]["section_no"] == "1.2"
    assert payload["provider"] == "retrieval-only"
    assert (
        adapter.normalize_answer({"refused": True, "refusal_reason": "not_in_corpus"})[
            "refusal_reason"
        ]
        == "not_in_corpus"
    )
    assert adapter.normalize_answer({"refused": "true"})["refused"] is True
    # no refusal flag at all must surface as None (unknown), never as False
    assert adapter.normalize_answer({"answer": "prose"})["refused"] is None


@pytest.mark.unit
def test_normalize_answer_rejects_non_mappings():
    with pytest.raises(adapter.AdapterError):
        adapter.normalize_answer("just a string")


@pytest.mark.unit
def test_bind_maps_logical_values_onto_declared_parameter_names():
    def search(query, subject=None, chapter_no=None, top_k=6):
        return None

    positional, kwargs = adapter._bind(
        search,
        {"question": "q", "subject": "science", "chapter_no": 3, "top_k": 4},
    )
    assert positional == []
    assert kwargs == {"query": "q", "subject": "science", "chapter_no": 3, "top_k": 4}


@pytest.mark.unit
def test_bind_omits_values_the_function_does_not_want():
    def answer(question, subject, chapter_no=None):
        return None

    _, kwargs = adapter._bind(
        answer,
        {"question": "q", "subject": "science", "chapter_no": None, "top_k": 6},
    )
    assert kwargs == {"question": "q", "subject": "science"}  # chapter_no None -> default kept


@pytest.mark.unit
def test_bind_refuses_to_guess_an_unknown_required_parameter():
    def search(question, conn):  # `conn` is required and unknown to the harness
        return None

    with pytest.raises(adapter.AdapterError) as excinfo:
        adapter._bind(search, {"question": "q", "subject": "s", "chapter_no": 1, "top_k": 6})
    assert "conn" in str(excinfo.value)


@pytest.mark.unit
def test_missing_api_module_is_a_loud_adapter_error():
    with pytest.raises(adapter.AdapterError):
        adapter.describe("api.definitely_not_a_module", "search")
