# OLLAMA CHUNK 1 — LEAD DECISION

**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Reviewed instruction:** `MACHI-OLLAMA-CHUNK-01-001`  
**Decision:** ACCEPTED WITH REQUIRED CORRECTIONS  
**Date:** 2026-09-24

## Accepted architecture

- Ollama is a continuous local execution tunnel under Machi control-plane semantics.
- Machi remains authoritative for host truth, ownership/storage truth, SAFE capacity, policy/provenance, DeployableModels, DeploymentConfiguration, ResourceRequest, ResourceManager admission, deployment identity, proof semantics, support claims, normalized analytics, and empirical evidence.
- Ollama may own its local runtime/daemon, model representation/store, runner/backend choice, GPU/CPU placement, pull/load/unload/residency, local scheduling, and serving mechanics.
- `FoundationEngine.OLLAMA` may be introduced. No new top-level macropath domain object is required.
- Linux/NVIDIA is the first implementation/qualification lane.
- Ollama Cloud is outside the local happy path.
- Docker/container execution stays deferred.
- AUTO fallback to Ollama is target policy only and remains inactive until Ollama independently qualifies.

## Required correction 1 — qualification must not become circular

Ollama has no documented dry-run fit API that provides the final specialist memory evidence before a load. The strong Machi funnel must therefore use a bounded qualification path rather than allowing normal deployment to load an unqualified model.

Target future flow:

```text
catalog
  -> cheap Machi filters
  -> coarse storage/capacity plausibility
  -> QualificationQueue
  -> bounded qualification ResourceRequest/Reservation
  -> Ollama acquisition if needed
  -> Ollama load/probe under that reservation
  -> specialist evidence + real token proof
  -> QualificationEvidence PASS/FAIL
  -> DeployableModels
  -> normal ModelSelection
  -> normal Plan
  -> normal ResourceManager admission
  -> normal Serve
```

A normal user deployment must not load merely to discover whether it is deployable.

## Required correction 2 — served identity

A mutable Ollama tag is not sufficient identity.

Target proof:
- Machi binds a requested Ollama name to an expected immutable digest after acquisition.
- Use a Machi-owned immutable binding/alias where practical.
- Verify the loaded digest immediately before request inference.
- Verify the digest again immediately after inference.
- The binding may not mutate while the ServingInstance exists.
- If Ollama later exposes the served manifest digest directly in a request result, the adapter may adopt it after review.

## Required correction 3 — two readiness layers

Foundation readiness:
- verified Ollama daemon on the approved private/loopback endpoint;
- exact approved version/build;
- cloud disabled;
- `/api/version` succeeds.

Deployment readiness:
- exact expected model digest is resident/loaded for the ServingInstance;
- deployment-specific readiness must not be satisfied by daemon health alone.

InferenceProof still requires a real request with generated output/tokens and matching identity.

## Required correction 4 — STOP vs RELEASE

Serving STOP unloads/ends residency but does not implicitly release a Machi ResourceReservation.

A valid still-held reservation may support restart if Plan and identities remain current. Release remains explicit.

## Required correction 5 — local API security boundary

Ollama's unauthenticated loopback API can be called by other trusted-local processes. Therefore the initial macropath may prove Machi governance for Machi-routed execution, but it must not claim hard enforcement against arbitrary local-process bypass.

Record this as explicit security debt/gate for multi-user/commercial hard-enforcement. Investigate stronger isolation later without blocking the bounded first Ollama macropath.

## Required correction 6 — version policy

Do not pin a prerelease by accident.

At Chunk-2 execution time:
- inspect the official Ollama release channel;
- select the latest **stable** supported release, not a prerelease, unless Lead explicitly approves otherwise;
- freeze its exact version and official asset SHA-256 in the Foundation recipe/generation;
- do not auto-update within a generation.

## Provider decisions

1. Verified-existing local Ollama: APPROVED.
2. Machi-owned managed-prefix Ollama: APPROVED as the intended product path, provided the official Linux artifact is safely relocatable under Machi-owned state without mutating `/usr`, global systemd, or unrelated host state.
3. If safe relocation is not possible: DECISION_REQUIRED. Do not silently install host-wide.
4. Ollama Cloud: OUT OF HAPPY PATH.
5. AUTO fallback: TARGET POLICY ONLY until independent Ollama qualification closes.
6. `FoundationEngine.OLLAMA`: APPROVED.

## Analytics refinements

Use one provider-neutral normalized vocabulary plus path-specific raw evidence.

Do not conflate:
- runtime-reported total duration with Machi end-to-end request latency;
- Ollama `size_vram` with externally observed peak VRAM;
- specialist fit evidence with ResourceManager authorization.

Prefer Machi external timing for comparable TTFT/end-to-end latency when technically observable. Preserve runtime-native metrics as raw provenance.

## Chunk 2 authorization

Chunk 2 may now implement the Ollama Runtime Substrate / Foundation under the accepted decisions above.

It must not:
- download model weights;
- run ordinary model inference;
- create a physical GPU server;
- mutate `/usr` or global systemd;
- enable Ollama cloud;
- activate AUTO fallback.

