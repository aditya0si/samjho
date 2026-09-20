"""Signature-adaptive bridge from the eval harness to the frozen ``api/`` package.

The contract (docs/CONTRACTS.md §3) fixes the *HTTP* shapes; the Python signatures are the API
builder's to write. This adapter therefore binds logical values (question / subject / chapter_no /
top_k) onto whatever parameter names ``api.retriever.search`` and ``api.answer.answer`` actually
declare, and normalises whatever they return into plain dicts. It never guesses a value into a
parameter it does not recognise — an unknown required parameter raises :class:`AdapterError` with
the exact signature, so a mismatch is loud instead of silently scoring zero.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
from typing import Any

__all__ = [
    "AdapterError",
    "ANSWER_ATTRS",
    "SEARCH_ATTRS",
    "describe",
    "normalize_answer",
    "normalize_hits",
    "search",
    "answer",
]

# Entry points the harness will accept, in order. api/answer.py ships `answer_question`; `answer`
# is accepted too so the harness does not break if the API builder renames it back.
SEARCH_ATTRS: tuple[str, ...] = ("search", "retrieve", "search_detailed")
ANSWER_ATTRS: tuple[str, ...] = ("answer", "answer_question", "ask")


class AdapterError(RuntimeError):
    """The api/ package is missing, or its signature cannot be satisfied without guessing."""


# logical name -> parameter names accepted, best first
_ALIASES: dict[str, tuple[str, ...]] = {
    "question": ("question", "query", "q", "text", "prompt", "user_question"),
    "subject": ("subject", "subject_id", "subject_name"),
    "chapter_no": ("chapter_no", "chapter_number", "chapter_num", "chapter", "chapter_id"),
    "top_k": ("top_k", "k", "limit", "n", "num_results", "top_n"),
}

_HIT_FIELDS = (
    "id",
    "subject",
    "chapter_no",
    "chapter_title",
    "section_no",
    "section_title",
    "page_start",
    "page_end",
    "score",
    "text",
    "math_heavy",
)

_NESTED_KEYS = ("chunk", "document", "doc", "record", "row", "hit")

_LIST_KEYS = (
    "results",
    "chunks",
    "hits",
    "matches",
    "items",
    "documents",
    "data",
    "context",
)


def _logical_for(param_name: str) -> str | None:
    lowered = param_name.lower()
    for logical, names in _ALIASES.items():
        if lowered in names:
            return logical
    # Tolerate suffixed spellings such as question_text or chapter_no_filter, but only for
    # multi-character aliases: a loose match on "n" or "k" would happily claim "conn".
    for logical, names in _ALIASES.items():
        for name in names:
            if len(name) < 4:
                continue
            if lowered.startswith(name) or lowered.endswith(name):
                return logical
    return None


def _import_callable(module_name: str, attr: str | tuple[str, ...]) -> Any:
    candidates = (attr,) if isinstance(attr, str) else tuple(attr)
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 - the reason matters more than the type
        raise AdapterError(f"cannot import {module_name}: {type(exc).__name__}: {exc}") from exc
    for name in candidates:
        fn = getattr(module, name, None)
        if fn is None:
            continue
        if not callable(fn):
            raise AdapterError(f"{module_name}.{name} is not callable")
        return fn
    raise AdapterError(
        f"{module_name} has none of the expected entry points {list(candidates)} "
        f"(found: {sorted(a for a in dir(module) if not a.startswith('_'))[:20]}…)"
    )


def _bind(fn: Any, values: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    """Map logical values onto ``fn``'s parameters. Raises AdapterError when it cannot."""
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError) as exc:
        raise AdapterError(f"cannot inspect {fn!r}: {exc}") from exc

    positional: list[Any] = []
    kwargs: dict[str, Any] = {}
    unsatisfied: list[str] = []

    for name, param in signature.parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        logical = _logical_for(name)
        if logical is None:
            if param.default is param.empty:
                unsatisfied.append(name)
            continue
        value = values.get(logical)
        if value is None:
            if param.default is param.empty:
                unsatisfied.append(name)
            continue
        if param.kind is param.POSITIONAL_ONLY:
            positional.append(value)
        else:
            kwargs[name] = value

    if unsatisfied:
        raise AdapterError(
            f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__name__', fn)} requires parameters "
            f"the harness does not know how to supply: {unsatisfied}; signature is {signature}"
        )
    return positional, kwargs


def describe(module_name: str, attr: str | tuple[str, ...]) -> str:
    """Human-readable signature line for the run log, naming the entry point actually used."""
    fn = _import_callable(module_name, attr)
    name = getattr(fn, "__name__", "?")
    try:
        return f"{module_name}.{name}{inspect.signature(fn)}"
    except (TypeError, ValueError):
        return f"{module_name}.{name}(?)"


def _to_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    for attr in ("model_dump", "dict", "_asdict"):
        method = getattr(obj, attr, None)
        if callable(method):
            try:
                dumped = method()
            except TypeError:
                continue
            if isinstance(dumped, dict):
                return dict(dumped)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return {}


def _unwrap(item: Any) -> dict[str, Any]:
    """Flatten a scored-chunk wrapper like ``{"chunk": {...}, "score": 0.8}`` into one dict."""
    outer = _to_dict(item)
    if not outer:
        return {}
    for key in _NESTED_KEYS:
        inner = outer.get(key)
        if inner is None or isinstance(inner, str | int | float | bool):
            continue
        inner_dict = _to_dict(inner)
        if not inner_dict:
            continue
        outer_fields = {k: v for k, v in outer.items() if k != key and v is not None}
        merged = dict(inner_dict)
        merged.update(outer_fields)
        return merged
    return outer


def normalize_hits(result: Any) -> list[dict[str, Any]]:
    """Normalise a retriever/search return value into a ranked list of plain dicts."""
    items: list[Any]
    if result is None:
        return []
    if isinstance(result, dict) and any(k in result for k in _LIST_KEYS):
        for key in _LIST_KEYS:
            candidate = result.get(key)
            if isinstance(candidate, list | tuple):
                items = list(candidate)
                break
        else:  # pragma: no cover - defensive
            items = []
    elif isinstance(result, list | tuple):
        items = list(result)
        if items and isinstance(items[0], list | tuple):  # (hits, meta) style return
            items = list(items[0])
    else:
        items = [result]

    normalized = [_unwrap(item) for item in items]
    return [item for item in normalized if item]


def normalize_answer(result: Any) -> dict[str, Any]:
    """Normalise an answer-path return value.

    Returns ``{"refused": bool | None, "citations": [...], "refusal_reason": str | None,
    "provider": str | None, "keys": [...]}``. ``refused`` is ``None`` when the returned object
    carries no refusal flag at all — the runner treats that as a contract violation rather than
    assuming the question was answered.
    """
    payload = _to_dict(result)
    if not payload:
        raise AdapterError(f"answer path returned something that is not a mapping: {result!r}")

    refused = payload.get("refused")
    if refused is None:
        refused = payload.get("is_refused")
    if refused is None:
        refused = payload.get("refusal")
    if isinstance(refused, str):
        refused = refused.strip().lower() in {"true", "yes", "1"}

    citations = None
    for key in ("citations", "sources", "references", "used_chunks"):
        if key in payload:
            citations = payload[key]
            break

    reason = payload.get("refusal_reason")
    if reason is None:
        reason = payload.get("reason")

    return {
        "refused": None if refused is None else bool(refused),
        "citations": normalize_hits(citations),
        "refusal_reason": reason,
        "provider": payload.get("provider"),
        "keys": sorted(payload.keys()),
    }


def search(
    *,
    question: str,
    subject: str,
    chapter_no: int | None,
    top_k: int,
    module_name: str = "api.retriever",
    attr: str | tuple[str, ...] = SEARCH_ATTRS,
) -> list[dict[str, Any]]:
    """Call the retriever, adapting to its declared parameter names."""
    fn = _import_callable(module_name, attr)
    positional, kwargs = _bind(
        fn,
        {"question": question, "subject": subject, "chapter_no": chapter_no, "top_k": top_k},
    )
    return normalize_hits(fn(*positional, **kwargs))


def answer(
    *,
    question: str,
    subject: str,
    chapter_no: int | None,
    top_k: int,
    module_name: str = "api.answer",
    attr: str | tuple[str, ...] = ANSWER_ATTRS,
) -> dict[str, Any]:
    """Call the answer path, adapting to its declared parameter names."""
    fn = _import_callable(module_name, attr)
    positional, kwargs = _bind(
        fn,
        {"question": question, "subject": subject, "chapter_no": chapter_no, "top_k": top_k},
    )
    return normalize_answer(fn(*positional, **kwargs))
