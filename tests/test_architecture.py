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
    unmapped_adapter_families,
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


def adapter_edge(
    family: str, target: str, *, submodule: str | None = None
) -> ImportEdge:
    """A synthetic edge from an adapter in `family` to a core package."""
    target_module = f"kultrun.{target}" + (f".{submodule}" if submodule else "")
    return ImportEdge(
        source_module=f"kultrun.adapters.{family}.thing",
        source_package="adapters",
        target_module=target_module,
        target_package=target,
        target_submodule=submodule,
        line=1,
        source_adapter_family=family,
    )


class TestTheRealTree:
    def test_every_package_has_a_tier(self) -> None:
        """A module added without a place in the law must fail, not escape it."""
        assert unassigned_packages(SOURCE_ROOT) == []

    def test_every_adapter_family_declares_a_port_domain(self) -> None:
        """Law 5 cannot evaluate an adapter whose port is unknown."""
        assert unmapped_adapter_families(SOURCE_ROOT) == []

    def test_the_tree_obeys_the_dependency_law(self) -> None:
        assert violations(scan(SOURCE_ROOT)) == []

    def test_nothing_in_the_core_imports_an_adapter(self) -> None:
        """Only the composition root. An adapter may still use its own tier."""
        offenders = [
            e.describe()
            for e in scan(SOURCE_ROOT)
            if e.target_package == "adapters"
            and e.source_package not in ("main", "adapters")
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
            ("execution", "capacity"),
            ("storage", "model"),
            ("capacity", "model"),
            ("knowledge", "gateway"),
            ("knowledge", "inference"),
            ("vendor", "knowledge"),
            ("intelligence", "resource"),
            ("training", "inference"),
            ("agents", "platform"),
        ],
    )
    def test_each_declared_non_edge(self, source: str, target: str) -> None:
        problems = violations([edge(source, target)])
        assert problems != []
        assert "non-edge" in problems[0]

    def test_an_import_of_the_intelligence_tier(self) -> None:
        assert violations([edge("gateway", "intelligence")])

    def test_an_adapter_imported_by_the_core(self) -> None:
        assert violations([edge("inference", "adapters")])

    def test_an_adapter_imported_by_the_composition_root_is_allowed(self) -> None:
        assert violations([edge("main", "adapters")]) == []

    @pytest.mark.parametrize(
        ("source", "target"),
        [("capacity", "storage"), ("capacity", "host"), ("execution", "host")],
    )
    def test_a_narrow_edge_reaching_past_its_permitted_submodule(
        self, source: str, target: str
    ) -> None:
        """A narrowed edge may read contracts, never the domain's logic."""
        problems = violations([edge(source, target, submodule="probe")])
        assert problems != []
        assert "may import only" in problems[0]

    @pytest.mark.parametrize(
        ("source", "target"),
        [("capacity", "storage"), ("capacity", "host"), ("execution", "host")],
    )
    def test_a_narrow_edge_into_contracts_is_allowed(
        self, source: str, target: str
    ) -> None:
        assert violations([edge(source, target, submodule="contracts")]) == []

    def test_agents_reaching_an_infrastructure_domain_directly(self) -> None:
        """The Team Agent may use the serving path; nothing may bypass the API."""
        problems = violations([edge("agents", "resource")])
        assert problems != []
        assert "may import only" in problems[0]

    def test_agents_using_its_permitted_path_is_allowed(self) -> None:
        for target in ("api", "gateway", "knowledge", "brains", "identity"):
            assert violations([edge("agents", target)]) == [], target

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


class TestLawFive:
    """An adapter may not do what the domain declaring its port may not.

    Law 3 lets an adapter import core tiers, which on its own would make
    `adapters/` a back channel: a host-discovery provider could reach the
    Resource Manager, and a dependency no core module is permitted would be
    acquired anyway. These tests are the proof that the loophole is shut.
    """

    def test_an_adapter_may_import_the_domain_whose_port_it_implements(self) -> None:
        assert violations([adapter_edge("host", "host")]) == []
        assert violations([adapter_edge("persistence", "kernel")]) == []

    def test_an_adapter_may_import_what_its_domain_may_import(self) -> None:
        """A host provider legitimately needs the tier-1 semantics."""
        assert violations([adapter_edge("host", "evidence")]) == []
        assert violations([adapter_edge("host", "kernel")]) == []

    @pytest.mark.parametrize(
        "target", ["model", "planning", "resource", "runtime", "inference"]
    )
    def test_a_host_provider_cannot_reach_upward(self, target: str) -> None:
        """The rule that matters: a provider cannot decide anything."""
        problems = violations([adapter_edge("host", target)])
        assert problems != []
        assert "Law 5" in problems[0]

    def test_an_adapter_inherits_its_domains_forbidden_edges(self) -> None:
        """A container engine adapter is still forbidden to read capacity."""
        problems = violations([adapter_edge("container", "capacity")])
        assert problems != []
        assert "non-edge" in problems[0]
        assert "Law 5" in problems[0]

    def test_an_adapter_inherits_its_domains_narrow_edges(self) -> None:
        problems = violations([adapter_edge("capacity", "storage", submodule="probe")])
        assert problems != []
        assert "may import only" in problems[0]

    def test_an_adapter_cannot_import_the_unimportable_tier(self) -> None:
        problems = violations([adapter_edge("usage", "intelligence")])
        assert problems != []
        assert "nothing may import" in problems[0]

    def test_an_adapter_family_with_no_declared_port_domain_is_a_violation(
        self,
    ) -> None:
        """A new adapter must say whose port it implements before importing."""
        problems = violations([adapter_edge("invented", "kernel")])
        assert problems != []
        assert "declares no port domain" in problems[0]

    def test_an_adapter_may_use_its_own_tier(self) -> None:
        edge_within = ImportEdge(
            source_module="kultrun.adapters.host.hwloc",
            source_package="adapters",
            target_module="kultrun.adapters.host.shared",
            target_package="adapters",
            target_submodule="host",
            line=1,
            source_adapter_family="host",
        )
        assert violations([edge_within]) == []

    def test_the_failure_names_the_rule_and_the_inheritance(self) -> None:
        """A failure has to be diagnosable by someone who did not write it."""
        (problem,) = violations([adapter_edge("host", "resource")])
        assert "kultrun.adapters.host.thing" in problem
        assert "kultrun.resource" in problem
        assert "'host' adapter inherits 'host's import budget" in problem
