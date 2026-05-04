"""``Input`` subclass that releases the tab-shortcut digits ``1``..``5``.

Textual's ``Input.check_consume_key`` claims every printable character, which
means an App-level priority binding for ``1`` (jump to Profiles tab) is
filtered out of the binding chain whenever an Input is focused. Overriding
``check_consume_key`` here keeps every other character routed to the Input
(typing still works) while letting the digits ``1``..``5`` and ``?`` rise
back up to the App for shortcut handling.
"""
from __future__ import annotations

from textual.widgets import Input

# Keys that should be reclaimed by the App for tab navigation / help.
_RELEASED_CHARACTERS: frozenset[str] = frozenset({"1", "2", "3", "4", "5", "?"})


class TabAwareInput(Input):
    """Input that lets a small set of shortcut keys pass to App bindings."""

    def check_consume_key(self, key: str, character: str | None) -> bool:  # type: ignore[override]
        if character in _RELEASED_CHARACTERS:
            return False
        return super().check_consume_key(key, character)


__all__ = ["TabAwareInput"]
