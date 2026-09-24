# Ollama Execution Macropath Program

**Program ID:** `MACHI-OLLAMA-MACROPATH-001`  
**Starting checkpoint:** `checkpoint/native-vllm-partial-pass-2026-09-24`  
**Integration branch:** `automation/ollama-macropath`  
**Development style:** six substantial chunks, Lead Developer review between chunks.

## Product intent

Ollama is the second execution macropath under Machi/Kultrun. It is the compatibility/fallback path after the direct managed native-vLLM path.

The program must preserve two ideas at once:

1. Machi retains the filtering, governance, capacity, policy, global admission, identity, proof, evidence, and normalized analytics semantics learned from the native-vLLM macropath.
2. Machi must not reimplement or obstruct useful Ollama capabilities such as its integrated local runtime, model store, exact/specialist fit evaluation where available, runner/backend choice, GPU/CPU placement, load/unload, scheduling, and serving.

The design is therefore a **continuous Ollama execution tunnel** wrapped by Machi control-plane semantics.

## Runtime target

```text
MACHI OUTER CONTROL

Install / Discover / Steward / Capacity
              ↓
Foundation / macropath selection
              ↓
policy + coarse eligibility
              ↓
global resource authorization
              ↓
════════════ ENTER OLLAMA TUNNEL ════════════
local Ollama runtime / service
              ↓
Ollama model representation / model store
              ↓
Ollama specialist fit evaluation
              ↓
runner / backend choice
              ↓
GPU / CPU placement
              ↓
pull / load / unload
              ↓
local scheduling / residency
              ↓
serving API
              ↓
real inference
════════════ EXIT OLLAMA TUNNEL ═════════════
              ↓
Machi identity verification
              ↓
InferenceProof / Witness
              ↓
normalized macropath analytics
              ↓
empirical evidence
```

This is not a second control plane. It is a different execution realization under stable Machi semantics.

## Stable Machi authorities

These remain Machi-owned across vLLM, Ollama, and future Dynamo:
- install and host identity;
- hardware discovery and host truth;
- storage topology/ownership;
- SAFE capacity;
- policy and model intent;
- coarse eligibility;
- global resource authorization / ResourceManager;
- DeploymentConfiguration identity;
- deployment provenance;
- support claims;
- ReadinessProof and InferenceProof semantics;
- witness/evidence;
- normalized analytics schema.

External runtime-local discovery may be specialist evidence; it does not silently replace Machi global physical truth.

## Ollama-delegated responsibilities

Subject to Chunk-1 verification, the Ollama tunnel may own:
- local Ollama installation/runtime mechanics after Machi selects the path;
- local model representation, manifests, blobs, and store mechanics;
- supported model-format interpretation;
- specialist/exact fit evaluation exposed by Ollama;
- runner/backend choice;
- GPU/CPU placement and local memory allocation;
- model pull/load/unload/residency;
- local scheduling/concurrency mechanics;
- local serving implementation.

Machi should use these capabilities rather than duplicate them, while retaining the outer authorization boundary.

## Model-funnel principle

The funnel remains strong, but the evidence sources change.

```text
Machi catalog / policy / license / provenance
        ↓
cheap coarse eligibility
        ↓
host/storage/capacity plausibility
        ↓
Ollama tunnel candidate
        ↓
Ollama specialist compatibility / fit evidence
        ↓
Machi interprets evidence against approved envelope
        ↓
DeployableModels
        ↓
selection / Plan / ResourceManager
        ↓
authorized Ollama execution
```

Known impossible or disallowed models must be rejected before ordinary pull/load where available metadata can prove the answer.

Machi must not duplicate Ollama's exact fit algorithm merely to preserve the shape of the vLLM implementation.

## Analytics principle

Define one common analytics vocabulary behind a macropath adapter seam.

Candidate architecture:
- `MacropathAnalyticsAdapter`
- `NativeVllmAnalyticsAdapter`
- `OllamaAnalyticsAdapter`
- later `DynamoAnalyticsAdapter`

Every normalized metric carries a value plus explicit availability/provenance.

Required availability states should distinguish at least:
- `OBSERVED`
- `DERIVED`
- `ESTIMATED`
- `HIDDEN_INTERNAL`
- `NOT_EXPOSED`
- `NOT_APPLICABLE`
- `UNSUPPORTED`
- `UNRESOLVED`

A missing metric is not an ambiguous null.

Normalize, where meaningful:
- host/runtime/model identities;
- install/provision/start/load durations;
- model acquisition bytes/time;
- model fit verdict;
- estimated requirement;
- macropath-declared/specialist requirement where exposed;
- ResourceRequest / reservation;
- observed RAM/VRAM;
- context/concurrency;
- input/output tokens;
- TTFT;
- prompt evaluation duration/rate;
- generation duration/rate;
- end-to-end request latency;
- errors/retries;
- model residency/unload/reload;
- stop/restart/re-infer;
- cost/run duration.

The empirical-lab schema built during native-vLLM remains the development evidence spine. Extend it; do not create an Ollama-specific evidence database.

## Privacy/security constraints

This program is local self-hosted Ollama only.
- Ollama cloud models/services are outside this macropath.
- No long-lived cloud API key is required for the local happy path.
- Keep the local serving interface loopback/private by default.
- Do not store secrets or customer prompts/responses in empirical telemetry.
- Model license/provenance remains explicit Machi policy, even when Ollama metadata exposes license fields.

## Six development chunks

### Chunk 1 — Tunnel Boundary + Provider/Analytics Architecture Gate
No product implementation. No server.
- inspect actual repository seams;
- define exact Machi-vs-Ollama responsibility matrix;
- decide verified-existing vs managed Ollama installation policy;
- define tunnel input/output contracts;
- define exact model identity binding;
- define how Ollama specialist fit evidence becomes Machi feasibility evidence;
- define the common analytics adapter/availability model;
- identify canonical docs requiring correction;
- identify commercial/license/security implications;
- define physical qualification/model matrix;
- STOP for Lead review.

### Chunk 2 — Ollama Runtime Substrate / Foundation
Implement the front of the tunnel.
- managed and/or verified-existing local Ollama per approved Chunk 1;
- ownership, versioning, installation provenance;
- service lifecycle;
- environment/foundation identity;
- storage accounting;
- runtime verification;
- analytics for install/start/verify.
Exit: Ollama RuntimeCapability VERIFIED without a production model deployment.

### Chunk 3 — Model + Specialist Feasibility Bridge
Implement model intent binding into Ollama.
- Machi model identity ↔ exact Ollama representation/manifest/digest;
- policy/license/provenance;
- store accounting;
- coarse filters before pull;
- specialist compatibility/fit evidence;
- DeployableModels semantics;
- stale/runtime/model invalidation;
- analytics for funnel, pull, fit, quantization/format.
Exit: exact selected model binding and truthful Ollama deployability, no ordinary bypass.

### Chunk 4 — Machi Authorization Wrapper
Prove Plan/Admit remain generic around the continuous tunnel.
- DeploymentConfiguration;
- ResourceRequest;
- current Capacity;
- ResourceManager;
- ResourceReservation;
- approved envelope passed to the Ollama path;
- no duplication of Ollama internal scheduler;
- analytics for estimates/request/reservation/headroom.
Exit: admitted Ollama deployment, not yet physical product closure.

### Chunk 5 — Ollama Serve + Proof + Analytics
Complete the local inference tunnel.
- load/residency/lifecycle;
- ReadinessProof;
- real request InferenceProof;
- exact served model identity;
- normalized analytics adapter;
- stop/restart/re-infer semantics;
- explicit HIDDEN_INTERNAL/NOT_EXPOSED states.
Exit: local/fixture full Ollama vertical passes.

### Chunk 6 — Physical Qualification + Fallback + Comparative Closure
Use real NVIDIA hardware and the empirical lab.
- prefer hardware/models overlapping native-vLLM evidence where possible;
- multiple positive model cases;
- at least one meaningful negative/excluded case;
- real inference + restart/re-infer;
- compare vLLM vs Ollama on shared metrics;
- test AUTO: healthy supported vLLM preferred, Ollama fallback only when vLLM is unsupported/unhealthy according to approved Foundation policy;
- explicit VLLM and explicit OLLAMA fail closed rather than silently switching;
- fallback produces a new valid selection/plan/admission path, not a hidden Serve retry;
- exact support claims only.
Exit: Ollama macropath closed or truthfully partial.

## Review discipline

Every chunk:
- runs local gates;
- records evidence;
- ends with a bounded paste-back;
- updates stale canonical-doc recommendations;
- stops at architecture/product/provider/commercial decisions;
- does not automatically begin the next chunk until Lead review.

Use bounded decision branches when credible alternatives have materially different architecture/coupling.

## Failure discipline

Reuse the native-vLLM policies:
- model-specific failure → exact evidence + exclusion, not whole-path failure;
- product defect → fix owning layer locally, new SHA/artifact, rerun affected gates;
- provider/environment block → approved fallback or typed block;
- architecture/product/commercial question → DECISION_REQUIRED and STOP;
- unknown → unresolved, never optimistic PASS;
- no remote source patching;
- max 3 same-root automatic fix iterations per chunk.

## Strategic checkpoints

At the end of every chunk explicitly ask:
1. Did we accidentally duplicate a capability Ollama already performs better?
2. Did we accidentally surrender a Machi global authority?
3. Did we preserve early filtering without converting Machi into a second Ollama scheduler?
4. Did we keep analytics comparable to native vLLM?
5. Are hidden/internal macropath details represented explicitly rather than as ambiguous missing data?
6. Did any vLLM-specific assumption leak into a generic Machi contract?
7. Does the design still leave a credible path for a much larger future Dynamo tunnel?
