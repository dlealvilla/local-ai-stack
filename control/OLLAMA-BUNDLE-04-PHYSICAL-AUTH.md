# Ollama Bundle 04 — Physical Qualification + Comparative Evidence + Residency Seam

**Status:** APPROVED EXECUTION PACKAGE  
**Starting accepted HEAD:** `4aa21ccabade398a8f931c5a231baed84bbf45f0`  
**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Execution policy:** `control/EXECUTION-BUNDLE-POLICY.md`

## Package objective

Move through several adjacent microlayers in one controlled run:

1. stabilize the real Ollama public-API/timing adapter;
2. prove one real managed Ollama qualification on a disposable NVIDIA host;
3. persist and inspect the first real Machi-shadow vs Ollama-authoritative
   comparison evidence;
4. prove bounded re-entry/cleanup behavior;
5. if physical qualification passes, build the provider-side residency
   observation/guard seam needed by long-lived Serve;
6. analyze the remaining long-lived ResourceManager authorization contract and
   continue only if no critical decision gate is crossed.

## Binding architecture

- Native/vLLM catalog remains Machi Model Warehouse.
- Ollama catalog remains Ollama-owned.
- Native qualification is Machi/native authoritative.
- Ollama specialist fit is authoritative on Ollama macropath.
- Machi shadow is analytics-only and cannot veto/upgrade Ollama.
- ResourceManager is the one global resource authorization ledger.
- Ollama owns private fit, placement, offload, runner and residency mechanics.
- Machi owns product policy, global authorization, durable evidence, identity
  verification, normalized analytics and support claims.
- No Ollama private scheduler logic may be copied into Machi.
- Customer content must not enter telemetry/evidence.
- This package uses one synthetic non-customer probe prompt only; do not persist
  prompt or generated response text.

## Physical lab posture

The physical run is acceptance evidence, not customer deployment.

Preferred test model:
`smollm2:135m-instruct-q8_0`.

Reason:
- small footprint;
- same SmolLM2 135M family as one native physical case;
- explicit instruct/quantized representation;
- exact local Ollama digest will be discovered after pull and is the identity.

Fallback if that exact tag is unavailable:
`smollm2:135m`.

Any fallback to a materially different family/size requires the physical record
to say the cross-runtime comparison is not like-for-like. Do not silently
substitute a large model.

The model pull is **operator lab setup only** in this package. It does not
constitute a supported Machi Ollama acquisition feature and does not authorize
changing product storage/acquisition ontology.

Prefer the exact L40S class previously used for native N2 when live RunPod stock
and price permit, because same-hardware evidence is more useful. If unavailable,
a different single NVIDIA Linux/x86_64 host within lab policy may be used.
Record the exact hardware and do not claim a same-host native/Ollama comparison.

## Carry-forward truth correction

Before physical evidence, `load_seconds` must represent the initial empty-
generate preload's `load_duration`, not the later warm token request's
`load_duration`.

The token request's own load duration may be retained as raw/provider-specific
evidence if useful, but must not be labeled initial load time.
