"""Bounded command runner (MACHI Discover adapters)."""

from __future__ import annotations

import sys

from machi.adapters.discover.command import (
    MAX_COMMAND_OUTPUT_CHARS,
    run_command,
)


def test_oversized_stdout_fails_closed_without_retaining_payload() -> None:
    outcome = run_command(
        [sys.executable, "-c", f"print('x' * {MAX_COMMAND_OUTPUT_CHARS + 1})"],
        8.0,
    )
    assert outcome.found is True
    assert outcome.timed_out is False
    assert outcome.returncode == 1
    assert outcome.stdout == ""
    assert outcome.stderr == "command output exceeded the observation bound"


def test_normal_output_is_retained() -> None:
    outcome = run_command([sys.executable, "-c", "print('ok')"], 8.0)
    assert outcome.found is True
    assert outcome.returncode == 0
    assert "ok" in outcome.stdout
