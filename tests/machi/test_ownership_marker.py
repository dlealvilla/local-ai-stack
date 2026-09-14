"""SelfOwnershipMarker (MACHI 1.3.1)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from machi.adapters.journal.jsonl import JsonlJournal
from machi.install.binder import StateRootBinder
from machi.install.contracts import (
    LocalOwnershipEstablishment,
    LocalOwnershipMarker,
    LocalOwnershipStatus,
    SelectionSource,
    StateRootBinding,
)
from machi.install.defaults import (
    KULTRUN_OWNER_FILENAME,
    MACHI_OWNER_FILENAME,
    journal_dir,
)
from machi.install.events import (
    LOCAL_MARKED_TYPE,
    LocalOwnershipMarkedPayload,
    local_ownership_marked,
    root_fingerprint,
)
from machi.install.marker import SelfOwnershipMarker
from machi.kernel.clock import FixedClock
from machi.kernel.errors import ConflictError, ValidationError
from machi.kernel.ids import LocalOwnershipId
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import from_dict, to_dict, unresolved_fields
from machi.main import main

FIXED = dt.datetime(2026, 9, 14, 23, 0, tzinfo=dt.UTC)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(FIXED)


@pytest.fixture
def binder(tmp_path: Path, clock: FixedClock) -> StateRootBinder:
    return StateRootBinder(clock=clock, default_root=tmp_path / "unused-default")


@pytest.fixture
def marker(clock: FixedClock) -> SelfOwnershipMarker:
    return SelfOwnershipMarker(clock=clock)


def _binding(
    root: Path,
    clock: FixedClock,
    *,
    created: bool,
    existed: bool,
) -> StateRootBinding:
    return StateRootBinding(
        root=str(Path(root).resolve()),
        selection_source=SelectionSource.EXPLICIT,
        existed=existed,
        created=created,
        bound_at=clock.now(),
    )


def test_new_machi_root_writes_a_local_marker(
    binder: StateRootBinder, marker: SelfOwnershipMarker, tmp_path: Path
) -> None:
    root = tmp_path / "fresh"
    binding = binder.bind(explicit=root)
    result = marker.establish(binding)
    dest = root / MACHI_OWNER_FILENAME
    assert dest.is_file()
    assert result.status is LocalOwnershipStatus.LOCAL_MARKER_PRESENT
    assert result.dual_ownership is False
    assert result.destructive_authorization is False
    assert result.created is True
    assert result.existed is False
    assert result.marker.product == "machi"
    assert result.marker.root_fingerprint == root_fingerprint(str(root.resolve()))
    assert result.marker.marker_id.value.startswith("lown_")
    document = json.loads(dest.read_text(encoding="utf-8"))
    assert str(root.resolve()) not in json.dumps(document)
    assert document["kind"] == "local_ownership_marker"


def test_reentry_preserves_marker_identity(
    binder: StateRootBinder, marker: SelfOwnershipMarker, tmp_path: Path
) -> None:
    root = tmp_path / "once"
    first = marker.establish(binder.bind(explicit=root))
    original = (root / MACHI_OWNER_FILENAME).read_text(encoding="utf-8")
    second = marker.establish(binder.bind(explicit=root))
    assert second.marker.marker_id == first.marker.marker_id
    assert second.marker.created_at == first.marker.created_at
    assert second.existed is True
    assert second.created is False
    assert (root / MACHI_OWNER_FILENAME).read_text(encoding="utf-8") == original


def test_two_roots_have_distinct_markers(
    binder: StateRootBinder, marker: SelfOwnershipMarker, tmp_path: Path
) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    mark_a = marker.establish(binder.bind(explicit=root_a))
    mark_b = marker.establish(binder.bind(explicit=root_b))
    assert mark_a.marker.marker_id != mark_b.marker.marker_id
    assert mark_a.marker.root_fingerprint != mark_b.marker.root_fingerprint
    assert (root_a / MACHI_OWNER_FILENAME).is_file()
    assert (root_b / MACHI_OWNER_FILENAME).is_file()
    assert not (root_a / "only-b").exists()
    (root_a / "only-a").write_text("a", encoding="utf-8")
    assert not (root_b / "only-a").exists()


def test_copied_marker_is_not_valid_on_another_root(
    binder: StateRootBinder, marker: SelfOwnershipMarker, tmp_path: Path
) -> None:
    root_a = tmp_path / "src"
    root_b = tmp_path / "dst"
    marker.establish(binder.bind(explicit=root_a))
    binding_b = binder.bind(explicit=root_b)
    copied = root_b / MACHI_OWNER_FILENAME
    copied.write_text((root_a / MACHI_OWNER_FILENAME).read_text(encoding="utf-8"))
    before = copied.read_text(encoding="utf-8")
    with pytest.raises(ConflictError, match="copied marker"):
        marker.establish(binding_b)
    assert copied.read_text(encoding="utf-8") == before


def test_unknown_preexisting_content_is_not_claimed(
    marker: SelfOwnershipMarker, tmp_path: Path, clock: FixedClock
) -> None:
    root = tmp_path / "customer"
    root.mkdir()
    (root / "notes.txt").write_text("customer", encoding="utf-8")
    with pytest.raises(ConflictError, match="unknown pre-existing"):
        marker.establish(_binding(root, clock, created=False, existed=True))
    assert not (root / MACHI_OWNER_FILENAME).exists()
    assert (root / "notes.txt").read_text(encoding="utf-8") == "customer"


def test_empty_existing_root_may_be_claimed(
    marker: SelfOwnershipMarker, tmp_path: Path, clock: FixedClock
) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    result = marker.establish(_binding(root, clock, created=False, existed=True))
    assert result.created is True
    assert (root / MACHI_OWNER_FILENAME).is_file()


def test_known_bootstrap_journal_may_be_claimed(
    binder: StateRootBinder, marker: SelfOwnershipMarker, tmp_path: Path
) -> None:
    root = tmp_path / "boot"
    binder.bind(explicit=root)
    JsonlJournal(journal_dir(root)).path.parent.mkdir(parents=True, exist_ok=True)
    (journal_dir(root) / "events.jsonl").write_text("", encoding="utf-8")
    reentry = binder.bind(explicit=root)
    assert reentry.created is False
    result = marker.establish(reentry)
    assert result.created is True
    assert result.destructive_authorization is False


def test_kultrun_marker_is_not_claimed_or_modified(
    marker: SelfOwnershipMarker, tmp_path: Path, clock: FixedClock
) -> None:
    root = tmp_path / "legacy"
    root.mkdir()
    kultrun = root / KULTRUN_OWNER_FILENAME
    kultrun.write_text('{"created_by":"kultrun"}\n', encoding="utf-8")
    with pytest.raises(ConflictError, match="Kultrun"):
        marker.establish(_binding(root, clock, created=True, existed=False))
    assert kultrun.read_text(encoding="utf-8") == '{"created_by":"kultrun"}\n'
    assert not (root / MACHI_OWNER_FILENAME).exists()


def test_malformed_marker_fails_closed_without_rewrite(
    binder: StateRootBinder, marker: SelfOwnershipMarker, tmp_path: Path
) -> None:
    root = tmp_path / "broken"
    binder.bind(explicit=root)
    dest = root / MACHI_OWNER_FILENAME
    dest.write_text("{not-json\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="malformed JSON"):
        marker.establish(binder.bind(explicit=root))
    assert dest.read_text(encoding="utf-8") == "{not-json\n"


def test_unsupported_schema_fails_closed(
    binder: StateRootBinder, marker: SelfOwnershipMarker, tmp_path: Path
) -> None:
    root = tmp_path / "future"
    binding = binder.bind(explicit=root)
    fingerprint = root_fingerprint(str(root.resolve()))
    dest = root / MACHI_OWNER_FILENAME
    dest.write_text(
        json.dumps(
            {
                "kind": "local_ownership_marker",
                "schema_version": 99,
                "marker_id": "lown_aaaaaaaaaaaaaaaa",
                "product": "machi",
                "root_fingerprint": fingerprint,
                "created_at": FIXED.isoformat().replace("+00:00", "Z"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    before = dest.read_text(encoding="utf-8")
    with pytest.raises(ValidationError, match="refusing to repair"):
        marker.establish(binding)
    assert dest.read_text(encoding="utf-8") == before


def test_wrong_product_fails_closed(
    binder: StateRootBinder, marker: SelfOwnershipMarker, tmp_path: Path
) -> None:
    root = tmp_path / "other"
    binding = binder.bind(explicit=root)
    dest = root / MACHI_OWNER_FILENAME
    dest.write_text(
        json.dumps(
            {
                "kind": "local_ownership_marker",
                "schema_version": 1,
                "marker_id": "lown_bbbbbbbbbbbbbbbb",
                "product": "kultrun",
                "root_fingerprint": root_fingerprint(str(root.resolve())),
                "created_at": FIXED.isoformat().replace("+00:00", "Z"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    before = dest.read_text(encoding="utf-8")
    with pytest.raises((ValidationError, ConflictError)):
        marker.establish(binding)
    assert dest.read_text(encoding="utf-8") == before


def test_event_is_restricted_omits_path_and_does_not_mint_install_ids(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    tmp_path: Path,
    clock: FixedClock,
) -> None:
    root = tmp_path / "private-org" / "proj"
    result = marker.establish(binder.bind(explicit=root))
    event = local_ownership_marked(result, clock=clock)
    assert event.event_type.value == LOCAL_MARKED_TYPE
    assert event.component_id.value == "1.3.1"
    assert event.privacy is PrivacyClass.RESTRICTED
    assert isinstance(event.payload, LocalOwnershipMarkedPayload)
    blob = json.dumps(to_dict(event))
    assert str(root.resolve()) not in blob
    assert "private-org" not in blob
    assert "install_run_id" in unresolved_fields(event)
    assert "install_id" in unresolved_fields(event)
    assert "host_id" in unresolved_fields(event)
    assert event.payload.destructive_authorization is False
    assert event.payload.dual_ownership is False


def test_establishment_cannot_claim_destructive_authority() -> None:
    with pytest.raises(ValidationError, match="must not authorize destruction"):
        LocalOwnershipEstablishment(
            marker=LocalOwnershipMarker(
                marker_id=LocalOwnershipId.generate(),
                product="machi",
                root_fingerprint="a" * 64,
                created_at=FIXED,
            ),
            status=LocalOwnershipStatus.LOCAL_MARKER_PRESENT,
            dual_ownership=False,
            destructive_authorization=True,
            existed=False,
            created=True,
        )


def test_establishment_cannot_claim_dual_ownership() -> None:
    with pytest.raises(ValidationError, match="must not claim dual ownership"):
        LocalOwnershipEstablishment(
            marker=LocalOwnershipMarker(
                marker_id=LocalOwnershipId.generate(),
                product="machi",
                root_fingerprint="a" * 64,
                created_at=FIXED,
            ),
            status=LocalOwnershipStatus.LOCAL_MARKER_PRESENT,
            dual_ownership=True,
            destructive_authorization=False,
            existed=False,
            created=True,
        )


def test_marker_contract_roundtrip(
    binder: StateRootBinder, marker: SelfOwnershipMarker, tmp_path: Path
) -> None:
    result = marker.establish(binder.bind(explicit=tmp_path / "round"))
    restored = from_dict(to_dict(result.marker))
    assert restored == result.marker
    establishment = from_dict(to_dict(result))
    assert establishment == result
    document = to_dict(result.marker)
    assert "install_id" not in document
    assert "install_run_id" not in document
    assert "host_id" not in document
    assert "managed_root" not in document


def test_invalid_marker_id_fails_closed(
    binder: StateRootBinder, marker: SelfOwnershipMarker, tmp_path: Path
) -> None:
    root = tmp_path / "bad-id"
    binding = binder.bind(explicit=root)
    dest = root / MACHI_OWNER_FILENAME
    dest.write_text(
        json.dumps(
            {
                "kind": "local_ownership_marker",
                "schema_version": 1,
                "marker_id": "not-an-id",
                "product": "machi",
                "root_fingerprint": root_fingerprint(binding.root),
                "created_at": FIXED.isoformat().replace("+00:00", "Z"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    before = dest.read_text(encoding="utf-8")
    with pytest.raises(ValidationError, match="refusing to repair"):
        marker.establish(binding)
    assert dest.read_text(encoding="utf-8") == before


def test_cli_mark_local_then_reentry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "cli"
    assert main(["install", "mark-local", "--state-root", str(root)]) == 0
    first = capsys.readouterr().out
    assert "install.ownership.local_marked" in first
    assert '"privacy": "restricted"' in first
    assert '"status": "local_marker_present"' in first
    assert '"destructive_authorization": false' in first
    assert '"dual_ownership": false' in first
    assert (root / MACHI_OWNER_FILENAME).is_file()
    assert main(["install", "mark-local", "--state-root", str(root)]) == 0
    second = capsys.readouterr().out
    assert '"existed": true' in second
    assert '"created": false' in second
    assert main(["kernel", "prove", "--journal-dir", str(journal_dir(root))]) == 0
    capsys.readouterr()
    assert main(["kernel", "events", "--journal-dir", str(journal_dir(root))]) == 0
    listed = capsys.readouterr().out
    assert "kernel.alive" in listed
    assert "install.state_root.bound" in listed
    assert "install.ownership.local_marked" in listed


def test_cli_unknown_content_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "occupied"
    root.mkdir()
    (root / "notes.txt").write_text("nope", encoding="utf-8")
    assert main(["install", "mark-local", "--state-root", str(root)]) == 2
    err = capsys.readouterr().err
    assert "unknown pre-existing" in err
    assert not (root / MACHI_OWNER_FILENAME).exists()
    assert not (journal_dir(root) / "events.jsonl").exists()


def test_binder_does_not_create_the_marker(
    binder: StateRootBinder, tmp_path: Path
) -> None:
    root = tmp_path / "bind-only"
    binder.bind(explicit=root)
    assert not (root / MACHI_OWNER_FILENAME).exists()
