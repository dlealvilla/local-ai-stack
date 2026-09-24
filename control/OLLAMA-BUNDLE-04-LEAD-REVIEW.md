# Ollama Bundle 04 — Lead Review

**Reviewed final HEAD:** `ea9cb26a6034eeaca1058d6635ee4008fc833bed`  
**Physical passing source:** `e8bba2becd9b7e5244e987556c88812bad5895c0`  
**Disposition:** PRODUCT/FUNCTIONAL PHYSICAL PASS, QUALIFICATION-COVERAGE CORRECTION REQUIRED, SERVE AUTHORIZATION DECISION REQUIRED

## Product outcome achieved

Bundle 04 successfully moved the Ollama path from fixture-only behavior to a
real managed execution path on one disposable NVIDIA L40S host.

Physically demonstrated:
- Machi realized and verified managed Ollama 0.34.3 from its owned prefix;
- Ollama's own catalog supplied the exact provider model digest;
- ResourceManager created one temporary qualification hold from the remaining
  SAFE envelope;
- Ollama's provider-specific fit/load path was authoritative;
- Machi's shadow evaluator ran independently and did not veto/upgrade Ollama;
- the expected provider digest was resident before and after a real token probe;
- two real token probes completed;
- comparison analytics were durably journaled;
- cleanup proved residency absent before the ResourceManager hold was released;
- a second cold/re-entry qualification repeated the lifecycle;
- the owned RunPod was terminated and proved absent;
- the provider residency observation seam was added locally without becoming an
  authorization mechanism.

This is meaningful Stage-1 progress and validates the dual-evaluator product
philosophy.

## Delivery-process review

The broader execution-bundle approach worked as intended.

During physical acceptance Cursor discovered two implementation defects:
1. the official Ollama archive legitimately contains in-prefix soname symlinks;
2. runner executable bits needed to survive safe archive realization.

Both were implementation defects, not Product Vision or authority changes.
Cursor fixed them locally, rebuilt immutable wheels, redeployed, reran the
affected physical path, and preserved evidence of the failed attempts.

This is the desired fix-vs-architecture behavior.

## Blocking evidence-integrity correction

The physical run was invoked with Machi qualification context `2048`, and
that value was written into `OllamaQualificationEvidence` and its
qualification identity.

However, the real `LoopbackOllamaClient` did not send `options.num_ctx` in
either preload or token generation. Exact Ollama v0.34.3 source confirms that
when `num_ctx` is omitted Ollama may select its automatic/default context.
The physical runner reported `n_ctx_slot = 8192`.

Therefore:
- the physical run proves real managed Ollama FIT/token/identity/cleanup on this
  host and digest;
- it does **not** prove the configuration identified as context 2048;
- the two existing qualification records must not be treated as reusable
  context-2048 qualification coverage;
- the physical evidence document should describe them as provider-functional
  execution evidence at provider-selected effective context, not exact
  context-2048 coverage.

Before normal Ollama Plan/Serve may rely on qualification coverage:
- qualification must send the requested context through the public
  `options.num_ctx` field on the preload and token request;
- the same context must be material to the provider runner identity/reload
  behavior;
- a new physical qualification must prove the intended bounded context or fail
  closed if effective context cannot be established;
- old records remain historical lab evidence and are not rewritten into a
  stronger claim.

Concurrency 1 remains truthful because the campaign issued one request at a
time; no broader concurrency claim is earned.

## Non-blocking observations

- Initial preload `load_duration` was not exposed by these empty-generate
  responses. Keeping `load_seconds=not_measured` was correct.
- Two token-throughput observations differed materially (~100 vs ~395 tok/s).
  Preserving both without averaging or selecting a winner was correct.
- The native-vs-Ollama evidence is same GPU SKU class but different physical
  host, driver/runtime environment, and model representation. Cursor correctly
  avoided a runtime winner claim.
- zstd remains a host prerequisite debt and this host does not retire the
  general plug-and-play requirement.

## Long-lived Serve authorization decision

D (Ollama residency itself authorizes resources) is rejected by accepted
architecture.

C (a separate Ollama reservation type) is not recommended:
- provider leakage into the ledger;
- duplicated accounting/reconciliation concepts;
- poor scaling to additional providers;
- increased double-booking risk.

B (generic workload/deployment claim below Plan) is architecturally credible
but deeper than Stage-1 currently requires:
- it changes the shared workload ontology;
- it broadens beyond model-serving toward future training/indexing concerns;
- it requires wider native M8/M9 adaptation;
- it is valuable future-proofing but is the higher-complexity path.

### Lead recommendation: A, refined

Preserve `Plan` as the product concept: an immutable model-serving request
that asks ResourceManager for admission.

Do not pretend every Plan must cite a Machi ModelArtifact.

Add a sibling provider-owned deployment configuration/request for models whose
authoritative identity is supplied by a runtime catalog, initially Ollama:
- native configuration continues to cite ModelArtifact/revision;
- provider configuration cites provider + immutable provider digest +
  foundation/generation + execution fingerprint + bounded serving settings;
- tag/name is display/addressing data, never immutable identity;
- both produce holds in the existing `ResourceReservation` ledger;
- stale Capacity and one-ledger admission rules stay identical;
- existing native M8/M9 contracts and physical evidence remain valid;
- Ollama Serve verifies the expected digest before and after inference and
  treats residency as evidence, not authorization.

Recommended implementation direction, not a line-by-line mandate:
- add new versioned sibling plan/request contracts instead of overloading
  `artifact_id`;
- reuse/refactor ResourceManager's shared private placement logic;
- add the smallest provider Serve path or shared internal authorization seam
  needed to consume the sibling configuration;
- avoid creating a general training/indexing workload ontology in this stage.

Cursor may choose a cleaner bounded technical realization if it preserves these
semantics and explains the deviation.

## Product Vision alignment of recommended A

ALIGNED:
- self-hosted/customer controlled;
- one Machi global resource authority;
- runtime/provider mechanics remain replaceable adapters;
- no fake warehouse identity;
- native and Ollama catalogs stay separate;
- durable evidence and exact identity remain Machi product semantics;
- does not force future training/indexing concepts into the Stage-1 spine;
- keeps the path open to generalize later if a third workload/provider proves
  the abstraction is warranted.

## Next package after Lead decision

The next broader bundle should combine:
1. context-truth correction + local tests;
2. one short physical requalification at explicit context;
3. implementation of the selected long-lived authorization shape;
4. bounded Ollama Serve skeleton;
5. identity-before/after real inference;
6. reservation/cleanup/restart/re-entry QA;
7. durable Serve proof/analytics;
8. native regression gates.

It should stop before AUTO fallback or broader Chunk-5/6 closure.
