"""The dependency law, enforced — and the enforcer, verified.

Two halves. The first runs the checker over the real tree. The second runs it
over synthetic edges, because a checker that has nothing to find yet would
otherwise pass while being broken, and would keep passing right up to the
moment it was needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.architecture import (
    KERNEL_CONCEPTS,
    ImportEdge,
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
