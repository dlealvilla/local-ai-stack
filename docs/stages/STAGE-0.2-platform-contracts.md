# Stage 0.2 — Contracts that must exist before their subsystems

**Milestone 0 — Architectural kernel.** Second stage.

This file holds the **brief**, in the format of `docs/ROADMAP.md` Part V.
The output package required by Part II §4.9 is appended here when the stage
closes.

Status: **CLOSED.** Brief below, output package at the end.

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

**Output:** `PlatformContracts v1` · **Acceptance:** `L1`, 196 tests passing ·
**Checkpoint:** `checkpoints/STAGE-0.2-platform-contracts.json`

Fourteen packages, thirty-one domain contracts, thirty-six in total with the
kernel's five. The brief said thirteen packages; it undercounted by one.

| Package | Tier | Contracts |
|---|---|---|
| `evidence` | 1 | `Provenance`, `LayeredBytes` |
| `policy` | 1 | `PolicyRef` |
| `identity` | 1 | `Subject`, `AccessContext` |
| `entitlement` | 1 | `Entitlement` |
| `audit` | 1 | `AuditEvent` |
| `host` | 2 | `HostCapabilities` and its six fact types |
| `storage` | 2 | `StoragePool` |
| `capacity` | 2 | `CapacityEvidence` |
| `model` | 3 | `ModelMetadata`, `ModelArtifact`, `ModelRequirement`, `ModelInventoryRecord` |
| `resource` | 4 | `Workload`, `WorkloadProfile`, `ResourceReservation` |
| `inference` | 6 | `InferenceInstance`, `InferenceEndpoint` |
| `analytics` | 6 | `UsageEvent` |
| `knowledge` | 7 | `KnowledgeSource`, `KnowledgeItem` |
| `training` | 7 | `DatasetSnapshot`, `DerivedModel` |

### The discipline, and where it was refined

The brief set a three-part test for whether a field belongs in v1. In
practice a fourth distinction did the most work, and it is worth recording
because it resolves a tension the brief did not anticipate.

**A specified field set is transcription; an unspecified one is
speculation.** `docs/PRODUCT_VISION.md` §8 enumerates what host inspection
must cover, §23 enumerates capacity evidence, §39 knowledge items, §46
usage events, §75 derived-model lineage. Writing those out is not guessing
at a future caller's needs — the constitution already decided them, and
deferring them would mean Stage 1.1 rediscovering a list that already
exists. Where the constitution is silent, the contract stays minimal:
`StoragePool` has eight fields, `PolicyRef` three.

Without that distinction the brief's rule would have forced
`HostCapabilities` to be an empty shell until Stage 1.1, and then required
a `schema_version` bump to fill it — churn with no reader benefit, since
nothing had shipped.

### Distinctions the contracts are built to preserve

Each of these is a conflation the previous attempt made, or was explicitly
warned against, and each has a test that fails if it is undone.

| Distinction | Where |
|---|---|
| Five identities on a usage event, plus requested versus actual model | `analytics` |
| Reported, effective and safe, with only safe authorizing | `evidence` |
| Whether an action was permitted, versus whether it worked | `audit` |
| Requested, admitted, observed and peak consumption | `resource` |
| Port reachable, versus API healthy | `inference` |
| Peak additional storage, versus installed size | `model` |
| Permission to retrieve, versus permission to train | `training` |
| Model requirement independent of any host | `model` |
| Mount facts as inspection, versus pool as allocatable capacity | `host` / `storage` |

### Two architecture checks added

Both needed contracts to inspect, which is why Stage 0.1 could not write
them.

**Reference by identifier** distinguishes an entity from a value object,
which turned out to be the load-bearing detail. A contract may embed
`Provenance` from another package, because a value object has no identity
to be referenced by; it may not embed `Subject`, because that would give
one thing's shape two owners. The rule is implemented as: a cross-package
contract field is a violation if the referenced contract carries its own
minted identifier. Verified by embedding `Subject` in a synthetic contract
and confirming the failure names the rule.

**Host scoping** asserts that the six host-scoped contracts carry a
`HostId`, and that `accelerators` and `mounts` are collections on a
reference host that has one of each. This is the whole of what keeps
Milestone 14 an extension rather than a rewrite.

Both discover contract modules from the tree rather than from a list, so a
new domain package is covered the moment it exists — the same property that
makes the tier-assignment check useful.

### Acceptance evidence

`L1`, 196 tests, ruff clean, mypy strict clean on 57 files.

Every contract round-trips, including unresolved values carrying each
reason. The registry-and-fingerprint test asserts the two mechanisms agree,
rather than checking a magic number that would drift.

One test was found to be order-dependent — contract registration is an
import side effect, so a check reading the registry saw only what happened
to have been imported. That is now fixed at the source: both the fingerprint
and the architecture checks import every `contracts.py` in the tree first.

### Debt

No new entries. Nothing here can mutate, so nothing here can authorize one.
`K-03` — no migration engine — remains the only entry with a hard deadline,
and it is now more load-bearing than it was: thirty-one contracts are at
version 1, and the first bump needs a migration path.

### Deferred

Ports, `CapacityEnvelope`, `FeasibilityResult`, `DeploymentPlan`,
`ComponentManifest`, the identity directory behind `Subject`, `ModelOutcome`
and observed capacity fields — each named in the brief with the stage that
owns it.

### What this stage does not prove

`L1`, and less than that suggests. These contracts have been serialized and
inspected; not one has been populated from a real host, a real model or a
real request. `HostCapabilities` describes a machine nothing has looked at
yet. The first evidence that any of these shapes is right arrives at the
Stage 1.1 gate, on hardware.
