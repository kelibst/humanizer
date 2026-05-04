"""Output post-processing helpers shared by every adapter."""
from __future__ import annotations

import pytest

from sis_caro_humanizer.backends import clean_output, wrap_user_message


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Here is the rewritten text:\n\nHello.", "Hello."),
        ("Sure! Here you go:\n\nHello.", "Hello."),
        ("Certainly, here is the edited version: Hello.", "Hello."),
        ("Of course! Hello.", "Hello."),
        ("Okay, here is the rewrite:\n\nHello.", "Hello."),
        ("Hello.\n\nI hope this helps!", "Hello."),
        ("Hello.\n\nLet me know if you'd like changes.", "Hello."),
        ("```\nHello.\n```", "Hello."),
        ("```text\nHello.\n```", "Hello."),
        ("<text>Hello.</text>", "Hello."),
        ("Hello.", "Hello."),
        ("", ""),
    ],
)
def test_clean_output_strips_known_chatter(raw, expected):
    assert clean_output(raw) == expected


def test_wrap_user_message_uses_text_tags():
    out = wrap_user_message("hello")
    assert "<text>" in out
    assert "</text>" in out
    assert "hello" in out
