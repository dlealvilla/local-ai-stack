"""Steward Tier 2: ownership, lifecycle, occupancy, reclaim candidates."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pytest

from machi.adapters.persistence.file_store import FileStore
from machi.adapters.steward.measure import measure_owned_tree
from machi.adapters.steward.native import NativeSteward, RootClaim
from machi.install.binder import StateRootBinder
from machi.install.defaults import KULTRUN_OWNER_FILENAME, MACHI_OWNER_FILENAME
from machi.install.identity import InstallIdentity
from machi.install.marker import SelfOwnershipMarker
from machi.install.registry import RegistrySeed
from machi.kernel.build import identity as build_identity
from machi.kernel.clock import FixedClock
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import to_dict
from machi.steward.classify import OwnershipFacts, classify_ownership
from machi.steward.contracts import (
    GenerationHint,
    InstallFact,
    LifecycleStatus,
    MarkerFact,
    ObsoletePolicy,
    OwnershipStatus,
    ProtectionHint,
    ProtectionStatus,
    Reclaimability,
    RegistryFact,
)
from machi.steward.events import steward_events
from machi.steward.policy import default_steward_settings
from machi.steward.project import occupancy_map, resource_from_classification

FIXED = dt.datetime(2026, 9, 22, 1, 0, tzinfo=dt.UTC)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(FIXED)


def _facts(
    marker: MarkerFact = MarkerFact.VALID,
    registry: RegistryFact = RegistryFact.MATCH,
    install: InstallFact = InstallFact.MATCH,
    legacy: bool = False,
) -> OwnershipFacts:
    return OwnershipFacts(
        marker=marker,
        registry=registry,
        install_record=install,
        legacy_marker=legacy,
        marker_id="lown_0123456789abcdef",
        install_id="inst_0123456789abcdef" if install is InstallFact.MATCH else None,
    )


def _classify(
    facts: OwnershipFacts,
    *,
    generation: GenerationHint = GenerationHint.CURRENT,
    protection: ProtectionHint = ProtectionHint.DEFAULT,
    policy: ObsoletePolicy = ObsoletePolicy.CANDIDATE,
):
    return classify_ownership(
        facts,
        generation=generation,
        protection=protection,
        settings=default_steward_settings(obsolete_policy=policy),
    )


def test_marker_and_registry_agree() -> None:
    result = _classify(_facts())
    assert result.ownership is OwnershipStatus.VERIFIED_MACHI_OWNED
    assert result.lifecycle is LifecycleStatus.ACTIVE
    assert result.protection is ProtectionStatus.ACTIVE_PROTECTED
    assert result.reclaimability is Reclaimability.NOT_RECLAIMABLE


def test_marker_missing_is_not_machi() -> None:
    result = _classify(
        _facts(marker=MarkerFact.ABSENT, registry=RegistryFact.NOT_CONSULTED)
    )
    assert result.ownership is OwnershipStatus.NOT_MACHI_OWNED
    assert result.reclaimability is Reclaimability.NOT_RECLAIMABLE


def test_registry_missing_stays_unknown() -> None:
    result = _classify(
        _facts(registry=RegistryFact.ABSENT, install=InstallFact.NOT_CONSULTED)
    )
    assert result.ownership is OwnershipStatus.UNKNOWN
    assert result.reclaimability is Reclaimability.NOT_RECLAIMABLE


def test_store_not_consulted_stays_unknown() -> None:
    result = _classify(
        _facts(registry=RegistryFact.NOT_CONSULTED, install=InstallFact.NOT_CONSULTED)
    )
    assert result.ownership is OwnershipStatus.UNKNOWN


def test_registry_mismatch_is_conflict() -> None:
    result = _classify(_facts(registry=RegistryFact.MISMATCH))
    assert result.ownership is OwnershipStatus.CONFLICTED
    assert result.reclaimability is Reclaimability.NOT_RECLAIMABLE


def test_install_id_mismatch_is_conflict() -> None:
    result = _classify(_facts(install=InstallFact.MISMATCH))
    assert result.ownership is OwnershipStatus.CONFLICTED


def test_copied_marker_is_conflict() -> None:
    result = _classify(_facts(marker=MarkerFact.FINGERPRINT_MISMATCH))
    assert result.ownership is OwnershipStatus.CONFLICTED


def test_malformed_marker_fails_closed() -> None:
    result = _classify(_facts(marker=MarkerFact.MALFORMED))
    assert result.ownership is OwnershipStatus.CONFLICTED


def test_unsupported_marker_fails_closed() -> None:
    result = _classify(_facts(marker=MarkerFact.UNSUPPORTED))
    assert result.ownership is OwnershipStatus.CONFLICTED


def test_legacy_marker_is_not_adopted() -> None:
    result = _classify(
        _facts(
            marker=MarkerFact.ABSENT,
            registry=RegistryFact.NOT_CONSULTED,
            install=InstallFact.NOT_CONSULTED,
            legacy=True,
        )
    )
    assert result.ownership is OwnershipStatus.LEGACY_UNVERIFIED
    assert result.reclaimability is Reclaimability.NOT_RECLAIMABLE


def test_active_resource_stays_protected_even_if_unprotect_hint() -> None:
    result = _classify(_facts(), protection=ProtectionHint.UNPROTECTED)
    assert result.protection is ProtectionStatus.ACTIVE_PROTECTED


def test_rollback_generation_is_protected() -> None:
    result = _classify(_facts(), generation=GenerationHint.ROLLBACK)
    assert result.lifecycle is LifecycleStatus.STANDBY
    assert result.protection is ProtectionStatus.ROLLBACK_PROTECTED
    assert result.reclaimability is Reclaimability.NOT_RECLAIMABLE


def test_evidence_retention_blocks_reclaim() -> None:
    result = _classify(
        _facts(),
        generation=GenerationHint.OBSOLETE,
        protection=ProtectionHint.EVIDENCE,
    )
    assert result.protection is ProtectionStatus.EVIDENCE_RETAINED
    assert result.reclaimability is Reclaimability.NOT_RECLAIMABLE


def test_obsolete_unprotected_is_a_candidate_not_a_delete() -> None:
    result = _classify(_facts(), generation=GenerationHint.OBSOLETE)
    assert result.lifecycle is LifecycleStatus.OBSOLETE
    assert result.protection is ProtectionStatus.UNPROTECTED
    assert result.reclaimability is Reclaimability.RECLAIMABLE


def test_abandoned_unprotected_is_a_candidate() -> None:
    result = _classify(_facts(), generation=GenerationHint.ABANDONED)
    assert result.reclaimability is Reclaimability.RECLAIMABLE


def test_ask_policy_does_not_mark_a_candidate() -> None:
    result = _classify(
        _facts(),
        generation=GenerationHint.OBSOLETE,
        policy=ObsoletePolicy.ASK,
    )
    assert result.reclaimability is Reclaimability.REQUIRES_POLICY_DECISION


def test_unknown_lifecycle_when_install_record_is_absent() -> None:
    result = _classify(_facts(install=InstallFact.ABSENT))
    assert result.ownership is OwnershipStatus.VERIFIED_MACHI_OWNED
    assert result.lifecycle is LifecycleStatus.UNKNOWN
    assert result.reclaimability is Reclaimability.NOT_RECLAIMABLE


def test_defaults_are_inspectable() -> None:
    settings = default_steward_settings()
    names = {item.name: item.value for item in settings.settings}
    assert names["ownership.unknown"] == "preserve"
    assert names["ownership.conflicted"] == "preserve"
    assert names["ownership.legacy"] == "preserve"
    assert names["destructive.authorization"] == "false"
    assert settings.destructive_authorization is False


def test_events_omit_paths_and_do_not_authorize_deletion() -> None:
    classification = _classify(_facts())
    resource = resource_from_classification(
        resource_id="lown_0123456789abcdef",
        path="/tmp/customer-secret/root",
        classification=classification,
        generation=GenerationHint.CURRENT,
        install_id="inst_0123456789abcdef",
        size_bytes=12,
        mount_id="mnt:1",
        backing_store_id="dev:1:2",
        storage_class="local_physical",
    )
    occupancy = occupancy_map(
        (resource,),
        settings=default_steward_settings(),
        observed_at=FIXED,
        provider="native",
    )
    events = steward_events(occupancy, clock=FixedClock(FIXED))
    assert len(events) == 4
    blob = json.dumps([to_dict(event) for event in events])
    assert "/tmp/customer-secret/root" not in blob
    assert "SAFE_STORAGE" not in blob
    assert occupancy.destructive_authorization is False
    assert all(event.privacy is PrivacyClass.OPERATIONAL for event in events)


def test_verified_root_measures_bytes_and_keeps_the_tree(
    tmp_path: Path, clock: FixedClock
) -> None:
    root = tmp_path / "owned"
    binder = StateRootBinder(clock=clock, default_root=tmp_path / "unused")
    binding = binder.bind(explicit=root)
    marker = SelfOwnershipMarker(clock=clock).establish(binding)
    store = FileStore(tmp_path / "store")
    seeded = RegistrySeed(clock=clock).seed(binding, marker, store)
    InstallIdentity(clock=clock).establish(
        binding, marker, seeded, store, build_identity()
    )
    payload = root / "keep.txt"
    payload.write_bytes(b"abcdef")
    occupancy = NativeSteward(
        (RootClaim(path=str(root)),),
        store=store,
        clock=clock,
    ).assess()
    resource = occupancy.resources[0]
    assert resource.ownership is OwnershipStatus.VERIFIED_MACHI_OWNED
    assert resource.protection is ProtectionStatus.ACTIVE_PROTECTED
    assert isinstance(resource.size_bytes, int)
    assert resource.size_bytes >= 6
    assert payload.read_bytes() == b"abcdef"
    assert occupancy.destructive_authorization is False


def test_copied_marker_on_disk_is_conflicted(tmp_path: Path, clock: FixedClock) -> None:
    source = tmp_path / "source"
    copied = tmp_path / "copied"
    binder = StateRootBinder(clock=clock, default_root=tmp_path / "unused")
    binding = binder.bind(explicit=source)
    SelfOwnershipMarker(clock=clock).establish(binding)
    copied.mkdir()
    (copied / MACHI_OWNER_FILENAME).write_text(
        (source / MACHI_OWNER_FILENAME).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    occupancy = NativeSteward(
        (RootClaim(path=str(copied)),),
        store=FileStore(tmp_path / "store"),
        clock=clock,
    ).assess()
    assert occupancy.resources[0].ownership is OwnershipStatus.CONFLICTED
    assert (copied / MACHI_OWNER_FILENAME).is_file()


def test_obsolete_candidate_is_not_deleted(tmp_path: Path, clock: FixedClock) -> None:
    root = tmp_path / "old"
    binder = StateRootBinder(clock=clock, default_root=tmp_path / "unused")
    binding = binder.bind(explicit=root)
    marker = SelfOwnershipMarker(clock=clock).establish(binding)
    store = FileStore(tmp_path / "store")
    seeded = RegistrySeed(clock=clock).seed(binding, marker, store)
    InstallIdentity(clock=clock).establish(
        binding, marker, seeded, store, build_identity()
    )
    kept = root / "obsolete.bin"
    kept.write_bytes(b"zzzz")
    occupancy = NativeSteward(
        (
            RootClaim(
                path=str(root),
                generation=GenerationHint.OBSOLETE,
                protection=ProtectionHint.DEFAULT,
            ),
        ),
        store=store,
        clock=clock,
    ).assess()
    assert occupancy.resources[0].reclaimability is Reclaimability.RECLAIMABLE
    assert kept.is_file()
    assert occupancy.totals.reclaimable_bytes == occupancy.resources[0].size_bytes


def test_symlink_escape_is_not_counted(tmp_path: Path) -> None:
    root = tmp_path / "managed"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "inside.txt").write_bytes(b"ab")
    (outside / "secret.bin").write_bytes(b"x" * 1000)
    (root / "leak").symlink_to(outside / "secret.bin")
    measured = measure_owned_tree(root)
    assert isinstance(measured.size_bytes, int)
    assert measured.size_bytes < 1000
    assert measured.symlink_escapes == 1
    assert (outside / "secret.bin").is_file()


def test_hardlink_is_counted_once(tmp_path: Path) -> None:
    linked = tmp_path / "linked"
    copied = tmp_path / "copied"
    linked.mkdir()
    copied.mkdir()
    first = linked / "a.bin"
    first.write_bytes(b"12345")
    os.link(first, linked / "b.bin")
    (copied / "a.bin").write_bytes(b"12345")
    (copied / "b.bin").write_bytes(b"12345")
    linked_size = measure_owned_tree(linked).size_bytes
    copied_size = measure_owned_tree(copied).size_bytes
    assert isinstance(linked_size, int)
    assert isinstance(copied_size, int)
    assert linked_size < copied_size


def test_inaccessible_directory_stays_unresolved(tmp_path: Path) -> None:
    root = tmp_path / "managed"
    hidden = root / "hidden"
    hidden.mkdir(parents=True)
    (hidden / "file.txt").write_bytes(b"secret")
    hidden.chmod(0)
    try:
        measured = measure_owned_tree(root)
    finally:
        hidden.chmod(0o700)
    assert not isinstance(measured.size_bytes, int)
    assert measured.inaccessible >= 1


def test_same_backing_store_groups_two_roots() -> None:
    first = resource_from_classification(
        resource_id="lown_aaaaaaaaaaaaaaaa",
        path="/data/a",
        classification=_classify(_facts()),
        generation=GenerationHint.CURRENT,
        install_id="inst_0123456789abcdef",
        size_bytes=10,
        mount_id="mnt:1",
        backing_store_id="dev:7:1",
        storage_class="local_physical",
    )
    second_facts = _facts()
    second = resource_from_classification(
        resource_id="lown_bbbbbbbbbbbbbbbb",
        path="/data/b",
        classification=_classify(second_facts),
        generation=GenerationHint.CURRENT,
        install_id="inst_0123456789abcdef",
        size_bytes=5,
        mount_id="mnt:2",
        backing_store_id="dev:7:1",
        storage_class="local_physical",
    )
    occupancy = occupancy_map(
        (first, second),
        settings=default_steward_settings(),
        observed_at=FIXED,
        provider="native",
    )
    assert len(occupancy.backing) == 1
    assert occupancy.backing[0].resource_count == 2
    assert occupancy.backing[0].size_bytes == 15


def test_duplicate_resource_id_is_counted_once() -> None:
    resource = resource_from_classification(
        resource_id="lown_0123456789abcdef",
        path="/data/a",
        classification=_classify(_facts()),
        generation=GenerationHint.CURRENT,
        install_id="inst_0123456789abcdef",
        size_bytes=4,
        mount_id="mnt:1",
        backing_store_id="dev:1:1",
        storage_class="local_physical",
    )
    occupancy = occupancy_map(
        (resource, resource),
        settings=default_steward_settings(),
        observed_at=FIXED,
        provider="native",
    )
    assert len(occupancy.resources) == 1
    assert occupancy.totals.active_bytes == 4


def test_legacy_file_on_disk_is_preserved(tmp_path: Path, clock: FixedClock) -> None:
    root = tmp_path / "legacy"
    root.mkdir()
    marker = root / KULTRUN_OWNER_FILENAME
    marker.write_text("{}\n", encoding="utf-8")
    occupancy = NativeSteward((RootClaim(path=str(root)),), clock=clock).assess()
    assert occupancy.resources[0].ownership is OwnershipStatus.LEGACY_UNVERIFIED
    assert marker.is_file()


def test_unrelated_directory_is_not_machi_owned(
    tmp_path: Path, clock: FixedClock
) -> None:
    root = tmp_path / "customer"
    root.mkdir()
    (root / "notes.txt").write_text("customer", encoding="utf-8")
    occupancy = NativeSteward((RootClaim(path=str(root)),), clock=clock).assess()
    assert occupancy.resources[0].ownership is OwnershipStatus.NOT_MACHI_OWNED
    assert not isinstance(occupancy.resources[0].size_bytes, int)
    assert (root / "notes.txt").is_file()
