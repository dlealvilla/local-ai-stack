# Stage 0.2 — Contracts that must exist before their subsystems

**Milestone 0 — Architectural kernel.** Second stage.

This file holds the **brief**, in the format of `docs/ROADMAP.md` Part V.
The output package required by Part II §4.9 is appended here when the stage
closes.

Status: **BRIEF — not yet implemented.**

---

## CURRENT STAGE

Stage 0.2 creates the tier-1 shared semantics and one `contracts.py` in
each owning domain package, for the concepts the roadmap names as
expensive to retrofit.

**This is the stage Milestone 0 warns about, by name.** The previous
attempt's `capacity_contracts.py` had 473 of its 640 lines rewritten
fourteen minutes after it was created, because it was written before
anything consumed it. Writing fifteen contracts with no callers is exactly
that situation, so the discipline below matters more here than anywhere
else in the milestone.

### What "minimal but intentional" means, concretely

A field belongs in v1 only if it passes one of three tests. Everything
else waits for the stage that consumes it.

1. **It is a distinction that would be collapsed if omitted.** The
   previous attempt kept `logical_name`, `model_id`, `provider`,
   `service_id` and `route_reason` separate and left the instruction not
   to merge them. Re-separating conflated identities after analytics is
   written is expensive; keeping them apart now costs nothing.
2. **It is host scoping or plurality.** `docs/ARCHITECTURE.md` Part II §6:
   Milestone 14 is an extension of these contracts only if they are
   host-scoped and plural from v1, and a rewrite of the whole control
   plane otherwise.
3. **It is an identity or reference another contract needs to point at.**
   Contracts reference by identifier, not by import (Law 2), so the
   identifiers have to exist.

A field that merely *will* be needed by Stage 2.3 does not qualify. It is
added by Stage 2.3.

**Why deferring is now safe rather than optimistic.** Stage 0.1's
fingerprint classifier treats adding an **optional** field to a shipped
contract as a compatible change, requiring no `schema_version` bump. Only
removing a field, retyping one, or restating its meaning is breaking. So a
contract that starts minimal and grows as its callers appear costs nothing
in version churn, while a contract that starts speculative and gets
corrected costs a version bump every time. The cheap direction is
deliberately the correct one.

**Unknown, not absent, for anything unmeasured.** Every field describing a
measured or externally supplied quantity is declared `Maybe[...]`. The
previous attempt's catalogue routinely carried `context_length: null` and
`download_bytes: null`, and the honest representation of that is "we do
not know", not "zero" and not "absent".

## PREDECESSOR OUTPUTS

`PlatformKernel v1`, Stage 0.1, checkpoint
`checkpoints/STAGE-0.1-platform-kernel.json`, contract surface token
`f4f256efb2541451`. Verified rather than assumed:

| Consumed | Provided by |
|---|---|
| `Contract` base and the `@contract` decorator | `kernel/schema.py` |
| The unresolved-value semantic and `Maybe[...]` | `kernel/unresolved.py` |
| `EntityId` and `Name` | `kernel/ids.py` |
| Typed errors with stable codes | `kernel/errors.py` |
| UTC-only timestamps | `kernel/clock.py` |
| The architecture test harness | `tests/architecture.py` |

The harness already asserts that every package has a tier assignment, so
each package created here must appear in `TIERS` or the build fails.

## THIS STAGE'S REQUIRED OUTPUT

`PlatformContracts v1` — the tier-1 semantics modules, plus a
`contracts.py` in each owning domain package.

### Tier 1 — shared semantics

| Module | Owns |
|---|---|
| `evidence` | `Basis` (reported, effective, safe, theoretical, observed, policy), `Confidence`, `Provenance`, the immutable fact envelope, and the three-layer value in which only *safe* authorizes |
| `policy` | What a policy is: identity, version, effective-at, and the determinism rule |
| `identity` | `Subject`, `AccessContext`, principal kinds |
| `entitlement` | `Entitlement` as generic feature and capacity claims |
| `audit` | `AuditEvent` — actor, action, target, decision, approval reference, outcome |

`evidence` is the highest-leverage module in this stage. Basis and
confidence appear on every leaf of every capacity structure later; if each
domain defines its own, the rule that only the safe layer may authorize
cannot be enforced anywhere.

### Domain contracts

| Package | Contracts |
|---|---|
| `host` | `HostCapabilities`, `HostFingerprint` |
| `storage` | `StoragePool` — plural from v1 |
| `capacity` | `CapacityEvidence` |
| `model` | `ModelMetadata`, `ModelArtifact`, `ModelRequirement`, `ModelInventoryRecord` |
| `resource` | `Workload`, `ResourceReservation`, `WorkloadProfile` |
| `inference` | `InferenceInstance` |
| `analytics` | `UsageEvent` |
| `knowledge` | `KnowledgeSource`, `KnowledgeItem` |
| `training` | `DatasetSnapshot`, `DerivedModel` |

Each package gets `__init__.py` and `contracts.py` only. No `ports.py`, no
logic, no reconciliation — those arrive with the stage that owns the
behaviour.

### Also produced

Two architecture checks that could not be written in Stage 0.1 because
they need contracts to inspect:

- **host scoping** — every host-scoped contract carries a host identifier,
  and every collection of host-scoped things is plural;
- **reference by identifier** — no contract field is typed as another
  domain's entity class.

## CORE CONTRACTS AFFECTED

All of them; none exists yet. Four decisions are worth stating before
implementation rather than discovering during it.

**The three-layer value is one type, owned by `evidence`.** `Reported`,
`Effective` and `Safe` recur for RAM, VRAM and storage, and the
authorization rule attaches to the type rather than to each use of it.
`capacity` and `storage` both build on it, which is why it sits at tier 1
below both.

**`UsageEvent` keeps five identities apart.** `logical_name`, `model_id`,
`provider`, `service_id` and `route_reason`, plus the later distinction
between `requested_model` and `actual_model`. This is the field set the
previous attempt explicitly warned against collapsing.

**`AuditEvent` is not `UsageEvent`.** Usage describes AI consumption;
audit describes administrative change. They share the kernel event
envelope and nothing else.

**`ModelRequirement` is host-independent.** What a model needs is a
property of the model. Where host and requirement meet is feasibility,
which belongs to `planning` at Milestone 3. Putting a host reference on
the requirement now would invert the dependency the tier order exists to
protect.

## ADAPTERS AFFECTED

None. This stage declares no ports and registers no implementations. A
`contracts.py` that needed an adapter would not be a contract module.

## PERSISTED STATE

None. These contracts describe state that later stages hold; no stage
before 0.3 writes anything. There is therefore no reconciliation
obligation here, and Part II §4.4 is satisfied vacuously rather than
skipped.

## MUTATION / FAILURE BOUNDARY

No mutation. Every failure mode is inherited from the kernel codec:
unregistered kind or version, unexpected or missing field, enumeration
member outside its declared set, naive timestamp, non-JSON-safe value.

What is new is **what fails closed by construction**: a quantity that was
not measured is `Maybe[...]`, so a consumer cannot read it as zero, and
cannot branch on it without either handling the unknown case or raising.

## CANCELLATION / CLEANUP

Not applicable. Nothing here runs, mutates, or can be interrupted.

## ACCEPTANCE LEVEL

**L1 — Contract**, and here the level is not a judgement call: contracts
that import no runtime and hold no state have nothing an L2 run would
reveal. The Milestone 0 gate is exactly this — contracts serialize without
importing a runtime or provider library.

Evidence required to close:

- every contract round-trips, including `Maybe[...]` fields carrying each
  unresolved reason;
- the fingerprint golden file is regenerated and reviewed, and every field
  states its meaning;
- `validate_registry()` passes across all of `kultrun.`;
- the architecture harness passes, now including host scoping and
  reference-by-identifier;
- contract isolation: each `contracts.py` imports only the kernel and
  lower-tier contracts;
- ruff clean, mypy strict clean.

The consolidation checkpoint at the end of Milestone 0 compares module
count against concept count. This stage adds thirteen packages, so it is
the first real test of that census.

## ADMIN SURFACE

Still no endpoints; Stage 0.3 builds them. What this stage adds is the
material: the kind registry can now enumerate a real contract catalogue,
which becomes the contracts endpoint, and `unresolved_fields()` over any
record becomes the honest "what we do not know" that the Admin console and
Admin Agent show rather than a blank.

## DEBT ENTRIES

Expected, to be confirmed at close:

| Item | Label | Retire when |
|---|---|---|
| Contracts are minimal and will grow as callers appear | `WORKING` | Not debt in itself; recorded because a reader may mistake a thin contract for an incomplete one. Growth is compatible by design |
| No contract has a second version, so `K-03` (no migration engine) stays untested | `PROVISIONAL` | Inherited from Stage 0.1; retires before the first version bump |

No entry here may authorize a mutation, because nothing here can mutate.

## DEFERRED ITEMS

- **Ports.** Every `ports.py` belongs to the stage that owns the
  behaviour behind it.
- **Capacity, feasibility and plan contracts.** `CapacityEnvelope` is
  Stage 1.2, `FeasibilityResult` and `DeploymentPlan` are Milestone 3.
  Each has a caller at its own stage and none has one here.
- **`ComponentManifest`.** The component seam is Stage 1.3.
- **Identity beyond `Subject`.** User, Group, Team, Application and
  `AccessPolicy` are Stage 5.1. `Subject` and `AccessContext` exist now
  because they are threaded through everything; the directory behind them
  is not.
- **`ModelOutcome`.** Milestone 11, once there is usage to describe.
- **Observed capacity fields.** Milestone 11. `CapacityEvidence` exists
  now to fix the shape of a provider's answer, not to be populated.

Per Part V's closing rule, none is necessary to produce this stage's
output.

---

## OUTPUT PACKAGE

*To be completed when the stage closes.*
