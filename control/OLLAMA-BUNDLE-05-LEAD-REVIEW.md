# Ollama Bundle 05 — Lead Review

**Reviewed final source:** `ebfabe56b2ae09b916e5e70ea4d2b1c028f48af6`  
**Physical passing source:** `9285af1057de2ed06f5d11090ee1459a1787ae1b`  
**Physical host:** one secure NVIDIA A40  
**Disposition:** PHYSICAL PRODUCT-LIFECYCLE PASS / SOURCE CLOSURE BLOCKED BY BOUNDED CORRECTIONS

## Product outcome that is genuinely achieved

Bundle 05 made a major Stage-1 step.

On one real A40 host the run demonstrated:
- explicit Ollama `num_ctx=2048` qualification;
- provider FIT and real inference at the requested context;
- provider-backed Machi Plan without fake ModelArtifact identity;
- admission through the existing global ResourceManager ledger;
- real Ollama serving under the admitted provider Plan;
- exact digest proof before and after inference;
- durable provider serving instance / inference proof records;
- STOP proving expected digest absence without releasing the reservation;
- restart/re-infer under the same still-held reservation;
- second STOP;
- explicit ResourceManager release;
- restart refusal after release;
- native Plan/Admit/Serve regression gates remaining green;
- the owned RunPod terminated and then returned 404.

This validates the accepted Option-A product philosophy.

## Delivery-process review

The broader execution bundle worked as intended.

The physical run exposed an Ollama unload/visibility lag. Cursor correctly
classified this as an implementation defect, changed STOP to poll bounded
`/api/ps` evidence for absence, rebuilt a new exact wheel, and reran the
acceptance path. It did not turn the provider race into a new architecture.

That is the desired autonomous fix behavior.

## BLOCKER 1 — Serve does not verify the actual planned Foundation generation

The provider Plan correctly contains:
- provider identity;
- Foundation/generation identity;
- execution-environment fingerprint;
- exact digest;
- context and qualification.

However, the provider Serve entry point accepts only:
`foundation_ready: bool`.

It does not receive and verify the current `OllamaSubstrate`,
`OllamaFoundationGeneration`, or equivalent verified runtime identity against
the Plan before establishing residency/inference.

The current checks prove:
- reservation matches the Plan;
- qualification covers the Plan;
- expected model digest is resident.

They do **not** prove that the daemon serving that digest is the exact verified
Foundation generation/environment cited by the Plan.

This is weaker than native Serve, which checks the real selected/generation
identity.

### Required correction

Before Bundle 05 can close:
- provider Serve must bind to a verified current runtime/Foundation identity,
  not a caller boolean;
- provider, generation id, and material execution-environment identity must
  match the provider Plan;
- a stale/different Foundation generation must refuse before residency/inference;
- local tests must prove the mismatch refusal;
- the correct physical path must prove the real current generation.

RECOMMENDED, not binding at code level:
pass a small provider runtime identity/substrate object into the provider Serve
authorization seam, or use the existing verified Ollama substrate directly.

Do not duplicate Ollama verification logic inside Serve.

## BLOCKER 2 — runtime-environment id and Foundation-generation id are conflated in physical evidence

The Bundle-05 physical report calls:
`renv_ceedac1939fecd21`
the "Foundation generation".

Repository truth distinguishes:
- `renv_...` = managed runtime-environment/artifact realization identity;
- `fgen_...` = verified Ollama Foundation generation identity, which includes
  the execution-environment fingerprint.

Bundle 04 and Bundle 05 report the same `renv_...` across different hardware,
which is correct for the same managed runtime artifact but is not a
hardware-bound Foundation generation.

### Required correction

Determine from raw/lab evidence whether the physical qualification/Plan actually
used the real `fgen_...` identity or the `renv_...` realization id.

- If the real `fgen_...` was used and only the report/paste-back label is
  wrong: correct the evidence docs and preserve the physical run.
- If `renv_...` was used as the qualification/Plan generation: the generation
  binding is not valid and a short physical requalification + Serve rerun is
  required after the source correction.

Do not infer or manufacture the missing fgen value from prose.

## BLOCKER 3 — schema-version compatibility governance is still unresolved

Bundle 05 changes `model.ollama_qualification` to schema version 2 and adds
`context_binding`.

The current registry contains the v2 contract, but the old
`model.ollama_qualification@1` contract is no longer registered for readback.

The repository's K-03 rule remains OPEN and explicitly requires a registered
upgrade/migration path before schema-version evolution ships.

This is not an Ollama architecture decision. It is an existing Kernel
compatibility obligation that is now directly relevant.

### Required correction

Before closing this source as a durable checkpoint:
- preserve truthful readback of historical v1 qualification records;
- implement the bounded schema-upgrade/migration mechanism required by K-03,
  rather than silently treating v1 as v2;
- v1 Ollama evidence must upgrade to a representation that preserves the fact
  that context was NOT sent and therefore cannot cover a provider Plan;
- prove v1 -> current read/upgrade in tests;
- preserve fail-closed handling of unknown versions;
- update/retire K-03 only when its stated condition is actually satisfied.

Technical implementation is delegated to Cursor within Kernel invariants.

## Accepted/non-blocking behavior

### Context truth
The actual public Ollama requests now carry `options.num_ctx`.
Physical evidence reports runner `-c 2048` and `n_ctx_slot=2048`.
That fixes the Bundle-04 context mismatch for this A40 run.

### One ResourceManager ledger
Provider and native admission use the same `ResourceReservation` records,
same active-hold sum, same reconciliation, and same release mechanism.

### Conservative full-SAFE reservation
The provider Plan reserves the full cited SAFE host and accelerator envelope.
That is conservative, but it matches the current native single-accelerator
Plan policy, which also places SAFE host/device ceilings into ResourceRequest.
This is not a new Ollama-only sizing regression.

### Separate catalogs / truthful identity
The provider Plan does not populate native `artifact_id`,
`immutable_revision`, or `dtype` with Ollama values.

### STOP vs release
The implementation preserves the accepted lifecycle distinction.

### Residency remains evidence
`/api/ps` and keep_alive do not become ResourceManager authorization.

## Carry-forward robustness, not a closure blocker

A failed provider STOP leaves the logical instance in STOPPING/failed state
while the reservation remains held. The next lifecycle package should exercise
explicit reconciliation/recovery from that state rather than assuming every
failed unload is terminal. Do not broaden this into scheduler ownership.

Journal append failure remains separate from the durable ProviderServeLog
operational records. If normalized analytics become mandatory for a support
claim later, expose analytics persistence failure explicitly rather than
silently equating inference success with analytics success.

## Product Vision alignment

The implementation remains aligned:
- self-hosted/local;
- one Machi resource authority;
- provider mechanics stay behind adapters;
- exact provider identity instead of fake warehouse identity;
- native and Ollama catalogs remain separate;
- customer content stays out of durable evidence;
- no premature generic training/indexing workload abstraction;
- no AUTO fallback yet.

## Lead disposition

Do not discard the A40 physical evidence.

It is valid evidence that the desired lifecycle can work on that exact host.

But do not close Bundle 05 as an accepted source checkpoint until:
1. Serve verifies actual current Foundation generation/environment;
2. renv-vs-fgen evidence identity is reconciled;
3. K-03 schema evolution compatibility is satisfied.

These are bounded corrections inside the already accepted Product Vision and
Option-A architecture. No new product decision is required.

## Next bundle recommendation

Use the broader-bundle model again.

The next package should begin with the three corrections above, then—if local
and physical correction gates pass—continue into the next adjacent Chunk-6
work rather than stopping after each fix.

A sensible package boundary is:
1. Foundation-generation binding correction;
2. schema migration/legacy v1 compatibility and K-03 retirement;
3. evidence identity repair;
4. short physical reproof if required;
5. provider Serve reconciliation/recovery hardening;
6. begin bounded AUTO fallback planning/implementation only within the already
   accepted rule: fallback is a new valid Foundation -> Plan -> Admit -> Serve
   path, never a hidden Serve retry;
7. STOP before broad multi-model/general production claims.
