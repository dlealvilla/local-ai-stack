"""Machine-readable Machi dependency law.

Machi production code must not import Kultrun. Kernel must not import
adapters, Install, or the composition root. Install may import Kernel
and must not import adapters or later Blocks.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

TIERS: dict[str, int] = {
    "kernel": 0,
    "install": 1,
    "adapters": 2,
    "main": 3,
}

FORBIDDEN_TOP_LEVEL = frozenset({"kultrun"})

FUTURE_PACKAGES = frozenset(
    {
        "discover",
        "steward",
        "capacity",
        "foundation",
        "model",
        "plan",
        "admit",
        "serve",
    }
)

KERNEL_POLICY_TOKENS = (
    "MACHI_STATE_ROOT",
    ".local/state/machi",
    "StateRootBinder",
    "KULTRUN_STATE_ROOT",
)


@dataclass(frozen=True, slots=True)
class ImportEdge:
    source_module: str
    source_package: str
    target_module: str
    line: int

    def describe(self) -> str:
        return f"{self.source_module}:{self.line} imports {self.target_module}"


def source_root() -> Path:
    return Path(__file__).resolve().parents[2] / "src" / "machi"


def _module_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root.parent)
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _package_of(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) < 2:
        return None
    if parts[0] != "machi":
        return None
    if len(parts) == 2 and parts[1] in {"main", "__main__"}:
        return "main"
    return parts[1]


def scan(root: Path) -> list[ImportEdge]:
    edges: list[ImportEdge] = []
    for path in sorted(root.rglob("*.py")):
        source_module = _module_name(path, root)
        source_package = _package_of(source_module)
        if source_package is None:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    edges.append(
                        ImportEdge(
                            source_module=source_module,
                            source_package=source_package,
                            target_module=alias.name,
                            line=node.lineno,
                        )
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                edges.append(
                    ImportEdge(
                        source_module=source_module,
                        source_package=source_package,
                        target_module=node.module,
                        line=node.lineno,
                    )
                )
    return edges


def violations(edges: Iterable[ImportEdge]) -> list[str]:
    found: list[str] = []
    for edge in edges:
        top = edge.target_module.split(".", 1)[0]
        if top in FORBIDDEN_TOP_LEVEL:
            found.append(
                f"{edge.describe()} (production Machi must not import kultrun)"
            )
            continue
        if top != "machi":
            continue
        parts = edge.target_module.split(".")
        if len(parts) >= 2 and parts[1] in FUTURE_PACKAGES:
            found.append(f"{edge.describe()} (future Block is not implemented)")
            continue
        target_package = _package_of(edge.target_module)
        if target_package is None:
            continue
        if edge.source_package not in TIERS:
            found.append(f"{edge.source_module} is in no Machi tier")
            continue
        if target_package not in TIERS:
            found.append(f"{edge.describe()} targets an unassigned Machi package")
            continue
        if TIERS[target_package] < TIERS[edge.source_package]:
            continue
        if TIERS[target_package] == TIERS[edge.source_package]:
            continue
        found.append(
            f"{edge.describe()} "
            f"(tier {edge.source_package} may not import {target_package})"
        )
    return found


def unassigned_packages(root: Path) -> list[str]:
    found = {
        child.name
        for child in root.iterdir()
        if child.is_dir() and not child.name.startswith(("_", "."))
    }
    assigned = set(TIERS) - {"main"}
    return sorted(found - assigned)


def kernel_policy_violations(root: Path) -> list[str]:
    """Kernel must not encode Install state-root policy."""
    kernel = root / "kernel"
    found: list[str] = []
    for path in sorted(kernel.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in KERNEL_POLICY_TOKENS:
            if token in text:
                found.append(f"{path.name} contains Install policy token {token!r}")
    return found
