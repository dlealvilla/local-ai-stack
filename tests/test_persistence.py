"""The store: atomic writes, orphan sweeping, and defects reported not skipped."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kultrun.adapters.persistence.file_store import FileStore
from kultrun.kernel.errors import PersistenceError, ValidationError
from kultrun.kernel.persistence import (
    ReconciliationReport,
    Store,
    validate_record_key,
)
from kultrun.kernel.schema import to_dict
from tests.fixtures.contracts import Leaf, Probe
from tests.test_schema import make_probe


def test_the_file_store_satisfies_the_port(store: FileStore) -> None:
    assert isinstance(store, Store)


class TestRoundTrip:
    def test_a_record_survives_a_write_and_read(self, store: FileStore) -> None:
        probe = make_probe()
        store.put("pool-0", probe)
        assert store.get(Probe, "pool-0") == probe

    def test_a_missing_record_reads_as_absent_rather_than_raising(
        self, store: FileStore
    ) -> None:
        assert store.get(Probe, "never-written") is None

    def test_a_record_is_self_describing_on_disk(self, store: FileStore) -> None:
        """A record recovered by hand must say what it is and where it belongs."""
        store.put("pool-0", make_probe())
        document = json.loads(
            (store.root / "test.probe" / "pool-0.json").read_text(encoding="utf-8")
        )
        assert document["kind"] == "test.probe"
        assert document["schema_version"] == 1
        assert document["record_key"] == "pool-0"

    def test_keys_and_records_are_listed_per_kind(self, store: FileStore) -> None:
        store.put("a", make_probe())
        store.put("b", make_probe())
        store.put("leaf", Leaf(label="unrelated"))
        assert store.keys(Probe) == ("a", "b")
        assert len(store.records(Probe)) == 2

    def test_delete_reports_whether_anything_was_removed(
        self, store: FileStore
    ) -> None:
        store.put("a", make_probe())
        assert store.delete(Probe, "a") is True
        assert store.delete(Probe, "a") is False

    def test_a_record_filed_under_the_wrong_kind_is_refused(
        self, store: FileStore
    ) -> None:
        """Records are namespaced by kind, so this only happens by hand or by bug.

        It still must not load: returning a `Leaf` from a call that asked for a
        `Probe` would put the wrong type into a caller that cannot check it.
        """
        directory = store.root / "test.probe"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "misfiled.json").write_text(
            json.dumps(to_dict(Leaf(label="x"))), encoding="utf-8"
        )
        with pytest.raises(PersistenceError, match="not of the requested kind"):
            store.get(Probe, "misfiled")


class TestKeySafety:
    @pytest.mark.parametrize(
        "key", ["../escape", "nested/key", "..", ".hidden", "with space", ""]
    )
    def test_an_unsafe_key_is_refused_not_sanitized(self, key: str) -> None:
        """Rewriting a key would store the record somewhere unexpected."""
        with pytest.raises(ValidationError):
            validate_record_key(key)

    def test_traversal_cannot_reach_outside_the_store_root(
        self, store: FileStore
    ) -> None:
        with pytest.raises(ValidationError):
            store.put("../../etc/passwd", make_probe())

    @pytest.mark.parametrize("key", ["pool-0", "host_a1b2", "evt.2026-09-05", "A1"])
    def test_ordinary_keys_are_accepted(self, key: str) -> None:
        assert validate_record_key(key) == key


class TestAtomicWrites:
    def test_a_write_leaves_no_temporary_behind(self, store: FileStore) -> None:
        store.put("pool-0", make_probe())
        assert list(store.root.glob("*/.writing-*")) == []

    def test_an_interrupted_write_leaves_the_previous_record_intact(
        self, store: FileStore
    ) -> None:
        """The reason writes go through os.replace rather than in place."""
        first = make_probe(requested_bytes=1024)
        store.put("pool-0", first)

        # Simulate a crash between the temporary write and the replace.
        directory = store.root / "test.probe"
        (directory / ".writing-pool-0.json.deadbeef").write_text(
            json.dumps(to_dict(make_probe(requested_bytes=2048))), encoding="utf-8"
        )

        assert store.get(Probe, "pool-0") == first

    def test_sweeping_removes_the_orphan_and_counts_it(
        self, store: FileStore
    ) -> None:
        store.put("pool-0", make_probe())
        directory = store.root / "test.probe"
        (directory / ".writing-pool-0.json.deadbeef").write_text("{", encoding="utf-8")

        report = store.reconcile()
        assert report.swept_temporaries == 1
        assert report.records_verified == 1
        assert report.defects == ()
        assert list(store.root.glob("*/.writing-*")) == []

    def test_an_orphan_is_never_mistaken_for_a_record(
        self, store: FileStore
    ) -> None:
        store.put("pool-0", make_probe())
        (store.root / "test.probe" / ".writing-pool-1.json.cafe").write_text(
            "{", encoding="utf-8"
        )
        assert store.keys(Probe) == ("pool-0",)


class TestReconciliation:
    def test_a_clean_store_reports_clean(self, store: FileStore) -> None:
        store.put("pool-0", make_probe())
        assert store.reconcile().is_clean

    def test_an_empty_store_reports_clean(self, store: FileStore) -> None:
        assert store.reconcile() == ReconciliationReport(
            swept_temporaries=0, records_verified=0, defects=()
        )

    def test_unreadable_records_are_reported_not_skipped(
        self, store: FileStore, store_root: Path
    ) -> None:
        """A silently skipped record is how a platform lies about its own state."""
        store.put("good", make_probe())
        directory = store_root / "test.probe"
        (directory / "corrupt.json").write_text("{not json", encoding="utf-8")
        (directory / "unknown.json").write_text(
            json.dumps({"kind": "test.invented", "schema_version": 1}),
            encoding="utf-8",
        )

        report = store.reconcile()
        assert report.records_verified == 1
        assert len(report.defects) == 2
        assert not report.is_clean
        locations = sorted(defect.location for defect in report.defects)
        assert locations == ["test.probe/corrupt.json", "test.probe/unknown.json"]

    def test_a_defect_records_the_kind_it_claimed_to_be(
        self, store: FileStore, store_root: Path
    ) -> None:
        directory = store_root / "test.probe"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "wrong.json").write_text(
            json.dumps({"kind": "test.probe", "schema_version": 1}), encoding="utf-8"
        )
        (defect,) = store.reconcile().defects
        assert defect.record_kind == "test.probe"
        assert "missing a required field" in defect.problem

    def test_reconciliation_reports_facts_and_decides_nothing(
        self, store: FileStore, store_root: Path
    ) -> None:
        """The store never refuses to open; policy decides what a defect means."""
        directory = store_root / "test.probe"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "corrupt.json").write_text("{", encoding="utf-8")

        report = store.reconcile()
        assert isinstance(report, ReconciliationReport)
        # Still usable afterwards: the store did not fail closed on its own state.
        store.put("good", make_probe())
        assert store.get(Probe, "good") is not None
