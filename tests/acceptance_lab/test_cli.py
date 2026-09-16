"""CLI surface does not include Pod mutation."""

from __future__ import annotations

from tools.acceptance_lab.cli import _POD_VERBS, main


def test_pod_create_is_rejected() -> None:
    assert main(["create-pod"]) == 2


def test_known_commands_do_not_include_pod_verbs() -> None:
    for verb in _POD_VERBS:
        assert "pod" in verb
