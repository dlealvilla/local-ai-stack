"""CLI identity and kernel.alive proof."""

from __future__ import annotations

from pathlib import Path

import pytest

from machi.main import main


def test_version_identifies_machi(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("machi ")
    assert "origin" in out
    assert "kultrun" not in out.lower()


def test_kernel_prove_then_events_round_trip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = tmp_path / "journal"
    assert main(["kernel", "prove", "--journal-dir", str(journal)]) == 0
    first = capsys.readouterr().out
    assert "kernel.alive" in first
    assert "public_ops" in first
    assert '"distribution": "machi"' in first
    assert main(["kernel", "prove", "--journal-dir", str(journal)]) == 0
    capsys.readouterr()
    assert main(["kernel", "events", "--journal-dir", str(journal)]) == 0
    listed = capsys.readouterr().out
    assert "records  2" in listed
    assert listed.count('"event_type": "kernel.alive"') == 2
    assert (journal / "events.jsonl").is_file()


def test_prerequisites_observe_only_does_not_mutate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = tmp_path / "journal"
    assert (
        main(
            [
                "prerequisites",
                "check",
                "--policy",
                "observe_only",
                "--journal-dir",
                str(journal),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert '"kind": "prerequisite.readiness_report"' in out
    assert '"mutated": false' in out
    assert "observe_only" in out
    journal_text = (journal / "events.jsonl").read_text(encoding="utf-8")
    assert "prerequisite.inspected" in journal_text
    assert "prerequisite.remediation_started" not in journal_text


def test_missing_journal_dir_is_an_error() -> None:
    with pytest.raises(SystemExit):
        main(["kernel", "prove"])
