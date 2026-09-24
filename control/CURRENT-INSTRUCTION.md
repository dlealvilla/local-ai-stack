# CURRENT LEAD DEVELOPER INSTRUCTION

**Instruction ID:** `MACHI-OLLAMA-CHUNK-02-001`  
**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Chunk:** 2 of 6 — Ollama Runtime Substrate / Foundation  
**Mode:** BOUNDED PRODUCT IMPLEMENTATION + LOCAL ACCEPTANCE  
**Physical server:** NO  
**GPU qualification:** NO  
**Model weights:** FORBIDDEN  
**Normal model inference:** FORBIDDEN  
**Integration branch:** `automation/ollama-macropath`  
**Recovery checkpoint:** `checkpoint/native-vllm-partial-pass-2026-09-24`

Read first:
- `control/OLLAMA-MACROPATH-PROGRAM.md`
- `control/OLLAMA-CHUNK-01-DECISION.md`
- canonical strategy/product/architecture/contracts/roadmap/telemetry docs
- current Foundation implementation and accepted native-vLLM/AMD environment evidence

The Lead has accepted Chunk 1 subject to the decision file. Those decisions are binding.

# 0. Objective

Implement the **front of the continuous Ollama tunnel** as a proper Machi Foundation provider without weakening generic Core semantics.

Chunk 2 must establish both:

1. a verified-existing local Ollama path; and
2. a Machi-owned managed-prefix path, **only if** the official stable Linux artifact can be safely realized under Machi-owned state without host-global mutation.

The chunk ends when Machi can truthfully produce a VERIFIED Ollama RuntimeCapability/Foundation generation locally through fixture/local acceptance, with no model pull and no inference.

# 1. Core product rules

Preserve:

```text
Install / Discover / Steward / SAFE Capacity
        ↓
FoundationSet
        ↓
FoundationSelection
        ↓
Ollama provider
        ↓
RuntimeInstallation
        ↓
RuntimeCapability VERIFIED
```

Do not implement Model, Plan, Admit, Serve, fallback, or physical qualification beyond the minimum generic seams required for Foundation identity.

Ollama is an integrated platform, not a vLLM mode flag.

# 2. Provider Selection Gate — already decided

Implement first coverage:

- OS: Linux
- accelerator/product lane: NVIDIA first
- execution: native process
- cloud: disabled
- bind: private/loopback only
- Docker: deferred
- AMD: deferred
- Windows/macOS: deferred

`FoundationEngine.OLLAMA` is approved.

Do not create a new top-level ExecutionMacropath domain object.

# 3. Stable release selection

At execution time, verify the **official Ollama release channel**.

Requirements:
- choose the latest supported STABLE release;
- reject prerelease/preview/nightly as the default;
- freeze exact version;
- freeze official Linux artifact identity and SHA-256/checksum provenance;
- record the release/source URL or canonical source identity in recipe provenance;
- no automatic update inside a Foundation generation.

If official release metadata/checksums are inadequate to create a reproducible pinned artifact, STOP `DECISION_REQUIRED`.

Do not hard-code v0.34.3 merely because Chunk 1 reviewed it.

# 4. Verified-existing provider

Implement a truthful verified-existing path.

Do not trust:
- process name alone;
- PATH presence alone;
- systemd unit name alone;
- container tag alone.

Verify at minimum:
- executable/service can be identified;
- exact version satisfies the pinned recipe policy;
- endpoint is loopback/private as required;
- cloud is disabled for the Machi happy path;
- `/api/version` responds consistently;
- local vs cloud/remote mode is distinguishable;
- runtime identity/provenance is recorded;
- observed configuration does not silently auto-update the current Machi generation.

If existing Ollama is incompatible, report typed unsupported/unverified state rather than repairing unrelated host state.

# 5. Machi-managed prefix provider

The intended product path is a Machi-owned environment analogous to the managed-runtime principles learned from AMD.

Target shape:

```text
<state-root>/foundation/environments/<environment-id>/ollama/
    bin / runtime assets
    config
    models/        reserved for later chunks
    logs/          bounded/owned if needed
    ownership metadata
```

First prove whether the official stable Linux artifact is safely relocatable.

The managed path MUST:
- remain under Machi-owned state;
- record ownership/installation generation;
- record exact artifact checksum/provenance;
- avoid `/usr`;
- avoid global systemd registration;
- avoid creation/mutation of unrelated global users where possible;
- avoid global `ldconfig` or shell-profile mutation;
- set any required `OLLAMA_MODELS` or related environment inside the owned environment;
- bind the daemon to loopback/private endpoint;
- disable cloud in the happy path;
- be startable/stoppable by Machi through the existing executor semantics;
- remain removable/reconcilable by ownership proof.

If the official artifact fundamentally requires host-global installation or cannot operate truthfully from an owned prefix:
- do NOT invent a brittle relocation hack;
- do NOT run the official installer into `/usr`;
- publish evidence;
- STOP `DECISION_REQUIRED_MANAGED_PREFIX`.

# 6. Daemon lifecycle semantics

Separate Foundation daemon lifecycle from later ServingInstance/model residency.

Chunk 2 may establish:

```text
Foundation daemon
  START
  VERIFY
  STOP
  RESTART
```

It must not imply:
- a model is loaded;
- a deployment is ready;
- inference is proven.

Foundation readiness requires:
- approved version/build;
- approved local endpoint;
- cloud disabled;
- successful `/api/version`;
- expected managed/verified-existing identity.

Do not call this `ReadinessProof` for a model deployment if the existing contract uses that term for Block 9.

# 7. Local API security boundary

Ollama's local API has no Machi authentication boundary.

For this chunk:
- keep endpoint loopback/private;
- do not widen `OLLAMA_HOST` to public interfaces;
- do not store an Ollama cloud API key;
- no cloud model path;
- record explicit debt: arbitrary trusted-local processes may bypass Machi by directly calling the local daemon.

Do not claim ResourceManager hard-enforces arbitrary local-process access to Ollama.

The debt must be visible in canonical debt/evidence after this chunk if canonical docs support such a record.

Do not solve the entire multi-user isolation problem in Chunk 2.

# 8. Qualification architecture — preserve, do not implement model execution yet

Chunk 1 exposed the fit-evidence circularity.

Do not load a model in Chunk 2.

Ensure any Foundation contracts introduced now leave room for this future bounded flow:

```text
QualificationQueue
  -> qualification ResourceRequest/Reservation
  -> Ollama pull/load/probe
  -> specialist evidence + token
  -> QualificationEvidence
  -> DeployableModels
```

Do not force normal DeployableModels membership before the qualification probe that earns it.

Do not implement an Ollama-specific second ResourceManager.

If current generic contracts make a bounded qualification reservation impossible without a major semantic redesign, report `DECISION_REQUIRED`; do not hide the issue in Foundation.

# 9. Foundation identity / invalidation

Define the material Ollama Foundation identity conservatively.

It should include enough to invalidate downstream evidence when the execution substrate materially changes, such as:
- exact Ollama version/build;
- managed vs verified-existing provider identity;
- pinned artifact/checksum where managed;
- relevant accelerator/runtime environment fingerprint;
- material cloud/local mode;
- other runtime facts proven load-bearing by the repository.

Do not put Ollama-only fields into generic Core unless there is a genuine cross-macropath concept.

Changing the Ollama Foundation generation must invalidate later qualification evidence just as native-vLLM generation changes do.

# 10. Foundation analytics adapter seam

Implement only the smallest common analytics substrate needed now.

Use a common normalized metric/availability representation behind the macropath adapter boundary.

Availability must distinguish:
- OBSERVED
- DERIVED
- ESTIMATED
- HIDDEN_INTERNAL
- NOT_EXPOSED
- NOT_APPLICABLE
- UNSUPPORTED
- UNRESOLVED

Chunk-2 Foundation metrics should include where truthful:
- macropath/foundation engine;
- provider mode: verified-existing or managed-prefix;
- runtime version/build;
- artifact/checksum provenance;
- installation/discovery duration;
- install footprint bytes;
- daemon startup duration;
- daemon verification duration;
- endpoint/bind mode;
- cloud-enabled/disabled state;
- stop/restart outcome;
- failure/refusal reason.

Do not add request-token or model-fit metrics yet except schema-compatible placeholders when required.

Preserve raw Ollama/provider evidence separately from normalized metrics. A normalized value must retain provenance.

# 11. Repository architecture audit before changes

Before implementation, audit for:
- vLLM-only enums that need an Ollama value;
- generic contracts polluted with vLLM argv/provider details;
- Plan/Serve imports that might accidentally be touched;
- assumptions that Foundation means Python environment;
- assumptions that one Foundation generation equals one serving process;
- hard-coded model-warehouse requirements not applicable to Ollama.

Make the smallest generic seam needed.

If the correct implementation would require changing Block ownership or ResourceManager semantics, STOP `DECISION_REQUIRED`.

# 12. Canonical documentation

This chunk MAY update canonical docs only for accepted truths proven by implementation.

At minimum reconcile:
- current native-vLLM physical state where stale;
- current vs target AUTO behavior:
  - CURRENT until Ollama qualifies: fail closed where Ollama unavailable/unqualified;
  - TARGET after Ollama closes: prefer supported healthy vLLM, otherwise supported Ollama;
- Ollama Foundation implementation status after this chunk;
- explicit local-API enforcement debt.

Do not mark Ollama model/Serve/fallback as implemented.

# 13. Local acceptance

No physical server is required.

Required local/fixture tests include at least:
- `FoundationEngine.OLLAMA` serialization/persistence/re-entry;
- verified-existing exact supported version PASS;
- wrong version refusal;
- prerelease refusal under stable-only policy;
- endpoint not loopback/private refusal;
- cloud-enabled refusal or explicit non-happy-path state;
- daemon unavailable;
- daemon version mismatch;
- managed-prefix ownership/provenance;
- checksum mismatch refusal;
- safe stop/restart of owned daemon via fixture/local process seam;
- managed environment never writes outside approved state root in tests;
- no model pull;
- no model load;
- no inference;
- existing vLLM tests remain green.

If a real Ollama binary is downloaded purely to validate relocatability, it must be the exact pinned stable runtime artifact, content-addressed/checksummed, used only for bounded local Foundation validation, and MUST NOT pull model weights. Record it as development evidence. If local platform is incompatible with the Linux artifact, use fixture/static inspection rather than pretending physical Linux proof.

# 14. Gates

Run:
- targeted tests;
- full Machi test suite;
- architecture boundary tests;
- ruff;
- scoped strict mypy used by the repository;
- packaging/isolated-wheel verification if product code changed.

Max three same-root local fix iterations.

No remote/server source patching.

# 15. Chunk-2 strategic checks

Before PASS answer explicitly:

1. Did we reuse Ollama's integrated platform rather than reconstruct it?
2. Did we keep Machi Foundation identity/provenance truthful?
3. Can the provider be managed without host-global mutation?
4. Did we preserve the future bounded qualification reservation path?
5. Did we accidentally make daemon health equal deployment readiness?
6. Did we overclaim local API enforcement?
7. Are Foundation analytics comparable to native-vLLM without pretending path-specific metrics are identical?
8. Did any Ollama-specific field leak into generic Core unnecessarily?
9. Does this still leave a credible future Dynamo tunnel?
10. Are current support claims exact and no broader than the evidence?

# 16. PASS criteria

`OLLAMA_CHUNK_2_PASS` requires:

- approved stable version frozen with provenance;
- verified-existing path implemented and tested;
- Machi-managed-prefix path implemented and tested, OR a clearly evidenced `DECISION_REQUIRED_MANAGED_PREFIX` if safe relocation is genuinely impossible;
- exact Foundation identity/generation and invalidation semantics;
- daemon local lifecycle verified without model load;
- loopback/private + cloud-off happy-path enforcement in provider configuration;
- common Foundation analytics seam implemented;
- all gates green;
- no model weights;
- no inference;
- no physical GPU server;
- native-vLLM behavior/regressions remain green.

If managed prefix is blocked but verified-existing passes, do not silently downgrade the product goal. Use the typed decision state.

# 17. Mandatory paste-back

Return the complete response bounded exactly by:

==================== BEGIN PASTE BACK — OLLAMA CHUNK 2 ====================

Include:

A. STATUS  
B. Starting SHA / branch / recovery checkpoint  
C. Stable Ollama release selected and official provenance/checksum evidence  
D. Repository architecture audit  
E. Files/contracts changed  
F. FoundationEngine/provider design  
G. Verified-existing implementation and tests  
H. Managed-prefix relocatability result  
I. Managed-prefix implementation and ownership  
J. Daemon lifecycle semantics  
K. Foundation identity/fingerprint/invalidation  
L. Security boundary and explicit debt  
M. Foundation analytics schema/adapter and availability states  
N. Qualification-path compatibility check  
O. Canonical doc updates  
P. Local test/gate results  
Q. Packaging/wheel SHA if built  
R. Strategic checks 1–10  
S. Decisions made within bounded authority  
T. DECISION_REQUIRED items  
U. Debt added  
V. Exact proposed Chunk-3 scope  
W. Exact branch/HEAD/final state

Then end with exactly one of:

`STOP — OLLAMA CHUNK 2 PASS. WAIT FOR LEAD REVIEW.`

or

`STOP — OLLAMA CHUNK 2 DECISION REQUIRED: <typed reason>. WAIT FOR LEAD REVIEW.`

or

`STOP — OLLAMA CHUNK 2 FAIL: <typed reason>. WAIT FOR LEAD REVIEW.`

==================== END PASTE BACK — OLLAMA CHUNK 2 ====================

Publish the paste-back through the existing GitHub handoff helper.

Do not begin Chunk 3.
