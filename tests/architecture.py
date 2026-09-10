"""The machine-readable form of the dependency law, and the checker for it.

`docs/ARCHITECTURE.md` Part II is the authority. This module mirrors it so a
test can enforce it, and `test_architecture.py` asserts that the mirror stays
complete — a new package with no tier assignment fails, rather than silently
escaping the law.

The previous attempt had sound rules and drifted anyway. The difference here
is that drift fails a test.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, cast, get_args, get_origin, get_type_hints

from kultrun.kernel.ids import EntityId
from kultrun.kernel.schema import Contract

#: Part II §1. Tiers are bands; imports may only go downward between them.
TIERS: Mapping[str, int] = {
    "kernel": 0,
    "evidence": 1,
    "policy": 1,
    "identity": 1,
    "entitlement": 1,
    "audit": 1,
    "host": 2,
    "components": 2,
    "storage": 2,
    "capacity": 2,
    "model": 3,
    "planning": 4,
    "resource": 4,
    "execution": 5,
    "runtime": 5,
    "inference": 6,
    "analytics": 6,
    "telemetry": 6,
    "gateway": 6,
    "knowledge": 7,
    "training": 7,
    "brains": 7,
    "platform": 8,
    "api": 8,
    "agents": 9,
    "intelligence": 9,
    "vendor": 9,
    "install": 9,
    "adapters": 10,
    "main": 11,
}

#: Part II §3. The complete list; any other intra-tier import is a violation.
INTRA_TIER_EDGES: frozenset[tuple[str, str]] = frozenset(
    {
        ("entitlement", "identity"),
        ("audit", "identity"),
        ("components", "host"),
        ("storage", "host"),
        ("capacity", "host"),
        ("capacity", "storage"),
        ("gateway", "inference"),
        ("gateway", "analytics"),
        ("brains", "knowledge"),
        ("api", "platform"),
    }
)

#: Part II §4. Pairs that must not know about each other at all.
FORBIDDEN_EDGES: frozenset[tuple[str, str]] = frozenset(
    {
        # Recommendation and authorization stay independently auditable.
        ("planning", "resource"),
        ("resource", "planning"),
        # Executor logic must not leak into runtime domain logic.
        ("execution", "runtime"),
        ("runtime", "execution"),
        # How a workload is launched is a different question from what may
        # safely be launched. Execution consumes an authorized allocation.
        ("execution", "capacity"),
        ("capacity", "execution"),
        # Runtime translates a recipe. It receives already-resolved
        # constraints through its own inputs and never owns capacity policy.
        ("runtime", "capacity"),
        ("capacity", "runtime"),
        # Storage probing must not know model identities; managed usage
        # arrives through a port that speaks only bytes per pool.
        ("storage", "model"),
        ("capacity", "model"),
        # Retrieval assembles authorized context; `brains` decides what to
        # do with it. Knowledge must not be able to call a model.
        ("knowledge", "gateway"),
        ("knowledge", "inference"),
        # The outbound boundary has no import path to customer content.
        ("vendor", "knowledge"),
        # Intelligence produces evidence and recommendations; making it
        # unable to reach the authorizer makes "never authorizes" structural.
        ("intelligence", "resource"),
        # Training infrastructure stays separate from inference
        # infrastructure (Part IV `training`; PRODUCT_VISION §74).
        ("training", "inference"),
        # The Admin Agent has no private back channel because it has no
        # import path to one.
        ("agents", "platform"),
    }
)

#: Part IV `agents`. It reaches control-plane and infrastructure domains
#: through `api` or not at all. Listed as an allow-list because the Team
#: Agent legitimately uses the serving and knowledge path, so a blanket ban
#: would be wrong and a list of banned pairs would be long and lossy.
DOMAIN_IMPORT_ALLOWLISTS: Mapping[str, frozenset[str]] = {
    "agents": frozenset(
        {
            "kernel",
            "evidence",
            "policy",
            "identity",
            "entitlement",
            "audit",
            "api",
            "gateway",
            "knowledge",
            "brains",
        }
    ),
}

#: Part II Law 5. Which domain's port each adapter family implements. An
#: adapter is evaluated against that domain's import budget, so the adapter
#: tier cannot become a loophole around the dependency law.
#:
#: A family present in the tree but absent here is itself a violation: a new
#: adapter must declare which port it implements before it may import
#: anything.
ADAPTER_PORT_DOMAIN: Mapping[str, str] = {
    "persistence": "kernel",
    "http": "api",
    "host": "host",
    "components": "components",
    "execution": "execution",
    # Genuine space reservation implements storage's own probe port, so it
    # inherits storage's budget and cannot reach capacity or model.
    "storage": "storage",
    "container": "execution",
    "runtime": "runtime",
    "model_source": "model",
    "estimators": "model",
    "acquisition": "model",
    "capacity": "capacity",
    "usage": "analytics",
    "inference": "gateway",
    "identity": "identity",
    "knowledge": "knowledge",
    "embedding": "knowledge",
    "telemetry": "telemetry",
    "entitlement": "entitlement",
    "adaptation": "training",
    "install": "install",
    "provisioning": "runtime",
    "verification": "runtime",
}

#: Part II §4. Nothing may import this package; it is strictly additive.
UNIMPORTABLE: frozenset[str] = frozenset({"intelligence"})

#: Part II §3. Edges permitted only into a named submodule.
NARROW_EDGES: Mapping[tuple[str, str], str] = {
    ("capacity", "storage"): "contracts",
    # Capacity consumes HostCapabilities without learning which tool
    # observed it: no reach into the discovery service or any provider.
    ("capacity", "host"): "contracts",
    # Execution needs to know whether a container engine exists — that fact
    # is on HostCapabilities — without acquiring the ability to go and look.
    ("execution", "host"): "contracts",
}

#: Part II §5. `contracts` may import only the kernel and lower contracts.
CONTRACT_MODULE = "contracts"

#: Tiers below `adapters` that may never import it (Law 3).
ADAPTER_TIER = TIERS["adapters"]

#: Part II §6. Contracts scoped to a single host, which must carry a host
#: identifier from v1. Milestone 14 extends these into a fleet; that is an
#: extension only if the scoping is already there.
HOST_SCOPED_KINDS: frozenset[str] = frozenset(
    {
        "host.capabilities",
        "storage.pool",
        "model.inventory_record",
        "resource.workload",
        "resource.request",
        "resource.reservation",
        "resource.admission_decision",
        "resource.summary",
        "inference.instance",
        "execution.handle",
        "execution.capability_profile",
        "runtime.capability_profile",
        "runtime.verification_basis",
        "runtime.foundation_selection",
        "runtime.eligible_model_view",
        "runtime.memory_profile",
        "telemetry.host_observation",
        "planning.model_selection",
        "planning.available_model_view",
    }
)

#: Part II §6. Collections that must be plural from v1 even where the
#: reference host has one, because a singular field is a rewrite later.
PLURAL_FIELDS: Mapping[str, tuple[str, ...]] = {
    "host.capabilities": ("accelerators", "mounts"),
}

#: Part IV tier 0. One concept, one module. Reviewed at every consolidation
#: checkpoint; a new kernel module must be a new kernel concept.
KERNEL_CONCEPTS: frozenset[str] = frozenset(
    {
        "errors",
        "ids",
        "unresolved",
        "clock",
        "schema",
        "results",
        "events",
        "config",
        "registry",
        "persistence",
        # Which artifact is executing. A mechanism with no product meaning,
        # like `clock`; needed because a real-host observation must be
        # traceable to the source state that produced it.
        "build",
    }
)


@dataclass(frozen=True, slots=True)
class ImportEdge:
    """One import of one Kultrun module by another."""

    source_module: str
    source_package: str
    target_module: str
    target_package: str
    target_submodule: str | None
    line: int
    #: For a module under `adapters/<family>/`, which family. Law 5 uses it
    #: to decide whose import budget the adapter inherits.
    source_adapter_family: str | None = None

    def describe(self) -> str:
        return f"{self.source_module}:{self.line} imports {self.target_module}"


def scan(source_root: Path) -> list[ImportEdge]:
    """Every internal import in the tree, as edges between packages."""
    edges: list[ImportEdge] = []
    package_root = source_root / "kultrun"
    for path in sorted(package_root.rglob("*.py")):
        source_module = _module_name(path, source_root)
        source_package = _package_of(source_module)
        if source_package is None:
            continue  # kultrun/__init__.py itself
        family = _adapter_family(source_module)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            edges.extend(
                _edges_from(
                    node,
                    source_module=source_module,
                    source_package=source_package,
                    family=family,
                )
            )
    return edges


def _adapter_family(module: str) -> str | None:
    """The adapter family of a module, if it is one."""
    parts = module.split(".")
    if len(parts) >= 3 and parts[1] == "adapters":
        return parts[2]
    return None


def _edges_from(
    node: ast.AST, *, source_module: str, source_package: str, family: str | None
) -> Iterable[ImportEdge]:
    if isinstance(node, ast.Import):
        for alias in node.names:
            edge = _make_edge(
                alias.name, source_module, source_package, node.lineno, None, family
            )
            if edge is not None:
                yield edge
    elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
        for alias in node.names:
            edge = _make_edge(
                node.module,
                source_module,
                source_package,
                node.lineno,
                alias.name,
                family,
            )
            if edge is not None:
                yield edge


def _make_edge(
    dotted: str,
    source_module: str,
    source_package: str,
    line: int,
    imported_name: str | None,
    family: str | None = None,
) -> ImportEdge | None:
    if not dotted.startswith("kultrun"):
        return None
    parts = dotted.split(".")
    if len(parts) < 2:
        return None
    target_package = parts[1]
    if len(parts) > 2:
        target_submodule: str | None = parts[2]
    else:
        target_submodule = imported_name
    return ImportEdge(
        source_module=source_module,
        source_package=source_package,
        target_module=dotted if imported_name is None else f"{dotted}.{imported_name}",
        target_package=target_package,
        target_submodule=target_submodule,
        line=line,
        source_adapter_family=family,
    )


def _module_name(path: Path, source_root: Path) -> str:
    relative = path.relative_to(source_root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _package_of(module: str) -> str | None:
    parts = module.split(".")
    return parts[1] if len(parts) > 1 else None


def unassigned_packages(source_root: Path) -> list[str]:
    """Packages present in the tree with no tier assignment.

    This is the check that keeps the mirror honest: a module added without a
    place in the law fails rather than escaping it.
    """
    package_root = source_root / "kultrun"
    found = {
        child.name
        for child in package_root.iterdir()
        if child.is_dir() and not child.name.startswith(("_", "."))
    }
    return sorted(found - set(TIERS))


def violations(edges: Iterable[ImportEdge]) -> list[str]:
    """Every breach of the dependency law, as readable messages."""
    found: list[str] = []
    for edge in edges:
        found.extend(_check(edge))
    return found


def _check(edge: ImportEdge) -> list[str]:
    problems: list[str] = []
    source, target = edge.source_package, edge.target_package

    if source not in TIERS:
        return [f"{edge.source_module} is in no tier; add it to TIERS"]
    if target not in TIERS:
        return [f"{edge.describe()}, which is in no tier; add it to TIERS"]

    # Law 5. An adapter is evaluated as the domain whose port it implements,
    # so the adapter tier cannot be used to reach something the domain itself
    # may not reach.
    law5 = ""
    if source == "adapters":
        if target == "adapters":
            return problems  # an adapter may use its own tier
        family = edge.source_adapter_family
        domain = ADAPTER_PORT_DOMAIN.get(family) if family is not None else None
        if domain is None:
            return [
                f"{edge.describe()}: adapter family {family!r} declares no port "
                f"domain; add it to ADAPTER_PORT_DOMAIN before it imports "
                f"anything (Law 5)"
            ]
        source = domain
        law5 = f" [Law 5: '{family}' adapter inherits '{domain}'s import budget]"

    source_tier, target_tier = TIERS[source], TIERS[target]

    if target in UNIMPORTABLE and source != target:
        problems.append(
            f"{edge.describe()}: nothing may import '{target}' (Part II §4){law5}"
        )

    if target == "adapters" and source_tier < ADAPTER_TIER and source != "main":
        problems.append(
            f"{edge.describe()}: only the composition root may import "
            f"adapters (Law 3){law5}"
        )

    if (source, target) in FORBIDDEN_EDGES:
        problems.append(
            f"{edge.describe()}: '{source}' and '{target}' are a declared "
            f"non-edge (Part II §4){law5}"
        )

    allowed = DOMAIN_IMPORT_ALLOWLISTS.get(source)
    if (
        allowed is not None
        and target != source
        and target not in allowed
        and (source, target) not in FORBIDDEN_EDGES
    ):
        problems.append(
            f"{edge.describe()}: '{source}' may import only "
            f"{sorted(allowed)} (Part IV `{source}`){law5}"
        )

    if source == target:
        return problems  # a package may always import itself

    if target_tier > source_tier:
        problems.append(
            f"{edge.describe()}: tier {source_tier} may not import tier "
            f"{target_tier} (Part II §1){law5}"
        )
    elif target_tier == source_tier and (source, target) not in INTRA_TIER_EDGES:
        problems.append(
            f"{edge.describe()}: intra-tier import is not in the declared "
            f"edge list (Part II §3){law5}"
        )

    narrow = NARROW_EDGES.get((source, target))
    if narrow is not None and edge.target_submodule != narrow:
        problems.append(
            f"{edge.describe()}: '{source}' may import only "
            f"'{target}.{narrow}' (Part II §3){law5}"
        )

    if (
        edge.source_module.endswith(f".{CONTRACT_MODULE}")
        and target != "kernel"
        and edge.target_submodule != CONTRACT_MODULE
    ):
        problems.append(
            f"{edge.describe()}: a contracts module may import only the kernel "
            f"and lower-tier contracts (Part II §5)"
        )

    return problems


def unmapped_adapter_families(source_root: Path) -> list[str]:
    """Adapter families in the tree that declare no port domain.

    Law 5 cannot evaluate an adapter whose port is unknown, so an unmapped
    family is a violation rather than an omission — a new adapter must say
    whose port it implements before it may import anything.
    """
    adapter_root = source_root / "kultrun" / "adapters"
    if not adapter_root.is_dir():
        return []
    found = {
        child.name
        for child in adapter_root.iterdir()
        if child.is_dir() and not child.name.startswith(("_", "."))
    }
    return sorted(found - set(ADAPTER_PORT_DOMAIN))


# ---------------------------------------------------------------------------
# Contract-shape checks — Part II §2 Law 2 and Part II §6
# ---------------------------------------------------------------------------


def owning_package(contract_type: type) -> str:
    """The domain package a type belongs to."""
    parts = contract_type.__module__.split(".")
    return parts[1] if len(parts) > 1 else ""


def _mentioned_types(annotation: Any) -> list[Any]:
    """Flatten an annotation into the concrete types it mentions."""
    args = get_args(annotation)
    if not args:
        return [annotation]
    found: list[Any] = []
    for arg in args:
        if arg is Ellipsis or arg is type(None):
            continue
        found.extend(_mentioned_types(arg))
    return found


def _carries_identity(contract_type: type[Contract]) -> bool:
    """Whether a contract has its own minted identity.

    This is what separates an entity from a value object. `Provenance` has
    no identity and may be embedded anywhere; `Subject` has one and must be
    referenced by it.
    """
    hints = get_type_hints(contract_type)
    return any(
        isinstance(hints[field.name], type) and issubclass(hints[field.name], EntityId)
        for field in fields(cast("Any", contract_type))
    )


def reference_violations(
    contracts: Mapping[tuple[str, int], type[Contract]],
) -> list[str]:
    """Law 2: cross-package references are by identifier, not by import.

    A contract may embed a **value object** from another package, because a
    value has no identity to reference it by. It may not embed another
    package's **entity**: that would give one thing's shape two owners and
    stop the contract graph being a DAG.
    """
    problems: list[str] = []
    for (kind, version), contract_type in sorted(contracts.items()):
        package = owning_package(contract_type)
        if package == "kernel":
            continue  # the kernel defines the mechanism; Event.payload is generic
        hints = get_type_hints(contract_type)
        for field in fields(cast("Any", contract_type)):
            for mentioned in _mentioned_types(hints[field.name]):
                if not isinstance(mentioned, type):
                    continue
                if not issubclass(mentioned, Contract) or mentioned is Contract:
                    continue
                if owning_package(mentioned) in (package, "", "kernel"):
                    continue
                if not _carries_identity(mentioned):
                    continue  # a value object; safe to embed
                problems.append(
                    f"{kind}@{version}.{field.name}: embeds entity "
                    f"'{mentioned.__name__}' owned by '{owning_package(mentioned)}'; "
                    f"reference it by identifier instead (Part II §2 Law 2)"
                )
    return problems


def host_scoping_violations(
    contracts: Mapping[tuple[str, int], type[Contract]], *, host_id_type: type
) -> list[str]:
    """Part II §6: host-scoped contracts carry a host id and stay plural.

    Milestone 14 turns these contracts into a fleet. That is an extension
    only if the scoping is already present; otherwise it is a rewrite of
    every capacity and lifecycle contract.
    """
    problems: list[str] = []
    by_kind = {kind: cls for (kind, _), cls in contracts.items()}

    for kind in sorted(HOST_SCOPED_KINDS):
        contract_type = by_kind.get(kind)
        if contract_type is None:
            problems.append(f"{kind}: declared host-scoped but not registered")
            continue
        hints = get_type_hints(contract_type)
        if "host_id" not in hints:
            problems.append(
                f"{kind}: a host-scoped contract must carry 'host_id' from v1"
            )
        elif hints["host_id"] is not host_id_type:
            problems.append(f"{kind}.host_id: must be typed HostId")

    for kind, plural in PLURAL_FIELDS.items():
        contract_type = by_kind.get(kind)
        if contract_type is None:
            problems.append(
                f"{kind}: declared to have plural fields but not registered"
            )
            continue
        hints = get_type_hints(contract_type)
        for name in plural:
            if name not in hints:
                problems.append(f"{kind}.{name}: declared plural but absent")
            elif get_origin(hints[name]) not in (tuple, list):
                problems.append(
                    f"{kind}.{name}: must be a collection from v1, even where "
                    f"the reference host has one (Part II §6)"
                )
    return problems


def import_all_contracts(source_root: Path) -> None:
    """Import every ``<package>/contracts.py`` in the tree.

    Contract registration is a side effect of import, so a check that reads
    the registry sees only what happens to have been imported. Discovering
    the modules from the tree rather than listing them means a new domain
    package is covered by these checks the moment it exists, which is the
    same property that makes the tier assignment check useful.
    """
    import importlib

    for path in sorted((source_root / "kultrun").glob("*/contracts.py")):
        importlib.import_module(f"kultrun.{path.parent.name}.contracts")


BANNED_IMPLEMENTATION_FIELDS = frozenset(
    {
        "docker_image",
        "docker_network",
        "popen_kwargs",
        "cuda_visible_devices_for_vllm",
        "vllm_model_argument",
        "image",
    }
)

GENERIC_SEAM_KINDS = frozenset(
    {
        "runtime.launch_spec",
        "runtime.launch_request",
        "runtime.profile",
        "runtime.support_descriptor",
        "runtime.readiness",
        "runtime.policy",
        "runtime.candidate",
        "runtime.resolution",
        "runtime.provisioning_component",
        "runtime.provisioning_plan",
        "runtime.installation",
        "runtime.capability_profile",
        "runtime.verification_basis",
        "runtime.verification_check",
        "runtime.verification_probe",
        "runtime.foundation_selection",
        "runtime.eligible_model_candidate",
        "runtime.eligible_model_view",
        "execution.spec",
        "execution.handle",
        "execution.capability_profile",
        "inference.instance",
        "inference.request",
        "inference.response",
    }
)


def implementation_field_leaks(
    contracts: Mapping[tuple[str, int], type[Contract]],
) -> list[str]:
    """Generic seam contracts must not grow Docker or Popen fields."""
    problems: list[str] = []
    for (kind, version), contract_type in sorted(contracts.items()):
        if kind not in GENERIC_SEAM_KINDS:
            continue
        for field in fields(cast("Any", contract_type)):
            if field.name in BANNED_IMPLEMENTATION_FIELDS:
                problems.append(f"{kind}@{version}.{field.name}")
    return problems


def _module_matches(module: str, wanted: set[str]) -> bool:
    return any(module == name or module.startswith(f"{name}.") for name in wanted)


def _imports_named(path: Path, *names: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted = set(names)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _module_matches(alias.name, wanted):
                    found.append(f"{path}:{node.lineno} imports {alias.name}")
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and _module_matches(node.module, wanted)
        ):
            found.append(f"{path}:{node.lineno} imports {node.module}")
    return found


def seam_import_leaks(source_root: Path) -> list[str]:
    """Runtime owns WHAT; Executor owns HOW; Inference only composes."""
    problems: list[str] = []
    inference = source_root / "kultrun" / "inference"
    for path in inference.rglob("*.py"):
        problems.extend(
            _imports_named(path, "subprocess", "kultrun.adapters.container")
        )
    for path in (source_root / "kultrun" / "adapters" / "runtime").rglob("*.py"):
        if path.name.endswith("_workload.py"):
            continue
        problems.extend(
            _imports_named(
                path,
                "subprocess",
                "kultrun.adapters.execution",
                "kultrun.adapters.container",
            )
        )
    for path in (source_root / "kultrun" / "runtime").rglob("*.py"):
        problems.extend(
            _imports_named(
                path,
                "kultrun.execution",
                "kultrun.resource",
                "kultrun.model",
                "kultrun.planning",
                "kultrun.inference",
                "kultrun.adapters",
                "subprocess",
            )
        )
    for path in (source_root / "kultrun" / "adapters" / "verification").rglob("*.py"):
        problems.extend(
            _imports_named(
                path,
                "subprocess",
                "kultrun.execution",
                "kultrun.adapters.execution",
                "kultrun.model",
                "kultrun.resource",
                "kultrun.inference",
                "kultrun.planning",
            )
        )
    for path in (source_root / "kultrun" / "execution").rglob("*.py"):
        problems.extend(
            _imports_named(
                path,
                "kultrun.runtime",
                "kultrun.adapters.runtime",
                "kultrun.planning",
                "kultrun.model",
            )
        )
    for path in (source_root / "kultrun" / "adapters" / "execution").rglob("*.py"):
        problems.extend(
            _imports_named(
                path,
                "kultrun.runtime",
                "kultrun.adapters.runtime",
                "kultrun.planning",
                "kultrun.model",
            )
        )
    for path in (source_root / "kultrun" / "adapters" / "container").rglob("*.py"):
        problems.extend(
            _imports_named(
                path,
                "kultrun.runtime",
                "kultrun.adapters.runtime",
                "kultrun.planning",
                "kultrun.model",
                "kultrun.capacity",
            )
        )
    for path in (source_root / "kultrun" / "resource").rglob("*.py"):
        problems.extend(_imports_named(path, "kultrun.inference"))
    return problems
