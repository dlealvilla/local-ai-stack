"""Development-only estimator comparison. Not a product command.

Runs the same ModelEstimationRequest through KultrunRequirementEstimator
and LlmfitRequirementEstimator, then reports differences. Thresholds live
here, never in SelectionPolicy.

    python tools/compare_model_estimators.py
    python tools/compare_model_estimators.py --live
    python tools/compare_model_estimators.py \\
        --output validation/model-estimator-comparison.json

`--live` invokes the real llmfit executable. The default replays captured
plan JSON so CI stays offline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from kultrun.adapters.estimators.kultrun import KultrunRequirementEstimator
from kultrun.adapters.estimators.llmfit import (
    TESTED_VERSION,
    LlmfitRequirementEstimator,
    detect_version,
    fixture_plan,
)
from kultrun.adapters.model_source.candidates import (
    PROVIDER_VERSION,
    packaged_candidates,
)
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.model.contracts import (
    MemoryPlacement,
    ModelCatalogEntry,
    ModelEstimationRequest,
    ModelRequirement,
)

REPOSITORY = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPOSITORY / "tests" / "fixtures" / "estimators" / "llmfit"
GiB = 1024**3

#: Relative difference = (max - min) / max when max > 0.
GOOD_RELATIVE = 0.15
WARNING_RELATIVE = 0.35

SAFE_VRAM_FIXTURE_BYTES = 24 * GiB
PREFERRED_MIN = 0.20
PREFERRED_MAX = 1.00

LOAD_BEARING = (
    "ram_bytes",
    "estimated_vram_bytes",
    "vram_weights_bytes",
    "vram_overhead_bytes",
    "vram_kv_bytes_per_token",
)


def estimation_request(
    entry: ModelCatalogEntry,
    *,
    placement: MemoryPlacement = MemoryPlacement.DISCRETE_GPU,
    runtime: str = "vllm",
) -> ModelEstimationRequest:
    """A comparison-tool request. Product planning supplies the selected runtime."""
    meta = entry.metadata
    req = entry.requirement
    context = (
        req.assumed_context_tokens
        if is_resolved(req.assumed_context_tokens)
        else meta.context_length_tokens
    )
    return ModelEstimationRequest(
        model_id=meta.model_id,
        source_ref=meta.source_ref,
        source_revision=meta.source_revision,
        artifact_format=NOT_PROVIDED,
        quantization=meta.quantization,
        context_tokens=context,
        runtime=runtime,
        placement=placement,
        offload_allowed=False,
        tensor_parallel=1,
        batch_size=1,
    )


def relative_difference(left: int, right: int) -> float:
    ceiling = max(left, right)
    if ceiling <= 0:
        return 0.0
    return (ceiling - min(left, right)) / ceiling


def classify_relative(relative: float) -> str:
    if relative <= GOOD_RELATIVE:
        return "GOOD"
    if relative <= WARNING_RELATIVE:
        return "WARNING"
    return "LARGE_DIFFERENCE"


def snapshot(requirement: ModelRequirement) -> dict[str, Any]:
    return {
        "provider": requirement.estimator_provider
        if is_resolved(requirement.estimator_provider)
        else None,
        "version": requirement.estimator_version
        if is_resolved(requirement.estimator_version)
        else None,
        "method": requirement.estimation_method
        if is_resolved(requirement.estimation_method)
        else None,
        "confidence": requirement.confidence.value,
        "measured": requirement.measured,
        "assumptions": list(requirement.assumptions),
        "ram_bytes": _maybe(requirement.ram_bytes),
        "vram_bytes": _maybe(requirement.estimated_vram_bytes),
        "weights_bytes": _maybe(requirement.vram_weights_bytes),
        "overhead_bytes": _maybe(requirement.vram_overhead_bytes),
        "kv_per_token_bytes": _maybe(requirement.vram_kv_bytes_per_token),
        "unified_bytes": _maybe(requirement.unified_memory_bytes),
        "context_tokens": _maybe(requirement.assumed_context_tokens),
        "storage_bytes": _maybe(requirement.storage_bytes),
        "peak_additional_bytes": _maybe(requirement.peak_additional_bytes),
    }


def _maybe(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _field(requirement: ModelRequirement, name: str) -> object:
    return getattr(requirement, name)


def compare_field(
    name: str, left: ModelRequirement, right: ModelRequirement
) -> dict[str, Any]:
    a = _field(left, name)
    b = _field(right, name)
    a_ok = isinstance(a, int)
    b_ok = isinstance(b, int)
    if not a_ok and not b_ok:
        return {
            "field": name,
            "kultrun": None,
            "llmfit": None,
            "classification": "UNAVAILABLE",
            "notes": ["both unresolved"],
        }
    if not a_ok or not b_ok:
        missing = "kultrun" if not a_ok else "llmfit"
        return {
            "field": name,
            "kultrun": a if a_ok else None,
            "llmfit": b if b_ok else None,
            "classification": "UNAVAILABLE",
            "notes": [f"{missing} unresolved"],
        }
    assert isinstance(a, int)
    assert isinstance(b, int)
    kultrun_bytes, llmfit_bytes = a, b
    low = min(kultrun_bytes, llmfit_bytes)
    high = max(kultrun_bytes, llmfit_bytes)
    relative = relative_difference(kultrun_bytes, llmfit_bytes)
    return {
        "field": name,
        "kultrun": kultrun_bytes,
        "llmfit": llmfit_bytes,
        "min_estimate": low,
        "max_estimate": high,
        "difference": high - low,
        "relative_difference": relative,
        "lower_provider": "kultrun" if kultrun_bytes <= llmfit_bytes else "llmfit",
        "upper_provider": "llmfit" if kultrun_bytes <= llmfit_bytes else "kultrun",
        "classification": classify_relative(relative),
        "notes": [],
    }


def capacity_impact(vram: int | None) -> dict[str, Any] | None:
    if vram is None:
        return None
    ratio = vram / SAFE_VRAM_FIXTURE_BYTES
    if ratio > PREFERRED_MAX:
        band = "exceeds_safe"
    elif ratio < PREFERRED_MIN:
        band = "underutilized"
    else:
        band = "preferred"
    return {
        "safe_vram_bytes": SAFE_VRAM_FIXTURE_BYTES,
        "required_vram_bytes": vram,
        "utilization": ratio,
        "band": band,
    }


def assumption_mismatch(
    request: ModelEstimationRequest, left: ModelRequirement, right: ModelRequirement
) -> list[str]:
    notes: list[str] = []
    for requirement, label in ((left, "kultrun"), (right, "llmfit")):
        method = requirement.estimation_method
        if is_resolved(method) and method in {"unsupported", "provider-unavailable"}:
            notes.append(f"{label}: {method}")
        if (
            is_resolved(requirement.assumed_context_tokens)
            and is_resolved(request.context_tokens)
            and requirement.assumed_context_tokens != request.context_tokens
        ):
            notes.append(f"{label} substituted context")
    return notes


def compare_pair(
    entry: ModelCatalogEntry,
    kultrun: ModelRequirement,
    llmfit: ModelRequirement,
    request: ModelEstimationRequest,
) -> dict[str, Any]:
    fields = [compare_field(name, kultrun, llmfit) for name in LOAD_BEARING]
    mismatches = assumption_mismatch(request, kultrun, llmfit)
    vram = compare_field("estimated_vram_bytes", kultrun, llmfit)
    kultrun_impact = capacity_impact(_maybe(kultrun.estimated_vram_bytes))
    llmfit_impact = capacity_impact(_maybe(llmfit.estimated_vram_bytes))
    crossed = False
    if (
        kultrun_impact is not None
        and llmfit_impact is not None
        and kultrun_impact["band"] != llmfit_impact["band"]
    ):
        crossed = True
        if {kultrun_impact["band"], llmfit_impact["band"]} & {"exceeds_safe"}:
            vram.setdefault("notes", []).append(
                "ESTIMATORS CROSS THE FEASIBILITY BOUNDARY"
            )
    overall = "UNAVAILABLE"
    if mismatches:
        overall = "ASSUMPTION_MISMATCH"
    elif vram["classification"] in {"GOOD", "WARNING", "LARGE_DIFFERENCE"}:
        overall = vram["classification"]
    elif any(item["classification"] == "LARGE_DIFFERENCE" for item in fields):
        overall = "LARGE_DIFFERENCE"
    elif any(item["classification"] == "WARNING" for item in fields):
        overall = "WARNING"
    elif any(item["classification"] == "GOOD" for item in fields):
        overall = "GOOD"
    meta = entry.metadata
    return {
        "logical_name": meta.logical_name.value,
        "source_ref": meta.source_ref,
        "revision": meta.source_revision if is_resolved(meta.source_revision) else None,
        "quantization": meta.quantization if is_resolved(meta.quantization) else None,
        "context_tokens": request.context_tokens
        if is_resolved(request.context_tokens)
        else None,
        "runtime": request.runtime if is_resolved(request.runtime) else None,
        "placement": request.placement.value,
        "kultrun": snapshot(kultrun),
        "llmfit": snapshot(llmfit),
        "fields": fields,
        "overall_classification": overall,
        "assumption_mismatch": mismatches,
        "capacity_impact": {
            "kultrun": kultrun_impact,
            "llmfit": llmfit_impact,
            "crosses_feasibility_boundary": crossed,
        },
    }


def compare_catalog(
    *,
    live: bool = False,
    kultrun_estimator: KultrunRequirementEstimator | None = None,
    llmfit_estimator: LlmfitRequirementEstimator | None = None,
) -> dict[str, Any]:
    entries = packaged_candidates()
    kultrun_est = kultrun_estimator or KultrunRequirementEstimator(entries)
    if llmfit_estimator is not None:
        llmfit_est = llmfit_estimator
        llmfit_version = llmfit_estimator.version
        mechanism = "injected"
    elif live:
        llmfit_est = LlmfitRequirementEstimator()
        llmfit_version = detect_version() or TESTED_VERSION
        mechanism = "subprocess llmfit plan --json"
    else:
        llmfit_est = LlmfitRequirementEstimator(
            plan=fixture_plan(FIXTURE_ROOT), version=TESTED_VERSION
        )
        llmfit_version = TESTED_VERSION
        mechanism = "captured fixture plan JSON"
    comparisons = []
    for entry in entries:
        request = estimation_request(entry)
        comparisons.append(
            compare_pair(
                entry,
                kultrun_est.estimate(request),
                llmfit_est.estimate(request),
                request,
            )
        )
    return {
        "purpose": "development-only estimator cross-validation",
        "product_feature": False,
        "thresholds": {
            "good_relative": GOOD_RELATIVE,
            "warning_relative": WARNING_RELATIVE,
            "scheme": "GOOD <= 15%; WARNING <= 35%; else LARGE_DIFFERENCE",
            "relative": "(max - min) / max when max > 0",
        },
        "kultrun_estimator_version": PROVIDER_VERSION,
        "llmfit_version": llmfit_version,
        "llmfit_mechanism": mechanism,
        "candidate_count": len(entries),
        "comparisons": comparisons,
    }


def _git_head() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPOSITORY,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "DEVELOPMENT-ONLY estimator comparison (not a product feature)",
        f"Kultrun estimator {report['kultrun_estimator_version']}  "
        f"llmfit {report['llmfit_version']}  via {report['llmfit_mechanism']}",
        f"thresholds: {report['thresholds']['scheme']}",
        "",
    ]
    for item in report["comparisons"]:
        lines.append(
            f"{item['logical_name']}  {item['quantization']}  "
            f"ctx {item['context_tokens']}  {item['runtime']}"
        )
        lines.append(
            f"  overall {item['overall_classification']}"
            + (
                "  ASSUMPTION MISMATCH: " + "; ".join(item["assumption_mismatch"])
                if item["assumption_mismatch"]
                else ""
            )
        )
        for side in ("kultrun", "llmfit"):
            snap = item[side]
            lines.append(
                f"  {side}: RAM {_fmt(snap['ram_bytes'])}  "
                f"VRAM {_fmt(snap['vram_bytes'])}  "
                f"weights {_fmt(snap['weights_bytes'])}  "
                f"overhead {_fmt(snap['overhead_bytes'])}  "
                f"kv/token {_fmt(snap['kv_per_token_bytes'])}  "
                f"{snap['confidence']}/{snap['method']}"
            )
        vram = next(
            field
            for field in item["fields"]
            if field["field"] == "estimated_vram_bytes"
        )
        if vram["classification"] not in {"UNAVAILABLE"}:
            lines.append(
                f"  VRAM delta {vram['difference']} B  "
                f"relative {vram['relative_difference']:.1%}  "
                f"{vram['classification']}  "
                f"lower {vram['lower_provider']}  upper {vram['upper_provider']}"
            )
        impact = item["capacity_impact"]
        if impact["crosses_feasibility_boundary"]:
            lines.append("  ESTIMATORS CROSS THE FEASIBILITY BOUNDARY")
        for side in ("kultrun", "llmfit"):
            used = impact[side]
            if used:
                lines.append(
                    f"  {side} vs 24 GiB SAFE VRAM: {used['utilization']:.1%} "
                    f"({used['band']})"
                )
        lines.append("")
    return "\n".join(lines)


def _fmt(value: int | None) -> str:
    if value is None:
        return "unknown"
    return f"{value / GiB:.3f} GiB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare Kultrun and llmfit estimates. Development only."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="invoke the real llmfit executable instead of captured fixtures",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write the JSON report (default: stdout text; JSON to this path)",
    )
    args = parser.parse_args(argv)
    report = compare_catalog(live=args.live)
    report["kultrun_commit"] = _git_head()
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(report, indent=2, sort_keys=True)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        report["report_sha256"] = digest
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.output} sha256 {digest}", file=sys.stderr)
    print(render_text(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
