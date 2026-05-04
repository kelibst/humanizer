"""Strategically placed grammar slips ("bluppers").

Each blupper is gated by an independent Bernoulli trial whose probability
comes from `profile.blupper_probabilities`. Implemented:

    - data_singular_verb : `data show/are/were` → singular form
    - less_for_fewer     : `fewer Xs` → `less Xs`
    - which_for_that     : restrictive `that` → `which`
    - comma_splice_rate  : join two short adjacent independent clauses
                            (already split by `. `) with `, `
    - start_with_and_but : prepend `And` or `But` to a paragraph-internal
                            sentence
    - oxford_comma_rate  : flip a fraction of `X, Y, and Z` toward / away
                            from the target rate

`tense_shift_past_present` is intentionally NOT implemented; the heuristic is
brittle (per AGENT_A_BRIEF). We log nothing for it and document the no-op.

All transforms respect `protected` spans and never touch a span that
overlaps a citation, code fence, quote, etc.
"""
from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING

from .protected import is_protected, overlaps_protected

if TYPE_CHECKING:
    from ...profile.schema import Profile


# ---------------------------------------------------------------------------
# data → singular verb
# ---------------------------------------------------------------------------

_DATA_VERBS = {
    "show": "shows",
    "are": "is",
    "were": "was",
    "indicate": "indicates",
    "suggest": "suggests",
    "demonstrate": "demonstrates",
}
_DATA_RE = re.compile(
    r"\b(?P<lead>[Dd]ata)\s+(?P<verb>show|are|were|indicate|suggest|demonstrate)\b"
)


def _data_singular(text: str, rng: random.Random, protected, prob: float):
    from .runner import TransformLog

    logs: list[TransformLog] = []
    new_text = text
    for m in reversed(list(_DATA_RE.finditer(text))):
        if overlaps_protected(m.start(), m.end(), protected):
            continue
        if rng.random() > prob:
            continue
        verb = m.group("verb").lower()
        replacement_verb = _DATA_VERBS[verb]
        original_verb = m.group("verb")
        # Preserve case.
        if original_verb[:1].isupper():
            replacement_verb = replacement_verb[:1].upper() + replacement_verb[1:]
        before = m.group(0)
        after = f"{m.group('lead')} {replacement_verb}"
        new_text = new_text[: m.start()] + after + new_text[m.end():]
        logs.append(
            TransformLog(
                transform="blupper.data_singular_verb",
                site=(m.start(), m.end()),
                before=before,
                after=after,
                reason="treated 'data' as singular noun",
            )
        )
    logs.reverse()
    return new_text, logs


# ---------------------------------------------------------------------------
# fewer → less
# ---------------------------------------------------------------------------

_FEWER_RE = re.compile(r"\b(?P<lead>[Ff]ewer)\s+(?P<noun>\w+s)\b")


def _less_for_fewer(text: str, rng: random.Random, protected, prob: float):
    from .runner import TransformLog

    logs: list[TransformLog] = []
    new_text = text
    for m in reversed(list(_FEWER_RE.finditer(text))):
        if overlaps_protected(m.start(), m.end(), protected):
            continue
        if rng.random() > prob:
            continue
        original = m.group("lead")
        replacement = "Less" if original[:1].isupper() else "less"
        before = m.group(0)
        after = f"{replacement} {m.group('noun')}"
        new_text = new_text[: m.start()] + after + new_text[m.end():]
        logs.append(
            TransformLog(
                transform="blupper.less_for_fewer",
                site=(m.start(), m.end()),
                before=before,
                after=after,
                reason="used 'less' instead of 'fewer'",
            )
        )
    logs.reverse()
    return new_text, logs


# ---------------------------------------------------------------------------
# restrictive that → which
# ---------------------------------------------------------------------------

# Heuristic: noun + space + 'that' + space + verb. Skip if preceded by `,`
# (already non-restrictive) or by a complementizer-licensing verb.
_THAT_RE = re.compile(
    r"(?P<noun>\b[A-Za-z][\w\-]+)\s+that\s+(?P<verb>[a-z][a-z\-]+)\b"
)
_COMPLEMENTIZER_VERBS = {
    "say", "says", "said",
    "think", "thinks", "thought",
    "believe", "believes", "believed",
    "know", "knows", "knew",
    "show", "shows", "showed",
    "suggest", "suggests", "suggested",
    "indicate", "indicates", "indicated",
    "argue", "argues", "argued",
    "claim", "claims", "claimed",
    "find", "finds", "found",
    "report", "reports", "reported",
    "feel", "feels", "felt",
    "hope", "hopes", "hoped",
    "mean", "means", "meant",
}

# Tokens that, when appearing immediately before ``that``, license a
# complementizer reading. ``that`` here is a clause introducer, not a
# relative pronoun, so flipping it to ``which`` produces ungrammatical
# output (``It is worth noting which the X...``). Includes verbs of
# saying/thinking/believing in all common inflections plus a small set of
# noun and adverb cues (``the fact that``, ``so X that``, ``such X that``).
SKIP_THAT_AFTER = {
    "noting", "note", "noted", "notes",
    "thinking", "think", "thought", "thinks",
    "saying", "said", "say", "says",
    "believing", "believe", "believed", "believes",
    "knowing", "know", "knew", "knows",
    "claiming", "claim", "claimed", "claims",
    "suggesting", "suggest", "suggested", "suggests",
    "showing", "show", "showed", "shown", "shows",
    "arguing", "argue", "argued", "argues",
    "assume", "assumed", "assumes", "assuming",
    "found", "find", "finds", "finding",
    "fact", "idea", "view", "evidence", "concern",
    "so", "such",
}


def _which_for_that(text: str, rng: random.Random, protected, prob: float):
    from .runner import TransformLog

    logs: list[TransformLog] = []
    new_text = text
    for m in reversed(list(_THAT_RE.finditer(text))):
        if overlaps_protected(m.start(), m.end(), protected):
            continue
        # Prior char must not be `,`.
        prev_char = text[m.start() - 1] if m.start() > 0 else ""
        if prev_char == ",":
            continue
        noun_lower = m.group("noun").lower()
        if noun_lower in _COMPLEMENTIZER_VERBS:
            continue
        # Wider skip set: complementizer-licensing verbs (all inflections),
        # noun cues like "the fact that", and degree adverbs "so"/"such".
        if noun_lower in SKIP_THAT_AFTER:
            continue
        if rng.random() > prob:
            continue
        # Replace just the literal word "that".
        # find its offset within the match.
        local = m.group(0)
        idx = local.index("that")
        absolute = m.start() + idx
        before = local
        after = local[:idx] + "which" + local[idx + 4:]
        new_text = new_text[: m.start()] + after + new_text[m.end():]
        logs.append(
            TransformLog(
                transform="blupper.which_for_that",
                site=(m.start(), m.end()),
                before=before,
                after=after,
                reason="restrictive 'that' replaced with 'which'",
            )
        )
        # absolute is referenced for site clarity but not used; keep a no-op
        # so flake doesn't warn (intentional no-op).
        _ = absolute
    logs.reverse()
    return new_text, logs


# ---------------------------------------------------------------------------
# Comma splice
# ---------------------------------------------------------------------------

# Look for `<short clause>. <short clause>` where both clauses have <= 9
# words and the second begins with a lowercase-friendly subject pronoun
# ("this", "they", "it", "we", "you", "he", "she").
_SPLICE_RE = re.compile(
    r"(?P<a>(?:[A-Z][^.!?\n]{1,80}))\.\s+"
    r"(?P<b>(?:This|They|It|We|You|He|She)\b[^.!?\n]{1,80}[.!?])"
)


def _word_count(s: str) -> int:
    return len(re.findall(r"\b[\w'\-]+\b", s))


def _comma_splice(text: str, rng: random.Random, protected, prob: float):
    from .runner import TransformLog

    logs: list[TransformLog] = []
    new_text = text
    for m in reversed(list(_SPLICE_RE.finditer(text))):
        if overlaps_protected(m.start(), m.end(), protected):
            continue
        a, b = m.group("a"), m.group("b")
        if _word_count(a) > 9 or _word_count(b) > 9:
            continue
        if rng.random() > prob:
            continue
        # Replace the `. ` between them with `, `, and lowercase the first
        # letter of `b`.
        b_fixed = b[:1].lower() + b[1:]
        replacement = f"{a}, {b_fixed}"
        before = m.group(0)
        new_text = new_text[: m.start()] + replacement + new_text[m.end():]
        logs.append(
            TransformLog(
                transform="blupper.comma_splice",
                site=(m.start(), m.end()),
                before=before,
                after=replacement,
                reason="joined two short clauses with comma splice",
            )
        )
    logs.reverse()
    return new_text, logs


# ---------------------------------------------------------------------------
# Start sentence with And / But
# ---------------------------------------------------------------------------

# A "paragraph-internal" sentence is one that begins after `. ` (or `! ` /
# `? `) within the same paragraph (no blank line). We only target sentences
# starting with a capitalized non-conjunction.
_SENT_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_AND_BUT_OPENERS = ("And", "But")


def _start_with_and_but(text: str, rng: random.Random, protected, prob: float):
    from .runner import TransformLog

    if prob <= 0:
        return text, []
    logs: list[TransformLog] = []
    # Split by paragraph so we don't touch the very first sentence.
    paras = text.split("\n\n")
    out_parts: list[str] = []
    cursor = 0  # offset of current paragraph start in text

    for pi, para in enumerate(paras):
        para_start = cursor
        # Walk sentence boundaries inside this paragraph.
        positions = [m.start() + 1 for m in _SENT_BOUNDARY.finditer(para)]
        # `+1` so we land at the first character after the whitespace? Use
        # m.end() instead.
        positions = [m.end() for m in _SENT_BOUNDARY.finditer(para)]
        # Filter out positions whose absolute index is in a protected span.
        new_para = para
        # Iterate right-to-left so offsets stay valid.
        for p in reversed(positions):
            abs_p = para_start + p
            if is_protected(abs_p, protected):
                continue
            # Word at this position must be a normal capitalized word, not
            # already And/But/etc.
            m = re.match(r"([A-Z][\w'\-]*)", new_para[p:])
            if not m:
                continue
            first = m.group(1)
            if first in _AND_BUT_OPENERS:
                continue
            # Skip if it's already a thinking-marker style opener.
            if first in {"Interestingly", "Of", "From", "What", "This", "Looking"}:
                continue
            if rng.random() > prob:
                continue
            opener = rng.choice(_AND_BUT_OPENERS)
            # Lowercase the original first letter for a natural "And the…" feel.
            lowered = first[:1].lower() + first[1:]
            new_para = (
                new_para[:p] + f"{opener} {lowered}" + new_para[p + len(first):]
            )
            logs.append(
                TransformLog(
                    transform="blupper.start_with_and_but",
                    site=(abs_p, abs_p + len(first)),
                    before=first,
                    after=f"{opener} {lowered}",
                    reason=f"prepended informal opener '{opener}'",
                )
            )
        out_parts.append(new_para)
        cursor += len(para) + 2  # account for the "\n\n" separator we split on

    new_text = "\n\n".join(out_parts)
    logs.reverse()
    return new_text, logs


# ---------------------------------------------------------------------------
# Oxford comma flip
# ---------------------------------------------------------------------------

# We re-use a triple-list pattern but explicitly capture the comma (or
# absence of one) before "and Z".
_OXFORD_HAS = re.compile(
    r"\b([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})"
    r",\s+"
    r"([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})"
    r",\s+and\s+"
    r"([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})\b"
)
_OXFORD_HASNT = re.compile(
    r"\b([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})"
    r",\s+"
    r"([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})"
    r"\s+and\s+"
    r"([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})\b"
)


def _oxford_flip(text: str, rng: random.Random, protected, target: float):
    """Move toward `target` rate of Oxford-comma usage.

    Estimate the current rate, then flip a fraction of qualifying sites in
    whichever direction the gap is.
    """
    from .runner import TransformLog

    has = list(_OXFORD_HAS.finditer(text))
    hasnt = list(_OXFORD_HASNT.finditer(text))
    # `has` is a strict subset relationship to `hasnt` only by accident; both
    # patterns can match overlapping ranges. We dedupe by start index.
    has_starts = {m.start() for m in has}
    hasnt = [m for m in hasnt if m.start() not in has_starts]
    total = len(has) + len(hasnt)
    if total == 0:
        return text, []
    current = len(has) / total
    diff = target - current
    if abs(diff) < 0.05:
        return text, []
    logs: list[TransformLog] = []
    new_text = text
    if diff > 0:
        # Need MORE oxford commas: convert a fraction of `hasnt` to `has`.
        n_to_flip = max(1, int(round(diff * total)))
        candidates = list(hasnt)
        rng.shuffle(candidates)
        flipped = 0
        for m in sorted(candidates[:n_to_flip], key=lambda x: x.start(), reverse=True):
            if overlaps_protected(m.start(), m.end(), protected):
                continue
            # Insert a comma before " and ".
            local = m.group(0)
            replaced = re.sub(r"\s+and\s+", ", and ", local, count=1)
            new_text = new_text[: m.start()] + replaced + new_text[m.end():]
            logs.append(
                TransformLog(
                    transform="blupper.oxford_comma_flip",
                    site=(m.start(), m.end()),
                    before=local,
                    after=replaced,
                    reason="added Oxford comma to move toward target rate",
                )
            )
            flipped += 1
    else:
        # Need FEWER oxford commas: convert a fraction of `has` to `hasnt`.
        n_to_flip = max(1, int(round(-diff * total)))
        candidates = list(has)
        rng.shuffle(candidates)
        for m in sorted(candidates[:n_to_flip], key=lambda x: x.start(), reverse=True):
            if overlaps_protected(m.start(), m.end(), protected):
                continue
            local = m.group(0)
            replaced = re.sub(r",\s+and\s+", " and ", local, count=1)
            new_text = new_text[: m.start()] + replaced + new_text[m.end():]
            logs.append(
                TransformLog(
                    transform="blupper.oxford_comma_flip",
                    site=(m.start(), m.end()),
                    before=local,
                    after=replaced,
                    reason="removed Oxford comma to move toward target rate",
                )
            )
    logs.reverse()
    return new_text, logs


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def apply(
    text: str,
    profile: "Profile",
    rng: random.Random,
    protected: list[tuple[int, int]],
) -> tuple[str, list]:
    bp = profile.blupper_probabilities
    all_logs: list = []

    # Each sub-step rebuilds protected from input internally? No: callers
    # pass `protected` for the snapshot. Sub-steps mutate text but offsets
    # within each helper are self-consistent because we apply right-to-left
    # before returning. Between helpers we re-derive `protected` to be safe.

    text, logs = _data_singular(text, rng, protected, bp.data_singular_verb)
    all_logs.extend(logs)
    if logs:
        from .protected import build_protected_spans
        protected = build_protected_spans(text)

    text, logs = _less_for_fewer(text, rng, protected, bp.less_for_fewer)
    all_logs.extend(logs)
    if logs:
        from .protected import build_protected_spans
        protected = build_protected_spans(text)

    text, logs = _which_for_that(text, rng, protected, bp.which_for_that)
    all_logs.extend(logs)
    if logs:
        from .protected import build_protected_spans
        protected = build_protected_spans(text)

    text, logs = _comma_splice(text, rng, protected, bp.comma_splice_rate)
    all_logs.extend(logs)
    if logs:
        from .protected import build_protected_spans
        protected = build_protected_spans(text)

    text, logs = _start_with_and_but(text, rng, protected, bp.start_with_and_but)
    all_logs.extend(logs)
    if logs:
        from .protected import build_protected_spans
        protected = build_protected_spans(text)

    text, logs = _oxford_flip(text, rng, protected, bp.oxford_comma_rate)
    all_logs.extend(logs)

    # tense_shift_past_present: deliberate no-op. Heuristic is too brittle.
    return text, all_logs


__all__ = ["apply"]
