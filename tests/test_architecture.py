"""The dependency law, enforced — and the enforcer, verified.

Two halves. The first runs the checker over the real tree. The second runs it
over synthetic edges, because a checker that has nothing to find yet would
otherwise pass while being broken, and would keep passing right up to the
moment it was needed.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from kultrun.host.contracts import HostId
from kultrun.identity.contracts import Subject
from kultrun.kernel.schema import Contract, contract, meaning, registered_contracts
from tests.architecture import (
    KERNEL_CONCEPTS,
    ImportEdge,
    host_scoping_violations,
    import_all_contracts,
    reference_violations,
    scan,
    unassigned_packages,
    violations,
)

SOURCE_ROOT = Path(__file__).resolve().parent.parent / "src"
KERNEL_ROOT = SOURCE_ROOT / "kultrun" / "kernel"


def edge(source: str, target: str, *, submodule: str | None = None) -> ImportEdge:
    """A synthetic edge from one package to another."""
    target_module = f"kultrun.{target}" + (f".{submodule}" if submodule else "")
    return ImportEdge(
        source_module=f"kultrun.{source}.thing",
        source_package=source,
        target_module=target_module,
        target_package=target,
        target_submodule=submodule,
        line=1,
    )


class TestTheRealTree:
    def test_every_package_has_a_tier(self) -> None:
        """A module added without a place in the law must fail, not escape it."""
        assert unassigned_packages(SOURCE_ROOT) == []

    def test_the_tree_obeys_the_dependency_law(self) -> None:
        assert violations(scan(SOURCE_ROOT)) == []

    def test_nothing_in_the_core_imports_an_adapter(self) -> None:
        offenders = [
            e.describe()
            for e in scan(SOURCE_ROOT)
            if e.target_package == "adapters" and e.source_package != "main"
        ]
        assert offenders == []

    def test_the_kernel_imports_no_third_party_package(self) -> None:
        """The Milestone 0 gate: contracts serialize without a provider library."""
        allowed = set(sys.stdlib_module_names) | {"kultrun"}
        offenders: list[str] = []
        for path in sorted(KERNEL_ROOT.glob("*.py")):
            for module in _top_level_imports(path):
                if module not in allowed:
                    offenders.append(f"{path.name} imports {module}")
        assert offenders == []

    def test_the_kernel_holds_exactly_its_declared_concepts(self) -> None:
        """The concept census. Eleven modules for one concept fails here."""
        present = {
            path.stem for path in KERNEL_ROOT.glob("*.py") if path.stem != "__init__"
        }
        assert present == set(KERNEL_CONCEPTS)


class TestTheCheckerFinds:
    def test_an_upward_import(self) -> None:
        assert violations([edge("kernel", "gateway")])

    def test_an_undeclared_intra_tier_import(self) -> None:
        assert violations([edge("host", "storage")])

    def test_a_declared_intra_tier_import_is_allowed(self) -> None:
        assert violations([edge("capacity", "storage", submodule="contracts")]) == []
        assert violations([edge("api", "platform")]) == []

    @pytest.mark.parametrize(
        ("source", "target"),
        [
            ("planning", "resource"),
            ("resource", "planning"),
            ("execution", "runtime"),
            ("runtime", "execution"),
            ("storage", "model"),
            ("capacity", "model"),
            ("agents", "platform"),
        ],
    )
    def test_each_declared_non_edge(self, source: str, target: str) -> None:
        assert violations([edge(source, target)])

    def test_an_import_of_the_intelligence_tier(self) -> None:
        assert violations([edge("gateway", "intelligence")])

    def test_an_adapter_imported_by_the_core(self) -> None:
        assert violations([edge("inference", "adapters")])

    def test_an_adapter_imported_by_the_composition_root_is_allowed(self) -> None:
        assert violations([edge("main", "adapters")]) == []

    def test_a_narrow_edge_reaching_past_its_permitted_submodule(self) -> None:
        """`capacity` may read storage evidence, not storage's probing logic."""
        assert violations([edge("capacity", "storage", submodule="probe")])

    def test_a_contracts_module_reaching_into_domain_logic(self) -> None:
        offender = ImportEdge(
            source_module="kultrun.model.contracts",
            source_package="model",
            target_module="kultrun.storage.probe",
            target_package="storage",
            target_submodule="probe",
            line=1,
        )
        assert violations([offender])

    def test_a_contracts_module_importing_a_lower_contract_is_allowed(self) -> None:
        allowed = ImportEdge(
            source_module="kultrun.model.contracts",
            source_package="model",
            target_module="kultrun.storage.contracts",
            target_package="storage",
            target_submodule="contracts",
            line=1,
        )
        assert violations([allowed]) == []

    def test_a_package_with_no_tier(self) -> None:
        assert violations([edge("kernel", "invented")])

    def test_a_downward_import_is_allowed(self) -> None:
        assert violations([edge("gateway", "identity")]) == []

    def test_a_package_importing_itself_is_allowed(self) -> None:
        assert violations([edge("storage", "storage", submodule="evidence")]) == []


def _top_level_imports(path: Path) -> set[str]:
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


class TestContractShape:
    """The two checks that needed contracts to inspect. Stage 0.2 adds them."""

    def test_cross_package_references_are_by_identifier(self) -> None:
        assert reference_violations(_production_contracts()) == []

    def test_host_scoped_contracts_carry_a_host_id_and_stay_plural(self) -> None:
        problems = host_scoping_violations(
            _production_contracts(), host_id_type=HostId
        )
        assert problems == []

    def test_a_value_object_may_be_embedded_across_packages(self) -> None:
        """`Provenance` has no identity, so embedding it is not a reference."""
        embedded = {
            key: cls
            for key, cls in _production_contracts().items()
            if key[0] == "capacity.evidence"
        }
        assert reference_violations(embedded) == []


class TestTheContractCheckerFinds:
    """Synthetic violations, so the checks are not merely vacuous."""

    def test_an_embedded_entity_from_another_package(self) -> None:
        @contract(kind="test.arch.embeds_entity", version=1)
        @dataclass(frozen=True, slots=True)
        class EmbedsEntity(Contract):
            actor: Subject = meaning("embedded rather than referenced")

        offender = {("test.arch.embeds_entity", 1): EmbedsEntity}
        problems = reference_violations(offender)
        assert problems != []
        assert "reference it by identifier" in problems[0]

    def test_a_host_scoped_contract_with_no_host_id(self) -> None:
        @contract(kind="test.arch.unscoped", version=1)
        @dataclass(frozen=True, slots=True)
        class Unscoped(Contract):
            label: str = meaning("anything")

        with _host_scoped({"test.arch.unscoped"}):
            problems = host_scoping_violations(
                {("test.arch.unscoped", 1): Unscoped}, host_id_type=HostId
            )
        assert problems != []
        assert "host_id" in problems[0]

    def test_a_singular_field_where_plurality_is_required(self) -> None:
        @contract(kind="test.arch.singular", version=1)
        @dataclass(frozen=True, slots=True)
        class Singular(Contract):
            host_id: HostId = meaning("scoped correctly")
            accelerators: str = meaning("but singular, which is the defect")

        singular: dict[str, tuple[str, ...]] = {
            "test.arch.singular": ("accelerators",)
        }
        with _host_scoped(set()), _plural_fields(singular):
            problems = host_scoping_violations(
                {("test.arch.singular", 1): Singular}, host_id_type=HostId
            )
        assert problems != []
        assert "collection" in problems[0]


@contextmanager
def _host_scoped(kinds: set[str]) -> Iterator[None]:
    import tests.architecture as module

    original = module.HOST_SCOPED_KINDS
    module.HOST_SCOPED_KINDS = frozenset(kinds)
    try:
        yield
    finally:
        module.HOST_SCOPED_KINDS = original


@contextmanager
def _plural_fields(mapping: dict[str, tuple[str, ...]]) -> Iterator[None]:
    import tests.architecture as module

    original = module.PLURAL_FIELDS
    module.PLURAL_FIELDS = mapping
    try:
        yield
    finally:
        module.PLURAL_FIELDS = original


def _production_contracts() -> dict[tuple[str, int], type[Contract]]:
    import_all_contracts(SOURCE_ROOT)
    return {
        key: cls
        for key, cls in registered_contracts().items()
        if cls.__module__.startswith("kultrun.")
    }
