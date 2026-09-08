# Stage 1.6F — Runtime-aware Eligible Model View

**Milestone 1 — Walking skeleton.**

Status: **CLOSED — L1.** Checkpoint:
`checkpoints/STAGE-1.6F-eligible-model-view.json`.

This stage migrates live runtime/model compatibility onto the selected
fresh VERIFIED foundation. It does not reopen Stages 1.6B–1.6E.
It does not remap ModelRequirement or capacity. It does not infer.

UNKNOWN is never ELIGIBLE. MANUAL uses the selected candidate, never
the recommendation. Catalog metadata is not stamped. Inventory is not
mutated.

```text
CURRENT STAGE                Runtime-aware eligible model view.
                             Compatibility, not capacity.
PREDECESSOR OUTPUTS          Stage 1.6E CLOSED L1
                             (`bd9cdee29f385e3f284f5782443c31cf85d21438`).
THIS STAGE'S REQUIRED OUTPUT EligibleModelView; RuntimeEligibleModelCandidate;
                             ModelEligibilityService; vLLM interpreter;
                             API/CLI/Console; planning/admission consume
                             eligibility tokens.
CORE CONTRACTS AFFECTED      runtime.eligible_model_view@1;
                             runtime.eligible_model_candidate@1.
ADAPTERS AFFECTED            adapters/runtime/vllm (VllmModelCompatibility).
PERSISTED STATE              None. Derived view.
MUTATION / FAILURE BOUNDARY  GET only. No acquire, no admit.
CANCELLATION / CLEANUP       Read-only recomputation.
ACCEPTANCE LEVEL             L1 CLOSED. T0/T1 plus T2 clean-wheel
                             fixture chain. T3 not required.
ADMIN SURFACE                GET /v1/models/eligible;
                             kultrun models eligible;
                             Console Eligible models.
DEBT ENTRIES                 K-87 RETIRED. K-94 composition shim.
                             K-55, K-66, K-77, K-80, K-86 remain OPEN.
DEFERRED ITEMS               ModelRequirement + Capacity migration.
                             Authoritative selected DeploymentPlan
                             (K-86). Managed Python (K-66).
```

## Flow

```text
FoundationSelection
        ↓
selected RuntimeCandidate
        ↓
matching RuntimeInstallation
        ↓
fresh VERIFIED RuntimeCapabilityProfile
        +
RuntimeSupportDescriptor
        +
Global Model Catalog
        ↓
RuntimeEligibilityEvaluator
        ↓
EligibleModelView
        ↓
[STOP 1.6F]
```

Future, **not implemented here**:

```text
RuntimeEligibleModelCandidate
        +
fresh VERIFIED RuntimeCapabilityProfile
        +
deployment assumptions
        ↓
ModelRequirement
        ↓
CapacityAssessment
```

## View status

`CURRENT` requires current `FoundationSelection`, selected candidate,
matching INSTALLED installation, matching fresh VERIFIED profile.
`FoundationSelection.downstream_stale` is copied onto the view as
`foundation_stale` and does not by itself force STALE when that
verified path still matches (1.6E leaves `downstream_stale` true
after select+verify; treating it as view STALE would make CURRENT
unreachable without a GET mutation).

STALE: matching profile whose effective status is STALE (basis change),
or AUTO with recommended ≠ selected.

UNAVAILABLE: no selected candidate, no installation, missing / FAILED /
UNVERIFIED profile, or identity mismatch.

## Compatibility dimensions (vLLM 0.28.0)

Used when evidence exists: declared `supported_runtimes`, architecture,
quantization, artifact format, modality, preferred runtime version vs
profile version, GGUF-style quantization block in the adapter.

Missing declared support → UNRESOLVED. Positive incompatibility →
BLOCKED. No giant model-name table.

## Migration

Old authority: `planning.evaluate` intersected catalog
`supported_runtimes` with a caller `available_runtimes` list.

New authority: `ModelEligibilityService` → `EligibleModelView`.
Product API, CLI recommend/acquire --recommended, admission reserve,
and Console consume that view. Planning receives `CompatibilityVerdict`
tokens from composition (K-94).

## Must not

- Reopen or renumber 1.6B, 1.6C, 1.6D, or 1.6E
- `DeploymentFoundation` / `CompatibilityFramework` / `ModelMetadataV2`
- Remap ModelRequirement or Capacity
- Redesign ModelSelector
- Acquire, delete, or rank models
- Consult RAM, VRAM, disk, or reservations
- Treat UNKNOWN as ELIGIBLE
