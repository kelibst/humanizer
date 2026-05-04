"""Tab-cycling: ``1``..``5`` map to the five tabs in the right order.

Per ``plan/TUI_LAYOUT.md`` §1: ``1`` profiles · ``2`` check · ``3`` transform
· ``4`` grammar · ``5`` settings. The shortcuts must work even when an Input
on the destination screen has focus — that is what the
:class:`TabAwareInput` workaround in :mod:`tui.widgets` is for.
"""
from __future__ import annotations

import asyncio

from sis_caro_humanizer.tui.app import HumanizerApp


_EXPECTED_ORDER: tuple[tuple[str, str], ...] = (
    ("1", "ProfilesScreen"),
    ("2", "CheckScreen"),
    ("3", "TransformScreen"),
    ("4", "GrammarScreen"),
    ("5", "SettingsScreen"),
)


def _run(coro):
    return asyncio.run(coro)


def test_digits_cycle_through_tabs():
    async def go():
        app = HumanizerApp()
        observed: list[tuple[str, str]] = []
        async with app.run_test() as pilot:
            await pilot.pause()
            for key, expected in _EXPECTED_ORDER:
                await pilot.press(key)
                await pilot.pause()
                observed.append((key, type(app.screen).__name__))
        return observed

    observed = _run(go())
    assert observed == [(k, e) for k, e in _EXPECTED_ORDER], observed


def test_round_trip_back_and_forth():
    """Pressing the same digit twice still lands on the right screen."""

    async def go():
        app = HumanizerApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("3")  # transform
            await pilot.pause()
            await pilot.press("2")  # check
            await pilot.pause()
            await pilot.press("3")  # transform again — must work after focus moved into Input
            await pilot.pause()
            return type(app.screen).__name__

    assert _run(go()) == "TransformScreen"
