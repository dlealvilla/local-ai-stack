"""StateRootBinder (MACHI 1.2.1)."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pytest

from machi.adapters.journal.jsonl import JsonlJournal
from machi.install.binder import StateRootBinder
from machi.install.contracts import SelectionSource, StateRootBinding
from machi.install.defaults import (
    KULTRUN_OWNER_FILENAME,
    KULTRUN_SYSTEM_ROOT,
    STATE_ROOT_VARIABLE,
    journal_dir,
    platform_default_state_root,
)
from machi.install.events import (
    STATE_ROOT_BOUND_TYPE,
    StateRootBoundPayload,
    root_fingerprint,
    state_root_bound,
)
from machi.kernel.clock import FixedClock
from machi.kernel.errors import PersistenceError, ValidationError
from machi.kernel.events import EventOutcome
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import to_dict, unresolved_fields
from machi.main import bind_state_root, main

FIXED = dt.datetime(2026, 9, 14, 22, 0, tzinfo=dt.UTC)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(FIXED)


@pytest.fixture
def binder(tmp_path: Path, clock: FixedClock) -> StateRootBinder:
    return StateRootBinder(clock=clock, default_root=tmp_path / "default-machi")


def test_explicit_path_creates_a_directory(
    binder: StateRootBinder, tmp_path: Path
) -> None:
    root = tmp_path / "explicit"
    binding = binder.bind(explicit=root)
    assert binding.root == str(root.resolve())
    assert binding.selection_source is SelectionSource.EXPLICIT
    assert binding.existed is False
    assert binding.created is True
    assert binding.bound_at == FIXED
    assert root.is_dir()
    assert not (root / "models").exists()
    assert not (root / ".machi-owner.json").exists()


def test_environment_override_beats_default(
    binder: StateRootBinder, tmp_path: Path
) -> None:
    root = tmp_path / "from-env"
    binding = binder.bind(environment=str(root))
    assert Path(binding.root) == root.resolve()
    assert binding.selection_source is SelectionSource.ENVIRONMENT
    assert root.is_dir()


def test_blank_environment_is_not_configuration(
    binder: StateRootBinder, tmp_path: Path
) -> None:
    binding = binder.bind(environment="   ")
    assert binding.selection_source is SelectionSource.PLATFORM_DEFAULT
    assert Path(binding.root) == (tmp_path / "default-machi").resolve()


def test_explicit_wins_over_environment(
    binder: StateRootBinder, tmp_path: Path
) -> None:
    explicit = tmp_path / "explicit-wins"
    ignored = tmp_path / "env-ignored"
    binding = binder.bind(explicit=explicit, environment=str(ignored))
    assert Path(binding.root) == explicit.resolve()
    assert binding.selection_source is SelectionSource.EXPLICIT
    assert explicit.is_dir()
    assert not ignored.exists()


def test_binder_does_not_read_os_environ(
    binder: StateRootBinder, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trap = tmp_path / "trap"
    monkeypatch.setenv(STATE_ROOT_VARIABLE, str(trap))
    monkeypatch.setenv("KULTRUN_STATE_ROOT", str(tmp_path / "kultrun-trap"))
    binding = binder.bind(explicit=None, environment=None)
    assert Path(binding.root) == (tmp_path / "default-machi").resolve()
    assert not trap.exists()


def test_platform_default_is_user_local_and_absolute() -> None:
    default = platform_default_state_root()
    assert default.is_absolute()
    assert default.name == "machi"
    assert default.parent.name == "state"
    assert default != KULTRUN_SYSTEM_ROOT
    assert default.name != ".state"


def test_relative_input_is_resolved_once_against_cwd(
    binder: StateRootBinder, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    original = Path.cwd()
    try:
        os.chdir(tmp_path)
        first = binder.bind(explicit=Path("relative-root"))
        os.chdir(elsewhere)
        second = binder.bind(explicit=Path(first.root))
    finally:
        os.chdir(original)
    expected = (tmp_path / "relative-root").resolve()
    assert Path(first.root) == Path(second.root) == expected
    assert first.root.startswith("/")
    assert not (elsewhere / "relative-root").exists()


def test_tilde_is_expanded(
    binder: StateRootBinder, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    binding = binder.bind(explicit="~/machi-state")
    assert Path(binding.root) == (tmp_path / "machi-state").resolve()


def test_symlink_resolves_to_the_real_directory(
    binder: StateRootBinder, tmp_path: Path
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    binding = binder.bind(explicit=link)
    assert Path(binding.root) == real.resolve()
    assert binding.existed is True
    assert binding.created is False


def test_cli_platform_default_uses_injected_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    default = tmp_path / "xdg-machi"
    monkeypatch.setattr(
        "machi.install.binder.platform_default_state_root",
        lambda: default,
    )
    monkeypatch.delenv(STATE_ROOT_VARIABLE, raising=False)
    assert main(["install", "bind-root"]) == 0
    out = capsys.readouterr().out
    assert '"selection_source": "platform_default"' in out
    assert default.is_dir()


def test_redundant_separators_and_dot_segments_collapse(
    binder: StateRootBinder, tmp_path: Path
) -> None:
    nested = tmp_path / "a" / "b"
    binding = binder.bind(explicit=str(tmp_path / "a" / "." / "b" / ".." / "b"))
    assert Path(binding.root) == nested.resolve()


def test_file_at_path_is_refused(binder: StateRootBinder, tmp_path: Path) -> None:
    target = tmp_path / "not-a-dir"
    target.write_text("nope", encoding="utf-8")
    with pytest.raises(ValidationError, match="not a directory"):
        binder.bind(explicit=target)


def test_unwritable_existing_directory_fails(
    binder: StateRootBinder, tmp_path: Path
) -> None:
    root = tmp_path / "locked"
    root.mkdir()
    root.chmod(0o555)
    try:
        with pytest.raises(PersistenceError, match="not writable"):
            binder.bind(explicit=root)
    finally:
        root.chmod(0o755)


def test_creation_fails_when_parent_is_a_file(
    binder: StateRootBinder, tmp_path: Path
) -> None:
    parent = tmp_path / "file-parent"
    parent.write_text("nope", encoding="utf-8")
    with pytest.raises(PersistenceError, match="failed to create"):
        binder.bind(explicit=parent / "child")


def test_empty_explicit_path_is_refused(binder: StateRootBinder) -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        binder.bind(explicit="  ")


def test_filesystem_root_is_refused(binder: StateRootBinder) -> None:
    with pytest.raises(ValidationError, match="filesystem root"):
        binder.bind(explicit="/")


def test_kultrun_system_root_is_refused(binder: StateRootBinder) -> None:
    with pytest.raises(ValidationError, match="Kultrun"):
        binder.bind(explicit=KULTRUN_SYSTEM_ROOT)


def test_existing_kultrun_owner_marker_is_refused(
    binder: StateRootBinder, tmp_path: Path
) -> None:
    root = tmp_path / "legacy"
    root.mkdir()
    (root / KULTRUN_OWNER_FILENAME).write_text("{}", encoding="utf-8")
    with pytest.raises(ValidationError, match="Kultrun"):
        binder.bind(explicit=root)


def test_same_root_reentry_does_not_recreate(
    binder: StateRootBinder, tmp_path: Path
) -> None:
    root = tmp_path / "once"
    first = binder.bind(explicit=root)
    marker = root / "operator-note.txt"
    marker.write_text("keep", encoding="utf-8")
    second = binder.bind(explicit=root)
    assert first.created is True
    assert first.existed is False
    assert second.existed is True
    assert second.created is False
    assert Path(first.root) == Path(second.root)
    assert marker.read_text(encoding="utf-8") == "keep"
    assert {path.name for path in root.iterdir()} == {"operator-note.txt"}


def test_two_roots_are_isolated(binder: StateRootBinder, tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    bind_a = binder.bind(explicit=root_a)
    bind_b = binder.bind(explicit=root_b)
    (root_a / "only-a").write_text("a", encoding="utf-8")
    (root_b / "only-b").write_text("b", encoding="utf-8")
    assert Path(bind_a.root) != Path(bind_b.root)
    assert (root_a / "only-a").is_file()
    assert not (root_b / "only-a").exists()
    assert (root_b / "only-b").is_file()
    assert not (root_a / "only-b").exists()
    assert not (root_a / ".machi-owner.json").exists()
    assert not (root_b / ".machi-owner.json").exists()


def test_bind_event_is_restricted_and_omits_the_path(
    binder: StateRootBinder, tmp_path: Path, clock: FixedClock
) -> None:
    root = tmp_path / "private-org-name" / "project"
    binding = binder.bind(explicit=root)
    event = state_root_bound(binding, clock=clock)
    assert event.event_type.value == STATE_ROOT_BOUND_TYPE
    assert event.block_id.value == "1"
    assert event.component_id.value == "1.2.1"
    assert event.outcome is EventOutcome.PASS
    assert event.privacy is PrivacyClass.RESTRICTED
    assert isinstance(event.payload, StateRootBoundPayload)
    document = json.dumps(to_dict(event))
    assert binding.root not in document
    assert "private-org-name" not in document
    assert event.payload.root_fingerprint == root_fingerprint(binding.root)
    assert "install_run_id" in unresolved_fields(event)
    assert "install_id" in unresolved_fields(event)
    assert "host_id" in unresolved_fields(event)


def test_two_root_journals_do_not_share_events(
    tmp_path: Path, clock: FixedClock
) -> None:
    binder = StateRootBinder(clock=clock, default_root=tmp_path / "unused")
    root_a = tmp_path / "iso-a"
    root_b = tmp_path / "iso-b"
    bind_a = binder.bind(explicit=root_a)
    bind_b = binder.bind(explicit=root_b)
    journal_a = JsonlJournal(journal_dir(Path(bind_a.root)), clock=clock)
    journal_b = JsonlJournal(journal_dir(Path(bind_b.root)), clock=clock)
    journal_a.append(state_root_bound(bind_a, clock=clock))
    clock.advance(1)
    journal_b.append(state_root_bound(bind_b, clock=clock))
    records_a = journal_a.records()
    records_b = journal_b.records()
    assert len(records_a) == 1
    assert len(records_b) == 1
    payload_a = records_a[0].payload
    payload_b = records_b[0].payload
    assert isinstance(payload_a, StateRootBoundPayload)
    assert isinstance(payload_b, StateRootBoundPayload)
    assert payload_a.root_fingerprint != payload_b.root_fingerprint
    assert payload_a.root_fingerprint == root_fingerprint(bind_a.root)
    assert not journal_a.path.exists() or journal_a.path != journal_b.path
    assert bind_a.root not in json.dumps(to_dict(records_a[0]))
    assert bind_b.root not in json.dumps(to_dict(records_b[0]))


def test_cli_explicit_bind_then_kernel_regression(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "cli-root"
    assert main(["install", "bind-root", "--state-root", str(root)]) == 0
    first = capsys.readouterr()
    assert "install.state_root.bound" in first.out
    assert '"privacy": "restricted"' in first.out
    assert '"selection_source": "explicit"' in first.out
    assert root.is_dir()
    journal = journal_dir(root)
    assert main(["kernel", "prove", "--journal-dir", str(journal)]) == 0
    capsys.readouterr()
    assert main(["kernel", "events", "--journal-dir", str(journal)]) == 0
    listed = capsys.readouterr().out
    assert "records  2" in listed
    assert listed.count('"event_type": "kernel.alive"') == 1
    assert listed.count('"event_type": "install.state_root.bound"') == 1
    assert '"privacy": "public_ops"' in listed
    assert '"privacy": "restricted"' in listed


def test_cli_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "env-root"
    monkeypatch.setenv(STATE_ROOT_VARIABLE, str(root))
    monkeypatch.delenv("KULTRUN_STATE_ROOT", raising=False)
    assert main(["install", "bind-root"]) == 0
    out = capsys.readouterr().out
    assert '"selection_source": "environment"' in out
    assert root.is_dir()


def test_cli_explicit_wins_over_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    explicit = tmp_path / "cli-explicit"
    env_root = tmp_path / "cli-env"
    monkeypatch.setenv(STATE_ROOT_VARIABLE, str(env_root))
    assert main(["install", "bind-root", "--state-root", str(explicit)]) == 0
    out = capsys.readouterr().out
    assert '"selection_source": "explicit"' in out
    assert explicit.is_dir()
    assert not env_root.exists()


def test_cli_same_root_reentry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "reenter"
    assert main(["install", "bind-root", "--state-root", str(root)]) == 0
    capsys.readouterr()
    assert main(["install", "bind-root", "--state-root", str(root)]) == 0
    out = capsys.readouterr().out
    assert '"existed": true' in out
    assert '"created": false' in out
    lines = (
        (journal_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(lines) == 2


def test_cli_file_at_path_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "file"
    target.write_text("nope", encoding="utf-8")
    assert main(["install", "bind-root", "--state-root", str(target)]) == 2
    err = capsys.readouterr().err
    assert "not a directory" in err


def test_composition_bind_returns_contract_and_event(tmp_path: Path) -> None:
    root = tmp_path / "composed"
    binding, event, target = bind_state_root(
        explicit=str(root),
        environment=None,
        journal_dir_path=None,
    )
    assert isinstance(binding, StateRootBinding)
    assert target == journal_dir(root)
    assert event.privacy is PrivacyClass.RESTRICTED
    records, defects = JsonlJournal(target).records(), JsonlJournal(target).defects()
    assert len(records) == 1
    assert defects == ()
    assert records[0].event_id == event.event_id
