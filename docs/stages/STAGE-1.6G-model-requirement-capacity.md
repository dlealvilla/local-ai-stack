# Stage 1.6G — ModelRequirement + Capacity Migration

**Milestone 1 — Walking skeleton.**

Status: **CLOSED — L1.** Checkpoint:
`checkpoints/STAGE-1.6G-model-requirement-capacity.json`.

This stage migrates existing `ModelRequirement` derivation and capacity
evaluation onto the selected fresh VERIFIED foundation. It does not
reopen Stages 1.6B–1.6F. It does not redesign ModelSelector. It does
not create DeploymentPlan authority. It does not infer.

ELIGIBLE is not FEASIBLE. BLOCKED models do not enter normal capacity.
UNRESOLVED models are not estimated as compatible. Catalog metadata is
not mutated.

```text
CURRENT STAGE                ModelRequirement + Capacity migration.
                             Eligibility, then requirement, then
                             capacity. Stop.
PREDECESSOR OUTPUTS          Stage 1.6F CLOSED L1
                             (`804c2bd3761918b802683c7fe83718fe6acfcc97`).
THIS STAGE'S REQUIRED OUTPUT ModelRequirement from ELIGIBLE candidate
                             + selected VERIFIED runtime; capacity fit
                             from remapped requirement; API/CLI/Console;
                             K-94 RETIRED.
CORE CONTRACTS AFFECTED      model.requirement@1 optional provenance
                             fields. No ModelRequirementV2.
                             No CapacityPlannerV2.
ADAPTERS AFFECTED            None. Estimator ports unchanged.
PERSISTED STATE              None. Derived assessments.
MUTATION / FAILURE BOUNDARY  GET only. No acquire, no admit.
CANCELLATION / CLEANUP       Read-only recomputation.
ACCEPTANCE LEVEL             L1 CLOSED. T0/T1 plus T2 clean-wheel
                             fixture chain. T3 not required.
ADMIN SURFACE                GET /v1/models/requirements;
                             kultrun models requirements;
                             Console selection capacity labels.
DEBT ENTRIES                 K-94 RETIRED. K-55, K-66, K-77, K-80,
                             K-86 remain OPEN.
DEFERRED ITEMS               ModelSelector + bounded model selection.
                             Authoritative selected DeploymentPlan
                             (K-86). ResourceManager request remap.
```

## Flow

```text
FoundationSelection
        ↓
fresh VERIFIED RuntimeCapabilityProfile
        ↓
EligibleModelView
        ↓
RuntimeEligibleModelCandidate
        ↓
ModelRequirement
        ↓
CapacityAssessment
        ↓
[STOP 1.6G]
```

Future, **not implemented here**:

```text
FeasibleModelCandidate[]
        ↓
ModelSelector
        ↓
selected model
```

## Requirement derivation

Normal derivation requires `RuntimeEligibleModelCandidate.status ==
ELIGIBLE`, a CURRENT eligible view, and a selected runtime from the
fresh VERIFIED profile. BLOCKED is refused. UNRESOLVED is not-ready.
STALE / FAILED / missing profile is not authoritative.

Estimator identity is `RuntimeCapabilityProfile.runtime` (and version
when known). Catalog `supported_runtimes[0]` is not identity.

Generic `ModelRequirement` stays runtime-neutral: no vLLM CLI flags,
Docker arguments, or executor flags. Optional provenance fields:
`assumed_runtime`, `assumed_runtime_version`, `requirement_basis`.

Estimator architecture is unchanged: AUTO, typed failure, no shopping.

## Capacity

Existing SAFE math is reused. PREFERRED / UNDERUTILIZED map to
feasible; EXCEEDS_SAFE to infeasible; unknown load-bearing to
unresolved. BLOCKED / UNRESOLVED eligibility is `not_assessed`, not
a silent fit.

Free VRAM and ResourceManager reservations do not change runtime
eligibility. Planning capacity uses the envelope SAFE slice, not
reservation subtraction.

## K-94

Removed omit-mapping `COMPATIBLE` defaults from `recommend()`,
`evaluate()`, and admission. Missing mapping is `UNRESOLVED`.
Composition still copies EligibleModelView into planning tokens
because planning cannot import runtime. That copy is architecture,
not a compatibility default.

`plan_for_entry` still estimates numeric amounts for admission until
ResourceManager remap. Ranking and CapacityAssessment skip those
models.

## Must not

- Reopen or renumber 1.6B–1.6F
- `ModelRequirementV2` / `CapacityPlannerV2` / `DeploymentPlan` authority
- Redesign ModelSelector
- Remap ResourceManager or InferenceInstance
- Use `supported_runtimes[0]` as estimator identity
- Treat ELIGIBLE as FEASIBLE
- Treat UNRESOLVED as FEASIBLE
