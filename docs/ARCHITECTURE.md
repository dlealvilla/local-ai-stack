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

**Law 5 — An adapter inherits the import budget of the domain whose port
it implements.** Law 3 lets an adapter import core tiers, which on its own
would make `adapters/` a back channel: a host-discovery adapter could reach
the Resource Manager, and a concept that no core module is allowed to depend
on would acquire a dependency anyway. So an adapter may import the domain
that declares its port, that domain's own permitted imports, and nothing
more. An adapter can never do what its own domain could not.

The consequence that matters here: a `HostDiscoveryProvider` lives at tier
2's budget, so it cannot see `model`, `planning`, `resource`, `runtime` or
`inference`. A provider physically cannot decide which model runs.

## 3. The declared intra-tier edges

This is the complete list. Any other intra-tier import is a violation.

| Tier | Permitted edge | Why |
|---|---|---|
| 1 | `entitlement` → `identity` | An entitlement is claimed by a subject. |
| 1 | `audit` → `identity` | An audit event records which actor did what. |
| 2 | `components` → `host` | Component compatibility is evaluated against host capabilities. |
| 2 | `storage` → `host` | Pool identity derives from reported mount facts. |
| 2 | `capacity` → `host.contracts` **only** | The envelope interprets reported host values. It must not reach the discovery service or any provider: capacity consumes `HostCapabilities` without ever learning which tool observed it. |
| 2 | `capacity` → `storage.contracts` **only** | Capacity reads storage evidence as data. It must not reach probing, locking or mutation logic. |
| 6 | `gateway` → `inference` | Routing needs the endpoint registry. |
| 6 | `gateway` → `analytics` | Every request emits a usage event through a non-blocking sink. |
| 7 | `brains` → `knowledge` | A Team Brain scopes a knowledge domain. |
| 8 | `api` → `platform` | The API is a transport over control-plane services. |

`evidence`, `policy` and `identity` import nothing but `kernel`.
`inference` and `analytics` do not import each other. `training` imports
nothing else in tier 7.

## 4. Enforced non-edges

These pairs must not know about each other at all. Each separation is a
constitutional requirement, and making it structural is what stops it
eroding under delivery pressure.

| Pair | Why they are peers | Consequence |
|---|---|---|
| `planning` ⟂ `resource` | "Resource Manager is authoritative for admission. Capacity Planner recommends." Recommendation and authorization must be independently auditable. | Neither imports the other. `platform` sequences plan → admit. |
| `execution` ⟂ `runtime` | "Executor and inference runtime are separate abstractions." Executor logic must not leak into runtime domain logic. | Neither imports the other. `platform` copies a launch spec into an executor spec; later `inference` composes both. |
| `execution` ⟂ `capacity` | How a workload is launched is a different question from what may safely be launched. A container engine that could read the capacity envelope would eventually be asked to decide something. | Neither imports the other. `resource` authorizes; `execution` only materializes what was already admitted. |
| `runtime` ⟂ `capacity` | Runtime translates already-resolved configuration into an executable recipe. Capacity policy is not a runtime concern. | Neither imports the other. Constraints arrive on the launch spec as data. |

`execution` may import `host.contracts` and nothing else from `host`,
because it needs to know whether a container engine exists — that fact is
on `HostCapabilities` — and must not acquire the ability to go and look.

**Execution consumes an allocation that has already been authorized.** The
handoff runs one way and never doubles back:

```text
capacity        safe layer, which is the only layer that may authorize
   ↓
resource        admission → ResourceReservation, naming the device
   ↓
inference       composes the reservation into a DeviceRequest
   ↓
execution       materializes it: process, or container plus device
   ↓
adapter         translates to a runtime-specific device name
```

`inference` performs the translation rather than `execution`, which keeps
the executor ignorant of reservations entirely — it receives a request to
attach a device and has no vocabulary for asking whether it should. An
executor that could read the capacity envelope would eventually be asked to
decide something, and admission would quietly acquire a second author.

Four further non-edges matter enough to name explicitly:

- **`storage` and `capacity` may not import `model`.** Storage probing
  must not know model identities. Platform-managed usage enters storage
  through the `ManagedUsageSource` port, whose contract speaks bytes per
  pool and nothing else. `model` implements that port; storage never
  learns what the bytes are.
- **No core module may import a discovery provider.** Providers are
  adapters and reach the platform only through `HostDiscoveryProvider`.
  `capacity` never learns whether a value came from hwloc, NVML or a
  captured fixture; it reads `HostCapabilities` and the provenance recorded
  beside it. This is what stops a vendor tool's schema becoming Kultrun's
  schema by accretion.
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
`CapacityEnvelope`, `ModelInventoryRecord`, `ResourceReservation`,
`InferenceInstance` and `InferenceEndpoint` are all host-scoped.
`models[]` and `inference_instances[]` are collections from the first
schema — never `current_model` or `current_inference_instance`.
Milestone 14 extends them into
`FleetState`, and the roadmap states that the multi-pool and
per-accelerator contracts exist "precisely so this is an extension." If
v1 assumes a single implicit host, Milestone 14 is a rewrite of every
capacity and lifecycle contract rather than an extension. The cost of
honouring this now is one field and a plural; the cost of retrofitting it
is the entire control plane.

**A provider-local handle is never a Kultrun identity.** Discovery
libraries hand out handles for the devices they enumerate, and those
handles are adapter implementation details with adapter lifetimes. AMD's
own documentation states that a device handle "may change after restarting
the application, so it should not be considered a persistent identifier
across processes"; the same caution applies to NVML, Level Zero and any
comparable API.

So where Kultrun needs identity that survives an observation, a restart or
a provider swap, normalization derives it from **stable host-scoped
attributes** — a bus address, a serial, a model and ordinal, whatever the
platform genuinely keeps still. And where durable identity cannot be
established, the honest representation is that it could not be, not an
ephemeral handle wearing a stable name. A handle promoted to an identity is
a bug that surfaces only after a restart, in a value other records already
point at.

The complete device-identity algorithm is not designed here. The invariant
is, because it constrains every provider written afterwards.

**Adding a supported discovery provider must never require downstream
redesign.** A new hardware family may bring a new adapter, new
normalization, compatible optional contract extensions, a new runtime or
executor adapter, and new feasibility rules. It must not require
redefining what capacity is, what a reservation is, what an inference
instance is, what an executor or runtime is, how gateway requests flow, or
how analytics records usage.

If future hardware genuinely invalidates one of those concepts, that is an
**architecture review event**, not normal adapter work, and it is handled
by amending this document rather than by bending a domain to fit a device.

**Not-applicable is derived, not a third null on every field.** A unified
memory host has no dedicated accelerator memory — that is a different fact
from an unknown amount, and both must stay distinguishable from zero. The
distinction is carried structurally: `unified_memory` being true is what
makes dedicated memory inapplicable, so no field needs a third empty state
and no contract needs a nullability change. Where inapplicability cannot be
derived from a neighbouring capability, a **new** optional field is the
compatible mechanism; widening an existing field's type is a breaking
change and needs a version bump.

**Artifact existence is not current-host suitability.** A model artifact
that is present says nothing about whether *this* host can serve it. Reuse
always runs the same path as a fresh choice:

```text
stored artifact → ModelRequirement + current CapacityEnvelope
                → feasibility → reuse, or reject and reselect
```

`model` inventory answers "what artifacts exist"; `planning` feasibility
answers "can this host use them". The `host_id` on an inventory record
locates an artifact — it does not qualify it, and suitability is never
inferred from presence. Without this rule, moving between rented servers
day to day is unsafe in the least visible way possible: the artifact is
right there, so it looks fine.

**A `ModelArtifact` is not an `InferenceInstance`.** Storage state is
not runtime state. A stored artifact consumes disk; a running instance
consumes runtime resources and holds a `ResourceReservation`. Stopping
an instance does not delete the artifact. There is no
`model.running = true`. The same artifact may have many instances;
several different models may run at once when hardware permits. Request
concurrency (many requests, one instance) is not instance concurrency
(several instances). Planning recommends and never reserves; resource
admits. Frontend clients display platform APIs; they do not own product
logic.

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
       └──────────────┴──▶ host.contracts ◀────┘
                            │
                       host.discovery ◀── HostDiscoveryProvider (tier 10)
                            │                hwloc · NVML · native · NFD
  1  evidence   policy   identity ◀── entitlement, audit
                            │
  0                      kernel
```

Three edges in this diagram carry most of the architecture's weight.

`model` implements `storage.ManagedUsageSource`: the only path by which
storage learns how much space the platform occupies, carrying no entity
identity, so a defective inventory record can no longer crash capacity
observation.

Nothing points into `intelligence`: everything Milestones 11 and 12 add
arrives through a port that already exists beneath it.

And `capacity` reaches only `host.contracts`, never `host.discovery` and
never a provider. Capacity consumes what the platform knows about a host
without ever learning which tool observed it, which is what keeps hwloc,
NVML, NFD and every future vendor library replaceable rather than
load-bearing.

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
| **Owns** | `HostCapabilities`: operating environment, CPU, memory, accelerators with per-device VRAM, unified-memory characteristics, mount facts, execution capabilities, networking and ports, driver hints. The **normalization and reconciliation** of provider observations into it. The host fingerprint, over stable facts only. `DeploymentProfile` and the support matrix. |
| **Consumes** | `kernel` · `evidence` |
| **Produces** | `HostCapabilities v1`, durable, versioned, fingerprinted, and explainable — every value can name where it came from |
| **Ports** | `HostDiscoveryProvider` |
| **Must not** | Interpret capacity, apply headroom, or authorize anything. Implement low-level enumeration that mature tooling already provides. Let any provider's schema become the contract. |
| **Created** | 1.1 |

#### Discovery is a provider architecture, not a detector

This is the module's defining decision. Kultrun does **not** implement
cross-platform hardware enumeration. Mature tooling already does that, on
more platforms than Kultrun will ever validate, and rebuilding it would be
a large proprietary investment in a commodity.

```text
                  host.discovery — HostDiscoveryService
                  collect → normalize → reconcile
                              │
                     HostCapabilities
                              │
                              ▼
                          capacity
       ┌──────────────────────┴──────────────────────┐
       ▲ (port)                                      ▲
  HostDiscoveryProvider                       ManagedUsageSource
       │
  ┌────┴─────────────┬──────────────────┬────────────────────┐
general             vendor            environment          replay
hwloc          NVML · AMD SMI ·        NFD / K8s        captured fixture
               Level Zero · native
```

**A provider observes; it never installs.** It may report that it is
available, unavailable, failed, partially capable, or missing a
prerequisite. It may not install a package, invoke a package manager,
download a tool, alter system configuration or install a driver. Discovery
looks; preparation acts; they are different responsibilities with different
owners and different risk profiles, and a component that both inspects a
machine and modifies it cannot be safely run to find out what is there.

**A provider observes; it never decides.** It reports what a machine
appears to contain, records where the observation came from, and may be
partial, stale, slow, absent or wrong. It may not compute safe capacity,
choose a model, select a runtime or authorize a workload — and under Law 5
it has no import path to any of those, so the restriction is structural
rather than a request.

**The service owns meaning.** It decides which providers to consult,
collects their observations, normalizes them into Kultrun's vocabulary,
reconciles overlaps, preserves unknowns, and surfaces conflicts instead of
silently picking a winner. Reconciliation here means *merging observations*
and is a different operation from the restart reconciliation every stateful
domain performs; the two never share a module, because a name that means
two things is how a concept starts fragmenting.

**Providers overlap on purpose, and that is the interesting case.** hwloc
can see that a PCI accelerator exists and where it sits in the topology;
NVML knows how much memory that device has and which driver is loaded. NFD
can label a node as having a GPU vendor without quantifying anything.
Neither a general topology tool nor a Kubernetes label set answers the
question capacity needs, and neither vendor library works on a machine
without that vendor's hardware. A single detector would have to be all of
them; a service that merges partial observations does not.

Merge rules:

1. a later observation never blindly overwrites an earlier one;
2. a vendor observation may enrich a general one — richer detail about the
   same device is not a conflict;
3. two credible observations that genuinely disagree leave the value
   **unresolved**, with both observations and their provenance preserved
   and a conflict recorded;
4. a provider that is absent or fails means *that source of evidence was
   unavailable*, not that the host is unsupported;
5. what no provider reported stays unknown.

**There is no global provider precedence order, and there will not be
one.** No rule of the form "vendor beats general" exists at any level. Such
an ordering looks like common sense and is a way of deciding a question
nobody investigated: it would resolve every future conflict, including the
ones where the general tool happened to be right, and it would do so
silently.

Individual **fields** may acquire a documented reconciliation rule when
empirical evidence justifies one — for instance, a vendor interface may
turn out to be authoritative for a measurement that vendor owns. Such a
rule is per field, carries the evidence that motivated it, and never
generalizes to the providers that happen to be on either side of it.

Until a field has such a rule, a conflict stays a conflict. An unresolved
value that says two sources disagreed is more useful than a confident value
that is wrong, and the platform already refuses to authorize against
unknowns.

**Provider identity is not host identity.** AMD SMI's own documentation
warns that a device handle "may change after restarting the application, so
it should not be considered a persistent identifier across processes."
Kultrun mints its own stable identity and treats provider handles as
observations about it, which is the same reason `HostCapabilities` is a
Kultrun contract and not a vendor schema.

#### The contract is not "Linux with an NVIDIA card"

The reference implementation is Linux x86_64 with NVIDIA. `HostCapabilities`
must not quietly come to mean that, and downstream domains must consume
generic capability concepts rather than assumptions about the first host
that was validated.

Concretely, the contract must be able to represent zero, one, several
identical or several different accelerators; a vendor it has never seen; an
accelerator whose memory is unified with the system's; a CPU-only host; and
a value that is unknown as distinct from one that is zero or inapplicable.
It already can — accelerators are a plural collection, `AcceleratorVendor`
carries `UNKNOWN`, `unified_memory` is per device, and every quantity is
`Maybe[...]`.

What it must **not** acquire is speculative fields anticipating platforms
nobody has run. The requirement is extensibility, not prediction: a future
platform should arrive as a new adapter plus, at most, compatible optional
contract extensions.

Advanced heterogeneous scheduling is explicitly not designed. Plurality is a
structural requirement so that supporting it later is not a contract
redesign.

#### Explainability without an envelope per field

Every value must remain explainable — which provider supplied it, when, how
it was obtained, how much confidence it carries. Wrapping every leaf in an
envelope would double the size of every contract, so provenance is recorded
*beside* the values, keyed by the same dotted field path that
`unresolved_fields` already produces. `HostCapabilities` gains an optional
observation list and an optional conflict list, which under the fingerprint
rules is a compatible addition and needs no version bump.

So a reader gets `accelerators[0].memory_total_bytes = 48305799168`,
`provider = nvml`, `derivation = reported_by_source`, `confidence = high` —
rather than a number with no history.

#### Fingerprint and profile

The fingerprint is not decoration. It is the key by which cached evidence
is later judged reusable, so it must exist before any evidence does — and
it must cover only stable facts, or every cached probe is invalidated by a
change in free memory.

`DeploymentProfile` lives here because it is a statement about a host
shape. Its tier is earned from the acceptance level reached on that shape
rather than declared, which is what makes broad hardware support a claim
the evidence can back. It is also the only place Kultrun makes such a
claim, so support statements cannot scatter.

**Two support facts, kept separate.** An administrator may attach their own
support statement — "this configuration is vendor-supported by our
organisation", "our infrastructure team backs this host" — and that is
genuinely useful information for an operator reading a console.

It is a *different fact* from Kultrun's evidence profile, and it may never
alter it. An external declaration cannot promote `EXPERIMENTAL` to
`SUPPORTED`, because the profile means "this is the acceptance level
actually reached", and a statement that changed it would make the ladder
describe opinion instead of evidence. The two are stored separately, may be
displayed together, and only one of them is Kultrun's own claim.

The schema for the external statement is deliberately not designed here. It
has no consumer until an Admin console exists to show it.

### `components`

| | |
|---|---|
| **Owns** | `ComponentRequirement` — what is needed, acceptable versions, platform compatibility, required or optional, and why. `ComponentResolution` — already present, provisioned, unavailable or failed, with resolved version, provenance and verification result. |
| **Consumes** | `kernel` · `host.contracts` |
| **Ports** | `ComponentSource` |
| **Must not** | Let download logic scatter into other modules. Become a generic downloader. Perform provisioning itself — it states what is needed and what was found; `install` acts. |
| **Created** | **1.1**, expressing the discovery provider's requirement · **Deepened** 1.3 runtime components, 10.2 installation, 10.3 updates |

Presence and compatibility are separate questions, and keeping them apart
is what avoids a cycle at tier 2. Asking whether a component exists at an
acceptable version needs no host facts; asking whether it is *compatible*
with this machine does. `host` therefore consults only the first, and never
asks `components` to prepare anything.

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

`DeploymentCapacity` and `CapacityUtilization` are **not** owned here.
They are planning projections of this envelope for a proposed placement.
Capacity remains the owner of reported / effective / safe host facts.

**Who does what, restated because it is easy to blur.** `host` observes and
normalizes; it applies no capacity policy. `storage` performs empirical
storage probing and owns `EmpiricalProbeEvidence` — the filesystem is
touched there and nowhere else. `capacity` *consumes* evidence and owns the
reported → effective → safe interpretation; it must not probe a filesystem
itself. `execution` and `runtime` own no capacity policy: they consume an
allocation that was already authorized.

So the path is:

```
HostCapabilities  +  StoragePool evidence  +  EmpiricalProbeEvidence
                              ↓
                     capacity policy
                              ↓
                      CapacityEnvelope
```

A probe living inside a capacity service would put filesystem mutation
behind a read that planning calls freely, which is how the previous attempt
ended up with a 48-minute capacity query.

## TIER 3 — What can be served

### `model`

| | |
|---|---|
| **Owns** | `ModelMetadata` and `ModelArtifact` normalized from any source. `ModelInventoryRecord` with explicit artifact states (remote, acquiring, stored, invalid, updating, deleted) and lineage — parent model and revision, derivation type, owner, dataset reference, promotion state. Running is not an inventory state. `ModelRequirement`, host-independent: weight memory, artifact and peak-acquisition storage, estimated RAM / VRAM / unified memory, context, quantization (via the candidate's metadata), supported runtimes, architecture/device needs, runtime overhead, KV/cache, estimation method, confidence and evidence basis. `EstimatorRouter` and typed `EstimatorFailureReason` — ordered provider attempts and failover provenance, not ranking. The acquisition workflow and `AcquisitionReceipt`. |
| **Consumes** | `kernel` · `evidence` · `policy` · `storage` ports and contracts · `capacity` contracts (SAFE preflight only) |
| **Produces** | `ModelInventoryRecord v1` · `ModelRequirement v1` · `AcquisitionReceipt` · `ModelArtifact` |
| **Ports** | `ModelSource` · `ModelRequirementEstimator` · `ModelAcquisitionProvider` · `ModelMetadataEnricher` |
| **Implements** | `storage.ports.ManagedUsageSource` |
| **Must not** | Let a model requirement depend on the host — feasibility is where host and requirement meet. Fill a missing metadata field with a guess; absent values stay unresolved and are reported. Treat unknown requirement as zero or as a fit. Let an external source failure mark the local platform unhealthy. Collapse inventory into a single `current_model`. Treat a stored artifact as a running workload. Rank or recommend — that is `planning`. Let `ModelSource` download, store or own lifecycle. Collapse acquisition into `HuggingFaceSource`. Expose raw Hugging Face or llmfit objects as domain contracts. Reconcile multiple estimators in the product path. Reserve resources or start an InferenceInstance. |
| **Created** | 1.4A catalog/metadata · 1.4C acquisition and plural inventory · **Deepened** 2.5 source, 2.6 acquisition, 3.1 requirement |

Model sits above capacity and storage because of an explicit roadmap
rule: capacity precedes catalogue, and model requirements must never
determine a probe horizon. The tier order makes that rule structural — a
candidate model cannot influence storage characterization because storage
cannot see it.

The catalog Kultrun knows about is not the set of models currently
eligible to deploy. Stage 1.6F derives runtime/model technical
compatibility as `EligibleModelView` from the selected foundation, a
matching `RuntimeInstallation`, a fresh VERIFIED
`RuntimeCapabilityProfile`, `RuntimeSupportDescriptor`, and global
catalog facts. That view is contextual: the same `ModelMetadata` may be
ELIGIBLE under one foundation and BLOCKED under another. Stage 1.6G
derives `ModelRequirement` from an ELIGIBLE candidate plus the selected
fresh VERIFIED profile, then capacity-fit against SAFE. Stage 1.6H
ranks only currently feasible candidates and persists bounded
AUTO/MANUAL `ModelSelection`. Stage 1.6I persists the authoritative
current `DeploymentPlan` from those decisions. ELIGIBLE is not FEASIBLE.

## TIER 4 — Recommend and authorize

### `planning`

| | |
|---|---|
| **Owns** | `DeploymentCapacity` — the SAFE slice of the current envelope relevant to a proposed placement, never a universal server score. `CapacityUtilization` — max of required/safe across applicable deployment-limiting **memory** resources; storage is excluded. `SelectionPolicy` — configurable preferred-band bounds (v0 defaults 0.20–1.00), never architecture constants. `FeasibilityResult` — compatibility verdicts (`COMPATIBLE`, `CONDITIONALLY_COMPATIBLE`, `UNSUPPORTED`, `UNRESOLVED`) plus capacity-fit class (`PREFERRED`, `UNDERUTILIZED`, `EXCEEDS_SAFE`) with per-resource `{required, safe_available, fits, margin, limiting}`, limiting factor, reasons and evidence references. Underutilized is not unsupported. `FeasibleModelCandidate` — derived ranking input (eligible + currently feasible; not persisted). `ModelSelection` — host-scoped AUTO\|MANUAL recommended versus selected model; not a DeploymentPlan. `DeploymentPlan`. `SelectionRecommendation` (primary, preferred alternatives, underutilized alternatives, rejected candidates, rationale, policy version). Selection, with recorded rejection reasons. `NO_PREFERRED_CANDIDATE` and `NO_FEASIBLE_CANDIDATE` are explicit outcomes. |
| **Consumes** | `kernel` · `evidence` · `policy` · `host` · `components` · `capacity` · `model` |
| **Produces** | `FeasibilityResult` · `DeploymentPlan` · a selection decision with explained rejections |
| **Ports** | `Selector`, which becomes `ModelMixOptimizer` at 12.3 behind the same contract |
| **Must not** | Import `resource`. Reserve anything. Select on unverified or reported capacity. Return a boolean verdict. Be nondeterministic given identical inputs and policy version. Encode a global `selected = true`. Silently relax the minimum utilization. Average memory ratios. Sum all GPU VRAM regardless of placement. Treat storage as a utilization-ratio input. Subtract safety headroom twice. Persist a recommendation as permanent truth. Treat a recommendation as the selected configuration after a manual choice. Keep stale eligibility, requirement, or plan values after an upstream selection changes. Import a concrete estimator adapter, import `EstimatorRouter`, or branch on provider id. Average, min/max, or otherwise reconcile multiple estimators. Expose dual estimates. Fallback to another estimator because a valid estimate is over-capacity, underutilized, or low-ranked. |
| **Created** | 1.4B v0 · **Deepened** 3.3 feasibility, 3.4 plan, 3.5 selection · **ModelSelection** 1.6H · **Authoritative DeploymentPlan** 1.6I · **Plan-driven acquire/admit** 1.6J |

Feasibility must be computable for candidates that are not yet acquired.
The previous attempt could only assess models it already had, which is
what made selection impossible. Stage 1.4A supplies metadata and
host-independent requirements; Stage 1.4B owns filtering and selection.
Unknown load-bearing requirements yield `UNRESOLVED`, never a silent fit.

`SelectionRecommendation` already distinguishes a primary from preferred
and underutilized alternatives and rejected candidates. Stage 1.6H
keeps **recommended** distinct from **selected** on `ModelSelection`.
AUTO follows the current recommendation. MANUAL holds another currently
feasible model. Invalid MANUAL choice is refused. Return-to-AUTO
recomputes the current recommendation and selects it. The global model
catalog is not the eligible view; Stage 1.6F derives runtime
compatibility and composition supplies `CompatibilityVerdict` tokens.
Planning does not re-intersect catalog `supported_runtimes` with a
local runtime list. Stage 1.6G remaps `ModelRequirement` and
capacity-fit onto that view: the selected verified runtime is the
estimator identity, never `supported_runtimes[0]`. Stage 1.6H ranks
only `FeasibleModelCandidate[]` produced from those assessments.
`SelectionService.recommend()` remains for isolated estimator tests;
product recommendation authority is `rank_feasible()` via
`ModelSelectionService`. BLOCKED, UNRESOLVED, INFEASIBLE, and stale
assessments never enter ranking. Capacity math is unchanged.

The 1.4B `plan_from` helper remains a provisional recommendation
projection (`plan_authoritative: false`). It is not executable truth.
Product authority is the persisted `planning.deployment_plan@1` record
produced by `DeploymentPlanningService`. K-86 baseline CURRENT/STALE
and recommended-versus-selected provenance are implemented.

The composition root / control plane coordinates invalidation. `planning`
owns how feasibility and selection are computed. Do not introduce a
generic selection or dependency-graph engine here (K-83). Planning must
not import `runtime`; the eligibility → verdict copy lives in
`platform.eligibility`. Requirement derivation lives in
`platform.requirement`. Bounded model selection persistence lives in
`platform.model_selection`. Authoritative DeploymentPlan persistence
lives in `platform.deployment_plan`. Plan-driven acquire/admit lives in
`platform.deployment_prepare` and converts plan + artifact into a
generic `ResourceRequest` before calling ResourceManager. Plan-driven
InferenceInstance create lives in `platform.deployment_instance` so
`inference` does not import `planning`. None of these is a parallel
planner or deployment controller.

### `resource`

| | |
|---|---|
| **Owns** | `Workload` and the generic workload types, `ResourceRequest`, `AdmissionDecision`, `ResourceReservation`, `WorkloadProfile`, `ResourceSummary`. The Resource Manager. |
| **Consumes** | `kernel` · `evidence` · `policy` · `capacity` safe layer · `model` requirement |
| **Produces** | `AdmissionDecision` · `ResourceReservation`, persisted and reconciled |
| **Must not** | Import `planning`, `runtime` or `inference`. Know selection ranking. Admit against a reported or effective value. Conflate requested requirement, admitted reservation, observed consumption and peak observed consumption. Treat a manual override as authority to exceed SAFE bounds. |
| **Created** | 1.5A admission and reservation · **Deepened** 4.1 workload types, 4.2 oversubscription, 4.3 concurrency |

The ordering this module enforces is the mutation contract for the whole
platform: reserve before mutation, roll the reservation back if start
fails, stop the runtime before releasing the reservation, and hold
conservative state on a persistence error.

## TIER 5 — How to run, and what to run

### `execution`

| | |
|---|---|
| **Owns** | `ExecutorSpec`, `ExecutorHandle`, `ExecutorCapabilityProfile`, `DeviceRequest`, process execution, environment, filesystem mapping, signals, logs, process health, and PID reuse protection. Generic identity is `ExecutionId`; a PID is optional native evidence. |
| **Consumes** | `kernel` · `evidence` · `host.contracts` only |
| **Ports** | `Executor`, with native process execution as the first and reference implementation · `ContainerEngine`, for the optional container path |
| **Must not** | Contain model semantics or runtime options. Assume a container runtime exists. Import `capacity` — how a workload is launched is a different question from what may safely be launched. Import `runtime` — the executor receives a generic spec. Become a source of host facts. |
| **Created** | 1.3 · **Reconciled** 1.5C (`ExecutorCapabilityProfile`; generic `ExecutionId`) · **ContainerExecutor** 1.6A |

```text
                        Executor  (port)
                             │
          ┌──────────────────┴───────────────────┐
   NativeProcessExecutor              ContainerExecutor
   first class, the reference          optional
                                             │
                                    ContainerEngine  (port)
                                      │       │        │
                                   Docker  Podman  containerd
                                             │
                                    device attachment
                                             │
                                            CDI
```

**Native process execution is the first validated path and the reference
implementation. Container execution is a first-class optional executor.**
Neither is architecturally privileged in perpetuity: reference
implementation is not architectural dependency, and "first validated" is a
statement about evidence rather than a permanent ranking.

What must not happen is a container engine becoming mandatory by default.
Docker is not required, a commercial container product is not a dependency,
and Kubernetes is not the control plane — a platform that cannot start a
process without a container engine has made an optional component
mandatory, and it has done so without anyone deciding to.

Later, Kultrun may **recommend or select** an executor per deployment,
using host capabilities, runtime support, the deployment profile,
administrator policy and operational evidence. That is a decision the
platform earns the right to make once it has evidence on both paths; it is
not a default to be assumed now. `Runtime != Executor` holds throughout:
vLLM native, vLLM containerized, llama.cpp native and a future runtime
containerized are all combinations the core supports without redesign.

**Where CDI sits.** The Container Device Interface is a vendor-neutral way
for a container runtime to attach a third-party device, and its own
specification is explicit that "areas like resource management are
explicitly left out of CDI." That sentence is the whole of its position
here: CDI attaches a device that Kultrun has *already decided* to allocate.
It is not a source of host capabilities, not a capacity mechanism, and not
an admission decision.

```text
HostCapabilities  →  capacity  →  resource admits and reserves accelerator N
                                            │
                                   execution: DeviceRequest(N)
                                            │
                                   OCI executor → CDI device name
                                            │
                                   container runtime attaches it
```

`DeviceRequest` names an accelerator the way Kultrun identifies it. The
translation into a fully-qualified CDI name such as `nvidia.com/gpu=gpu0`
happens inside the OCI executor adapter, and the specification itself is
generated by vendor tooling — `nvidia-ctk cdi generate` or `amd-ctk`.
Kultrun neither implements CDI nor lets CDI vocabulary into a host or
capacity contract.

### `runtime`

| | |
|---|---|
| **Owns** | `RuntimeProfile`, `RuntimeSupportDescriptor` (declared/static), `RuntimeLaunchSpec`, `RuntimeReadiness`, `RuntimePolicy`, `RuntimeCandidate`, `RuntimeResolution`, `RuntimeProvisioningPlan`, `RuntimeInstallation`, `RuntimeCapabilityProfile`, `RuntimeVerificationBasis`, `FoundationSelection`, `RuntimeEligibleModelCandidate`, `EligibleModelView`, `ModelEligibilityService`, and the translation of platform concepts — context length, concurrency, memory utilization, parallelism, adapters — into runtime-specific configuration. Runtime answers whether a workload is READY. It does not exec or signal. RuntimeResolver classifies declared support against current host facts. RuntimeProvisioner installs an exact plan into a Kultrun-owned isolated environment. Installed is not verified. RuntimeVerifier interprets host/runtime/backend probes executed through the Executor. Verified is not model-compatible by itself. `FoundationSelection` records AUTO versus MANUAL choice; recommendation is not selection; provisionable is not executable. `EligibleModelView` is the authoritative runtime/model compatibility path for the currently selected verified foundation. It does not acquire, rank, or admit. |
| **Consumes** | `kernel` · `evidence` · `host.contracts` (resolution matching) |
| **Ports** | `InferenceRuntime` · `RuntimeProvisioner` |
| **Must not** | Import `execution`. Import `capacity`. Import `model` or `resource`. Own capacity policy. Let a runtime-specific option reach a core signature. Treat a candidate as installed or verified. Treat `INSTALLED` as `VERIFIED`. Treat `PROVISIONABLE` as `VERIFIED EXECUTABLE`. Silently substitute a different RuntimeCandidate than the one selected or supplied for provisioning. Rank or recommend during provisioning or verification. Overload `RuntimePolicy.mode` as product selection. Put raw pip/Docker commands on generic contracts. Mutate system Python, drivers, or CUDA. |
| **Created** | 1.3 · **Reconciled** 1.5C (`RuntimeSupportDescriptor`, runtime-owned readiness) · **Resolution** 1.6B (`RuntimeCandidate`) · **Provisioning** 1.6C (`RuntimeProvisioningPlan`, `RuntimeInstallation`) · **Verification** 1.6D (`RuntimeCapabilityProfile`) · **Selection** 1.6E (`FoundationSelection`) · **Eligibility** 1.6F (`EligibleModelView`) · **Requirement/Capacity** 1.6G · **Serving** 1.6L native vLLM first vertical · **Deepened** 4.3 concurrency binding, 13.4 adapter serving |

Stage 1.6F consumes catalog facts copied by composition
(`ModelEligibilityFacts`). Runtime still must not import `model`. It
must never read `capacity` or `execution`. Runtime-specific
compatibility interpretation is an adapter (`VllmModelCompatibility`),
not a new domain port. Stage 4.3 exists because the previous attempt
held a platform-level concurrency number that was never mapped to the
runtime's own control. The mapping belongs here, inside the adapter's
translation layer, and nowhere else.

`RuntimeSupportDescriptor` is declared support. It is not installed, not
operational, and not verified. A future `RuntimeCapabilityProfile` is a
different object and is not owned here until a verification stage exists.

```text
RuntimeAdapter
      ↓
RuntimeLaunchSpec
      ↓
Executor
     ↙                      ↘
NativeProcessExecutor    ContainerExecutor
      ↓                      ↓
                     ContainerEngine
                             ↓
                        Docker CLI
      ↓                      ↓
ExecutorHandle            ExecutorHandle
```

Runtime = WHAT. Executor = HOW. InferenceInstance composes them.
Docker Engine is the first `ContainerEngine` implementation. Docker is
not present on generic contracts. Native process execution remains the
default live path; container execution is optional and composition-selected.
Stage 1.6A closed L2 against a real Linux Docker Engine using host
networking v0. GPU device attachment, bridge networking, and
vLLM-in-container remain unproven.

Stage 1.6B resolution (composition feeds executor profiles; runtime
does not import `execution`):

```text
HostCapabilities
        +
ExecutorCapabilityProfile[]
        +
RuntimeSupportDescriptor[]
        +
RuntimePolicy
        ↓
RuntimeResolver
        ↓
RuntimeCandidate[]
```

`platform` copies executor capability evidence into the resolver call
the same way it copies a launch spec into an executor spec. Ranking is
deterministic and static (K-56). A candidate is not a
`RuntimeCapabilityProfile`.

Stage 1.6C provisioning (composition selects the provisioner adapter;
runtime owns the plan and the installation receipt):

```text
RuntimeCandidate
        ↓
RuntimeProvisioningPlan
        ↓
RuntimeProvisioner
        ↓
RuntimeInstallation
        ↓
[STOP]
```

`INSTALLED` means the pinned package landed in an isolated environment
under the Kultrun state root. It is not engine proof. The first product
adapter is `VllmNativeProvisioner` (`vllm==0.28.0`, Python 3.12 venv +
pip). Fixture provisioning is for T0/T1/T2 only.

Stage 1.6D verification (composition selects the verifier adapter;
runtime owns interpretation; executor owns probe execution):

```text
RuntimeCandidate
        ↓
RuntimeProvisioningPlan
        ↓
RuntimeInstallation
        ↓
RuntimeVerifier
        ↓
RuntimeCapabilityProfile
        ↓
[STOP 1.6D]
```

`VERIFIED` means the installed runtime passed its host/runtime/backend
checks against the current material verification basis. It is not model
compatibility. The first product adapter is `VllmNativeVerifier`. Fixture
verification is for T0/T1/T2 only. GET never executes a probe.

Stage 1.6E foundation selection composes the closed 1.6B–1.6D objects.
It does not introduce `FoundationCandidate`, `DeploymentFoundation`,
`EnvironmentProvider`, or a recipe DSL.

```text
HostCapabilities
        +
ExecutorCapabilityProfile[]
        +
RuntimeSupportDescriptor[]
        +
RuntimePolicy                    ← resolver coverage AUTO|EXPLICIT
        ↓
RuntimeResolver
        ↓
RuntimeCandidate[]
        ↓
hard feasibility (is_provisionable)
        ↓
RECOMMENDED TO PROVISION
OTHER PROVISIONABLE
BLOCKED
        ↓
FoundationSelection              ← product AUTO|MANUAL
recommended_candidate_id
selected_candidate_id
        ↓
RuntimeProvisioningPlan          ← environment recipe snapshot
        ↓
RuntimeProvisioner               ← realization family (adapter role)
        ↓
RuntimeInstallation              ← environment realization
        ↓
RuntimeVerifier
        ↓
fresh VERIFIED RuntimeCapabilityProfile
        =
VERIFIED EXECUTABLE FOUNDATION
        ↓
[STOP 1.6E]

Stage 1.6F runtime-aware eligible models consumes the selected
verified foundation. It does not introduce `DeploymentFoundation`,
`CompatibilityFramework`, or `ModelMetadataV2`.

```text
FoundationSelection
        ↓
selected RuntimeCandidate
        ↓
matching RuntimeInstallation
        ↓
fresh VERIFIED RuntimeCapabilityProfile
        +
RuntimeSupportDescriptor
        +
Global Model Catalog / ModelMetadata facts
        ↓
RuntimeEligibilityEvaluator (ModelEligibilityService)
        ↓
RuntimeEligibleModelCandidate[]
        ↓
EligibleModelView
        ↓
[STOP 1.6F]

Stage 1.6G ModelRequirement + Capacity migration consumes that view.
It does not introduce `ModelRequirementV2`, `CapacityPlannerV2`, or
`DeploymentPlan` authority.

```text
RuntimeEligibleModelCandidate
        +
fresh VERIFIED RuntimeCapabilityProfile
        +
requested deployment assumptions
        ↓
ModelRequirement
        ↓
CapacityAssessment
        ↓
[STOP 1.6G]
```

Stage 1.6H ModelSelector + bounded model selection consumes those
assessments. It does not reconstruct eligibility, requirements, or
SAFE capacity. It does not execute a deployment.

```text
RuntimeEligibleModelCandidate
        +
ModelRequirement
        +
CapacityAssessment
        ↓
FeasibleModelCandidate[]
        ↓
existing deterministic ranking
        ↓
recommended model
        ↓
AUTO | MANUAL ModelSelection
        ↓
AUTHORITATIVE DeploymentPlan
        ↓
exact ModelArtifact (acquire or reuse)
        ↓
plan-derived ResourceRequest
        ↓
ResourceManager
        ↓
ResourceReservation
        ↓
InferenceInstance
        ↓
vLLM RuntimeAdapter
        ↓
RuntimeLaunchSpec
        ↓
NativeProcessExecutor
        ↓
REAL vLLM
        ↓
Readiness
        ↓
InferenceRequest / InferenceResponse
```

This is the first real serving vertical. Native-process vLLM on a
single planned NVIDIA GPU is implemented. ContainerExecutor GPU,
multi-runtime, multi-GPU, streaming, and a production chat frontend
are not.

`CURRENT` requires current `FoundationSelection`, the selected
candidate, a matching INSTALLED installation, a matching fresh
VERIFIED profile, current `ModelSelection`, a READY requirement for
the selected model, and a currently feasible `CapacityAssessment`.
GET classifies a persisted plan against that basis; it does not
persist. POST create/refresh persists. MANUAL uses the selected
model, never the recommendation. Infeasible or invalid selection
yields no CURRENT plan. `plan_from` is not authority.

Normal executable acquisition and admission consume that CURRENT
plan. STORE_ONLY warehouse acquisition remains independent of the
plan. ResourceManager stays generic: it receives a `ResourceRequest`
and live host state, never DeploymentPlan internals. Capacity
feasibility is not live admission.

Normal instance create consumes that CURRENT plan plus the matching
artifact and ACTIVE reservation. Settings come from the plan. START of
a native-process product vLLM instance launches the exact verified
`RuntimeInstallation` against the exact local `ModelArtifact`. RUNNING
requires process liveness, health, and served-model identity match.
The reference-serving adapter remains test infrastructure only and is
not a vLLM substitute.

`RuntimePolicy.mode` AUTO|EXPLICIT is resolver coverage. It is not
`FoundationSelection.selection_mode` AUTO|MANUAL. Do not overload them.

`PROVISIONABLE` is not `EXECUTABLE`. `RECOMMENDED TO ATTEMPT` is not a
verified recommendation. Only a fresh VERIFIED profile is an
authoritative execution foundation.

Deployment Foundation is a conceptual composition of `RuntimeCandidate`
+ `RuntimeInstallation` + `RuntimeCapabilityProfile`. It is not a
persisted class.

| Architecture concept | Kultrun contract |
|---|---|
| Normalized host capability profile | `HostCapabilities` |
| Foundation possibility | `RuntimeCandidate` |
| Foundation possibility set | `RuntimeResolution.candidates` |
| Pre-provision recommendation | `FoundationSelection.recommended_candidate_id` (resolver `preferred_candidate_id` is the rank hint) |
| Environment recipe snapshot | `RuntimeProvisioningPlan` |
| Environment realization | `RuntimeInstallation` |
| Environment realization mechanism | `RuntimeProvisioner` adapter |
| Verified runtime upper capability | fresh VERIFIED `RuntimeCapabilityProfile` |
| Deployment Foundation | conceptual composition, not a new object |
| Bounded selected foundation | `FoundationSelection` |
| Runtime-aware model eligibility | `EligibleModelView` / `RuntimeEligibleModelCandidate` |
| Runtime-aware model requirement | `ModelRequirement` from an ELIGIBLE candidate + selected VERIFIED profile |
| Runtime-aware capacity fit | existing `ModelEvaluation` / `CapacityFitClass` via composition |
| Currently feasible ranking input | `FeasibleModelCandidate` (derived) |
| Bounded model selection | `ModelSelection` AUTO\|MANUAL; recommended ≠ selected |
| Authoritative current deployment decision | `DeploymentPlan`; CURRENT vs STALE vs UNAVAILABLE |
| Plan-driven stored bytes | exact `ModelArtifact` for the CURRENT plan |
| Plan-driven live admission | `ResourceRequest` from plan resource intent + artifact id |
| Live physical grant | `ResourceReservation` |
| Bounded generation | `InferenceRequest` / `InferenceResponse` |
| First real serving vertical | native vLLM + `NativeProcessExecutor` + local `ModelArtifact` |

RuntimeResolver answers structural plausibility. RuntimeProvisioner
installs the **explicitly selected** candidate, never an implicit
fallback. RuntimeVerifier produces evidence, not ranking.
FoundationSelection is the first bounded administrator foundation
override. A foundation change is not a field swap on the previous plan.
It marks downstream derived state stale. Stage 1.6F recomputes
`EligibleModelView`. Stage 1.6G recomputes `ModelRequirement` and
capacity-fit. Stage 1.6H recomputes the feasible set, recommendation,
and `ModelSelection` currentness. Stage 1.6I persists the authoritative
`DeploymentPlan` and classifies CURRENT vs STALE. Stage 1.6J migrates
normal executable acquisition and ResourceManager admission onto that
plan. InferenceInstance is not remapped.

## Recommendation, selection, and safety boundaries

Kultrun distinguishes recommendation from authorization.

A recommendation is the preferred member of the current approved feasible
set. A manual selection is another member of that same set. Blocked
options are unavailable. Neither recommendation nor administrator
preference may bypass compatibility, verification, policy, permission,
entitlement, capacity, or Resource Manager constraints.

The Control Plane coordinates **when** dependent domains must be
recomputed. Domain services own **how**. Downstream components consume
the **selected** configuration after recomputation. They must not
silently reconstruct the original recommendation.

The Admin UI and Admin AI Agent are clients of the same decision APIs.

## Managed prerequisites vs privileged host remediation

Kultrun prefers using the current host. It still owns application-level
prerequisites it can isolate. Three classes, owned as architecture, not
as Stage 1.6C code:

- **Managed prerequisites (Class A).** Python interpreters, isolated
  environments, runtime packages, runtime-owned dependency graphs, and
  models. Future: acquire under Kultrun state; never mutate system
  Python. Commercial installations must not require the customer to
  preinstall a specific Python (`docs/DEBT.md` K-66). Stage 1.6C still
  locates an already-present Python 3.12; that is a current reference
  proof, not the commercial target.
- **Privileged remediation (Class B).** GPU drivers and other
  machine-wide components. Prefer an existing adequate driver. Do not
  upgrade for recency. Missing/insufficient drivers leave the runtime
  candidate blocked until remediation succeeds. Future automatic
  remediation is only on validated platforms, only with explicit
  administrator approval, never silent, and must rediscover the host and
  recompute feasibility afterward (`docs/DEBT.md` K-77).
- **Fixed constraints (Class C).** Physical GPU, architecture, RAM,
  accelerator family, pass-through, physical capacity. Detect and
  explain; do not pretend to provision them.

`VllmNativeProvisioner` installs isolated packages only. It does not
install Python, drivers, or CUDA toolkits.

## TIER 6 — Serving and the record of it

### `inference`

| | |
|---|---|
| **Owns** | `InferenceInstance` — instance identity, host, model artifact and revision, runtime, executor, endpoint, reservation, context, runtime concurrency, platform request limit, access-policy reference, lifecycle state, desired vs observed vs health, configuration version. The lifecycle: create, start, observe, stop, restart. `InferenceEndpoint`. `InferenceRequest` / `InferenceResponse` — generic bounded generation, not a vLLM or OpenAI payload. The distinction between status and health. Collections are `inference_instances[]`. The same artifact may have many instances; many models may run at once. |
| **Consumes** | `kernel` · `resource` · `execution` · `runtime` · `model` |
| **Produces** | A running instance, a healthy endpoint, and reconciliation on restart |
| **Must not** | Route requests, authenticate, or emit usage events. Confuse a reachable port with a functioning API. Collapse to `current_inference_instance` or `model.running`. Delete a stored artifact on stop. Import `planning`. Import `platform`. Construct runtime argv. Reimplement subprocess management. Import `subprocess`. Auto-release a reservation on stop. Treat stored/active as capacity partitions. Require a PID from every executor. Persist prompts or generated text by default. Select a model, foundation, or runtime. |
| **Created** | 1.5B reference serving lifecycle (plural) · 1.5C compose Runtime+Executor · 1.6K plan-driven create · 1.6L first real native vLLM serving · **Deepened** 4.4 concurrent live instances |

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
| **Ports** | `HealthSource` and `ReconcilePhase`. These live at tier 8, so only tiers **above** 8 implement them directly. A lower domain reports facts in its own vocabulary and the composition root adapts them — discovered implementing Stage 1.1, where `host` needed to report health from tier 2. Not a workaround: whether a missing provider makes the platform "degraded" depends on the whole platform's state, which one subsystem cannot know, so grading belongs to the aggregator. The same division the record store uses — the store returns facts, policy decides. |
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
| **Consumes** | `api`, for the Admin Agent. `gateway`, `knowledge` and `brains` through `AccessContext` for the Team Agent, plus the tier-1 semantics. |
| **Must not** | Hold unrestricted shell access. Reach any control-plane or infrastructure domain directly — `platform`, `host`, `components`, `storage`, `capacity`, `model`, `planning`, `resource`, `execution`, `runtime`, `inference`, `analytics`, `intelligence`, `vendor`, `install` are reached through `api` or not at all. Perform a meaningful mutation without recorded administrator approval. |
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
| **Owns** | **Bootstrap and preparation.** The bootstrapper flow, component provisioning and offline bundles, modular updates and rollback, and the dependency and licence inventory. |
| **Consumes** | `host` · `components` · `planning` · `api` |
| **Must not** | Duplicate component resolution, which `components` owns. Become a generic downloader. Be required for the platform to start. |
| **Created** | **1.1, minimally** — enough to obtain or reuse the reference host's discovery provider · **Deepened** 10.1–10.4 |

Preparation is the step Trace A used to begin with and nobody owned. It
belongs here:

```text
fresh host → install: determine required components
                    → detect a reusable existing component
                    → provision only if required
                    → verify
           → host discovery → HostCapabilities
```

**Direction matters.** `install` sits above `host` and runs before it in
the startup sequence; `host` never calls `install` and never requests
provisioning. Discovery reports that a provider was unavailable, and
something above decides whether to act. Reversing that would put a tier-2
domain in the business of modifying the machine it is inspecting.

**The first mechanism is the host's own package manager.** For the Linux
NVIDIA reference environment, a component that is not already present is
obtained through the distribution's package manager. That is an
implementation choice behind this boundary, not an architectural
commitment: no distribution and no package-manager name appears in a core
contract, and a future verified-release-artifact mechanism — for
package-manager gaps, pinned versions, enterprise mirrors, offline bundles
and other environments — is deferred rather than designed.

**This is not a downloader.** Downloading is one provisioning mechanism
among several: an existing host binary, a system package manager, a managed
environment, a verified release artifact, an OCI image, an enterprise
mirror, an offline bundle. The stable concept is *component requirement →
resolution*, not *URL → file*. A core abstraction whose only idea is
`SoftwareDownloader` would encode the narrowest mechanism as the model and
make every other one an exception.

## TIER 10 — `adapters`

Every third-party implementation, one package per seam, mirroring the
port it implements:

```text
adapters/persistence/     file · sqlite
adapters/http/            stdlib_server · asgi
adapters/host/            hwloc · nvml · native_linux · native_darwin ·
                          amd_smi · level_zero · nfd · captured_fixture
adapters/execution/       native_process · recording · container
adapters/container/       docker · recording  (podman · containerd later)
adapters/runtime/         reference_process · vllm (declared support) · (llama_cpp · mlx later)
adapters/provisioning/    fixture · vllm_native
adapters/model_source/    huggingface · local_file
adapters/estimators/      kultrun · llmfit
adapters/acquisition/     huggingface · fixture · (local_file · object_storage later)
adapters/capacity/        accelerate · benchmark  (llmfit is a requirement estimator, not capacity authority)
adapters/usage/           partitioned_local · exporter
adapters/inference/       local_endpoint · litellm
adapters/identity/        local · oidc · scim
adapters/knowledge/       managed_files · smb · webdav · sharepoint · google_drive
adapters/embedding/       local_model · external
adapters/telemetry/       posthog
adapters/entitlement/     offline_licence · vendor_service
adapters/adaptation/      peft · merge
```

Every adapter is replaceable. Default product mode is **AUTO**: llmfit is
the primary requirement estimator; the Kultrun estimator is the built-in
fallback when llmfit cannot produce valid evidence for the exact request.
Strict `llmfit` and `kultrun` remain available; explicit `llmfit` does
not fall back, and explicit `kultrun` does not require llmfit.
Composition (`main.resolve_estimator`) builds `EstimatorRouter`; planning
consumes only the port. Cross-provider comparison lives in `tools/` and
tests, not in `planning`. The previous attempt used llmfit as capacity
evidence and found `recommend` nondeterministic on a real host; this
rebuild uses `llmfit plan` as a requirement estimate only, and Kultrun
SAFE capacity remains the fit boundary.

Note how much of `adapters/host/` names a third-party tool. That is the
point: every one of those is a commodity enumerator that someone else
maintains across more platforms than Kultrun will ever validate, and each
sits behind one Kultrun-owned port. Adding a vendor is an adapter, not an
architecture change. **None of them appears in the core module list**, and
Law 5 keeps each of them inside tier 2's import budget.

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

**Trace C — capacity is reserved, then later an instance starts**
(1.5A reservation; 1.5B/1.6 launch)

```text
STORED ModelArtifact ≠ ResourceReservation ≠ InferenceInstance

Planning / DeploymentPlan
  → exact ModelArtifact
  → platform translates DeploymentPlan.resource_request + artifact_id
    → ResourceRequest
  → ResourceManager + live SAFE − ACTIVE reservations
  → AdmissionDecision
  → ResourceReservation ACTIVE
  → InferenceInstance CREATED
       reserved is not running
  → vLLM RuntimeAdapter → RuntimeLaunchSpec
       admitted VRAM ÷ selected device total → `--gpu-memory-utilization`
       (runtime budget control, not a kernel VRAM cgroup)
  → NativeProcessExecutor.start → real vLLM
  → readiness (alive + health + served-model match)
  → RUNNING
  → InferenceRequest → adapter → local vLLM → InferenceResponse
  → stop via Executor; reservation remains ACTIVE until explicit release
       a vLLM plan does not start a reference server

STORE_ONLY warehouse acquisition remains independent of DeploymentPlan.

Stored / Active / Running are lifecycle states, not capacity partitions.
Disk, RAM, VRAM and unified memory stay separate. Capacity follows the
active reservation, not a fixed stored/active split.

failure: instance FAILED; reservation remains ACTIVE
stop:    stop the process; reservation remains ACTIVE
release: rejected while STARTING / RUNNING / STOPPING / UNKNOWN
```

**Trace D — a model is acquired** (1.4C thin v0; 2.6 deepened)

```text
ModelSource (identity/metadata only)
  ≠ ModelRequirementEstimator
  ≠ Planning / SelectionRecommendation
  → ModelAcquisitionRequest (known candidate; no caller path)
  → SAFE storage preflight (not ResourceReservation)
  → ModelAcquisitionProvider.pin_revision + fetch into staging
  → verify required files / revision / manifest
  → promote → ModelArtifact STORED
  → plural ModelInventory
  ≠ ResourceReservation
  ≠ InferenceInstance

interrupt/failure: staging cleaned, never STORED
stored is not running
```

**Trace E — a model is chosen** (1.4B v0; 3.3–3.5 deepened)

```text
curated candidates → ModelMetadata (unresolved fields explicit)
  → ModelEstimationRequest (identity, quant, context, runtime, placement;
    no silent substitution)
  → ModelRequirementEstimator port
  → EstimatorRouter (auto: llmfit primary → typed failure → Kultrun fallback;
    or a strict provider)
  → one ModelRequirement (bytes, method, confidence, effective provider,
    failover provenance)
  → capacity CapacityEnvelope (SAFE layer only for the fit boundary)
  → planning DeploymentCapacity for the proposed placement
  → planning FeasibilityResult per candidate: compatibility, storage,
    memory, CapacityUtilization, preferred-band status, reasons
  → planning Selector, deterministic under a recorded SelectionPolicy
  → SelectionRecommendation + DeploymentPlan
       (primary, preferred alternatives, underutilized alternatives,
        rejected, rationale, policy version, effective estimator only)
  → approval → Trace D → Trace C

every rejected or excluded candidate records why
a recommendation is recomputed; it is not stored as permanent truth
planning never reserves
planning never reconciles estimators
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
| 1.2A | Storage Sonar v0, Prototype Console | `capacity`, `storage`, `api` | ✅ closed |
| 1.3 | `execution`, `runtime`, component seam | `host` | ✅ via finding 2 |
| 1.4A | `ModelSource`, `ModelMetadata`, `ModelRequirement` v0 | `model` contracts | ✅ |
| 1.4B | `planning` v0: feasibility, selection, `DeploymentPlan`; `ModelRequirementEstimator` | `capacity`, `model`, `host` | ✅ |
| 1.4C | acquisition v0, plural inventory | `storage` pool, `model` | ✅ via finding 1 |
| 1.5A | `resource` admission and reservation | `capacity`, `ModelRequirement` | ✅ crude requirement, already in the ledger |
| 1.5B | `inference` instance lifecycle (plural, reference serving) | `resource`, `execution`, `runtime`, `model` | ✅ |
| 1.5C | Runtime / Executor boundary reconciliation | 1.5B | ✅ |
| 1.6A | Minimal ContainerExecutor + executor portability | 1.5C | ✅ closed L2 |
| 1.6B | RuntimeResolver + RuntimeCandidate | 1.6A, 1.5C descriptors | ✅ closed L1 |
| 1.6C | RuntimeProvisioningPlan + RuntimeProvisioner + RuntimeInstallation | 1.6B | ✅ closed L2 |
| 1.6D | RuntimeVerifier + RuntimeCapabilityProfile | 1.6C | ✅ closed L2 |
| 1.6E | FoundationSelection + two-phase provisionable/executable + invalidation seam | 1.6D | ✅ closed L1 |
| 1.6F | EligibleModelView + runtime/model compatibility authority | 1.6E | ✅ closed L1 |
| 1.6G | ModelRequirement + Capacity consume EligibleModelView | 1.6F | ✅ closed L1 |
| 1.6H | ModelSelector + bounded AUTO/MANUAL ModelSelection | 1.6G | ✅ closed L1 |
| 1.6I | Authoritative DeploymentPlan | 1.6H | ✅ closed L1 |
| 1.6J | Plan-driven Acquisition + Resource admission | 1.6I | ✅ closed L1 |
| 1.6K | Plan-driven InferenceInstance create | 1.6J | ✅ closed L1 |
| 1.6L | first real native vLLM serving + bounded inference | 1.6K | OPEN; T0/T1/T2 local; T3/T5 pending |
| 1.6 | first real-model `InferenceInstance` | 1.5C then 1.6A… | ✅ ordered; 1.6L is the serving vertical |
| 1.7 | `gateway`, `analytics` | `identity`, `inference`, `entitlement` | ✅ |
| 1.8 | milestone gate | `platform`, `api` | ✅ |
| 2.1–2.4 | `storage` deepened | `host`, `evidence`, `ManagedUsageSource` | ✅ implemented by `model` at 1.4C |
| 2.5–2.6 | `ModelSource` and acquisition deepened | storage mutation safety at 2.4 | ✅ correctly ordered as deepening |
| 3.1 | `ModelRequirement` real | `ModelMetadata` at 1.4A / 2.5 | ✅ |
| 3.2 | `CapacityEvidenceProvider` | `capacity` at 1.2, requirement at 3.1 | ✅ |
| 3.3–3.5 | `planning` deepened | 1.4B, 3.1, 3.2, `capacity`, `components` | ✅ via finding 2 |
| 4.1–4.4 | `resource`, `runtime` deepened | 1.5A, 1.3 | ✅ |
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
| 12.3 portfolio optimizer | `planning.ports.Selector` | 1.4B / 3.5 |
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
workflow starting at Stage 1.5A.

**Finding 4 — `Approval` has no owning stage.** Stage 6.2 requires that
meaningful mutations obtain explicit administrator approval, and the
constitution requires overrides to be validated, explained, recorded and
reversible. The recording mechanism is unassigned.
*Applied:* `platform` owns `Approval`, created at Stage 0.3 alongside local
administrator identity.

**Finding 5 — health has no seam, only a destination.** Stage 6.1
displays platform health and Stage 1.5B distinguishes status from health,
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
| Declared non-edges (§4) | `planning` ⊥ `resource`; `execution` ⊥ `runtime`; `execution` ⊥ `capacity`; `runtime` ⊥ `capacity`; `storage` and `capacity` ⊥ `model`; nothing imports `intelligence`; `agents` reaches the platform only via `api`. |
| Narrow edge scope (§3) | `capacity` imports only `storage.contracts` and `host.contracts`; `execution` imports only `host.contracts`. |
| Adapter budget (Law 5) | An adapter imports only what the domain declaring its port may import. A `HostDiscoveryProvider` cannot reach `model`, `planning`, `resource`, `runtime` or `inference`. |
| No provider in core | No core module names a discovery provider, a vendor library or a CDI concept. |
| Adapter boundary | Nothing in tiers 0–9 imports `adapters`. Only `main` does. |
| Kernel purity | `kernel` imports no third-party package and names no domain concept. |
| Contract isolation | Every `contracts.py` imports only `kernel` and lower-tier contracts, and serializes without importing a runtime or provider library. |
| Contract reference form | No contract field is typed as another domain's entity class; cross-entity references are identifiers. |
| Host scoping | Every host-scoped contract carries a host identifier, and every such collection is plural. |
| Concept census | Module count is compared against the declared concept inventory at every milestone consolidation checkpoint. |

The concept census is the direct control for Pattern 4. Eleven
`storage_*` modules for one concept would have failed it on the day the
second one was created.

## Counting the macrostructure

Three different numbers describe this architecture and they are routinely
confused, including in review conversations about this document. They
measure different things and none is a proxy for another.

| Measure | What it counts | Today |
|---|---|---|
| **Tiers** | Bands in the dependency law, tier 0 to tier 11 | **12** |
| **Architecture positions** | Named entries in the tier map: 27 domains, plus `adapters` and the composition root | **29** |
| **Implemented packages** | Directories that exist under `src/kultrun` | **18** |
| **Implemented modules** | `.py` files under `src/kultrun`, excluding `__init__.py` | **36** |

Positions are the *design*: every one exists in the map from the first
commit, including the ones that are still empty, because absence should be
visible. Implemented packages and modules are the *state*: what has been
built so far. The gap between 29 and 18 is not debt — it is the eleven
domains whose stages have not run.

The census in Part VII compares implemented **modules** against declared
**concepts** within each package. It does not compare positions to
packages, which would only measure how far through the roadmap we are.

Two corrections for the record. A figure of "24 modules" circulated in
review discussion; it was wrong and never entered this document — the tier
map has always held 29 positions. And the Stage 0.3 output package records
"35 modules", which counted only modules inside packages and omitted the
composition root at `src/kultrun/main.py`; the comparable figure under the
method defined here is 36. That stage package and its checkpoint are left
unedited, because a closed record is evidence of what was true and believed
at the time, and correcting it in place would destroy the thing it exists
to hold.

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

Part IX records where external technology sits and what Kultrun
deliberately does not build. It is part of the architecture rather than an
appendix: a decision not to build something is as structural as a module
boundary, and it is the decision most likely to be quietly reversed by
someone solving an immediate problem.

A stage brief cites this document for the modules it touches, and the
stage output package records any change to the map. A change to a module
boundary is a change to this document, made in the same commit as the
code — the same rule the roadmap applies to stage boundaries, for the same
reason.

---

# PART IX — EXTERNAL TECHNOLOGY AND SCOPE

## 0. The binding rule

**No concrete hardware-discovery technology is part of Kultrun's core
architecture.** hwloc, NVML, NVIDIA tooling, AMD SMI, Level Zero and
Sysman, NFD, native macOS discovery and anything comparable that arrives
later are implementations of Kultrun-owned ports.

```text
HostDiscoveryProvider          (port, owned by host)
├── HwlocProvider              general topology, first candidate
├── NvidiaProvider             vendor supplement
├── AppleProvider              future
├── AmdProvider                future
├── IntelProvider              future
├── NfdProvider                optional, Kubernetes environments
└── further providers
```

**No core domain or module is named after one of these technologies.** The
core must keep working when hwloc is replaced, when several providers are
combined, when a provider is unavailable, when a vendor is added, and when
a host uses no accelerator provider at all. Provider-local handles,
identifiers and schemas stay inside the adapter.

The test is worth applying literally: if a technology's name would have to
appear in a core module name, a core contract field or a core signature,
the boundary has been drawn in the wrong place.

## 1. What Kultrun does not build

Kultrun's differentiation is not that it can enumerate a PCI bus. Every
item below is a commodity that mature projects already maintain across
more platforms than Kultrun will ever validate, and building any of them
would be a large proprietary investment returning nothing a customer would
pay for.

**Do not build, absent a demonstrated gap:** CPU and NUMA topology
enumeration; generic PCI enumeration; vendor GPU management libraries; the
Container Device Interface; a container runtime; Kubernetes hardware
discovery; a GPU driver installer framework; a custom container device
injection protocol.

**Do build:** normalized capability contracts; evidence reconciliation and
conflict surfacing; safe capacity derivation; compatibility and
feasibility; provider selection and fallback; runtime and executor
selection; admission and resource policy; lifecycle orchestration;
explainability; and evidence-based support classification.

The line between the two lists is the line between *observing* a machine
and *deciding* what may safely be done with it. Everything on the first
list observes. Everything on the second decides, and deciding is the
product.

"Absent a demonstrated gap" is load-bearing. A gap is demonstrated by
running the candidate tool on a real machine and finding it does not answer
a question Kultrun needs — not by predicting that it might not.

## 2. Candidate technologies and their positions

Each of these is a **replaceable implementation dependency**. None is an
architectural dependency, and the architecture must survive any of them
being absent, broken or replaced.

| Technology | Role | Status | Sits behind |
|---|---|---|---|
| **hwloc** | General topology and device discovery: CPU, cores, NUMA, caches, memory, PCI and I/O objects | **Optional-preferred initial general discovery provider.** First candidate to evaluate; not core; never assumed preinstalled; absence is a valid state; **does not define `HostCapabilities`** | `HostDiscoveryProvider` |
| **NVML** | NVIDIA device memory, driver version, per-device detail | Likely supplement on NVIDIA hosts; the **smallest** supplement the evidence requires | `HostDiscoveryProvider` |
| **Native OS sources** | Whatever a platform exposes that a general tool does not | Supplement, only where a gap is demonstrated | `HostDiscoveryProvider` |
| **AMD SMI** | AMD device identity, memory, topology | Future, unscheduled | `HostDiscoveryProvider` |
| **Level Zero / Sysman** | Intel accelerator discovery and telemetry | Future, unscheduled | `HostDiscoveryProvider` |
| **Kubernetes NFD** | Node features as labels in a Kubernetes environment | Future, optional | `HostDiscoveryProvider` |
| **CDI** | Vendor-neutral device attachment for containers | Future, optional | The OCI executor adapter |
| **NVIDIA Container Toolkit** | Generates the CDI specification for NVIDIA devices | Future, optional | Host provisioning, not Kultrun code |
| **Docker / Podman / containerd** | Container execution | Optional; native process execution is the reference | `ContainerEngine` |

### What the research establishes, and what it does not

**hwloc** is portable across Linux, macOS, Windows and several Unix
variants, is largely processor-independent because it reads what the
operating system exposes, is BSD-licensed, and is packaged by most Linux
distributions as well as Homebrew and vcpkg. It ships interoperability
headers for CUDA, NVML, AMD ROCm SMI and Level Zero. Its own documentation
also states plainly that "platforms and/or operating system versions will
only report a subset of this information."

#### What "optional-preferred" means

hwloc holds a specific and deliberately narrow status:

- it is the **preferred initial** general-purpose provider candidate;
- it is **not a Kultrun core dependency**, and the architecture must
  survive its absence;
- it is **never assumed preinstalled**;
- the product may eventually **detect, reuse, provision or repair** it
  through product-managed preparation, because plug-and-play means the
  platform takes responsibility for what it needs rather than handing the
  customer a prerequisites list;
- other and future providers may replace or supplement it, and its absence
  remains representable in `HostCapabilities` rather than fatal;
- **it does not define `HostCapabilities`.** The contract is Kultrun's, and
  a field exists because a Kultrun decision needs it, never because hwloc
  happens to report it.

Preferring something and depending on it are different commitments. The
first survives the tool turning out to be wrong for us; the second does
not. Where the preparation mechanics eventually live is a Milestone 10
installer question and is not settled here.

That "subset" sentence is why the architecture is a provider *service*
rather than a provider *choice*. Partial observation is hwloc's documented normal
behaviour, not an edge case, and any design that assumed one tool answers
everything would be designed against a claim its own maintainers do not
make.

It also marks the boundary of what hwloc gives us. Its accelerator
interoperability is largely about *locality* — which processors are near a
device, and the corresponding topology object. Device memory size and
driver version come from the vendor library. So the shape "general provider
plus vendor supplement" is not a hedge; it follows from what these tools
actually do.

**CDI** is a CNCF specification. Runtimes read JSON or YAML from `/etc/cdi`
or `/var/run/cdi` and apply the described edits to the OCI specification;
Docker, Podman, containerd and CRI-O support it, and devices are requested
by fully-qualified name. The specification states that "areas like resource
management are explicitly left out of CDI," which places it exactly where
this document places it. NVIDIA's toolkit generates specifications via
`nvidia-ctk cdi generate`, and recent versions refresh them automatically
on driver or toolkit change; AMD's `amd-ctk` does the equivalent. A
CDI-only path exists that does not require the legacy runtime hook.

**NFD** detects node features and advertises them as Kubernetes labels,
extended resources, annotations and taints, across CPU, kernel, memory,
network, PCI, storage, system and USB sources. Labels are predominantly
boolean or short string facts — a node has a PCI device of some vendor and
class — rather than quantities. It can therefore save Kultrun rediscovering
what a cluster already knows, and cannot by itself answer how much memory a
device has.

**AMD SMI** exposes socket and processor handles, BDF, UUID, board
information and link topology. Its documentation warns that a device handle
"may change after restarting the application, so it should not be
considered a persistent identifier across processes" — a concrete
demonstration that provider identity is not platform identity, and that
Kultrun must mint its own.

**Intel** exposes discovery through Level Zero Sysman.

**On the NVIDIA supplement specifically.** If the spike shows the general
provider cannot answer something capacity needs on the reference host, the
remedy is the smallest mature vendor supplement, not a Kultrun-written
enumerator. Two constraints on it: NVIDIA-specific observations must never
become *required* for all accelerator types — a host with an AMD device or
no device must produce a valid `HostCapabilities` without them — and no
NVML structure or vocabulary may reach a downstream domain.

**Apple Silicon** is deliberately left open. hwloc supports Darwin, and
whether it reports enough for a Kultrun host profile is an empirical
question. Any macOS-specific collection stays behind a provider adapter,
and no Apple-specific concept enters `HostCapabilities` unless it describes
a genuinely cross-platform capability — unified memory does, because it
changes how any host's memory budget must be computed; a Metal-specific
detail does not.

**What none of this establishes** is that any particular tool is the right
choice for Kultrun. Documentation says what a tool can do on some machine,
not what it does on ours. That is what the Stage 1.1 spike is for.

## 3. Before bundling anything

`docs/PRODUCT_VISION.md` §57 already requires provenance and licence
classification for every bundled dependency. For a discovery or device
technology, record before it becomes anything more than a candidate:
licence and version; source and provenance; redistribution rights and any
commercial restriction; supported platforms; what installing it requires on
a customer machine; and **what Kultrun does when it is absent**.

The last is the one that gets skipped. A provider with no defined absent
behaviour is a mandatory dependency that nobody decided to make mandatory.

Technical usefulness is not sufficient grounds for bundling. hwloc being
excellent is an argument for trying it, not for shipping it.
