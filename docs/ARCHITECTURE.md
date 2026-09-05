# KULTRUN
## Company Brain Platform — Module Architecture

**Purpose:** Define Kultrun's macrostructure — what modules exist, what
each one owns, what it consumes, what it produces, which adapter seams it
defines, and which module may import which.

**Authority:** Authoritative for **module boundaries, concept ownership,
dependency direction and the composition root**. It is not authoritative
for product intent (`docs/PRODUCT_VISION.md`) or for build sequence and
gates (`docs/ROADMAP.md`). Where this document and the constitution
disagree about what a concept *means*, the constitution wins. Where this
document and the roadmap disagree about *when* something is built, the
roadmap wins.

**Why it exists:** `docs/PRODUCT_VISION.md` §125 Rule 1 requires the
complete skeleton to be designed before deep implementation, and
`docs/ROADMAP.md` Part I §3 states the sequencing rule as "design the
whole skeleton on paper, build it thin end-to-end, then deepen it." The
constitution designs the *system*. The roadmap orders the *work*. Neither
states the *module map*, and the previous attempt's most expensive failure
was structural: concepts lost their owners. This document is the missing
piece.

---

# PART I — WHAT THIS STRUCTURE IS CORRECTING

The previous attempt's structural failure is measurable, and each
correction below is a response to a specific measurement recorded in
`docs/ROADMAP.md` Part I.

| Measured outcome | Structural cause | Correction in this document |
|---|---|---|
| `core/` reached 152 files; 11 `storage_*` and 15 `model_*` modules, with `storage_capacity`, `_cache`, `_calibration`, `_evidence` and `_resolution` side by side | A single flat namespace where a concept could be extended by adding a neighbouring file | Domains are **packages, not filename prefixes**. A prefix cannot sprawl silently when it is a package with a declared concept inventory and an explicit public surface. |
| Storage was 40% of `core/`; identity, gateway, usage and analytics had **zero** post-baseline changes | Nothing made the unbuilt parts of the skeleton visible | Every module below exists in the map from the first commit, even when empty. Absence becomes visible instead of invisible. |
| All seven adapter families together were under 800 lines while `core/` grew past 30,000 | The boundary between concept and implementation was conventional, not structural | `adapters/` is a **separate top tier that only the composition root may import**. A core signature that names an adapter type fails an architecture test. |
| Capacity observation **crashed** on an inventory record with a null management section, found only during integration | Capacity read model inventory directly, so a model-shaped defect became a capacity crash | `storage` and `capacity` **may not import `model`**. Platform-managed usage enters through a port that speaks only bytes-per-pool. |
| `capacity_contracts.py` had 473 of 640 lines rewritten 14 minutes after creation | Contracts were written in one place, far from the code that would consume them | Contracts live **inside the domain package that owns them**, next to their consumer. There is no central `contracts/` package. |
| The plan silently drifted: planned C7 became the real C8 | The document described intent, not structure | The dependency law in Part II is **mechanically checkable**, so drift fails a test rather than going unnoticed. |

One further correction concerns vocabulary. The governing rules say "core
owns concepts; adapters own implementations." In this document **core**
means every Kultrun-owned tier, 0 through 9 — the whole left-hand side of
the adapter boundary. **`kernel`** is the specific package at tier 0 that
holds mechanisms and no domain concept. Naming it `kernel` rather than
`core` is deliberate: the word `core` is what the previous attempt's
dumping ground was called.

---

# PART II — THE DEPENDENCY LAW

## 1. Tiers

Every module belongs to exactly one tier. Tiers are bands, not a total
order, and the law has two halves:

> **A module may import from any strictly lower tier, and never from a
> higher one. Within its own tier it may import only along an edge
> declared in §3.** Every intra-tier pair not declared there is a
> non-edge.

Stating it this way rather than banning intra-tier imports outright is
deliberate. Several genuine dependencies are intra-tier — `capacity`
needs `storage`'s evidence, `entitlement` needs `identity`, `api` needs
`platform` — and a law that forbade them would be quietly violated on the
first day. A short, explicit edge list is enforceable; a rule with silent
exceptions is not.

```text
TIER 0   kernel                                    mechanisms, zero domain
TIER 1   evidence · policy · identity ·            semantics every domain shares
         entitlement · audit
TIER 2   host · components · storage · capacity     what the machine is and can safely do
TIER 3   model                                      what can be served
TIER 4   planning ⟂ resource                        recommend  /  authorize
TIER 5   execution ⟂ runtime                        how to run  /  what to run
TIER 6   inference · analytics · gateway            serving and the record of it
TIER 7   knowledge · training · brains              organisational intelligence
TIER 8   platform · api                             control plane
TIER 9   agents · intelligence · vendor · install   consumers and additive intelligence
TIER 10  adapters                                   every third-party implementation
TIER 11  main                                       composition root
```

The tier number is not a build order. Tier 8 is built at Stage 0.3, and
tier 3 is not finished until Milestone 3. Tiers constrain **direction**;
`docs/ROADMAP.md` constrains **sequence**. Part V verifies the two are
compatible.

## 2. Four further laws

**Law 1 — Ports down, implementations up.** A domain declares the seams
it needs as ports in its own `ports.py`. Implementations live in
`adapters/`. Therefore a domain never imports its own implementations,
and dependency inversion happens at the composition root rather than
through a cycle.

**Law 2 — Contracts reference by identifier, not by import.** A contract
that needs to point at another entity holds that entity's id, not its
type. `UsageEvent` holds a model id, an instance id and a subject id; it
does not import `model`, `inference` or `identity`. This is what keeps
the contract graph a DAG instead of one tangled object model, and it is
what makes every contract serializable in isolation.

**Law 3 — Only the composition root imports `adapters`.** An adapter may
import any core tier. Nothing in tiers 0–9 may import tier 10. This is
the structural form of "no third-party technology may become the semantic
owner of a platform concept."

**Law 4 — Every module states what it does not own.** Each entry in
Part IV carries a *Must not* line. Those lines are the enforced non-edges
and the architecture tests in Part VII check them.

## 3. The declared intra-tier edges

This is the complete list. Any other intra-tier import is a violation.

| Tier | Permitted edge | Why |
|---|---|---|
| 1 | `entitlement` → `identity` | An entitlement is claimed by a subject. |
| 1 | `audit` → `identity` | An audit event records which actor did what. |
| 2 | `components` → `host` | Component compatibility is evaluated against host capabilities. |
| 2 | `storage` → `host` | Pool identity derives from reported mount facts. |
| 2 | `capacity` → `host` | The envelope interprets reported host values. |
| 2 | `capacity` → `storage.contracts` **only** | Capacity reads storage evidence as data. It must not reach probing, locking or mutation logic. |
| 6 | `gateway` → `inference` | Routing needs the endpoint registry. |
| 6 | `gateway` → `analytics` | Every request emits a usage event through a non-blocking sink. |
| 7 | `brains` → `knowledge` | A Team Brain scopes a knowledge domain. |
| 8 | `api` → `platform` | The API is a transport over control-plane services. |

`evidence`, `policy` and `identity` import nothing but `kernel`.
`inference` and `analytics` do not import each other. `training` imports
nothing else in tier 7.

## 4. Enforced non-edges

Two pairs must not know about each other at all. Each separation is a
constitutional requirement, and making it structural is what stops it
eroding under delivery pressure.

| Pair | Why they are peers | Consequence |
|---|---|---|
| `planning` ⟂ `resource` | "Resource Manager is authoritative for admission. Capacity Planner recommends." Recommendation and authorization must be independently auditable. | Neither imports the other. `platform` sequences plan → admit. |
| `execution` ⟂ `runtime` | "Executor and inference runtime are separate abstractions." Executor logic must not leak into runtime domain logic. | Neither imports the other. `inference` composes both. |

Three further non-edges matter enough to name explicitly:

- **`storage` and `capacity` may not import `model`.** Storage probing
  must not know model identities. Platform-managed usage enters storage
  through the `ManagedUsageSource` port, whose contract speaks bytes per
  pool and nothing else. `model` implements that port; storage never
  learns what the bytes are.
- **Nothing may import `intelligence`.** Every capability in Milestones
  11 and 12 enters through a port that already exists in a lower tier.
  The intelligence tier is therefore strictly additive, and "none of them
  may start early" becomes structurally true rather than merely
  instructed.
- **`agents` reaches the platform only through `api`.** The Admin Agent
  has no private back channel, because it has no import path to one.

## 5. Package shape

Every domain package has the same predictable shape, so that what a
domain owns is legible without reading its code:

```text
<domain>/
  __init__.py     explicit public surface; nothing else is importable by convention
  contracts.py    the platform-owned data contracts this domain owns
  ports.py        the adapter seams this domain declares
  <concept>.py    one module per concept, named for the concept
  reconcile.py    how this domain's persisted state recovers on restart
  health.py       what this domain reports to the platform health surface
```

`contracts.py` may import only `kernel` and lower-tier `contracts`
modules. `ports.py` may import only contracts. These two constraints are
what make the Milestone 0 gate — "contracts serialize without importing
any runtime or provider library" — checkable by a test rather than by
inspection.

A domain that holds no state has no `reconcile.py`. A domain that holds
state and has no `reconcile.py` is incomplete by `docs/ROADMAP.md`
Part II §4.4.

## 6. Two structural constraints that are expensive to retrofit

**Every host-scoped contract carries a host identifier from v1, and
every collection is plural from v1.** `HostCapabilities`, `StoragePool`,
`CapacityEnvelope`, `ResourceReservation`, `InferenceInstance` and
`InferenceEndpoint` are all host-scoped. Milestone 14 extends them into
`FleetState`, and the roadmap states that the multi-pool and
per-accelerator contracts exist "precisely so this is an extension." If
v1 assumes a single implicit host, Milestone 14 is a rewrite of every
capacity and lifecycle contract rather than an extension. The cost of
honouring this now is one field and a plural; the cost of retrofitting it
is the entire control plane.

**Unknown is a distinct value, not a null.** `docs/DEBT.md` rule 6
requires that consumers can tell "needs nothing" from "we do not know",
and the roadmap requires missing metadata to surface in
`unresolved_fields` rather than being filled in. A single unresolved-value
semantic therefore belongs in `kernel`, before any contract exists,
because the alternative is fifteen domains each inventing their own
convention for absence — which is Pattern 4 in a new costume.

---

# PART III — THE MAP

Read downward. Every arrow points from a module to something it may
import; nothing points upward.

```text
 11  main ─────────────── the only module that names a concrete adapter
       │
 10  adapters ─────────── implements ports declared in tiers 1–8
       │
  9  agents      intelligence      vendor      install
       │              │
       │              └─ implements: capacity.CapacityEvidenceProvider
       │                             gateway.Router
       │                             planning.Selector
       ▼
  8  api ──▶ platform ── sequences every domain's reconcile + health
                │
  7  brains ──▶ knowledge        training
       │
  6  gateway ──▶ inference ──▶ analytics
       │            │      (gateway emits; inference does not)
       │            ├──────────────┐
       ▼            ▼              ▼
  5              execution   ⟂   runtime
                    │              │
  4              resource   ⟂   planning
                    │              │
  3                    model ──────┘
                    │      │
                    │      └─ implements storage.ManagedUsageSource
                    ▼
  2  capacity ──▶ storage.contracts        components
       │              │                        │
       └──────────────┴──▶ host ◀──────────────┘
                            │
  1  evidence   policy   identity ◀── entitlement, audit
                            │
  0                      kernel
```

Two edges in this diagram carry most of the architecture's weight. The
first is `model` implementing `storage.ManagedUsageSource`: it is the
only path by which storage learns how much space the platform occupies,
and it carries no entity identity, so a defective inventory record can no
longer crash capacity observation. The second is the absence of an arrow
into `intelligence`: everything Milestones 11 and 12 add arrives through
a port that already exists beneath it.

---

# PART IV — MODULE INVENTORY

Each entry states what the module owns, what it consumes, what it
produces, the ports it declares, what it must not do, and the stage that
creates it.

## TIER 0

### `kernel`

Mechanisms shared by everything, and no domain concept whatsoever. The
test for membership: if a name in `kernel` could appear in a sentence
spoken to a customer, it does not belong here.

| | |
|---|---|
| **Owns** | Entity identity — opaque minted ids and validated external names, kept distinct. Schema versioning, the contract base and the registry of kinds. Typed errors with stable wire codes. The result envelope. The domain event envelope with a correlation identifier. The unresolved-value semantic. UTC-only platform time. The configuration mechanism. The adapter registry. The persistence boundary. |
| **Consumes** | Nothing internal. Standard library only. |
| **Produces** | `PlatformKernel v1` |
| **Ports** | `Store` · `Clock` |
| **Must not** | Contain any domain concept, import any third-party package, or know that models, hosts or capacity exist. |
| **Created** | Stage 0.1 |

Two distinctions inside `kernel` are load-bearing. **Minted identity
versus external name**: an `InstanceId` is opaque and platform-generated,
while `logical_name`, `model_id`, `provider` and `service_id` are stable,
externally meaningful names that the previous attempt correctly refused to
collapse into one field. They need different types and different
validation. **Correlation from the first event**: a request must be
traceable across gateway, inference, usage and analytics, and threading a
correlation id through a finished serving path later is expensive.

## TIER 1 — Shared semantics

### `evidence`

The vocabulary in which every capacity, requirement and feasibility claim
is expressed. `docs/ROADMAP.md` Part II §6 is this module's specification.

| | |
|---|---|
| **Owns** | `Basis` — reported, effective, safe, theoretical, observed, policy. `Confidence` — high, medium, low, and unknown as a first-class value. `Provenance` — producer, producer version, policy version, observed at. The immutable fact envelope. The three-layer value, and the rule that **only the safe layer may authorize**. |
| **Consumes** | `kernel` |
| **Produces** | The value types from which `CapacityEnvelope`, `StorageEvidence`, `ModelRequirement` and `FeasibilityResult` are built |
| **Must not** | Know what is being measured. It owns how a claim is qualified, never the claim. |
| **Created** | Stage 0.2 · **Deepened** 2.2 empirical, 3.2 providers, 11.1 observed |

Placing this at tier 1 is the single highest-leverage decision in the
map. Basis and confidence appear on every leaf of every capacity
structure; if each domain defines its own, the authorization rule cannot
be enforced anywhere.

### `policy`

| | |
|---|---|
| **Owns** | What a policy *is*: identity, version, provenance, effective-at, and the determinism rule that identical inputs under an identical policy version yield an identical decision. |
| **Consumes** | `kernel` |
| **Must not** | Contain any specific policy. Headroom belongs to `capacity`, retention to `analytics`, routing to `gateway`, access to `identity`. |
| **Created** | Stage 0.2 |

This module exists so that "facts are immutable; policy reinterprets
them" has a home. Every decision records the policy version that produced
it, which is what makes a stored fact survive a change of objective.

### `identity`

| | |
|---|---|
| **Owns** | `Subject`, `AccessContext`, principal kinds — user, group, team, application, administrator — and the shape by which access policy is referenced. |
| **Consumes** | `kernel` |
| **Ports** | `IdentityProvider` |
| **Must not** | Depend on the gateway, knowledge or analytics. One identity model serves all four. |
| **Created** | 0.2 contracts · 0.3 local administrator · **Deepened** 5.1 |

`Subject` exists at tier 1 from Stage 0.2 because identity received zero
attention in the previous attempt and would otherwise have to be threaded
through a finished gateway, analytics and knowledge layer. When SSO
arrives at Milestone 5, no consumer of `Subject` changes.

### `entitlement`

| | |
|---|---|
| **Owns** | `Entitlement` as generic feature and capacity claims, local verification, grace-period semantics, offline licence. |
| **Consumes** | `kernel` · `identity` |
| **Ports** | `EntitlementProvider` |
| **Must not** | Contain a marketing tier name, or require network access to verify. Renewal *transport* belongs to `vendor`. |
| **Created** | 0.2 contract · **Deepened** 9.3 |

Separating local verification from outbound renewal is what makes
air-gapped operation possible without a second licensing implementation.

### `audit`

| | |
|---|---|
| **Owns** | `AuditEvent` — actor, action, target, decision, approval reference, outcome — built on the kernel event envelope, plus its retention. |
| **Consumes** | `kernel` · `identity` |
| **Must not** | Be the same thing as `analytics`. Usage events describe AI consumption; audit events describe administrative change. Collapsing them loses both. |
| **Created** | **Recommended Stage 0.2**, emitted from Stage 1.5 onward · See Part VI |

The constitution requires that a deployment can eventually answer who
changed a setting, installed a model, modified a permission or approved an
agent action, and asks that the schema leave room for audit events even
when the UI comes later. No roadmap stage currently creates this. It is
recorded as a finding in Part VI.

## TIER 2 — The machine and what it can safely do

### `host`

| | |
|---|---|
| **Owns** | `HostCapabilities`: operating environment, CPU, memory, accelerators with per-device VRAM, unified-memory characteristics, mount facts, execution capabilities, networking and ports, driver hints. The host fingerprint, over stable facts only. `DeploymentProfile` and the support matrix. |
| **Consumes** | `kernel` · `evidence` |
| **Produces** | `HostCapabilities v1`, durable, versioned and fingerprinted |
| **Ports** | `HostDetector` |
| **Must not** | Interpret, apply headroom, or authorize anything. Every value it emits carries basis *reported*. Interpretation is `capacity`'s job. |
| **Created** | 1.1 |

The fingerprint is not decoration. It is the key by which cached evidence
is later judged reusable, so it must exist before any evidence does — and
it must cover only stable facts, or every cached probe is invalidated by a
change in free memory.

`DeploymentProfile` lives here because it is a statement about a host
shape. Its tier is earned from the acceptance level reached on that shape
rather than declared, which is what makes broad hardware support a claim
the evidence can back. It is also the only place such a claim is made, so
support statements cannot scatter.

### `components`

| | |
|---|---|
| **Owns** | `ComponentManifest` and `ComponentRequirement`: version, supported OS, architecture, accelerator compatibility, dependencies, source, checksum, signature, licence, artifact location. Resolution and verification. |
| **Consumes** | `kernel` · `host` |
| **Ports** | `ComponentSource` |
| **Must not** | Let download logic scatter into other modules. The constitution names this failure explicitly. |
| **Created** | **Recommended 1.3 as verify-only** · **Deepened** 10.2 installation, 10.3 updates · See Part VI |

This sits at tier 2, not inside `install`, because `DeploymentPlan` at
Stage 3.4 consumes *resolved components*. The installer is a consumer of
this module, not its owner.

### `storage`

| | |
|---|---|
| **Owns** | `StoragePool` — mount identity, filesystem type, provider class, quota identity, fingerprint, generation. `StorageEvidence` and immutable `EmpiricalProbeEvidence`. Characterization in transaction, host and deep modes. The shared operation lock, staging, mutation admission, rollback and startup recovery. |
| **Consumes** | `kernel` · `evidence` · `policy` · `host` (mount facts only) |
| **Produces** | `StoragePool v1` · `StorageEvidence` · `StorageAdmissionDecision` |
| **Ports** | `ManagedUsageSource` — bytes per pool, no entity identity · `StorageBackend` |
| **Must not** | Import `model`, know a model identity, let raw filesystem capacity authorize a mutation, infer probe or cleanup success from a free-space delta, or treat an interrupted probe as a success. |
| **Created** | 0.2 contract · 1.2 reported-only view · **Deepened** 2.1–2.4 |

The `ManagedUsageSource` port is the correction for the previous
attempt's integration crash. Storage needs to know how many bytes the
platform's own artifacts occupy; it does not need to know that they are
models. A record with a null management section becomes the adapter's
problem to represent honestly as unresolved, and storage fails closed
instead of raising.

### `capacity`

| | |
|---|---|
| **Owns** | `CapacityEnvelope` — per resource, per accelerator, per pool, each leaf carrying reported, effective and safe with basis and confidence. `HeadroomPolicy`. `CapacityEvidence`. The internal conservative estimator, which is mandatory rather than optional. |
| **Consumes** | `kernel` · `evidence` · `policy` · `host` · `storage` contracts |
| **Produces** | `CapacityEnvelope v1` |
| **Ports** | `CapacityEvidenceProvider` · `ResourceStateProvider` |
| **Must not** | Import `model`, `planning`, `resource` or the selector. Recommend only — it never authorizes. Never aggregate per-accelerator memory unless the interconnect genuinely permits, and never double-subtract managed reservations from already-observed live availability. |
| **Created** | 1.2 policy-only · **Deepened** 3.2 providers, 11.1 and 11.3 observed fusion |

Stage 1.2's policy-only envelope authorizes *memory* admission and is
recorded as debt for retirement by the close of Milestone 2. It authorizes
no storage mutation, because Milestone 1 performs none — the model is
placed by hand. That is why a policy-only envelope is honest at Milestone
1 and would not be at Milestone 2.

## TIER 3 — What can be served

### `model`

| | |
|---|---|
| **Owns** | `ModelMetadata` and `ModelArtifact` normalized from any source. `ModelInventoryRecord` with explicit states and lineage — parent model and revision, derivation type, owner, dataset reference, promotion state. `ModelRequirement`, host-independent. The acquisition workflow and `AcquisitionReceipt`. |
| **Consumes** | `kernel` · `evidence` · `policy` · `storage` ports and contracts |
| **Produces** | `ModelInventoryRecord v1` · `ModelRequirement v1` · `AcquisitionReceipt` |
| **Ports** | `ModelSource` · `ModelMetadataEnricher` |
| **Implements** | `storage.ports.ManagedUsageSource` |
| **Must not** | Let a model requirement depend on the host — feasibility is where host and requirement meet. Fill a missing metadata field with a guess; absent values stay unresolved and are reported. Let an external source failure mark the local platform unhealthy. |
| **Created** | 1.4 local inventory · **Deepened** 2.5 source, 2.6 acquisition, 3.1 requirement |

Model sits above capacity and storage because of an explicit roadmap
rule: capacity precedes catalogue, and model requirements must never
determine a probe horizon. The tier order makes that rule structural — a
candidate model cannot influence storage characterization because storage
cannot see it.

## TIER 4 — Recommend and authorize

### `planning`

| | |
|---|---|
| **Owns** | `FeasibilityResult` — three verdicts, per-resource `{required, safe_available, fits, margin, limiting}`, limiting factor, maximum viable configuration, reasons and evidence references. `DeploymentPlan`. Selection, with recorded rejection reasons. |
| **Consumes** | `kernel` · `evidence` · `policy` · `host` · `components` · `capacity` · `model` |
| **Produces** | `FeasibilityResult` · `DeploymentPlan` · a selection decision with explained rejections |
| **Ports** | `Selector`, which becomes `ModelMixOptimizer` at 12.3 behind the same contract |
| **Must not** | Import `resource`. Reserve anything. Select on unverified capacity. Return a boolean verdict. Be nondeterministic given identical inputs and policy version. |
| **Created** | 3.3 feasibility, 3.4 plan, 3.5 selection |

Feasibility must be computable for candidates that are not yet acquired.
The previous attempt could only assess models it already had, which is
what made selection impossible.

### `resource`

| | |
|---|---|
| **Owns** | `Workload` and the generic workload types, `ResourceRequirement`, `AdmissionDecision`, `ResourceReservation`, `WorkloadProfile`. The Resource Manager. |
| **Consumes** | `kernel` · `evidence` · `policy` · `capacity` safe layer · `model` requirement |
| **Produces** | `AdmissionDecision` · `ResourceReservation`, persisted and reconciled |
| **Must not** | Import `planning`, `runtime` or `inference`. Know selection ranking. Admit against a reported or effective value. Conflate requested requirement, admitted reservation, observed consumption and peak observed consumption. |
| **Created** | 1.5 · **Deepened** 4.1 workload types, 4.2 oversubscription, 4.3 concurrency |

The ordering this module enforces is the mutation contract for the whole
platform: reserve before mutation, roll the reservation back if start
fails, stop the runtime before releasing the reservation, and hold
conservative state on a persistence error.

## TIER 5 — How to run, and what to run

### `execution`

| | |
|---|---|
| **Owns** | `ExecutorSpec`, `ExecutorHandle`, process execution, environment, filesystem mapping, signals, logs, process health, and PID reuse protection. |
| **Consumes** | `kernel` · `host` |
| **Ports** | `Executor`, with native process execution as the first and reference implementation |
| **Must not** | Contain model semantics or runtime options. Assume a container runtime exists. |
| **Created** | 1.3 |

### `runtime`

| | |
|---|---|
| **Owns** | `RuntimeProfile`, `RuntimeLaunchSpec`, and the translation of platform concepts — context length, concurrency, memory utilization, parallelism, adapters — into runtime-specific configuration. |
| **Consumes** | `kernel` · `host` · `model` contracts |
| **Ports** | `InferenceRuntime` |
| **Must not** | Import `execution`. Own capacity policy. Let a runtime-specific option reach a core signature. |
| **Created** | 1.3 · **Deepened** 4.3 concurrency binding, 13.4 adapter serving |

Stage 4.3 exists because the previous attempt held a platform-level
concurrency number that was never mapped to the runtime's own control.
The mapping belongs here, inside the adapter's translation layer, and
nowhere else.

## TIER 6 — Serving and the record of it

### `inference`

| | |
|---|---|
| **Owns** | `InferenceInstance` — instance identity, host, model and revision, runtime, executor, endpoint, reservation, context, runtime concurrency, platform request limit, access-policy reference, lifecycle state, configuration version. The lifecycle: start, health, stop, restart, unload. `InferenceEndpoint`. The distinction between status and health. |
| **Consumes** | `kernel` · `resource` · `execution` · `runtime` · `model` |
| **Produces** | A running instance, a healthy endpoint, and reconciliation on restart |
| **Must not** | Route requests, authenticate, or emit usage events. Confuse a reachable port with a functioning API. |
| **Created** | 1.6 · **Deepened** 4.4 multiple instances |

### `analytics`

| | |
|---|---|
| **Owns** | `UsageEvent`, keeping `logical_name`, `model_id`, `provider`, `service_id` and `route_reason` distinct. `ModelOutcome`. Retention policy and partitioning. |
| **Consumes** | `kernel` · `identity` · `policy` |
| **Ports** | `UsageEventSink`, non-blocking and bounded · `UsageAnalyticsStore` |
| **Must not** | Block an inference response, ever. Make the gateway wait on an exporter. Accept a service log as a usage event. Store events in a single unbounded file. |
| **Created** | 1.7 · **Deepened** 5.4 retention and exporter, 11.4 outcomes |

The sink contract is deliberately lossy under pressure rather than
blocking, and **a dropped event is counted as a fact**. Silent loss would
violate the same principle that makes an interrupted probe inconclusive
rather than successful.

### `gateway`

| | |
|---|---|
| **Owns** | Endpoint identity, the authentication and authorization enforcement point, model access policy, `RouteDecision`, request limits and queueing. |
| **Consumes** | `kernel` · `identity` · `entitlement` · `policy` · `inference` · `analytics` |
| **Produces** | `RouteDecision`, a served response, and one `UsageEvent` per request |
| **Ports** | `Router` — explicit and default at 1.7, policy-driven at 5.2, intelligent at 12.2 · `InferenceProvider` for local and external paths |
| **Must not** | Reserve resources. Delegate identity, route semantics, model identity, usage events, permissions, resource state or cost normalization to an external gateway implementation. |
| **Created** | 1.7 · **Deepened** 5.2 routing, 5.3 federation |

Milestone 5.3 requires that removing LiteLLM changes no core contract.
That is only true if LiteLLM is an `InferenceProvider` implementation in
`adapters/` and the platform concerns above stay here.

## TIER 7 — Organisational intelligence

### `knowledge`

| | |
|---|---|
| **Owns** | `KnowledgeSource` and `KnowledgeItem` with capabilities, permission reference, provenance, content reference and indexing state. Indexing, chunking, retrieval and authorized-context assembly. |
| **Consumes** | `kernel` · `identity` · `policy` |
| **Ports** | `KnowledgeConnector` · `ManagedStorageProvider` · `Retriever` · `EmbeddingProvider` |
| **Must not** | Call inference. Retrieval assembles authorized context; `brains` decides what to do with it. Require internet access at bootstrap for embedding assets. Copy content locally by assumption. |
| **Created** | 0.2 contracts · 7.1–7.4 |

Permission enforcement sits between candidate retrieval and authorized
context, inside this module, because a permission check performed anywhere
else can be bypassed by a new caller.

### `training`

| | |
|---|---|
| **Owns** | `DatasetSnapshot` with provenance, authorization, scope, version, retention and policy. `DerivedModel` lineage. Evaluation and promotion states. |
| **Consumes** | `kernel` · `identity` · `model` · `resource` workload types |
| **Ports** | `ModelAdaptationProvider` |
| **Must not** | Share infrastructure with inference. Treat retrieval permission as training permission. |
| **Created** | 0.2 contracts · 13.1–13.3 |

### `brains`

| | |
|---|---|
| **Owns** | `TeamBrain` as a composition — team identity, membership, permissions, knowledge scope, tools, agent configuration, base-model policy, routing policy, memory, evaluation profile, optional adapter references. Company Brain composition. |
| **Consumes** | `kernel` · `identity` · `knowledge` · `gateway` · `analytics` |
| **Must not** | Reduce a Team Brain to one fine-tuned model. |
| **Created** | 8.2–8.3 |

## TIER 8 — Control plane

### `platform`

| | |
|---|---|
| **Owns** | `PlatformState`, installation identity, platform version, configuration wiring, the startup sequence, the **single** reconciliation path, health aggregation, and `Approval`. |
| **Consumes** | Every domain's `reconcile` and `health` |
| **Ports** | `HealthSource` and `ReconcilePhase`, implemented by each domain |
| **Must not** | Contain domain algorithms. Own state that a domain should own. Require a model to be present in order to start. |
| **Created** | 0.3 · **Deepened** 6.3 idempotent startup |

An absent model is a valid unsatisfied deployment state. The previous
attempt hit a bootstrap deadlock — the platform needed a model to start,
but choosing a model needed the platform — and spent four commits
dismantling it. This module is where that is designed out.

### `api`

| | |
|---|---|
| **Owns** | The Platform API's route table, handlers, uniform error rendering from kernel error codes, identity and entitlement enforcement at the boundary, pagination and API versioning. |
| **Consumes** | `platform` and domain services |
| **Ports** | The router itself is the seam: a handler is a function from request to value, and the **HTTP transport is an adapter** in `adapters/http`. |
| **Must not** | Contain an algorithm. Expose an endpoint that bypasses the enforcement boundary. Let a web framework own routing — a framework that owns routing owns the API. |
| **Created** | 0.3, and grows at every subsequent stage |

Every stage's definition of done includes a Platform API surface, so this
module grows monotonically rather than being a late project. That is what
makes the Admin console at 6.1 an assembly job.

Separating the router from its transport has a second benefit beyond
replaceability: the entire API is exercised by calling the router, so the
Milestone 0 gate — "the Platform API answers from platform state" — is
provable at `L1` without a live port.

## TIER 9 — Consumers and additive intelligence

### `agents`

| | |
|---|---|
| **Owns** | Admin Agent tool definitions, risk classification — read-only, low-risk mutation, meaningful mutation — and the approval flow. Team Agent execution. |
| **Consumes** | `api` only, for the Admin Agent. `gateway`, `knowledge` and `brains` through `AccessContext` for the Team Agent. |
| **Must not** | Hold unrestricted shell access. Import a domain module directly. Perform a meaningful mutation without recorded administrator approval. |
| **Created** | 6.2 · 8.3 |

### `intelligence`

| | |
|---|---|
| **Owns** | The model effectiveness dataset, observed-capacity fusion, routing intelligence, and the portfolio optimizer. |
| **Consumes** | `analytics`, `capacity` and `model` contracts |
| **Implements** | `capacity.ports.CapacityEvidenceProvider` · `gateway.ports.Router` · `planning.ports.Selector` |
| **Must not** | Be imported by anything. Authorize an allocation — it produces evidence and recommendations only. |
| **Created** | 11.1–11.4 · 12.1–12.3 |

### `vendor`

| | |
|---|---|
| **Owns** | The single outbound boundary: heartbeat, product telemetry batching, optional cloud analytics export, update checks, crash reporting and entitlement renewal transport. Per-channel visibility and configuration. |
| **Consumes** | `entitlement`, `analytics` aggregates, `platform` state |
| **Ports** | `ProductTelemetryExporter` · `HeartbeatTransport` |
| **Must not** | Transmit prompts, responses, documents or retrieved content by default. Be required for the platform to function. |
| **Created** | 9.1–9.2 |

### `install`

| | |
|---|---|
| **Owns** | The bootstrapper flow, component installation and offline bundles, modular updates and rollback, and the dependency and licence inventory. |
| **Consumes** | `host` · `components` · `planning` · `api` |
| **Must not** | Duplicate component resolution, which `components` owns. |
| **Created** | 10.1–10.4 |

## TIER 10 — `adapters`

Every third-party implementation, one package per seam, mirroring the
port it implements:

```text
adapters/persistence/     file · sqlite
adapters/http/            stdlib_server · asgi
adapters/execution/       native_process · docker · podman
adapters/runtime/         vllm · llama_cpp · mlx
adapters/model_source/    huggingface · local_file
adapters/capacity/        llmfit · accelerate · benchmark
adapters/usage/           partitioned_local · exporter
adapters/inference/       local_endpoint · litellm
adapters/identity/        local · oidc · scim
adapters/knowledge/       managed_files · smb · webdav · sharepoint · google_drive
adapters/embedding/       local_model · external
adapters/telemetry/       posthog
adapters/entitlement/     offline_licence · vendor_service
adapters/adaptation/      peft · merge
adapters/host/            linux · darwin · captured_fixtures
```

Every adapter is advisory-capable: if an external provider is absent,
broken or nondeterministic, the domain must still function through a
mandatory internal fallback. `llmfit` was integrated, found
nondeterministic on the reference host, and demoted to advisory. That
outcome is the default assumption.

## TIER 11 — `main`

Reads configuration, resolves adapters from the kernel registry, builds
the object graph, and runs the platform startup sequence. It is the only
place where a concrete adapter name appears alongside a core type.

---

# PART V — VERIFICATION

## 1. Do the links hold end to end?

Six traces cover every module in the map. Each names the modules in order
and the contract handed between them.

**Trace A — startup and reconciliation** (0.3, completed at 6.3)

```text
config → kernel.Store → platform state load
  → host detect, compare fingerprint
  → storage reconcile: orphan sweep, generation check
  → capacity envelope rebuild from policy
  → model inventory reconcile
  → resource reservation reconcile
  → inference instance reconcile: status vs health, orphan process and port
  → gateway endpoint registry rebuild
  → analytics store open, partitions verified
  → platform health aggregate → api serves
```

No model installed is a valid outcome at every step.

**Trace B — a request is served** (1.7)

```text
client → api → gateway
  → identity authenticate            → Subject, AccessContext
  → entitlement check                → allowed or refused
  → gateway model access policy
  → Router                           → RouteDecision
  → inference endpoint               → runtime adapter
  → response
  → analytics UsageEventSink         (non-blocking; failure never blocks)
  → adapters/usage partition
```

**Trace C — an instance starts** (1.5, 1.6)

```text
model inventory record → ModelRequirement
  → resource ResourceRequirement
  → capacity safe layer               → AdmissionDecision
  → resource ResourceReservation      (reserve before mutation)
  → runtime RuntimeLaunchSpec
  → execution ExecutorHandle
  → inference InferenceInstance       → health → endpoint published

failure: release the reservation, no orphan process, no orphan port
stop:    stop the runtime, then release the reservation
```

**Trace D — a model is acquired** (2.6)

```text
model source → immutable revision → ModelArtifact
  → ModelRequirement incl. peak additional bytes
  → storage pool selection
  → storage evidence: reuse, else probe, persisting each fact before the next
  → storage admission, high confidence required
  → operation lock → staging → resumable transfer
  → integrity validation → commit
  → inventory reconciliation
  → evidence invalidation, storage generation advance
  → audit event

cancel: cooperative, lock released without relying on process exit,
        no orphan artifact, outcome inconclusive rather than failed
```

**Trace E — a model is chosen** (3.3–3.5)

```text
curated candidates → ModelMetadata (unresolved fields explicit)
  → ModelRequirement per candidate
  → capacity CapacityEnvelope
  → planning FeasibilityResult per candidate, with limiting factor
  → planning Selector, deterministic under a recorded policy version
  → DeploymentPlan with alternatives and confidence
  → approval → Trace D → Trace C

every rejected candidate records why it lost
```

**Trace F — knowledge answers a question** (7.2–7.3, 8.3)

```text
Subject → AccessContext
  → knowledge candidates
  → permission enforcement, optional source revalidation
  → authorized items → Retriever → assembled context
  → brains or agents → gateway → model → response with sources
  → analytics UsageEvent
```

## 2. Is the build order consistent with the graph?

For every stage, each input must be produced by an earlier stage, by a
lower tier, or by a declared provisional stand-in. The result:

| Stage | Creates | Requires | Available? |
|---|---|---|---|
| 0.1 | `kernel` | — | ✅ |
| 0.2 | tier-1 modules; `contracts.py` in each domain | `kernel` | ✅ |
| 0.3 | `platform`, `api`, local administrator | `kernel`, `identity` | ✅ |
| 1.1 | `host` | `evidence` | ✅ |
| 1.2 | `capacity` policy-only | `host`, `evidence`, `policy`, `StoragePool` | ✅ via finding 1 |
| 1.3 | `execution`, `runtime`, component seam | `host` | ✅ via finding 2 |
| 1.4 | `model` inventory | `storage` pool, `model` contracts | ✅ via finding 1 |
| 1.5 | `resource` | `capacity`, `ModelRequirement` | ✅ crude requirement, already in the ledger |
| 1.6 | `inference` | `resource`, `execution`, `runtime`, `model` | ✅ |
| 1.7 | `gateway`, `analytics` | `identity`, `inference`, `entitlement` | ✅ |
| 1.8 | milestone gate | `platform`, `api` | ✅ |
| 2.1–2.4 | `storage` deepened | `host`, `evidence`, `ManagedUsageSource` | ✅ implemented by `model` at 1.4 |
| 2.5–2.6 | `ModelSource`, acquisition | storage mutation safety at 2.4 | ✅ correctly ordered |
| 3.1 | `ModelRequirement` real | `ModelMetadata` at 2.5 | ✅ |
| 3.2 | `CapacityEvidenceProvider` | `capacity` at 1.2, requirement at 3.1 | ✅ |
| 3.3–3.5 | `planning` | 3.1, 3.2, `capacity`, `components` | ✅ via finding 2 |
| 4.1–4.4 | `resource`, `runtime` deepened | 1.5, 1.3 | ✅ |
| 5.1–5.4 | `identity`, `gateway`, `analytics` deepened | 0.2 contracts | ✅ deepens, never retrofits |
| 6.1–6.3 | console, agent, startup | `api` grown since 0.3 | ✅ |
| 7.x–8.x | `knowledge`, `brains` | `identity`, `gateway` | ✅ |
| 9.x–10.x | `vendor`, `install` | `entitlement`, `components` | ✅ |
| 11.x–14.x | `intelligence`, fleet | ports in capacity, gateway, planning | ✅ multi-host via host-scoped 0.2 contracts |

**No stage requires a module that a later stage owns.** The roadmap's
sequence is sound against this graph. What the check surfaced was five
missing seams rather than a misordering, and all five are now closed by
the Stage 0.2, 0.3 and 1.3 amendments recorded in Part VI.

## 3. Does every deferred capability have a way in?

If a Milestone 11–14 capability has no existing port, it will arrive as a
rewrite. Each one is accounted for:

| Deferred capability | Enters through | Port created at |
|---|---|---|
| 11.1 observed capacity evidence | `capacity.ports.CapacityEvidenceProvider` | 3.2 |
| 11.2 WorkloadProfile | `resource.contracts.WorkloadProfile` | 0.2 |
| 11.3 capacity intelligence v2 | same provider port; `planning` inputs | 3.2 |
| 11.4 ModelOutcome | `analytics.contracts` and its store port | 1.7 |
| 12.1 effectiveness dataset | reads the analytics store | 1.7 |
| 12.2 intelligent routing | `gateway.ports.Router` | 1.7 |
| 12.3 portfolio optimizer | `planning.ports.Selector` | 3.5 |
| 13.1 dataset governance | `training.contracts.DatasetSnapshot` | 0.2 |
| 13.2 model adaptation | `training.ports.ModelAdaptationProvider`, workloads via `resource` | 4.1 |
| 13.4 team-specific serving | `gateway.ports.Router` and runtime adapter capability | 1.7, 1.3 |
| 14.1 multi-host `FleetState` | **extension, not a port** — requires host-scoped contracts from v1 | Part II §6 |
| 14.2 model placement | `planning`, extended with fleet state | 3.4 |
| 14.3 coordination | `brains` and `intelligence` | 8.2, 11 |

Every capability except multi-host enters through a port that exists long
before it is needed. Multi-host is an extension of existing contracts, and
Part II §6 states the constraint that keeps it one.

---

# PART VI — FINDINGS, AND WHAT THEY CHANGED

The build-order check surfaced three missing seams and two unassigned
concepts. None was a misordered stage; all five were destinations without
a source. Because `docs/ROADMAP.md` is authoritative for stage scope,
each was applied there as an explicit edit rather than reinterpreted here
— the rule in Part II §10.

**All five are applied.** They are recorded below because the reasoning
is the evidence for the change, and because a reader comparing the
roadmap against the previous attempt will otherwise wonder where these
came from.

**Finding 1 — `StoragePool` is not in Stage 0.2's contract list, but
Stage 1.2 needs it.** Stage 1.2 computes a safe storage layer, which
requires pool identity. If pool identity is instead read from
`HostCapabilities` at Milestone 1 and moved into `storage` at Milestone
2.1, one concept has two owners across a milestone boundary — the drift
that Part II §7 forbids. The single-pool assumption is also the exact trap
`docs/DEBT.md` records as "multi-pool storage designed but never
exercised."
*Applied:* `StoragePool` added to Stage 0.2, plural from v1.

**Finding 2 — no stage creates the component seam, but Stage 3.4
consumes it.** `DeploymentPlan` is specified to combine "resolved
components." The constitution also warns against hard-coded download
logic scattered through the codebase. At Milestone 1 the runtime is
assumed already installed, which is reasonable — but the seam should exist
so that Milestone 10 fills it rather than introducing it.
*Applied:* the component seam is created at Stage 1.3, verification-only.

**Finding 3 — audit has no owning stage.** The constitution requires that
a deployment eventually answer who changed a setting, installed a model,
modified a permission or approved an agent action, and asks that the
schema leave room for audit events even if the UI comes later. Stage 5.1
mentions audit as a consumer of the identity model, and Part IV defers the
audit *UI*. No stage creates the audit *contract*. Retrofitting it means
revisiting every mutating workflow.
*Applied:* `AuditEvent` added to Stage 0.2, emitted from every mutating
workflow starting at Stage 1.5.

**Finding 4 — `Approval` has no owning stage.** Stage 6.2 requires that
meaningful mutations obtain explicit administrator approval, and the
constitution requires overrides to be validated, explained, recorded and
reversible. The recording mechanism is unassigned.
*Applied:* `platform` owns `Approval`, created at Stage 0.3 alongside local
administrator identity.

**Finding 5 — health has no seam, only a destination.** Stage 6.1
displays platform health and Stage 1.6 distinguishes status from health,
but nothing defines how a domain contributes to an aggregate view. Without
a `HealthSource` port from Stage 0.3, Milestone 6 becomes a survey of
every subsystem instead of an assembly.
*Applied:* `platform.ports.HealthSource` created at Stage 0.3, with each
domain implementing it as it is built.

Findings 1, 2 and 5 are cheap now and expensive later. Findings 3 and 4
are the two that would otherwise be discovered at Milestone 6 and paid for
across every mutating workflow already written.

---

# PART VII — ENFORCEMENT

The dependency law is worth nothing if it is only written down. The
previous attempt had sound rules and drifted anyway. These tests run at
`L1` and fail the build:

| Test | Asserts |
|---|---|
| Tier direction (§1) | No module imports a higher tier, and no intra-tier import exists outside the §3 edge list. |
| Declared non-edges (§4) | `planning` ⊥ `resource`; `execution` ⊥ `runtime`; `storage` and `capacity` ⊥ `model`; nothing imports `intelligence`; `agents` reaches the platform only via `api`. |
| Narrow edge scope (§3) | `capacity` imports `storage.contracts` and nothing else from `storage`. |
| Adapter boundary | Nothing in tiers 0–9 imports `adapters`. Only `main` does. |
| Kernel purity | `kernel` imports no third-party package and names no domain concept. |
| Contract isolation | Every `contracts.py` imports only `kernel` and lower-tier contracts, and serializes without importing a runtime or provider library. |
| Contract reference form | No contract field is typed as another domain's entity class; cross-entity references are identifiers. |
| Host scoping | Every host-scoped contract carries a host identifier, and every such collection is plural. |
| Concept census | Module count is compared against the declared concept inventory at every milestone consolidation checkpoint. |

The concept census is the direct control for Pattern 4. Eleven
`storage_*` modules for one concept would have failed it on the day the
second one was created.

---

# PART VIII — HOW TO READ THIS WITH THE OTHER DOCUMENTS

```text
docs/PRODUCT_VISION.md    what Kultrun is, what its concepts mean, what is non-negotiable
docs/ROADMAP.md           in what order it is built, and how each step is proven
docs/ARCHITECTURE.md      where each concept lives, and what may depend on what
docs/DEBT.md              every approximation, and the condition that retires it
docs/DEVELOPMENT_WORKFLOW.md   the bounded-step protocol and branch/GPU workflow
docs/legacy/              the previous attempt, as evidence only
```

A stage brief cites this document for the modules it touches, and the
stage output package records any change to the map. A change to a module
boundary is a change to this document, made in the same commit as the
code — the same rule the roadmap applies to stage boundaries, for the same
reason.
