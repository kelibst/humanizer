"""Tests for the protected-spans builder."""
from __future__ import annotations

from sis_caro_humanizer.pipeline.stage3_deterministic.protected import (
    build_protected_spans,
    is_protected,
    overlaps_protected,
)


def _covers(spans, fragment, text) -> bool:
    """True if the spans collectively cover the (first) occurrence of `fragment`."""
    idx = text.find(fragment)
    assert idx >= 0, f"fixture: fragment {fragment!r} not in text"
    return all(is_protected(idx + i, spans) for i in range(len(fragment)))


def test_fenced_code_block() -> None:
    text = (
        "Some prose before.\n\n"
        "```python\n"
        "x = 1 + 2  # delve into multifaceted things\n"
        "print(x)\n"
        "```\n\n"
        "Some prose after."
    )
    spans = build_protected_spans(text)
    # The "delve" inside the code block must be protected.
    assert _covers(spans, "delve into multifaceted", text)


def test_inline_code() -> None:
    text = "Use `delve` to traverse — it works."
    spans = build_protected_spans(text)
    assert _covers(spans, "`delve`", text)


def test_ascii_double_quote() -> None:
    text = 'She said "this is intricate and multifaceted" plainly.'
    spans = build_protected_spans(text)
    assert _covers(spans, '"this is intricate and multifaceted"', text)


def test_curly_double_quote() -> None:
    text = "She said “this is intricate and multifaceted” plainly."
    spans = build_protected_spans(text)
    assert _covers(spans, "“this is intricate and multifaceted”", text)


def test_curly_single_quote() -> None:
    text = "He noted ‘the data show clearly’ in his report."
    spans = build_protected_spans(text)
    assert _covers(spans, "‘the data show clearly’", text)


def test_apa_citation_paren() -> None:
    text = "Prior work (Smith, 2020) found that bystanders hesitated."
    spans = build_protected_spans(text)
    assert _covers(spans, "(Smith, 2020)", text)


def test_apa_etal_citation() -> None:
    text = "Recent work (Smith et al., 2023) confirmed it."
    spans = build_protected_spans(text)
    assert _covers(spans, "(Smith et al., 2023)", text)


def test_markdown_table_row() -> None:
    text = (
        "Body text.\n\n"
        "| Col A | Col B |\n"
        "| --- | --- |\n"
        "| delve | multifaceted |\n\n"
        "More body."
    )
    spans = build_protected_spans(text)
    assert _covers(spans, "| delve | multifaceted |", text)


def test_block_quote() -> None:
    text = "Body.\n\n> This delves into multifaceted concerns.\n\nAfter."
    spans = build_protected_spans(text)
    assert _covers(spans, "> This delves into multifaceted concerns.", text)


def test_references_section() -> None:
    text = (
        "Body of paper.\n\n"
        "## References\n\n"
        "Smith, J. (2020). On delving. Journal.\n"
        "Doe, A. (2021). Multifaceted things. Press.\n"
    )
    spans = build_protected_spans(text)
    assert _covers(spans, "Smith, J. (2020). On delving. Journal.", text)
    assert _covers(spans, "Multifaceted things. Press.", text)


def test_inline_math() -> None:
    text = "The model $\\alpha = 1$ delves into x."
    spans = build_protected_spans(text)
    assert _covers(spans, "$\\alpha = 1$", text)


def test_spans_are_sorted_and_merged() -> None:
    text = '"a delve" `b multifaceted` (Smith, 2020)'
    spans = build_protected_spans(text)
    assert spans == sorted(spans)
    # No overlap.
    for (s1, e1), (s2, _e2) in zip(spans, spans[1:]):
        assert e1 <= s2


def test_overlaps_protected() -> None:
    text = 'before "quoted text here" after'
    spans = build_protected_spans(text)
    q_start = text.index('"')
    q_end = text.index('"', q_start + 1) + 1
    assert overlaps_protected(q_start + 1, q_start + 5, spans)
    # Region entirely outside the quote.
    assert not overlaps_protected(0, 5, spans)


def test_is_protected_outside_returns_false() -> None:
    text = "plain text with no protection at all"
    spans = build_protected_spans(text)
    assert spans == []
    assert not is_protected(5, spans)
