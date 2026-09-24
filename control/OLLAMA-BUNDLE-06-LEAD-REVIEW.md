# Ollama Bundle 06 — Lead Review

**Reviewed final source:** `92555da8e3465cd1596098eb33579d31e1a12ae6`  
**Physical passing source:** `9813f72797875f21eaf68e43bb570784d8c37580`  
**Disposition:** ACCEPTED WITH CARRY-FORWARD KERNEL DURABILITY CORRECTION

## Product outcome accepted

Bundle 06 successfully closes the three Bundle-05 Ollama identity/source blockers
at the product level and advances the program into bounded AUTO fallback.

Accepted outcomes:
- `renv` runtime-environment identity and `fgen` Foundation-generation
  identity are now separate and correctly documented;
- provider Plan uses the verified `fgen`, not `renv`;
- provider Serve consumes an already verified current Ollama Foundation identity
  and refuses wrong generation/environment before residency/inference;
- explicit context 2048 qualification is generation-bound;
- one A40 physically proved Plan -> shared ResourceManager admission -> Serve ->
  exact digest inference -> STOP -> stale-generation refusal -> release ->
  post-release refusal;
- historical qualification schema v1 can be upgraded without strengthening what
  it proved;
- migrated old Ollama qualification remains unable to cover a provider Plan;
- STOP reconciliation can converge a lagged STOPPING instance to STOPPED without
  releasing its ResourceReservation;
- local AUTO policy prefers native/vLLM when supported/ready, selects Ollama only
  for policy-classified native unavailability, and explicit runtime choices
  fail closed;
- AUTO fallback is outside Serve and requires a fresh downstream provider chain;
- native and Ollama catalogs remain separate;
- no customer prompt/response content enters the decision/proof records;
- final source equals origin and the recovery checkpoint points at the final SHA.

## Physical evidence disposition

The Bundle-06 A40 proof is accepted as generation-bound evidence for the exact
tested:
- NVIDIA A40 environment;
- managed Ollama 0.34.3 generation;
- `smollm2:135m-instruct-q8_0` digest;
- context 2048;
- concurrency 1;
- source/wheel recorded in the physical evidence.

It does not qualify Ollama across NVIDIA and does not prove physical live
fallback.

Bundle-04/05 historical records are correctly weakened rather than rewritten:
they remain provider-functional evidence, not Foundation-generation-bound
evidence.

## AUTO fallback review

The new `foundation.runtime_choice` seam is aligned with the accepted product
policy.

Important positives:
- it is above Serve;
- it does not translate models across catalogs;
- it does not reuse native Plan/reservation/instance identities;
- unresolved/conditional states do not optimistically fall back;
- explicit vLLM/Ollama choices do not consult/switch to the other engine;
- Ollama AUTO selection declares full downstream recomputation.

This is correctly described as a **local control-plane policy**, not physical
live failover.

## K-03 / schema evolution review

The functional migration direction is correct:
- sequential explicit per-kind upgrades;
- unknown kinds/versions fail closed;
- old evidence migrates conservatively;
- FileStore rewrites the current representation on read;
- migration metadata contains no customer content.

Cursor correctly left K-03 OPEN because the original "before first schema bump"
timing condition was already missed historically.

### Carry-forward durability defect

The current FileStore migration sequence is:

```text
rewrite migrated record
 -> fsync record/directory
 -> append migration receipt
```

If the record rewrite succeeds but appending/fsyncing
`_schema_migrations.jsonl` fails:
- the `get()` call raises;
- the stored record is already current;
- the next read no longer detects a version change;
- therefore the missing migration receipt is not retried and can be lost
  permanently.

This means the implementation does not yet fully satisfy the stronger
requirement that a rewrite-on-read migration be **durably recorded**.

This does NOT invalidate:
- the migrated contract semantics;
- the A40 physical proof;
- the Ollama generation binding;
- the AUTO policy.

It remains a Kernel durability/debt issue and is appropriately contained by
K-03 remaining OPEN.

### Required carry-forward correction

In the next broader package:
- make migration rewrite + audit recording recoverable/convergent across either
  write failure;
- prove failure injection for record-write and audit-write failure;
- prove a later read can repair/retry any incomplete migration bookkeeping;
- avoid claiming atomicity unless it is actually provided;
- once the functional and durability conditions are accepted, Lead may revise
  K-03 from an impossible historical timing gate into a retired-late/historical
  governance record rather than keeping a never-retirable open item.

Exact mechanism is delegated to Cursor.

## Non-blocking observations for next depth

1. `RuntimeChoice` currently records support states and recompute scope, not
   concrete FoundationSelection/capacity evidence IDs. That is adequate for the
   bounded policy seam, but physical fallback/evidence should bind the choice to
   the concrete Foundation observations it consumed before a stronger support
   claim.

2. Provider Serve validates the verified Foundation at start. Replacement of
   the local daemon after start but before inference remains within the known
   trusted-local / unauthenticated-loopback enforcement debt; do not overclaim
   hard local-process isolation.

3. One archive-progress test failed once under load and passed on rerun. No
   product defect is established from one occurrence; watch for recurrence.

## Product Vision alignment

ALIGNED:
- self-hosted/local execution;
- one global ResourceManager authority;
- separate model catalogs;
- exact runtime/model identity;
- provider replaceability;
- no hidden Serve fallback;
- no premature model equivalence;
- privacy-preserving evidence;
- explainable runtime choice;
- exoskeleton-first progression.

## Lead disposition

Bundle 06 main product work is ACCEPTED.

The checkpoint:
`checkpoint/ollama-generation-bound-serve-2026-09-24`
at `92555da8e3465cd1596098eb33579d31e1a12ae6`
is a valid recovery point for:
- generation-bound Ollama Serve;
- local bounded AUTO runtime-choice policy.

K-03 remains open and migration-audit durability is a carry-forward correction.

The Ollama macropath remains open because physical AUTO fallback and the
remaining Chunk-6 closure evidence have not yet been completed.

## Recommended next broader bundle

Next package should combine:
1. migration audit recoverability / K-03 functional closure decision;
2. bind runtime-choice evidence to concrete Foundation observations;
3. physical AUTO-selection/fallback acceptance on one bounded NVIDIA host;
4. healthy-primary proof and fallback-primary-unavailable proof;
5. at least one meaningful negative/excluded case;
6. comparative closure against the existing native-vLLM evidence;
7. exact Ollama macropath support boundary / closure decision;
8. standing AMD preflight only, with no AMD Pod unless the existing policy gates
   permit it.

Do not broaden into multi-model, live request-failure switching, UI, fleet,
Dynamo, or generic workload scheduling.
