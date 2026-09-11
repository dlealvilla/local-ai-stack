# Stage 1.6R0 — Runtime breadth exoskeleton

**Milestone 1 — Walking skeleton (architecture increment, not 1.6L close).**

Status: **implementation on `stage/runtime-breadth-exoskeleton`.**
Does not close Stage 1.6L. Does not start 1.6M. Does not implement
llama.cpp or MLX.

Predecessor: 1.6L5 Manual capacity last-resort
`3aebeed39eeb1903915b654c45f4cb06b8911b51`.

```text
CURRENT STAGE                Three intended runtime families with one
                             active serving foundation per host.
                             Product preference after hard feasibility.
                             vLLM remains the only executable foundation.
PREDECESSOR OUTPUTS           1.6L5 last-resort manual + 20%×5 G-REPL
                             3aebeed.
THIS STAGE'S REQUIRED OUTPUT  FUTURE llama.cpp/MLX descriptors;
                             RuntimePreferencePolicy;
                             FoundationTransition;
                             one-active PRODUCT invariant.
CORE CONTRACTS AFFECTED      runtime.preference_policy@1;
                             runtime.preference_decision@1;
                             runtime.foundation_transition@1;
                             config.platform.foundation_comfortable_storage_bytes.
ADAPTERS AFFECTED            adapters/runtime/llama_cpp.py;
                             adapters/runtime/mlx.py
                             (declaration only).
PERSISTED STATE              still one FoundationSelection per host.
MUTATION / FAILURE BOUNDARY  FUTURE is not provisionable. AUTO does not
                             select unimplemented families. A second
                             live PRODUCT family is refused.
CANCELLATION / CLEANUP       Unchanged. Inactive installations may remain.
ACCEPTANCE LEVEL             L1. Not L2. Not T3. Not T5.
MUST NOT                     real llama.cpp; real MLX; runtime ranking
                             optimizer; merge to kultrun; RENT.
DEBT                         K-112 OPEN (families declared, not
                             executable). K-56 remains measured ranking.
```

## Families versus executability

```text
runtime family          vLLM | llama.cpp | MLX
implementation          provisioner / verifier / adapter / environment
FUTURE + production_candidate=false
    → AUTO excluded
    → is_provisionable false
    → launch refused
PRODUCT vLLM
    → candidate → feasible → recommended/selected → executable
```

Policy recommendation intent is not the currently executable set. Apple
Silicon product intent is MLX. With MLX unimplemented, production Apple
has no deployable foundation. That is truthful, not a fabricated MLX
path.

## Product preference (after hard feasibility)

```text
DISCOVER HOST + STORAGE TRUTH
        ↓
Apple Silicon?
    YES → MLX if hard-feasible else BLOCK
    NO  → vLLM / llama.cpp hard feasibility
                ↓
          neither BLOCK / one choose it / both:
            SAFE unresolved or SAFE < comfortable_storage_bytes
                → llama.cpp
            else vLLM
```

`comfortable_storage_bytes` defaults to 64 GiB of **SAFE** storage.
Configurable. Not feasibility. Not ResourceManager admission. Not
the 32 GiB Sonar tier.

AUTO follows the recommendation. MANUAL may hold another provisionable
candidate. MANUAL of a FUTURE family is refused. A selected but
unimplemented family must not proceed as VERIFIED.

## One active foundation

One current `FoundationSelection` per host. At most one PRODUCT serving
family may be live. Stored models, inactive installations, and historical
verification records may remain. Reference/TEST_ONLY harnesses are not
product foundations.

## Foundation transition

```text
same family (vLLM + model A → vLLM + model B)
    → existing model-switch lifecycle

different family (vLLM → llama.cpp)
    → foundation rebootstrap:
      stop live inference
      → release reservations
      → select foundation
      → realize or reuse installation
      → verify
      → recompute eligibility / requirement / Available Models /
        selection / DeploymentPlan / ResourceRequest
      → ResourceManager admission
      → launch
```

HostCapabilities and valid storage evidence may be reused when still
fresh. A family change does not by itself invalidate storage
characterization. G-REPL remains a storage-replan loop and does not
own runtime-family policy.

## Current executable path

vLLM still flows through host capabilities → resolution → managed
environment → verification → FoundationSelection → eligibility →
requirement → Available Models → selection → DeploymentPlan →
ResourceRequest → ResourceManager → InferenceInstance → Executor →
readiness/inference.

llama.cpp later plugs in as a PRODUCT descriptor plus provisioner,
verifier, GGUF eligibility, requirement, launch. MLX later plugs in as
a Darwin/arm64/Apple adapter with unified-memory requirements. This
stage does not implement those components.
