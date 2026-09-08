# KULTRUN
## Company Brain Platform — Technical Product Roadmap

**Purpose:** Define the build sequence for Kultrun, the Company Brain platform.  
**Authority:** Authoritative for milestone structure, stage scope, ordering and gates.  
**Derived from:** `docs/PRODUCT_VISION.md` (the architectural constitution) is authoritative for *what* Kultrun is and what its contracts mean. This document is authoritative for *in what order it gets built and how each step is proven*.  
**Companion:** `docs/ARCHITECTURE.md` is authoritative for *where each concept lives* — module boundaries, ownership, inputs and outputs, and tier dependency direction. This document orders the work; that one structures it, and its Part V verifies this sequence against the module graph.  
**Design basis:** The measured outcome of the previous implementation attempt, recorded in `docs/legacy/` and in the `phase9` and `backup/*` branch history.

---

# PART I — WHY THIS ROADMAP IS SHAPED THIS WAY

A roadmap that only lists subsystems in a plausible order is worthless;
the previous attempt had one and still failed in a specific, diagnosable
way. This part records what actually happened, because every ordering
decision in Part III exists to prevent a repeat.

## 1. What the previous attempt actually proved

The prior attempt was disciplined, well-documented and technically
strong. It was not sloppy work. It still ended without a working
product, and the reasons are measurable.

| Evidence | Measurement |
|---|---|
| Total work | 19 commits, 152 files, 58,706 lines |
| Growth pattern | +23,940 insertions against −425 deletions |
| Storage subsystem | 11,761 lines across 20 files — **40% of `core/`** |
| Model subsystem | 6,845 lines across 15 files |
| Identity, gateway, usage, analytics | **zero** post-baseline changes |
| All seven adapter families combined | under 800 lines |
| Largest file in the repository | `PROVISIONAL.md`, a register of approximations, at 2,187 lines |
| End-to-end proof on real hardware | **never achieved** |

The decisive fact is the last one. The prior plan's step C9 was
"fresh-host live inference acceptance — proof that an empty host reaches
real inference through platform-owned paths." Work stopped one step
short of it. Every completion claim in that history is unit-level or
single-subsystem evidence. **No commit anywhere in the prior attempt
demonstrates a request reaching a model and returning an answer through
platform-owned paths.**

Meanwhile, the genuine engineering information the project acquired came
almost entirely from running on real hardware:

- A storage probe run "spent roughly 48 minutes probing and kept
  nothing," because evidence was persisted only after the whole
  calibration returned. After the fix, the same 6.70 GiB requirement
  resolved in about **62 seconds**.
- The filesystem advertised roughly **239 TB free** while the platform
  correctly refused a **6.70 GiB** install for want of verified evidence.
- Deleting a 42,990 MiB probe file returned only about **1.1 GB** to
  `df` immediately; the volume reclaims asynchronously. Free-space deltas
  therefore cannot prove anything.
- A cancelled probe left a **42,990 MiB orphan file**, because the work
  ran on a daemon HTTP thread and the lock released only at process exit.
- `llmfit`'s `recommend` call proved **nondeterministic** on the real
  host and had to be demoted to advisory with an internal fallback.
- Catalog entries routinely carried `context_length: null` and
  `download_bytes: null`.
- Capacity observation **crashed** on a model discovered on disk whose
  inventory record carried an explicit null management section — found
  only when subsystems were finally wired together.

None of those were visible to unit tests. Real hardware was the only
oracle that mattered, and the plan deferred it to the end.

## 2. The five failure patterns this roadmap prevents

**Pattern 1 — Depth before proof.** Two of six subsystems consumed the
majority of the code before any end-to-end path existed. The
"exoskeleton-first" rule was itself written at commit 13, as a
corrective, after the imbalance had already happened. A rule adopted
after the damage is a lesson, not a control.

*Control:* the first milestone after the kernel is a complete working
vertical — crude everywhere, real end to end — and no subsystem may be
deepened until it passes on real hardware.

**Pattern 2 — Horizontal layering.** The prior plan built all of the
executor, then all of the runtime, then all of the storage chain, then
all of the model supply chain. Horizontal layers cannot be integrated
until the last one lands, so integration defects surface at maximum
cost. The null-management-section crash is exactly this.

*Control:* stages are ordered by what the next end-to-end path needs,
never by subsystem completeness.

**Pattern 3 — Unbounded approximation debt.** The provisional register
grew to 2,187 lines and 54 entries with 24 refinements still open in one
section alone. Recording approximations honestly is a genuine strength;
having no mechanism to retire them is not. The register became the
largest artifact in the repository.

*Control:* the debt ledger has explicit burn-down gates. A milestone
cannot close while its own stages' debt is still open.

**Pattern 4 — Concept ownership diffusion.** `core/` accumulated eleven
`storage_*` modules and fifteen `model_*` modules, including
`storage_capacity.py`, `storage_capacity_cache.py`,
`storage_capacity_calibration.py`, `storage_capacity_evidence.py` and
`storage_capacity_resolution.py` side by side, plus three overlapping
feasibility modules. Purely additive growth (+23,940/−425) let
near-synonymous modules coexist until nobody owned a concept.

*Control:* one concept has exactly one owning module, and every
milestone has a consolidation checkpoint.

**Pattern 5 — Silent plan drift.** The plan document defined C6 as
utility-and-ranking and C7 as the selector. In execution the two
collapsed and everything shifted down by one, so the real C7 was the
planned C8. The document was never corrected and stopped describing the
work for the final third of the project.

*Control:* stage briefs before, output packages after, and renumbering
requires editing this document in the same commit.

## 3. The governing sequencing rule

> **Design the whole skeleton on paper. Build it thin end-to-end. Then
> deepen it, in the order reality demands.**

This is not in tension with the constitution's "design the complete
skeleton before deep implementation" — it is how that rule is executed.
`docs/PRODUCT_VISION.md` already designs the whole system end to end.
This roadmap builds that design as a working vertical first, then earns
the right to add precision.

The operative test before any piece of work:

> Does the next end-to-end customer path need this?

If no, defer and record it. If yes, build the smallest version that is
**honest** — one that fails closed rather than guessing. Never optimize
a subsystem before the next end-to-end path works.

The prior attempt adopted this rule too late to benefit from it. Here it
is a precondition, not a retrospective.

---

# PART II — RULES THAT APPLY TO EVERY STAGE

## 4. Definition of done

A stage is complete only when all of the following exist. These are not
optional extras to be scheduled later; the prior attempt scheduled
reconciliation and cleanup separately and never reached them.

1. **Contract** — versioned domain contract with `schema_version`.
2. **One working implementation** behind a replaceable interface.
3. **Failure semantics** — explicit, and fail-closed on unknown.
4. **Persistence and reconciliation** — if the stage holds state, it
   reconciles that state on restart, and cleans up its own orphans.
   State without recovery is not done.
5. **Cancellation and cleanup** — if the stage can run long or mutate,
   it is interruptible and leaves no orphan artifact and no false
   evidence.
6. **Platform API surface** — control-plane exposure of what the stage
   produces, so the Admin surface and Admin Agent never need a private
   back channel.
7. **Acceptance evidence** at the level required below.
8. **Debt ledger entries** for every approximation, each with the
   condition that would retire it.
9. **Stage output package** in `docs/stages/` and checkpoint in
   `checkpoints/`.

## 5. Acceptance ladder

Adapted from the prior attempt's own ladder, which was sound; the
failure was in when it was applied, not in its design.

| Level | Meaning |
|---|---|
| **L1 — Contract** | Focused tests. Schemas, adapters, serialization. Runs anywhere. |
| **L2 — Real host** | Executed on the reference host. Real values, real filesystem, real driver. |
| **L3 — Live inference** | A real model serves a real request end to end and emits a usage event. |
| **L4 — Integrated** | Multiple subsystems together: admission, denial, lifecycle, restart reconciliation, clean teardown. |

**L1 evidence never closes a stage that touches hardware, storage or a
runtime.** The 48-minute probe, the async reclaim, the `llmfit`
nondeterminism and the null-metadata crash were all L1-clean.

Milestones 1 through 4 each require L2 or above to close. No milestone
closes on L1 alone.

### L2 and above require an installed artifact

**Binding from the workflow-adoption checkpoint forward.** An `L2`, `L3` or
`L4` result must come from a prototype artifact installed into an isolated
environment on the target host, not from a source tree executed in place.
The artifact must be traceable to a committed source state, and the
checkpoint records the deployment token. `docs/DEVELOPMENT_WORKFLOW.md`
holds the mechanics.

The reason is narrow: a result produced by a source tree on a rented host
cannot be reproduced once that host is gone, and a locally-patched
installation proves something about the machine rather than about the
product.

Stage 1.1 closed at `de9219e` under the earlier style and **remains accepted
historical evidence.** It is not reopened; it is what motivated the change.

## 5b. Hardware variability and testing intensity

**Hardware variability must be absorbed near the bottom of the
architecture.** The hardware-sensitive path is:

```
host → capacity → runtime / execution → inference
```

Once a machine is represented through `HostCapabilities`,
`CapacityEnvelope`, `ModelRequirement`, `ResourceReservation`,
`RuntimeLaunchSpec` and `InferenceInstance`, every domain above should be
testable without knowing which server produced them.

**If a higher-level domain repeatedly requires validation on specific
accelerator or server models, treat that as a potential architecture leak
and review the dependency boundary** rather than adding a platform
conditional. `docs/TESTING_STRATEGY.md` lists the questions to ask.

### Test modes

`docs/TESTING_STRATEGY.md` defines them; stage entries reference them.

| | |
|---|---|
| **T0** | pure and structural: no server |
| **T1** | replay of evidence captured from real machines: no server |
| **T2** | clean artifact install: no server |
| **T3** | one representative real host |
| **T4** | several representative shapes |
| **T5** | live inference on real hardware |

**A mode is not an evidence level.** T0–T2 produce `L1`; T3–T4 can produce
`L2`; T5 normally produces `L3`; integrated acceptance earns `L4`. A test
mode never redefines a `DeploymentProfile`: a wheel installing on macOS CI
proves packaging, not Apple support.

### Testing intensity by area

| Area | Real server | Cross-server intensity |
|---|---|---|
| Milestone 0 — contracts and kernel | No | None |
| Stage 1.1 — host discovery | Yes | **Very high** |
| Stage 1.2 — capacity | Yes | **Very high** |
| Stage 1.2A — storage sanity + console | Selective | Low |
| Stage 1.3 — runtime and executor | Yes | High |
| Stage 1.4A — catalog and metadata | No | None |
| Stage 1.4B — feasibility and selection | Selective | Low |
| Stage 1.4C — acquisition and inventory | Selective | Low |
| Stage 1.5A — admission and reservation | Selective | Low |
| Stage 1.5B — inference instance lifecycle | Selective | Low |
| Stage 1.5C — Runtime / Executor boundary reconciliation | No | None |
| Stage 1.6 — real inference vertical | Yes | **Very high** |
| Stage 1.7 — gateway | Integrated only | Low |
| Milestone 2 — storage empirical evidence | Yes | High |
| Milestone 3 — feasibility and selection | Selective | Low |
| Analytics | Integrated only | None |
| Identity, policy, entitlement, audit | No | None |
| Knowledge and RAG | Integrated only | Low |
| Training execution (future) | Yes | High |
| Multi-host placement (future) | Yes | High |

"Very high" means the layer interprets the machine itself, so breadth
accumulates over time — not that every shape blocks the first vertical.

**Do not rent hardware because a stage number is high.** Use a real host
only where it proves something a fixture cannot.

### Capture once, replay often

A newly tested real shape should usually become a sanitized fixture, so one
physical test creates permanent regression coverage and the machine is only
needed again when something material changes.

**Fixture replay is regression evidence, not current physical
compatibility evidence.** Real hardware must return when a driver
generation, runtime major version, provider implementation or host contract
changes materially, or when support is being claimed.

### Cadence

Every change runs T0, T1 and T2 — architecture, full suite, fixture replay,
lint, types, wheel build and clean-install smoke. A stage gate runs the
real-hardware proof it requires. Milestones run breadth. Releases run every
shape claimed Supported or Certified.

## 6. Evidence and authorization rules

These are the prior attempt's most valuable output and carry forward
unchanged.

**Three layers, one authority.**

```text
Reported    what a source claims        (nvidia-smi total, statvfs free)
Effective   corrected for real usability (overhead, async reclaim)
Safe        effective minus protected headroom and policy reserve
```

Only the **safe** layer may authorize an allocation or a mutation.
Reported values may be displayed and may inform search. They never
authorize.

**Raw filesystem capacity never authorizes a storage mutation.** Never
infer probe success, or cleanup success, from a free-space delta; verify
the artifact directly.

**Usable capacity is the verified lower bound.** Never a midpoint, never
an interpolation, never an unverified upper bound.

**Facts are immutable; policy reinterprets them.** "32 GiB succeeded at
time T" stays true when the selection objective changes. Persist each
completed probe as an immutable classified fact *before* the next
expensive probe begins.

**An interrupted operation is never a success.** It is inconclusive and
must not raise a lower bound.

**Unknown is not zero and is not a pass.** Missing metadata stays
missing and surfaces in `unresolved_fields`. Never guess a value that
could authorize a mutation.

**Verdicts are never booleans.** Feasibility is `compatible`,
`conditional` or `unsupported`, because "we cannot determine this" is a
common and honest answer.

**Fail closed** when authoritative capacity is unresolved, when unified
memory support is incomplete, and when confidence is below the threshold
a commit requires.

**Keep these distinct, always:**

```text
compatibility  ≠  capacity  ≠  admission        (plausible / feasible / may start now)
static         ≠  live                          (what the host is / what is free now)
desired        ≠  observed  ≠  health           (intent / reality / liveness)
control plane  ≠  data plane                    (management / inference traffic)
```

Never double-subtract managed reservations from already-observed live
availability. The prior attempt shipped that bug and had to fix it.

## 7. Concept ownership

One concept has exactly one owning module. If a second module needs the
concept, it imports it; it does not restate it.

Forbidden: near-synonymous modules for one concept. If a name needs a
qualifier to distinguish it from an existing module — `_cache`,
`_resolution`, `_calibration` alongside a base module — that is a signal
the concept is fragmenting.

Dependency direction, which lower layers may not violate:

```text
hardware/evidence → capacity → requirements → feasibility
  → selection → orchestration → runtime/resource lifecycle
```

Capacity must not import the selector. Storage probing must not know
model identities. The resource manager must not know selection ranking.
Runtime adapters must not own capacity policy. The CLI must contain no
algorithms.

**Consolidation checkpoint:** every milestone ends with a review of
module count against concept count. Divergence is addressed before the
milestone closes, not after.

## 8. Debt ledger and burn-down gates

`docs/DEBT.md` replaces the prior attempt's provisional register. Same
honesty, with a retirement mechanism.

Every entry records: what is approximated, why that is acceptable now,
what would make it real, **the condition that forces its retirement**,
and the stage that owns it.

Labels: `WORKING`, `PROVISIONAL`, `DEFERRED`.

**Burn-down gates:**

- A stage may not open a new `PROVISIONAL` entry in a subsystem that
  already has an entry retired by the current milestone's gate.
- A milestone cannot close while any entry marked "retire before
  milestone close" remains open.
- Any `PROVISIONAL` value that authorizes a mutation must be retired
  before the milestone that introduced it closes. Approximations may
  inform recommendations indefinitely; they may not authorize
  indefinitely.
- The ledger's size is reviewed at every milestone gate. Growth without
  retirement is treated as a schedule risk, not bookkeeping.

## 9. External dependency rule

Every third-party component is an adapter behind a Kultrun-owned
contract, and every evidence provider is **advisory with a mandatory
internal fallback**.

`llmfit` was integrated, then found nondeterministic on the reference
host, then demoted to advisory with a fallback to closest-safe-fit. That
outcome is the default assumption, not the exception. If a stage cannot
function when an external provider is absent, broken or nondeterministic,
the stage is not done.

Docker, vLLM and LiteLLM are replaceable adapters. Native process
execution is first class. No third-party package may own a Kultrun
concept.

## 10. Plan integrity

The plan document must describe the work actually being done.

- Produce the stage brief (Part V) before implementing.
- Produce the stage output package and checkpoint after.
- **Renumbering or rescoping a stage requires editing this document in
  the same commit as the code.** The prior attempt's silent C6/C7/C8
  shift is why this is a rule.
- If implementation reveals that a stage boundary is wrong, change the
  boundary deliberately and record why. Do not reinterpret it in place.

## 11. Bounded selection and dependency recalculation

Kultrun combines automatic recommendation with bounded administrator
selection. For configurable deployment domains the product slogan is:

```text
Discover → Evaluate → feasible set → recommend a default
  → AUTO or bounded MANUAL → revalidate the selected choice
  → authoritative DeploymentPlan → Resource Manager admission → execute
```

Revalidate means the selected option is still in the valid set **and**
dependent derived state is recomputed. The technical expansion is:

```text
DISCOVER
    ↓
EVALUATE
    ↓
DETERMINE COMPATIBLE / FEASIBLE SET
    ↓
RECOMMEND DEFAULT / OPTIMAL
    ↓
AUTO or BOUNDED MANUAL SELECTION
    ↓
INVALIDATE DEPENDENT DERIVED STATE
    ↓
RECOMPUTE ALL AFFECTED DOMAINS
    ↓
VALIDATE COMPLETE RESULTING CONFIGURATION
    ↓
GENERATE AUTHORITATIVE DEPLOYMENT PLAN
    ↓
RESOURCE ADMISSION
    ↓
EXECUTE
```

AUTO uses the platform recommendation. MANUAL may select another option
only from the current platform-approved feasible set. Categories:

Recommended — preferred member of the valid set.
Selectable — another valid member of that set.
Blocked — unsupported, unresolved, unverified where required,
policy-disallowed, entitlement-disallowed, physically infeasible, or
unsafe. Blocked is not an override.

A manual selection is never an isolated substitution. Changing runtime,
executor, model, context, concurrency, memory, placement, replicas,
headroom, or another deployment setting must invalidate and recompute
every dependent compatibility, eligibility, requirement, capacity,
resource, and planning decision before execution.

The Control Plane / Deployment Planner coordinates **when**
recomputation is necessary. Concrete domain services own **how** their
domain is evaluated. Do not introduce a generic `SelectionFramework` or
dependency-graph engine until repeated concrete implementations
demonstrate a real need (`docs/DEBT.md` K-83).

Resource Manager remains the final physical admission authority.

Introduce the pattern incrementally at existing domain seams:

```text
1.6C  provision the explicitly selected RuntimeCandidate; never
      silently substitute another path; INSTALLED ≠ VERIFIED
1.6D  verify that exact installation; structured evidence; no ranking
1.6E  first executable bounded foundation selection: provisionable
      recommendation + AUTO|MANUAL + realize/verify selected path;
      invalidate downstream derived-state seams; no silent fallback
1.6F  runtime-aware eligible model view from the selected verified
      foundation; authoritative runtime/model compatibility; no
      capacity remap
1.6G  ModelRequirement + Capacity consume EligibleModelView and the
      selected verified runtime; no ModelSelector redesign
later bounded model selection, authoritative selected DeploymentPlan
```

---

# PART III — THE BUILD SEQUENCE

```text
MILESTONE 0   Architectural kernel                         contracts only
MILESTONE 1   Walking skeleton — live inference proven      ← the gate the prior attempt never reached
MILESTONE 2   Storage truth and acquisition deepening
MILESTONE 3   Capacity evidence, feasibility and selection (deepening)
MILESTONE 4   Multi-workload resource management
MILESTONE 5   Governed access spine
MILESTONE 6   Operability — Admin console and agent
MILESTONE 7   Knowledge exoskeleton
MILESTONE 8   Company Brain and Team Brain
MILESTONE 9   Outbound boundary, telemetry, entitlements
MILESTONE 10  Installer, updates, commercial governance
MILESTONE 11  Capacity and effectiveness intelligence
MILESTONE 12  Intelligent routing and portfolio optimization
MILESTONE 13  Team Brain adaptation
MILESTONE 14  Multi-host and organisational coordination
```

Milestones 0–6 are the infrastructure exoskeleton. 7–8 are the Company
Brain. 9–10 make it shippable. 11–14 make it intelligent, and none of
them may start early.

---

## MILESTONE 0 — Architectural kernel

**Goal:** establish only the semantics that are expensive to retrofit.
Nothing that can be added later belongs here.

Keep this milestone small. The temptation is to design every contract in
detail; the prior attempt's contracts were reworked within hours of being
written (`capacity_contracts.py`: 473 of 640 lines changed 14 minutes
after creation) because they were written before anything consumed them.
Contracts get real when a caller exists.

### Stage 0.1 — Identity and result semantics

Stable IDs, `schema_version` on every persisted and API structure, typed
errors, result envelopes, domain event envelope, the unresolved-value
semantic, UTC platform time, configuration ownership, adapter registry,
replaceable persistence boundary.

Field meaning must never change silently. No existing config field may
be reinterpreted.

**Unknown is a value, not a null.** §8 rule 6 requires a consumer to
tell "needs nothing" from "we do not know", and Milestone 3 requires
gaps to be represented rather than filled. One unresolved semantic
belongs here, because the alternative is every contract in Stage 0.2
inventing its own convention for absence — Pattern 4 in a new costume.
An unresolved value has no truth value: treating it as falsy is a
failure, not a default.

Sizes are bytes at every contract boundary. The prior attempt carried
`minimum_reserve_bytes` in one place and `minimum_reserve_gb` in
another; unit drift in a value that authorizes a mutation is not a
cosmetic problem.

The event envelope carries a **correlation identifier from the first
event**, so a request stays traceable across gateway, inference, usage
and analytics. Threading one through a finished serving path later is
expensive.

This stage also builds the **architecture test harness** that enforces
`docs/ARCHITECTURE.md` Part II. The enforcement mechanism precedes the
structure it protects: eleven `storage_*` modules for one concept would
have failed the concept census on the day the second one appeared.

### Stage 0.2 — Contracts that must exist before their subsystems

Minimal but intentional. Named now because retrofitting them is
expensive:

```text
HostCapabilities      Workload              Subject / AccessContext
StoragePool           ResourceReservation   UsageEvent
ModelMetadata         InferenceInstance     AuditEvent
ModelArtifact         CapacityEvidence      Entitlement
ModelRequirement      WorkloadProfile       KnowledgeSource / KnowledgeItem
ModelInventoryRecord                        DatasetSnapshot / DerivedModel
```

Four of these are non-negotiable at this stage even though their
subsystems arrive much later, because the prior attempt shows what
happens otherwise:

- **`Subject` / `AccessContext`** — identity received zero attention in
  the prior attempt and would have had to be threaded through a finished
  gateway, analytics and knowledge layer retrospectively.
- **`UsageEvent`** — analytics received zero attention, and its identity
  fields (`logical_name`, `model_id`, `provider`, `service_id`,
  `route_reason`) must not be collapsed later.
- **`StoragePool`** — Stage 1.2 computes a safe storage layer, which
  needs pool identity. Without the contract here, pool identity would be
  read from `HostCapabilities` at Milestone 1 and move into `storage` at
  Stage 2.1, giving one concept two owners across a milestone boundary.
  Plural from v1: the prior attempt designed multi-pool storage and never
  exercised it, and a single-pool assumption baked in here is the same
  trap Milestone 14 hits with hosts.
- **`AuditEvent`** — actor, action, target, decision, approval reference
  and outcome. The constitution requires a deployment to answer who
  changed a setting, installed a model, modified a permission or approved
  an agent action, and asks that the schema leave room for audit events
  even when the UI comes later. Retrofitting it means revisiting every
  mutating workflow already written. It is emitted from Stage 1.5A onward;
  only the audit *UI* is deferred.

`AuditEvent` is not `UsageEvent`. Usage events describe AI consumption;
audit events describe administrative change. Collapsing them loses both.

The host provenance and conflict structures the provider architecture
requires are deliberately **not** here. Nothing observes a host until Stage
1.1, and they arrive there as optional fields — a compatible addition under
§10's own versioning rules. A provider's schema must never dictate a core
contract, and a field added because a tool happens to expose it is exactly
the failure this stage exists to prevent.

Every host-scoped contract here carries a host identifier, and every
collection of host-scoped things is plural, from v1. `docs/ARCHITECTURE.md`
Part II §6 records why: Milestone 14 is an extension of these contracts
only if that holds, and a rewrite of the whole control plane otherwise.

### Stage 0.3 — Control plane shell

Platform API skeleton, platform state, local administrator identity.
A thin Admin surface exists from here on and grows with every stage; it
is not a late project.

Two seams are created here rather than at Milestone 6, because both are
destinations that need a source in every stage that precedes them:

- **`Approval`** — Stage 6.2 requires meaningful mutations to obtain
  explicit administrator approval, and the constitution requires
  overrides to be validated, explained, recorded and reversible. The
  recording mechanism must exist before the first mutation does.
- **`HealthSource`** — Stage 6.1 displays platform health and Stage 1.6
  distinguishes status from health, but without a port from here, each
  domain would invent its own reporting and Milestone 6 would become a
  survey of every subsystem instead of an assembly. Each domain
  implements it as it is built.

**Output:** `PlatformContracts v1 + PlatformState v1 + ControlPlaneShell v1`

**Gate (L1):** contracts serialize without importing any runtime or
provider library. Platform API answers from platform state. Contracts
are minimal and boundaries are intentional.

---

## MILESTONE 1 — Walking skeleton

**This is the milestone the previous attempt never reached, and the
reason this roadmap is reordered.**

### Immediate sequence

```text
Milestone 0 complete
  ↓
architecture harness enforcement gap closed   ← prerequisite, DEBT K-12
  ↓
1.1 host discovery      reference NVIDIA host is the only blocking shape
  ↓
1.2 capacity            policy-only envelope
  ↓
1.2A storage sanity + prototype console   ← closed; not 1.3
  ↓
1.3 runtime / executor exoskeleton        ← no LLM required
  ↓
1.4A model sources / catalog + metadata
  ↓
1.4B feasibility + capacity-based selection + DeploymentPlan v0
  ↓
1.4C model acquisition + plural inventory
  ↓
1.5A resource admission + reservation
  ↓
1.5B inference instance lifecycle         ← plural schema; reference serving; stop ≠ release
  ↓
1.5C Runtime / Executor boundary          ← capability profile + support descriptor; no vLLM
  ↓
1.6A executor capability + ContainerExecutor  ← CLOSED L2
  ↓
1.6B Runtime Resolution                   ← CLOSED L1
  ↓
1.6C Runtime Provisioning                 ← CLOSED L2
  ↓
1.6D Runtime Verification                 ← CLOSED L2
  ↓
1.6E Foundation Selection                 ← CLOSED L1; two-phase provisionable ≠ executable
  ↓
1.6F Eligible Model View                  ← CLOSED L1; runtime-aware compatibility
  ↓
1.6G ModelRequirement + Capacity          ← CLOSED L1; remapped onto eligible view
  ↓
1.6 REAL INFERENCE VERTICAL               ← sequenced 1.6A…; not begun from 1.5C
  ↓
post-inference breadth review, then 1.7 onward
```

Nothing sophisticated is inserted into that path. Not Apple, AMD or Intel;
not Kubernetes; not containerization; not a universal installer; not a
marketplace; not a learned recommender; not a generic selection
framework; not a portfolio optimizer; not multi-instance scheduling.
Each has a home in the deferred capability register in `docs/DEBT.md`,
with its own revisit trigger.

The lifecycle **is** inserted as named thin stages. Catalog, metadata,
feasibility, selection, acquisition, inventory, admission, reservation
and inference instance are distinct concepts. Compressing them into
“model presence / admission / inference” is how ownership disappears
during implementation.

The harness gap comes first because Law 5 — an adapter inherits its
port-domain's import budget — is what keeps a discovery provider out of the
Resource Manager, and Stage 1.1 is where adapters start being written.

**Goal:** on the reference host, an authenticated request reaches a real
model through Kultrun-owned paths, returns an answer, emits a usage
event, and the platform restarts into a coherent state.

Everything here is deliberately crude — and everything here is real. No
mocks in the path. No subsystem is deepened until this passes on real
hardware.

Explicitly **not** in this milestone: empirical storage characterization
(Stage 2.2), capacity evidence providers (Stage 3.2), a marketplace, a
learned selector, a model-inventory optimizer, multiple concurrent live
instances as an acceptance gate (Milestone 4), external knowledge
providers, or teams. Those remain later. What *is* in this milestone is
the thin named lifecycle: one replaceable `ModelSource`, a small curated
set, host-independent metadata and requirements, deterministic
feasibility and selection, one acquisition path, plural inventory,
admission, reservation, and a first-class plural `InferenceInstance`
schema with one running instance acceptable.

### Relationship to the constitution's §111

`docs/PRODUCT_VISION.md` §111 defines a 19-step "first working
exoskeleton" flow and states, correctly, that "this vertical slice is
more important than advanced optimization." This roadmap now names each
of those steps in Milestone 1 as a thin stage, and still splits
*depth* across later milestones.

| §111 steps | Where |
|---|---|
| 1–6 inspect host, HostCapabilities, safe capacity, control plane, Admin UI, basic Admin Agent | Milestone 1 (Admin surface is the Prototype Console from 1.2A; console proper at Milestone 6) |
| 7–9 search curated set, evaluate compatibility, recommend one model | **Stages 1.4A–1.4B** (thin). Milestone 3 deepens evidence and selection. |
| 10 safely acquire or import | **Stage 1.4C** (thin). Milestone 2 deepens storage truth and mutation safety. |
| 11–19 inventory, reservation, instance, gateway, request, UsageEvent, analytics, safe stop/restart, reconciliation | **Milestone 1** |

The previous attempt built the entire model supply chain and empirical
storage machinery *without ever proving the spine*. Milestone 1 still
forbids that depth. It no longer forbids naming the spine. A hand-placed
artifact remains a valid *test fixture*; it is not the product's only
path to a first model.

§111's full *deepened* flow — evidence providers, honest empirical
storage, automatic select-acquire-serve on a fresh host with explained
rejections — is achieved at the **Milestone 3 gate**.

The first vertical may prove **several models stored and one running**.
A later bounded gate (Milestone 4) proves **two different inference
instances running concurrently** when hardware permits. Two-running-model
acceptance is not a blocker for first inference.

### Stage 1.1 — Host discovery

`HostDiscoveryService` producing normalized `HostCapabilities`: OS,
version, architecture, CPU, RAM, accelerator vendor and count and VRAM,
unified memory where relevant, storage mount identity, execution
capabilities, ports, driver hints.

**Kultrun does not implement this enumeration itself.** Discovery is a
provider architecture — mature tooling observes, Kultrun normalizes,
reconciles and decides. See `docs/ARCHITECTURE.md` Part IX. Providers are
adapters behind `HostDiscoveryProvider`; they may be partial, absent or
wrong; unknown stays unknown; and a failed provider means that source was
unavailable, not that the host is unsupported.

**This stage opens with a bounded provider validation spike.** Not a
research project — a short empirical exercise on the machines actually
available, answering: what does the preferred general provider report on
each shape, what does it miss, is it practical to provision, which vendor
or native supplements are genuinely required, and do the outputs normalize
cleanly into `HostCapabilities`. **No custom fallback is written until a
real gap has been demonstrated on a real machine.** Documentation says what
a tool can do somewhere; only a run says what it does here.

The preferred provider is **optional-preferred**: the spike may not assume
it is already present, may obtain it on the reference development host in
order to evaluate it, and must record how it was obtained and at what
version. Final bundling and installer mechanics are a Milestone 10
question and are not solved here.

**The spike is outcome-bounded, not research-bounded.** It ends when the
reference host can be observed with the smallest practical combination of
mature providers; those observations normalize into valid
`HostCapabilities`; what Stage 1.2 needs is available, explicitly
unresolved, or documented as needing a small supplement; there is no
demonstrated need for Kultrun to write commodity enumeration itself; and
remaining gaps are recorded in the deferred capability register. Once those
hold, provider exploration stops.

Then implement the smallest provider stack that Stage 1.1 acceptance
actually requires — expected to be a general provider plus a vendor
supplement on the NVIDIA host, but the spike confirms rather than assumes
it. No AMD or Intel provider is written for completeness.

Reference implementation: Linux x86_64 + NVIDIA.

**One blocking real shape: Linux x86_64 with NVIDIA.** Stage 1.1 closes
when the reference host meets its acceptance contract, and nothing else
gates it. Apple Silicon and CPU-only Linux are **non-blocking**
opportunities: captured if available, recorded in the deferred capability
register if not. AMD, Intel, Kubernetes and container execution are not in
scope at all.

This is a deliberate narrowing. Each of those shapes exercises a real and
distinct failure mode, and none is required for a real server to serve a
real model — which is the only thing Milestone 1 exists to prove. Breadth
that delays that proof repeats the previous attempt's mistake in a new
costume.

Every real run that *is* performed is committed as a fixture, so later
stages test capability branching against real machines rather than
hand-written guesses about them, and any new hardware ever encountered
becomes a permanent regression test by being observed once.

Durable, versioned, fingerprinted. **The fingerprint covers stable facts
only** — architecture, CPU and accelerator models, mount identity — and
never available memory or free space. It is the key by which cached
evidence is judged reusable from Milestone 2, and a fingerprint over
volatile values would invalidate every expensive probe on every restart.

Every value stays **explainable**: which provider supplied it, when, how it
was obtained, and with what confidence. Provenance is recorded beside the
values by dotted field path rather than by wrapping every leaf, which makes
it a compatible addition to the Stage 0.2 contract rather than a revision
of it.

**A minimal preparation path is in scope, and only a minimal one.** The
reference host must be able to obtain or reuse the provider it needs
without a human installing it by hand, so `components` expresses the
requirement and `install` acts on it. The smallest honest implementation:
detect an existing compatible component, reuse it if valid, otherwise
invoke one approved mechanism for this one supported environment, verify it
runs, record version and source, proceed.

Explicitly not here: multiple package managers, OCI images, enterprise
mirrors, offline bundles, or any distribution beyond the reference. The
*interface* must permit those; the implementation must not attempt them.
Milestone 10 owns the installer, and moving it into Milestone 1 by accident
is the specific risk this paragraph exists to prevent.

**Discovery never installs anything.** A provider reports available,
unavailable, failed, partially capable, or missing a prerequisite. It does
not run a package manager, download a tool, change system configuration or
install a driver. `install` acts; `host` looks.

**`DeploymentProfile`** is created here, satisfying
`docs/PRODUCT_VISION.md` §89. A tier — certified, supported, compatible,
experimental, unsupported — is earned from the acceptance level reached on
that host shape, not declared: `L4` certifies, `L3` supports, `L2`
qualifies as compatible, a captured fixture alone is experimental. This is
the mechanism that makes broad hardware support honest rather than a claim,
and it means a tier cannot get ahead of its evidence. An unsupported
profile never prevents the platform from starting; fail-closed governs
mutations, not existence.

Stage 1.1 classifies **the reference host only**. Other shapes stay
unclassified or experimental until evidence exists; building a portfolio of
profiles is not this stage's job.

**Output:** `HostCapabilities v1 + DeploymentProfile v1 + HostDiscoveryProvider` · **Gate:** L2

### Stage 1.2 — Minimum safe capacity

The three-layer model — Reported, Effective, Safe — for RAM, VRAM and
storage, using **policy headroom only**. No probing, no calibration, no
evidence providers.

This stage is the roadmap's central sequencing insight. Safe admission
does not require empirical characterization; it requires honest
conservatism. A protected fraction with an absolute floor, unified memory
failing closed, and unknown resolving to refusal is enough to admit a
first workload safely. The prior attempt built 11,761 lines of storage
machinery before proving a single inference, when a headroom policy
would have unblocked the vertical on day one.

Per-accelerator, never aggregated unless the interconnect genuinely
permits. Unmanaged external usage accounted for. Managed reservations
never double-subtracted from observed live availability.

**Output:** `CapacityEnvelope v1` (policy-based) · **Gate:** L2

**Testing:** T1 + T0 primarily, T3 for closure · real host **selective** ·
cross-server intensity **very high over time** · artifact-based remote
acceptance **required** · fixture replay **required**.

Most of this stage is developed against the committed Stage 1.1 fixture with
no host at all. The reference host's 2.15 PB `/workspace` mount is the
central regression case: reported storage of that size must never become
safe capacity of that size. A real host is needed only for the physical
claims — cgroup and system memory behaviour, assigned accelerator capacity,
and empirical storage characterization.

Brief: `docs/stages/STAGE-1.2-capacity.md`.

### Stage 1.2A — Storage sanity and prototype visibility (closed)

Bounded Storage Sonar v0, local Fixture Replay Console, Live Host Console
architecture. Explicit probe execution only. No Stage 1.3 logic.

Accepted at `d38e1ed`. Checkpoint:
`checkpoints/STAGE-1.2A-storage-sanity-console.json`.

The Prototype Console grows with the lifecycle. After 1.2A it shows host,
capacity and storage sanity. Planned panels, in order:

HOST → CAPACITY → STORAGE SANITY → RUNTIME / EXECUTOR → MODEL CATALOG →
MODEL SELECTION → MODEL INVENTORY (stored) → RESOURCE RESERVATIONS →
INFERENCE INSTANCES (running) → INFERENCE TEST

Stored models and running instances are visually distinct. The frontend
never owns product logic.

This stage is not reopened. Historical checkpoints are not rewritten.

### Stage 1.3 — Runtime / executor exoskeleton

`Executor` with `NativeProcessExecutor` as the first and reference
implementation. `InferenceRuntime` port and `RuntimeProfile` /
`RuntimeLaunchSpec` contracts. Process lifecycle: start, signal, health,
stop, PID reuse protection.

No LLM is required to close this stage. A vLLM adapter may exist as a
seam; serving a model is Stage 1.6.

The executor owns process execution, environment, filesystem mapping,
signals, logs and process health — never model semantics. Runtime
options stay inside the runtime adapter.

`Executor` also declares the **`ContainerEngine`** seam, unimplemented.
Native process execution is the first validated path and the reference
implementation; container execution is a first-class optional executor, and
neither is privileged in perpetuity. Selecting between them from host
capabilities, runtime support, profile, policy and operational evidence is
a later capability, not a default assumed now. The seam exists now so that
an OCI executor is later an adapter rather than a redesign, and so that
device attachment through the vendor-neutral container device standard has
an obvious home — beneath the executor, after allocation, never as a source
of host facts or of capacity. Docker is not required and Kubernetes is not
the control plane.

The **component seam** already exists — Stage 1.1 created
`ComponentRequirement` and `ComponentResolution` to express its provider's
needs. This stage extends it to the runtime: is a runtime present, at what
version, compatible with this host. The runtime is assumed already
installed at Milestone 1, so nothing is provisioned here. Stage 1.4B's
`DeploymentPlan` v0 consumes *resolved components* where they exist, and
Milestone 10 fills the seam rather than introducing it.

**Output:** `ExecutorSpec + ExecutorHandle + DeviceRequest + RuntimeProfile + RuntimeLaunchSpec + ComponentRequirement` · **Gate:** L2

### Stage 1.4A — Model sources / catalog + metadata

Provide a small **source-agnostic candidate set** plus normalized
metadata and requirement evidence sufficient for later feasibility and
selection. This stage does **not** choose a model, download one, or
rank.

One replaceable `ModelSource` implementation. First source: Hugging Face
Hub identity behind a Kultrun-owned adapter; live Hub search of the
whole corpus is not in v0. A curated set of approximately 4–8 variants
chosen for spread across family, parameter size, quantization, memory
requirement and context. Normalize into platform-owned `ModelMetadata`
and host-independent `ModelRequirement` v0.

Every candidate exposes enough for an administrator to see: identity,
parameters, quantization, artifact size, estimated RAM, estimated VRAM
(or unified memory where applicable), context, supported runtime(s),
license, requirement confidence and estimation method. Load-bearing
unknowns stay unresolved. Runtime-overhead and KV estimates may be
coarse and conservative; a seam remains for later runtime evidence
(Stage 1.6) to improve them.

Quantized variants are distinct candidates when deployment requirements
differ. No recommendation in the Prototype Console — a **Model Catalog**
panel only.

**Output:** `ModelSource` + `ModelMetadata v1` + `ModelRequirement v0` + catalog API + Prototype Console catalog panel · **Gate:** L1 (L2 only if a real source fetch is claimed)

### Stage 1.4B — Feasibility + capacity-based selection

Kultrun's first capacity-based model selection stage. It owns
compatibility, feasibility, `DeploymentCapacity`, `CapacityUtilization`,
lower/upper utilization filtering, deterministic ranking,
`SelectionRecommendation` and `DeploymentPlan` v0.

**One active estimator.** Requirements arrive through
`ModelRequirementEstimator`. Original close defaulted to Kultrun
(packaged / formula_v0) with llmfit as an alternative. The post-close
amendment below makes AUTO the default (llmfit primary, Kultrun
fallback). Explicit `llmfit` / `kultrun` remain. Composition selects the
mode; planning does not branch on provider id. Cross-provider comparison
is `tools/compare_model_estimators.py` plus tests — not API, Console, or
`DeploymentPlan`.

The candidate catalog expands to roughly 18–30 representative
deployment variants (the original 1.4A six remain regression fixtures)
with a meaningful overlap both estimators can evaluate.

Consumes `HostCapabilities`, `CapacityEnvelope` (SAFE for the fit
boundary), `RuntimeProfile`s, `ModelMetadata[]`, the active estimator's
`ModelRequirement[]` and `SelectionPolicy`. It never reserves and never
downloads.

Every candidate receives an explainable evaluation: compatibility,
storage feasibility (peak acquisition distinct from installed size),
required vs safe memory, utilization, preferred-band status, reasons,
unresolved requirements, confidence. Preferred band is the configured
policy window (v0 default 20–100% of SAFE deployment capacity).
Underutilized candidates are classified, not collapsed into unsupported.
No silent threshold relaxation.

`SelectionRecommendation`: primary, preferred alternatives, underutilized
alternatives, rejected, rationale, utilization, expected resource use,
runtime, confidence, policy version, **active** estimator identity.
`DeploymentPlan` v0 names selected model/variant, runtime, executor
kind, placement, expected RAM/VRAM/unified/storage, expected
utilization and rationale.

Boundary tests are part of the brief: 19.99% underutilized, 20% and 100%
preferred if otherwise compatible, 100.01% infeasible, unknown
requirement unresolved, storage failure infeasible regardless of memory
utilization. Fixture-driven against current host/capacity fixtures
(tiny host, medium GPU, CPU-only, and the cases above). Planning tests
run with both estimators where both support the models. T2 proves real
`llmfit plan` from an installed artifact. No inference. T3 only if
integration is genuinely host-sensitive.

**Output:** `FeasibilityResult v0` + `SelectionRecommendation v0` + `DeploymentPlan v0` + `ModelRequirementEstimator` · **Gate:** L1 (T2 includes real llmfit execution; T3 not required unless host-sensitive)

**Post-close amendment (provider policy).** Closed Stage 1.4B remains
closed at L1. Default mode is now AUTO: llmfit is the primary requirement
estimator; the Kultrun estimator is the built-in fallback when llmfit
fails to produce valid evidence for the exact request. Explicit `llmfit`
and `kultrun` stay strict. Fallback is typed estimator failure only —
not over-capacity, underutilized, or ranking preference. No product
reconciler. Development comparison is unchanged. Estimator contracts and
the 19-candidate catalog are unchanged.

### Stage 1.4C — Model acquisition + inventory

Selection is not storage. Acquisition is a distinct mutation:

```text
SelectionRecommendation
  → acquisition decision
  → storage safety check
  → download / staging
  → verification
  → atomic commit
  → Model Inventory
```

Reuse existing artifacts. Plural inventory (`models[]`) from the first
schema. Artifact states: remote, acquiring, stored, invalid, updating,
deleted. Minimal delete hook if it is cheap: refuse deletion while an
instance references the artifact.

No running model is required. Several stored models may be proven here
(the first vertical's "3+ stored, 1 running" stored-side). Empirical
pool characterization remains Stage 2.2.

**Output:** `AcquisitionReceipt v0` + `ModelInventoryRecord v1` (plural) · **Gate:** L1 (T2 includes bounded real Hugging Face acquisition; T3 not required)

The platform must operate coherently with **no model installed**: an
absent model is a valid unsatisfied deployment state, the control plane
starts anyway, and the Platform API remains available.

**Artifact existence is not current-host suitability.** An artifact that is
present says nothing about whether this host can serve it. Inventory
answers "what exists"; feasibility answers "can this host use it".

### Stage 1.5A — Resource admission + reservation

`Workload`, `ResourceRequirement`, `AdmissionDecision`,
`ResourceReservation`. Resource Manager is the sole owner of admission,
reservations, oversubscription prevention, release and reconciliation.

It consumes a proposed deployment/workload. It does not rank candidate
models.

```text
Planning:  "What should we run?"
Resource:  "May it run now?"
```

A reservation belongs to an inference/workload instance and may cover
CPU, RAM, VRAM/unified memory, storage where relevant, GPU/device
assignment, ports, and other runtime-specific constrained resources.

Capacity, reservation and utilization stay separate. Real reservation
against the safe layer from 1.2.

Ordering is the contract: **reserve before mutation; roll back the
reservation if start fails; stop the runtime before releasing the
reservation; hold conservative state on persistence error.** Denial is
explainable. A denied admission mutates nothing.

This is the first mutating *workload* workflow, so it emits an
`AuditEvent`. Every mutating workflow from here on emits one.

**Output:** `AdmissionDecision + ResourceReservation` · **Gate:** L1 (control-plane accounting; T3 not required)

### Stage 1.5B — Inference instance lifecycle

First-class `InferenceInstance`, plural from v1 (`inference_instances[]`,
never `current_inference_instance`): instance id, ModelArtifact
reference, runtime, executor, RuntimeLaunchSpec, ResourceReservation,
endpoint, lifecycle state, desired vs observed vs health, timestamps.

Lifecycle: create, start, observe, stop, restart — plus **reconciliation
on restart**. A reference serving process proves the path. Real LLM
loading is later. Stage 1.5C reconciles the Runtime / Executor seam first.

Stop does **not** release the reservation. Release is a separate
primitive and is refused while a linked instance is STARTING, RUNNING,
STOPPING, or UNKNOWN. Stored / active / running are lifecycle labels,
not fixed capacity partitions. Active commitments follow the current
reservations.

**Output:** `InferenceInstance v1` (plural) + reference serving lifecycle · **Gate:** L1

### Stage 1.5C — Runtime / Executor boundary reconciliation

Inspect and minimally correct the Runtime / Executor contracts so a later
real runtime can be added without embedding `subprocess` or Docker in
domain types. Preserve ResourceManager and InferenceInstance lifecycle.

Adds `ExecutorCapabilityProfile` (current-host capability evidence) and
`RuntimeSupportDescriptor` (declared/static support). Reuses
`RuntimeLaunchSpec` and `ExecutorHandle`. Reference serving is explicitly
`TEST_ONLY`. A recording executor proves the generic spec is not
native-process-specific. No ContainerExecutor, no RuntimeResolver, no
provisioning, no verification, no model-selection remap, no vLLM.

**Output:** reconciled Runtime / Executor seam · **Gate:** L1 (T3 not required)

### Stage 1.6A — Minimal ContainerExecutor + executor portability

Prove that the same `RuntimeAdapter` and executor-neutral
`RuntimeLaunchSpec` can be realized by `NativeProcessExecutor` and a
minimal `ContainerExecutor`. Docker Engine is the first
`ContainerEngine` implementation and is not a generic contract.

No vLLM, no RuntimeResolver, no provisioning, no verification, no
model-selection remap, no Kubernetes.

**Output:** `ContainerExecutor` + Docker CLI `ContainerEngine` + same
reference-serving Runtime through both executors · **Gate:** L2 **CLOSED**
(Linux Docker Engine T3; host-network v0; no GPU/bridge/vLLM container proof)

### Stage 1.6B — Runtime Resolution

Given current `HostCapabilities`, current `ExecutorCapabilityProfile`s
and declared `RuntimeSupportDescriptor`s, emit `RuntimeCandidate`s.
No install, verify, benchmark, model selection, or vLLM execution.

**Output:** `RuntimePolicy` + `RuntimeCandidate` + `RuntimeResolver` ·
**Gate:** L1 **CLOSED** (T0/T1/T2; T3 not required)

### Stage 1.6C — Runtime Provisioning

Given a current `RuntimeCandidate`, create an exact
`RuntimeProvisioningPlan` and install that pin into a Kultrun-owned
isolated environment. `INSTALLED` is not `VERIFIED`. Product pin:
vLLM `0.28.0`, native-process, Python 3.12, stdlib venv + pip.

**Output:** `RuntimeProvisioningPlan` + `RuntimeProvisioner` +
`RuntimeInstallation` · **Gate:** L2 **CLOSED** (T3 real
`vllm==0.28.0` isolated install on Linux x86_64 NVIDIA).
`INSTALLED` is not `VERIFIED`.

Provisioning consumes an **explicitly identified** `RuntimeCandidate`.
It does not assume the AUTO recommendation and must not silently
substitute another runtime or executor. `INSTALLED` is not `VERIFIED`.
This preserves the bounded-selection seam; it does not implement
recommendation, alternatives, or override UX.

The current L2 reference proof requires Python 3.12 and a working NVIDIA
driver already on the host. That is a bounded validation assumption, not
the commercial target. Managed Python (K-66) and privileged driver
remediation (K-77) remain deferred; 1.6C must not apt-install either.

### Stage 1.6D — Runtime Verification

Verify a specific `RuntimeInstallation` on the actual
runtime+executor+host path. Produce a `RuntimeCapabilityProfile` with
VERIFIED / FAILED / STALE / UNVERIFIED states. Do not rank, recommend,
or silently fall back. Only VERIFIED paths may later enter the
selectable runtime set. Installed is not verified. Verified is not
model-compatible.

**Output:** `RuntimeVerifier` + `RuntimeCapabilityProfile` for an exact
installation · **Gate:** L2 required. T2 is fixture L1. Real NVIDIA T3
required to close.

### Stage 1.6E — Foundation Selection

First concrete bounded foundation-selection stage. Compose closed
1.6B–1.6D objects. Distinguish `ELIGIBLE TO PROVISION` from
`VERIFIED EXECUTABLE`. Classify recommended-to-provision, other
provisionable alternatives, and BLOCKED. Persist
`FoundationSelection` AUTO|MANUAL with recommended ≠ selected.
AUTO follows the current pre-provision recommendation. MANUAL may
select another **provisionable** candidate — that is an attempt
instruction, not proof of executability. Realize and verify only the
selected candidate through the existing provisioner and verifier.
Failure keeps truthful evidence and never silently executes another
foundation. Mark downstream derived state stale. Do not introduce a
Foundation domain, EnvironmentProvider port, weighted scorer, or
generic SelectionFramework.

**Output:** `FoundationSelection` + classified candidate view +
selected path through existing provision/verify + invalidation seam
· **Gate:** L1 CLOSED. T0/T1/T2 fixture. T3 not required; this stage does
not add a hardware path. Do not reopen 1.6B–1.6D.

### Stage 1.6F — Runtime-aware Eligible Model View

First concrete migration of live runtime/model compatibility onto the
selected verified foundation. Consume closed 1.6B–1.6E objects. A
merely provisionable `RuntimeCandidate` is not eligibility authority.
Evaluate the global catalog against the selected
`RuntimeCandidate` + matching `RuntimeInstallation` + fresh VERIFIED
`RuntimeCapabilityProfile` + `RuntimeSupportDescriptor`. Statuses are
ELIGIBLE / BLOCKED / UNRESOLVED; the view is CURRENT / STALE /
UNAVAILABLE. UNKNOWN is never ELIGIBLE. MANUAL uses the selected
candidate, never the recommendation. Do not stamp compatibility onto
`ModelMetadata`. Do not mutate inventory. Do not remap
`ModelRequirement` or capacity. Migrate existing runtime/model
compatibility callers onto this path; keep a composition shim where
planning cannot import runtime.

**Output:** `EligibleModelView` + `RuntimeEligibleModelCandidate[]` +
authoritative runtime/model compatibility seam · **Gate:** L1 CLOSED.
T0/T1/T2 fixture. T3 not required; this stage adds no hardware path.
Do not reopen 1.6B–1.6E.

### Stage 1.6G — ModelRequirement + Capacity Migration

Migrate existing `ModelRequirement` derivation and capacity evaluation
onto `RuntimeEligibleModelCandidate` plus the selected fresh VERIFIED
`RuntimeCapabilityProfile`. The selected runtime is the estimator
identity; catalog `supported_runtimes[0]` is not. BLOCKED models do
not enter normal capacity. UNRESOLVED models are not falsely feasible.
Preserve estimator AUTO, capacity SAFE math, and existing ranking.
Do not redesign ModelSelector. Do not create DeploymentPlan authority.
Do not remap ResourceManager or InferenceInstance. Retire K-94.

**Output:** remapped `ModelRequirement` + `CapacityAssessment` from the
eligible view · **Gate:** L1 CLOSED. T0/T1/T2 fixture. T3 not required;
this stage adds no hardware path. Do not reopen 1.6B–1.6F.

### Stage 1.6 — Real inference vertical

Split after 1.5C. **1.6A** is the ContainerExecutor portability proof.
**1.6B** is resolution. **1.6C** is isolated installation.
**1.6D** is verification. **1.6E** is bounded foundation selection.
**1.6F** is runtime-aware eligible models.
**1.6G** is ModelRequirement + Capacity migration.
Later letters cover ModelSelector, acquisition gating, admission
remap, and real inference.
**1.6D is CLOSED L2.** **1.6E is CLOSED L1.** **1.6F is CLOSED L1.**
**1.6G is CLOSED L1.**
Next is ModelSelector + bounded model selection; do not begin it from
1.6G.

Selected stored model, admitted reservation, runtime, executor,
InferenceInstance, endpoint, a real prompt, a real response. Prototype
Console inference-test view.

**Output:** healthy `InferenceEndpoint` serving a real request · **Gate:** L3

### Milestone 1 Hardware Breadth Review — after Stage 1.6, before broadening

A required review and evidence checkpoint, not a stage, and **not an
instruction to implement any platform.** Once a real request has reached a
real model on real hardware, review — and decide, rather than drift into:

- Apple Silicon capture and provider;
- CPU-only capture and runtime;
- additional NVIDIA host shapes;
- container executor and device attachment;
- AMD and Intel providers;
- Kubernetes and a node-feature provider;
- whether the minimal component provisioner should be generalized.

Each has an entry in the deferred capability register with its own revisit
trigger. This checkpoint exists so that breadth is chosen deliberately at
the first moment it is affordable, rather than either forgotten or smuggled
into Milestone 1.

**Classify each shape rather than scheduling it.** For every candidate
decide which of these it needs:

| | |
|---|---|
| **A** | the architecture already handles it |
| **B** | a fixture capture only |
| **C** | a provider adapter |
| **D** | a runtime or executor adapter |
| **E** | genuine architecture review |

A, B, C or D is the expected answer. **An E is a signal that hardware
variability leaked above the boundary in Part II §5b**, and it is more
important than the platform that revealed it.

Also decide at this checkpoint:

- **Automated ephemeral hardware acceptance** — whether CI should allocate a
  real host, install the artifact, run acceptance and destroy it. No vendor
  is chosen now; criteria are in `docs/TESTING_STRATEGY.md`. Development
  infrastructure, never product architecture.
- **A rotating compatibility matrix** — which shapes run at which cadence
  once more than one is validated. Cadence deliberately undefined until
  there is a second shape.
- The first **clean-install acceptance** since the workflow was adopted.

### Stage 1.7 — Gateway, subject and usage event

The Kultrun Gateway owns endpoint identity, authentication and
authorization hooks, model access policy, and route decision. One local
provider adapter. Routing is explicit-model or default-model only.

Every request emits a `UsageEvent` through a replaceable
`UsageAnalyticsStore`.

Two invariants hold from the first event: **analytics recording failure
must never block an inference response**, and the gateway must never
wait on an exporter. Storage is partitioned from the start — the prior
attempt shipped a single unbounded JSONL file, then had to migrate it.

**Output:** `RouteDecision + UsageEvent v1 + LocalUsageStore` · **Gate:** L3

### Stage 1.8 — MILESTONE GATE: fresh-host live inference

**The proof the prior attempt never obtained.** On a clean reference
host, at L4:

1. Detect host, produce `HostCapabilities`.
2. Start the control plane **with no model installed**.
3. From a small curated set, evaluate feasibility and produce a
   `SelectionRecommendation` (a hand-placed artifact remains a valid
   fixture if a source is unavailable).
4. Acquire or reuse into inventory; prove plural stored records.
5. Compute a requirement and obtain admission against safe capacity.
6. Reserve, start an `InferenceInstance`.
7. Authenticate a subject and serve a real `/v1/chat/completions`.
8. Emit a `UsageEvent` with correct token accounting.
9. Report status, health and usage through the Platform API.
10. Stop cleanly — no orphan process, port, file or reservation; the
    stored artifact remains.
11. Restart and reconcile into a coherent state.
12. Prove denial: request a workload exceeding safe capacity and confirm
    refusal with an explanation and no mutation.

Until this passes, no work begins on milestone 2 or later. If it cannot
pass, the architecture is wrong and that is the most valuable thing this
roadmap can discover — at 5,000 lines instead of 58,000.

---

## MILESTONE 2 — Storage truth and acquisition deepening

Now that inference works end to end, the platform has earned the right
to make storage honest and to deepen the thin acquisition path from
Stage 1.4C. This is where the prior attempt's deepest and
most valuable engineering belongs — second, not first.

### Stage 2.1 — Storage pools and identity

Storage as a **set of pools**, each with mount identity, filesystem
type, provider class, quota identity and fingerprint. A mutation is
admitted against the specific pool it will mutate. Single pool on the
reference host; the contract must not encode that.

### Stage 2.2 — Empirical evidence

**Design record:** `docs/design/EMPIRICAL-STORAGE-CHARACTERIZATION.md`,
extracted from the previous implementation. Read it before implementing:
it records the allocation primitive that actually works
(`posix_fallocate`, never a sparse `truncate`), why network filesystems
report zero allocated blocks after a successful reservation, the
bounds-not-a-number result semantics, the ~110 MB/s probe cost that makes
budgets a money question, the 42,990 MiB orphan left when a probe ran on a
daemon thread and its cleanup never executed, and the 48-minute search that
was really a transaction question answered by a pool-ceiling climb.
**Not Stage 1.2.**

`StorageEvidence` and immutable `EmpiricalProbeEvidence`, keyed by pool
and host fingerprint, probe implementation version and policy version.

Outcomes are `success`, `classified_failure` or `inconclusive`. Only
classified capacity or quota failures (`ENOSPC`, `EDQUOT`) may establish
an upper bound; policy ceilings and probe-shape limits establish nothing
about capacity.

**Persist each completed probe before the next expensive probe begins.**
This single rule is what turns a 48-minute total loss into resumable
work.

### Stage 2.3 — Decision-directed characterization

Characterize to make a decision, not to produce a precise number. The
useful horizon is the largest figure that could still change the current
decision, and it is derived from the decision, not from the pool.

- **TRANSACTION mode** — the only mode needed for acquisition. Stop the
  moment the verified lower bound clears the requirement. No refinement.
- **HOST mode** — deliberately coarse, budget-bounded, describes the
  machine independently of any catalog.
- **DEEP mode** — deferred. Admin reporting and warehouse planning only.
  Never blocks bootstrap.

**Capacity precedes catalogue.** Model requirements must never determine
the initial probe horizon. The prior attempt let candidate thresholds
drive the search, inverted the ordering, and rewrote the module within
24 hours.

### Stage 2.4 — Mutation safety

Shared operation lock, staging, preflight, commit admission requiring
high confidence, rollback, and **startup recovery** that distinguishes
completed evidence from an incomplete probe from a stale temporary
artifact.

Cancellation is cooperative, releases the lock without relying on
process exit, and guarantees no orphan artifact. The prior attempt's
42,990 MiB orphan is the specification for this stage's acceptance test.

Successful mutation invalidates affected evidence and advances the
storage generation.

### Stage 2.5 — Model source and inventory (deepening)

Stage 1.4A created the `ModelSource` port and 1.4C created plural
inventory. This stage fills the remaining adapters and lineage depth:
Hugging Face and local-file as first-class sources, richer
`ModelMetadata`, durable lineage hooks. A curated candidate set, not a
marketplace.

Durable inventory with explicit states and lineage hooks: parent model
and revision, derivation type, owner, dataset reference, promotion
state. Missing metadata stays null and is reported as unresolved.
External source failure never marks the local platform unhealthy.

### Stage 2.6 — Safe acquisition (deepening)

Stage 1.4C proved a thin acquire-and-commit path. This stage is the
mutation-safety spine the prior attempt actually paid for:

```text
resolve immutable revision → calculate requirement (incl. peak additional)
→ storage admission → lock → stage → transfer → integrity validation
→ commit → inventory reconciliation
```

Resumable. Revision-pinned. Interrupted transfer recovers without false
evidence or orphan bytes.

**Output:** `StorageCapacity v1 + StorageAdmissionDecision + AcquisitionReceipt`

**Milestone gate (L4):** on a real host, acquire a model into an
uncharacterized pool; interrupt mid-transfer and prove no orphan
artifact, no false evidence and a released lock; resume and complete;
restart and reconcile inventory. Confirm that raw filesystem free space
never authorized any step. Consolidation checkpoint and debt burn-down.

---

## MILESTONE 3 — Capacity evidence, feasibility and selection (deepening)

**Goal:** the platform chooses well, and explains itself.

Stage 1.4B already produced `FeasibilityResult` v0, a deterministic
`SelectionRecommendation` and `DeploymentPlan` v0 against policy-based
capacity. This milestone adds real `ModelRequirement` depth, advisory
`CapacityEvidenceProvider`s with a mandatory internal fallback, and
richer planning — not the first existence of those concepts.

### Stage 3.1 — ModelRequirement

Normalized, versioned, host-independent: storage including peak
additional bytes, VRAM split into weights, KV per token and runtime
overhead, RAM, compute features, quantization, dtype, runtime
constraints — each with confidence and exactness.

Represent gaps rather than filling them. The prior attempt had **no RAM
estimator anywhere in its source** and one provisional
weights-plus-margin VRAM figure; both correctly appeared in
`unresolved_fields`. Carry that honesty and retire the gaps here.

### Stage 3.2 — CapacityEvidence

`CapacityEvidenceProvider` with a **required internal conservative
estimator**. External providers for *host capacity* — Accelerate,
runtime-native, benchmarks — are advisory adapters with a mandatory
fallback, per §9. llmfit is **not** a capacity authority; Stage 1.4B
already uses it as a replaceable `ModelRequirementEstimator`.

Theoretical and observed evidence stay distinguishable, each carrying
basis and confidence.

### Stage 3.3 — Feasibility (deepening)

Four verdicts: `COMPATIBLE`, `CONDITIONALLY_COMPATIBLE`, `UNSUPPORTED`,
`UNRESOLVED`. Per-resource `{ required, safe_available, fits, margin,
limiting }`, a limiting factor, a maximum viable configuration, reasons
and evidence references.

Must evaluate **candidates before acquisition**, not only inventory. The
prior attempt could only assess models it already had.

### Stage 3.4 — Deployment planner (deepening)

Combine host capabilities, resolved components, artifact, requirement,
feasibility and policy into a full `DeploymentPlan`: runtime, executor,
components, revision, resource requirement, context, configured
concurrency, ports, expected use, confidence, alternatives, approvals.

### Stage 3.5 — Selection (deepening)

Deterministic given the same inputs and policy version. Never selects on
unverified capacity. Prefers `compatible` over `conditional` at equal
utility. Records why each rejected candidate lost.

Retries are capped — the prior attempt's rule that "repeatedly trying
models on a host that just refused one is how a bootstrap becomes an
outage" is correct and stands.

**Milestone gate (L4):** on a fresh host with no model, the platform
selects, acquires, plans, admits and serves inference automatically, and
explains every rejection. A commit-time proof never resurfaces as a
description of host capacity.

---

## MILESTONE 4 — Multi-workload resource management

**Goal:** several governed workloads coexist safely on one host.

### Stage 4.1 — Generic workload types

Represent `inference`, `embedding`, `reranking`, `indexing`,
`benchmark`, `training`, `evaluation`, `quantization`, `distillation`,
`agent_worker`. Only inference executes.

### Stage 4.2 — Oversubscription prevention

Multiple concurrent reservations. Requested requirement, admitted
reservation, observed consumption and peak observed consumption stay
separate. Explainable denial. Persisted reservations reconcile on
restart — the prior attempt's Step 07 was never completed and is a
first-class requirement here.

### Stage 4.3 — Concurrency binding

Bind the two dimensions properly: request concurrency within one
instance, and simultaneous instance concurrency. The generic platform
concurrency concept maps to the runtime's own control through the
adapter. The prior attempt left a platform-level concurrency number
unmapped to `max_num_seqs`.

### Stage 4.4 — Multiple live instances

The schema has been plural since Stage 1.5B. This stage is the
**hardware proof**, not the introduction of the concept.

**Milestone gate (L4):** two genuinely simultaneous inference instances
with safe per-instance allocations on real hardware; a third correctly
denied; either stopped independently without disturbing the other;
restart reconciles both. Several models stored and two different
instances running is the intended demonstration. Advanced scheduling,
replica autoscaling and multi-host placement remain later.

---

## MILESTONE 5 — Governed access spine

**Goal:** identity, routing and external federation become real.
`Subject` and `UsageEvent` have existed since milestone 0, so this
deepens rather than retrofits.

- **5.1 Identity, teams, policy** — User, Group, Team, Application,
  Role, AccessPolicy, behind a replaceable `IdentityProvider` for later
  SSO and SCIM. One identity model serves gateway, analytics, knowledge,
  agents and audit.
- **5.2 Routing v1** — explicit, default, policy-driven, administrator
  override, simple fallback. Routing never reserves resources directly.
- **5.3 External federation** — one external path via a LiteLLM
  adapter, behind the Kultrun Gateway. LiteLLM must not own identity,
  route semantics, model identity, usage events, permissions, resource
  state or cost normalization.
- **5.4 Usage analytics** — partitioned store, retention policy,
  exporter present but disabled by default. Service logs are never usage
  events. No prompts, responses or retrieved content leave by default.

**Gate (L4):** one Gateway API serves local and external inference with
identity attribution throughout; removing LiteLLM changes no core
contract.

---

## MILESTONE 6 — Operability

**Goal:** the platform is administrable without a shell.

The Admin surface has grown since milestone 0; this is where it becomes
primary.

- **6.1 Admin console v1** — host, capacity, catalog, inventory,
  instances, reservations, gateway, usage, users and teams, health,
  configuration. Settings expose automatic versus manual override, with
  recommendation, reason and confidence.
- **6.2 Admin AI Agent v1** — structured tools only. Read-only needs no
  approval; low-risk mutation follows policy; meaningful mutation
  requires explicit administrator approval. No unrestricted shell.
- **6.3 Idempotent startup** — one reconciliation path across models,
  components, runtimes, workloads, reservations, ports and endpoints.

**Gate (L4):** ordinary administration requires no shell command, and a
hard restart preserves coherent inventory, reservations, instances and
gateway state.

### Infrastructure exoskeleton gate

Milestones 0–6 complete when a clean supported host reaches: host
detection, capability profile, component resolution, control plane,
Admin UI, Admin Agent, curated catalog browsing, requirement
calculation, feasibility, deployment plan, safe acquisition, inventory,
reservation, running instance, gateway endpoint, authenticated request,
answer, usage event, visible usage and health, safe stop and restart,
and coherent reconciliation — with every approximation that authorizes a
mutation retired from the debt ledger.

---

## MILESTONE 7 — Knowledge exoskeleton

- **7.1 Sources and connectors** — normalized `KnowledgeSource`,
  `KnowledgeItem`, capabilities, permission reference, provenance,
  content reference, indexing state. Managed local files, a network
  share, and one enterprise document source.
- **7.2 Permission-aware indexing and retrieval** —
  `AccessContext` → candidates → permission enforcement → authorized
  items → retrieval. Source revalidation remains possible for sensitive
  systems.
- **7.3 RAG v1** — indexing, chunking, embeddings, retrieval, prompt
  assembly and inference stay separate modules. Only authorized context
  reaches a model. Embedding assets must not require internet access at
  bootstrap; the prior attempt's frontend broke air-gapped operation by
  fetching them.
- **7.4 Knowledge administration** — connect, disconnect, health,
  indexing state, permission explanation, retrieval diagnosis, reindex.

**Gate (L4):** a user retrieves only what they are authorized to see,
proven by a negative test where an unauthorized item is present in the
index and provably absent from the answer.

---

## MILESTONE 8 — Company Brain and Team Brain

- **8.1 First-party end-user UI** — authentication, conversation,
  streaming, permitted model or brain selection, history, knowledge
  interaction and source visibility. Third-party frontends remain
  replaceable clients.
- **8.2 TeamBrain logical model** — team, membership and policy,
  knowledge scope, tools, agent configuration, base-model policy,
  routing policy, memory placeholder, evaluation profile, optional
  adapter references. A TeamBrain is not one model.
- **8.3 Team agent v1** — execution through `AccessContext`, the
  Gateway, permission-aware knowledge, approved tools and TeamBrain
  policy.

Initial specialization is composition, not training:

```text
base model + team permissions + team knowledge + team tools + team profile
```

### First Company Brain gate

A knowledge source connects, normalizes, preserves permissions, indexes
and retrieves permission-aware; RAG receives only authorized context;
the employee UI uses it; the Admin console shows knowledge health; the
Admin Agent configures and diagnoses it; and a TeamBrain scopes model,
knowledge and tools to a team.

---

## MILESTONE 9 — Outbound boundary, telemetry, entitlements

- **9.1 Three data domains** kept separate: customer AI analytics,
  vendor product telemetry, licensing and entitlement.
- **9.2 Heartbeat agent** — one outbound boundary for heartbeat,
  telemetry, optional cloud analytics, update checks, crash reporting
  and entitlement renewal. Channels independently visible and
  configurable. Air-gapped mode disables all outbound traffic.
- **9.3 Entitlements** — signed, locally verified, feature and capacity
  claims, renewal, grace, offline license. Marketing tier names never
  enter core logic. No destructive kill switch.

**Gate:** air-gapped operation verified with all outbound disabled, and
no customer content in any outbound channel by default.

---

## MILESTONE 10 — Installer, updates, commercial governance

- **10.1 Product bootstrapper** — the developer harness becomes the
  non-technical installer: inspect host, ask business questions, resolve
  components, build a plan, obtain approval, download and verify,
  install, initialize, health check.
- **10.2 Component installation and offline bundles** — only required
  compatible components, from versioned signed manifests.
- **10.3 Modular updates and rollback** — core, UI, runtime adapters,
  executors, connectors and telemetry update independently, versioned,
  verified and rollback-aware.
- **10.4 Commercial governance** — dependency inventory, provenance,
  license metadata, Green/Amber/Red classification, SBOM, packaged
  artifact audit.

**Gate:** a non-technical administrator installs Kultrun on a clean
supported host and reaches a working deployment without shell access.

---

## MILESTONE 11 — Capacity and effectiveness intelligence

Begins only after the exoskeleton and Company Brain work. This is where
the precision deferred from milestones 1 through 3 is finally earned.

- **11.1 Observed capacity evidence** — real RAM and VRAM, context,
  concurrency, TTFT, ITL, TPOT, throughput, queue delay, OOM and
  failure.
- **11.2 WorkloadProfile** — input and output length, request rate,
  burstiness, concurrency, streaming, SLO targets, priority.
- **11.3 Capacity intelligence v2** — fuse theoretical and observed
  evidence; keep `memory_max_concurrency`,
  `performance_max_concurrency`, `slo_max_concurrency`,
  `configured_concurrency` and `platform_max_concurrent_requests`
  distinct. Compare prediction against reality and report confidence.
  The Capacity Planner stays advisory; the Resource Manager stays
  authoritative.
- **11.4 ModelOutcome** — model and configuration, task, team and role,
  cohort, latency, tokens, errors, cost, explicit ratings, retries and
  switching, acceptance proxies. Raw customer content stays local.

---

## MILESTONE 12 — Intelligent routing and portfolio optimization

- **12.1 Model effectiveness dataset** — join metadata, capacity
  evidence, workload profile, usage events, outcomes and cohort.
- **12.2 Intelligent routing** — policy, team, task, privacy, capacity,
  quality, latency, cost, availability and effectiveness. Explainable,
  with administrator override.
- **12.3 Model inventory optimizer** — explainable portfolios: highest
  quality, balanced, broadest coverage, lowest resource use, lowest
  cost, best concurrent mix. The `SingleModelSelector` interface from
  3.5 becomes a `ModelMixOptimizer` behind the same contracts, not a
  rewrite.

---

## MILESTONE 13 — Team Brain adaptation

- **13.1 Training data governance** — `DatasetSnapshot` with
  provenance, authorization, scope, version, retention and policy.
  **Permission to retrieve does not imply permission to train.**
- **13.2 ModelAdaptationProvider** — replaceable seam for LoRA and
  PEFT, SFT, preference optimization, merging and distillation. Training
  infrastructure stays separate from inference infrastructure and runs
  through resource manager workload contracts.
- **13.3 Evaluation and promotion** — draft, evaluating, approved,
  production, deprecated. Compared against the base model on quality,
  outcomes, latency, resource use, cost and safety.
- **13.4 Team-specific serving** — base model plus adapter plus routing
  policy.

---

## MILESTONE 14 — Multi-host and organisational coordination

- **14.1 Multi-host control plane** — extend the existing
  `HostCapabilities`, resource manager, deployment plan,
  `InferenceInstance` and endpoint registry into `FleetState`. The
  multi-pool and per-accelerator contracts from milestones 1 and 2 exist
  precisely so this is an extension.
- **14.2 Model placement** — which host should run this workload, using
  the same normalized capacity semantics.
- **14.3 Organisational coordination** — expertise discovery,
  duplicate-effort detection, cross-team knowledge flow, governed task
  coordination, organisational recommendations. Explainable, with human
  approval central.

---

# PART IV — WHAT MUST NOT DELAY THE EXOSKELETON

Do not let any of these block the first complete working product:
exhaustive benchmarks; Kubernetes and any Kubernetes-sourced discovery
provider; container execution and device attachment; AMD, Intel or any
provider written for completeness rather than for a host in front of us;
multi-host orchestration; deep
capacity calibration; DEEP storage characterization; learned routing;
the portfolio optimizer; more than a curated model candidate set; more
than a minimal connector set; knowledge graphs; fine-tuning or
distillation; autonomous Team Brain learning; organisational
coordination; custom billing; a polished UI; an exhaustive audit UI;
a generic Selection Framework; a reactive dependency-graph engine.

Create the seam. Defer the depth. Record the debt.

The same rule governs discovery providers and execution backends. The
seams — `HostDiscoveryProvider`, `Executor`, `ContainerEngine` — are cheap
and belong early. What sits behind them arrives when a real host or a real
deployment needs it, and each one is an adapter.

The prior attempt's own closing instruction remains the right one:
**stop refining once the next architectural dependency is unblocked.**

---

# PART V — STAGE BRIEF

Before implementing any stage, produce:

```text
CURRENT STAGE
PREDECESSOR OUTPUTS          (verified, not assumed)
THIS STAGE'S REQUIRED OUTPUT
CORE CONTRACTS AFFECTED
ADAPTERS AFFECTED
PERSISTED STATE              + how it reconciles on restart
MUTATION / FAILURE BOUNDARY  + what fails closed
CANCELLATION / CLEANUP       + what orphans are possible
ACCEPTANCE LEVEL             L1 | L2 | L3 | L4, and why that level suffices
ADMIN SURFACE                Platform API and console representation
DEBT ENTRIES                 new PROVISIONAL items and their retirement condition
DEFERRED ITEMS
```

If a proposed change is not necessary to produce the current stage's
output, defer and record it.

### Stage 1.3 brief

```text
CURRENT STAGE                Runtime / executor exoskeleton. No LLM.
PREDECESSOR OUTPUTS          Stage 1.2A closed (Storage Sanity + Prototype
                             Console); model-lifecycle roadmap checkpoint.
THIS STAGE'S REQUIRED OUTPUT ExecutorSpec, ExecutorHandle, DeviceRequest,
                             RuntimeProfile, RuntimeLaunchSpec,
                             NativeProcessExecutor, InferenceRuntime port,
                             ContainerEngine seam (unimplemented).
CORE CONTRACTS AFFECTED      execution.*, runtime.* (new); architecture
                             non-edge runtime ⟂ capacity added.
ADAPTERS AFFECTED            adapters/execution/native_process;
                             adapters/runtime/reference_process
                             (acceptance harness, not an inference engine).
PERSISTED STATE              ExecutorHandle records. On restart, PIDs we
                             cannot prove are ours become UNVERIFIED and
                             are never signalled (K-31).
MUTATION / FAILURE BOUNDARY  POST /v1/runtime/execution starts only the
                             reference workload; arbitrary argv is refused.
                             Missing executable fails closed.
CANCELLATION / CLEANUP       SIGTERM then SIGKILL after a bounded grace.
                             Output capture is bounded. No supervisor.
ACCEPTANCE LEVEL             L2 — process lifecycle on a real OS. Local T2
                             on macOS proves portable primitives; the
                             stage gate still wants a generic Linux host
                             (no GPU) because L1 cannot close a runtime.
ADMIN SURFACE                GET /v1/runtime, POST start/stop; Prototype
                             Console runtime panel; kultrun runtime CLI.
DEBT ENTRIES                 K-31 reattach, K-32 health UNKNOWN, K-33
                             ContainerEngine, K-34 unauthenticated mutation.
DEFERRED ITEMS               Production reconciliation; OCI executor;
                             inference health; Stage 1.4A catalog.
```

### Stage 1.4A brief

```text
CURRENT STAGE                Model sources / catalog + metadata. No
                             selection, download, admission or inference.
PREDECESSOR OUTPUTS          Stage 1.3 closed at L2 (runtime/executor);
                             Stage 1.2 capacity envelope; Stage 1.2A console;
                             model-lifecycle roadmap checkpoint.
THIS STAGE'S REQUIRED OUTPUT ModelSource port, one Hugging-Face-identity
                             adapter, 4–8 curated candidates, ModelMetadata,
                             ModelRequirement v0 with evidence/confidence,
                             GET catalog API, Prototype Console catalog panel.
CORE CONTRACTS AFFECTED      model.metadata, model.requirement (fields added
                             additively); model.ports.ModelSource (new).
ADAPTERS AFFECTED            adapters/model_source (huggingface-curated).
PERSISTED STATE              None required. Catalog is packaged evidence,
                             not inventory. Inventory remains 1.4C.
MUTATION / FAILURE BOUNDARY  Read-only. GET never downloads. Unknown
                             requirement stays unresolved, never zero.
CANCELLATION / CLEANUP       No mutation, no orphans.
ACCEPTANCE LEVEL             L1. L2 only if a live source fetch is claimed.
                             T0/T1/T2; no GPU. Wheel clean install.
ADMIN SURFACE                GET /v1/models; Prototype Console Model Catalog.
                             No recommendation, no ranking display.
DEBT ENTRIES                 Live huggingface_hub fetch deferred until a
                             network T3 is claimed. Requirement estimates
                             are conservative v0 (K-entry). Console
                             unresolved-PID rendering fixed on this frontend
                             touch if still present.
DEFERRED ITEMS               Selection (1.4B), acquisition (1.4C), local-file
                             source, whole-Hub search, learned ranking.
```

### Stage 1.4B brief

```text
CURRENT STAGE                Feasibility + capacity-based selection +
                             DeploymentPlan v0. One active estimator.
                             No download, no reservation. No product
                             cross-provider reconciliation.
PREDECESSOR OUTPUTS          Stage 1.4A catalog and ModelRequirement v0;
                             Stage 1.2 CapacityEnvelope; Stage 1.3 runtimes.
THIS STAGE'S REQUIRED OUTPUT ModelRequirementEstimator port; Kultrun and
                             llmfit adapters; ModelEstimationRequest;
                             DeploymentCapacity, CapacityUtilization,
                             SelectionPolicy, FeasibilityResult per
                             candidate, SelectionRecommendation,
                             DeploymentPlan v0; development-only
                             compare_model_estimators tool.
CORE CONTRACTS AFFECTED      model.estimation_request (new);
                             model.requirement (additive provider fields);
                             planning.* (new). planning ⟂ resource preserved.
ADAPTERS AFFECTED            adapters/estimators (kultrun, llmfit).
PERSISTED STATE              Recommendations are recomputed, not stored as
                             truth. Comparison reports are not runtime state.
MUTATION / FAILURE BOUNDARY  No mutation. SAFE capacity only. No silent
                             relaxation of utilization bounds. Unknown
                             load-bearing requirement → UNRESOLVED.
                             AUTO: llmfit typed failure → Kultrun fallback.
                             Strict llmfit: no Kultrun fallback.
                             Strict kultrun: llmfit irrelevant.
                             Valid over-capacity / underutilized llmfit
                             evidence does not trigger fallback.
CANCELLATION / CLEANUP       No mutation.
ACCEPTANCE LEVEL             L1. T2 proves real llmfit plan from a clean
                             wheel. T3 only if host-sensitive. Boundary
                             tests: 19.99% underutilized; 20% and 100%
                             preferred; 100.01% infeasible; unknown
                             requirement; storage failure independent
                             of memory utilization; tiny host; medium GPU;
                             CPU-only; multiple preferred candidates;
                             both estimators through the same Planning.
ADMIN SURFACE                GET /v1/models/selection; kultrun models
                             recommend; Prototype Console Model Selection
                             (active estimator only).
DEBT ENTRIES                 SelectionPolicy defaults 0.20 / 1.00.
                             allow_underutilized_fallback reserved, off.
                             llmfit optional extra; RAM floor in llmfit
                             ram_gb documented. Multi-GPU seam unused.
DEFERRED ITEMS               Learned ranking, portfolio optimizer, live
                             Hub search, offload optimizer, acquisition,
                             admission, inference, production reconciler.
```

### Stage 1.4C brief

```text
CURRENT STAGE                Model acquisition + plural Model Inventory.
                             Stored ≠ running. No reservation, no
                             InferenceInstance, no inference.
PREDECESSOR OUTPUTS          Stage 1.4B closed at L1 (selection + plan);
                             Stage 1.4A catalog; Stage 1.2 SAFE capacity;
                             Stage 1.2A console.
THIS STAGE'S REQUIRED OUTPUT ModelAcquisitionProvider port; Hugging Face
                             and fixture adapters; ModelAcquisitionRequest;
                             verified staged ModelArtifact; ArtifactManifest;
                             plural ModelInventory; acquire/delete API,
                             CLI and Console inventory panel.
CORE CONTRACTS AFFECTED      model.acquisition_request, model.acquisition_receipt,
                             model.artifact_manifest (new); model.artifact
                             and config.platform additive fields;
                             InventoryState gains invalid/deleted.
ADAPTERS AFFECTED            adapters/acquisition (huggingface, fixture).
                             ModelSource remains discovery-only.
PERSISTED STATE              ModelArtifact + inventory records + files under
                             {state_root}/models/{staging,artifacts}.
                             Deleted artifacts remain tombstones.
MUTATION / FAILURE BOUNDARY  POST acquire / DELETE artifact. No caller path
                             or arbitrary URL. SAFE storage preflight.
                             Partial files never STORED. Serving states
                             never written on artifacts.
CANCELLATION / CLEANUP       Staging removed on failure. No download
                             scheduler or pause/cancel orchestration.
ACCEPTANCE LEVEL             L1. Fixture T0/T1 offline. T2 clean wheel
                             plus bounded public Hub repo. T3 not required.
ADMIN SURFACE                GET /v1/models/inventory; POST /v1/models/acquire;
                             DELETE /v1/models/artifact; kultrun models
                             inventory|acquire|delete; Console Model Inventory.
DEBT ENTRIES                 Resumable-download manager, pause/cancel,
                             throttle, parallel scheduler, warehouse,
                             conversion/quant, update polling, gated UX,
                             license engine deferred.
DEFERRED ITEMS               ResourceReservation (1.5A), InferenceInstance
                             (1.5B), runtime loading, large production
                             model download.
```

### Stage 1.5A brief

```text
CURRENT STAGE                Resource admission + persistent
                             ResourceReservation. Reserved ≠ running.
                             No InferenceInstance, no launch.
PREDECESSOR OUTPUTS          Stage 1.4C closed at L1 (STORED artifacts);
                             Stage 1.4B DeploymentPlan; Stage 1.2 SAFE
                             capacity.
THIS STAGE'S REQUIRED OUTPUT ResourceRequest; AdmissionDecision;
                             ResourceReservation ACTIVE/RELEASED;
                             ResourceManager; SAFE − ACTIVE arithmetic;
                             atomic concurrent admission; release;
                             resource summary; API/CLI/Console.
CORE CONTRACTS AFFECTED      resource.request, resource.admission_decision,
                             resource.summary, resource.device_summary
                             (new); resource.reservation additive fields.
ADAPTERS AFFECTED            none. Composition translates plan → request.
PERSISTED STATE              ResourceReservation + Workload + ResourceRequest
                             in the platform store. Available is recomputed.
MUTATION / FAILURE BOUNDARY  POST reserve / DELETE release. Client amounts
                             are not authoritative. STORED artifact required.
                             SAFE layer only. Overcommit rejects new work.
CANCELLATION / CLEANUP       Explicit release. No TTL/lease daemon.
ACCEPTANCE LEVEL             L1. T0/T1 fixture arithmetic and persistence.
                             T2 clean wheel. T3 not required.
ADMIN SURFACE                GET /v1/resources; GET/POST/DELETE
                             /v1/resources/reservations; kultrun resources;
                             Console Resource reservations.
DEBT ENTRIES                 Leases, ports, quotas, preemption, scheduler,
                             physical enforcement deferred.
DEFERRED ITEMS               InferenceInstance (1.5B), runtime launch,
                             model load, inference.
```

### Stage 1.5B brief

```text
CURRENT STAGE                InferenceInstance lifecycle. STORED artifact
                             + ACTIVE reservation + Runtime + Executor
                             → create/start/observe/stop. Reference
                             serving only. No real LLM, no prompts.
PREDECESSOR OUTPUTS          Stage 1.5A ResourceReservation; Stage 1.4C
                             STORED artifacts; Stage 1.3 Runtime/Executor.
THIS STAGE'S REQUIRED OUTPUT InferenceInstance; InstanceId; desired vs
                             observed; reference-serving runtime;
                             readiness; persistence; restart
                             reconciliation; release-while-live guard;
                             dynamic Small→Large→Small mobility;
                             API/CLI/Console.
CORE CONTRACTS AFFECTED      inference.instance additive lifecycle
                             fields; runtime.launch_request (new).
ADAPTERS AFFECTED            adapters/runtime/serving + serving_workload.
PERSISTED STATE              InferenceInstance in the platform store.
                             Process identity is not blindly trusted
                             after control-plane restart.
MUTATION / FAILURE BOUNDARY  POST create/start/stop. Stop does not
                             release. Release refused while live or
                             UNKNOWN. Client argv and amounts rejected.
CANCELLATION / CLEANUP       Explicit stop; explicit release after
                             STOPPED. No scheduler.
ACCEPTANCE LEVEL             L1. T0/T1 lifecycle + mobility. T2 clean
                             wheel. T3 not required (1.3 already proved
                             generic process lifecycle).
ADMIN SURFACE                GET/POST /v1/inference/instances;
                             POST start/stop; kultrun instances;
                             Console Inference instances.
DEBT ENTRIES                 Port allocator (K-45), supervisor/PID
                             reattach (K-31), real inference, cache,
                             auto-switch, scheduler (K-46).
DEFERRED ITEMS               Stage 1.5C Runtime / Executor reconciliation,
                             then 1.6A ContainerExecutor / real inference.
```

### Stage 1.5C brief

```text
CURRENT STAGE                Runtime / Executor boundary reconciliation.
                             No vLLM, no provisioning, no verification,
                             no model-selection remap.
PREDECESSOR OUTPUTS          Stage 1.5B CLOSED L1
                             (620a78be94433a0e8a6624d36147b0e870fafd61).
THIS STAGE'S REQUIRED OUTPUT ExecutorCapabilityProfile;
                             RuntimeSupportDescriptor (reference TEST_ONLY);
                             executor-neutral RuntimeLaunchSpec (KEEP/ADJUST);
                             executor-neutral ExecutorHandle (KEEP/ADJUST);
                             RecordingExecutor fixture; runtime-owned
                             readiness; 1.5B/1.5A/1.4 regressions.
CORE CONTRACTS AFFECTED      execution.capability_profile;
                             runtime.support_descriptor; runtime.readiness;
                             additive generic fields on launch spec,
                             executor spec, and handle.
ADAPTERS AFFECTED            NativeProcessExecutor.capabilities;
                             reference-serving / reference-process;
                             adapters/execution/recording (fixture only).
PERSISTED STATE              InferenceInstance + ExecutorHandle as in 1.5B.
                             Additive handle fields decode with defaults.
MUTATION / FAILURE BOUNDARY  No new mutating workflows.
CANCELLATION / CLEANUP       Unchanged executor stop + explicit release.
ACCEPTANCE LEVEL             L1. T3 not required.
ADMIN SURFACE                Existing instance / runtime / resource / model
                             surfaces. No Runtime Setup.
DEBT ENTRIES                 K-33 ContainerExecutor (1.6A); verified
                             RuntimeCapabilityProfile; runtime-first remap.
DEFERRED ITEMS               1.6A minimal ContainerExecutor and later 1.6
                             letters. Do not begin them from this stage.
```

### Stage 1.6A brief

```text
CURRENT STAGE                Minimal ContainerExecutor + executor
                             portability. No vLLM, no RuntimeResolver,
                             no provisioning, no model-selection remap.
PREDECESSOR OUTPUTS          Stage 1.5C CLOSED L1
                             (8e78dea7a56dcd9cd23faef0a4a45fb08a1141a3).
THIS STAGE'S REQUIRED OUTPUT ContainerExecutor on the generic Executor
                             port; first ContainerEngine (Docker CLI);
                             truthful ExecutorCapabilityProfile;
                             executor-owned ContainerExecutionConfig;
                             same reference-serving RuntimeLaunchSpec
                             realized by native and container executors;
                             runtime-owned readiness preserved.
CORE CONTRACTS AFFECTED      execution.container_config (new);
                             execution.engine_probe (new);
                             ExecutorCapabilityProfile consumed, not
                             reshaped; RuntimeLaunchSpec remains generic.
ADAPTERS AFFECTED            adapters/execution/container;
                             adapters/container/docker;
                             adapters/container/recording (T1 fake
                             engine); NativeProcessExecutor resolves
                             logical `python`; reference runtimes emit
                             a component name, not sys.executable.
PERSISTED STATE              ExecutorHandle as in 1.5C. Container id
                             lives in external_identity. PID remains
                             optional. Restart: unheld containers are
                             UNVERIFIED and are not signalled.
MUTATION / FAILURE BOUNDARY  Engine unavailable, image missing, invalid
                             image, immediate exit, command missing,
                             stop-already-stopped, forced stop. No raw
                             Docker object leaves the adapter. No
                             public image/mount/CLI fragment API.
CANCELLATION / CLEANUP       Graceful docker stop then bounded kill.
                             Remove only kultrun-labelled containers
                             this executor created. Unrelated
                             containers are never touched.
ACCEPTANCE LEVEL             L2 CLOSED. Real Linux Docker Engine T3
                             passed. Docker Desktop is not an
                             architectural dependency. Physical limits:
                             host-network v0, Docker Engine first
                             implementation, no GPU/bridge/vLLM proof.
ADMIN SURFACE                Existing runtime/instance surfaces may
                             show executor identity, ExecutionId,
                             external identity, capability
                             availability. No `kultrun docker`. No
                             container-management UI.
DEBT ENTRIES                 GPU/device exposure in containers;
                             bridge/publish networking if host net
                             used; multiple engines; image management;
                             Kubernetes.
DEFERRED ITEMS               1.6B Runtime Resolution and later 1.6
                             letters. Do not begin them from this stage.
```

### Stage 1.6B brief

```text
CURRENT STAGE                Runtime resolution. No install, verify,
                             vLLM execution, or model-selection remap.
PREDECESSOR OUTPUTS          Stage 1.6A CLOSED L2
                             (f3d4baf3d255ca944ffd626aaf1f3505f3b20b27).
THIS STAGE'S REQUIRED OUTPUT RuntimePolicy; RuntimeCandidate;
                             RuntimeResolution; RuntimeResolver;
                             conservative vLLM declared-support
                             descriptor; read-only candidates API/CLI.
CORE CONTRACTS AFFECTED      runtime.policy; runtime.candidate;
                             runtime.resolution (new);
                             support_descriptor additive preferred_version.
ADAPTERS AFFECTED            adapters/runtime/vllm (declared support only).
PERSISTED STATE              None. Candidates are derived per read.
MUTATION / FAILURE BOUNDARY  Read-only.
CANCELLATION / CLEANUP       None.
ACCEPTANCE LEVEL             L1. T3 not required.
ADMIN SURFACE                GET /v1/runtimes/candidates;
                             kultrun runtimes candidates;
                             read-only Console panel.
DEBT ENTRIES                 K-56…K-65.
DEFERRED ITEMS               1.6C Runtime Provisioning and later 1.6
                             letters. Do not begin them from this stage.
```

### Stage 1.6C brief

```text
CURRENT STAGE                Runtime provisioning. Exact plan + isolated
                             install. INSTALLED is not VERIFIED.
                             CLOSED L2.
PREDECESSOR OUTPUTS          Stage 1.6B CLOSED L1
                             (cfbfc2f5d488e73cb94642c643f095355964f083).
THIS STAGE'S REQUIRED OUTPUT RuntimeProvisioningPlan;
                             RuntimeProvisioner; RuntimeInstallation;
                             vLLM 0.28.0 pin; venv+pip; persistence;
                             idempotency; explicit retry; T2 fixture;
                             T3 real install for L2.
CORE CONTRACTS AFFECTED      runtime.provisioning_component@1;
                             runtime.provisioning_plan@1;
                             runtime.installation@1;
                             support_descriptor preferred_version 0.28.0.
ADAPTERS AFFECTED            adapters/provisioning/fixture;
                             adapters/provisioning/vllm_native;
                             adapters/runtime/vllm pin only.
PERSISTED STATE              Plan and Installation. Candidates derived.
                             Interrupted INSTALLING → FAILED.
MUTATION / FAILURE BOUNDARY  POST plan / POST provision only.
                             No system Python/driver/CUDA mutation.
CANCELLATION / CLEANUP       Staging deleted on failure; never promoted.
ACCEPTANCE LEVEL             L2 CLOSED. T3 real isolated vLLM 0.28.0
                             install. INSTALLED is not VERIFIED.
ADMIN SURFACE                POST /v1/runtimes/provisioning-plans;
                             POST /v1/runtimes/provision;
                             GET plans/installations;
                             kultrun runtimes plan|provision|installations;
                             Console Create plan / Provision. No Verify.
DEBT ENTRIES                 K-66…K-79. K-56…K-65 preserved.
                             Selection/replanning debt K-80…K-87 recorded;
                             not blocking 1.6C.
DEFERRED ITEMS               1.6D Runtime Verification and later 1.6
                             letters. Do not begin them from this stage.
SELECTION SEAM               Provision the explicitly identified
                             RuntimeCandidate. Never silently substitute
                             the AUTO recommendation or another path.
                             INSTALLED is not VERIFIED. No ranking UI.
```

### Stage 1.6D brief

```text
CURRENT STAGE                Runtime verification. Exact installation
                             → host/executor probe → capability profile.
                             CLOSED L2.
PREDECESSOR OUTPUTS          Stage 1.6C CLOSED L2
                             (`0f39753d9d2b2c9e2942ca852983efa2e6203ad3`).
THIS STAGE'S REQUIRED OUTPUT RuntimeVerifier; RuntimeCapabilityProfile;
                             RuntimeVerificationBasis; vLLM native
                             verifier; fixture verifier; persistence;
                             idempotency; staleness; API/CLI/Console;
                             T0/T1/T2; real T3 for L2.
MUST NOT                     Rank; recommend; silently fall back;
                             treat INSTALLED as VERIFIED; treat VERIFIED
                             as model-compatible; load a model; infer.
ACCEPTANCE LEVEL             L2 CLOSED. Real NVIDIA T3: import vllm,
                             backend, tiny CUDA. No model.
DEFERRED ITEMS               1.6E bounded runtime selection. K-88…K-93.
```

### Stage 1.6E brief

```text
CURRENT STAGE                Foundation selection. Two-phase
                             provisionable ≠ executable. Compose
                             closed 1.6B–1.6D objects.
PREDECESSOR OUTPUTS          Stage 1.6D CLOSED L2
                             (`fb67e7d6bcaf011cc39951472ae1ebf692e7fd88`).
THIS STAGE'S REQUIRED OUTPUT FoundationSelection (AUTO|MANUAL;
                             recommended_candidate_id ≠
                             selected_candidate_id);
                             pre-provision classification
                             (recommended / other provisionable /
                             blocked);
                             selected candidate flows through existing
                             RuntimeProvisioningPlan →
                             RuntimeProvisioner → RuntimeInstallation
                             and RuntimeVerifier →
                             RuntimeCapabilityProfile;
                             truthful FAILED without silent fallback;
                             downstream_stale + stale_domains seam.
CORE CONTRACTS AFFECTED      runtime.foundation_selection@1 (new).
                             No FoundationCandidate.
                             No DeploymentFoundation class.
                             No EnvironmentProvider port.
                             No recipe DSL.
ADAPTERS AFFECTED            None. Existing fixture/vLLM provisioner
                             and verifier are reused.
PERSISTED STATE              One current FoundationSelection per host
                             (fsel_<16 hex> from
                             runtime.foundation_selection@1|{host_id}).
MUTATION / FAILURE BOUNDARY  POST select / realize / verify-selected.
                             GET /runtimes/foundation never persists,
                             provisions, or probes.
CANCELLATION / CLEANUP       Selection lock (runtimes/select.lock).
                             Failed verify does not change selection
                             or delete the installation.
ACCEPTANCE LEVEL             L1 CLOSED. T0/T1 plus T2 clean-wheel
                             fixture chain. T3 not required.
ADMIN SURFACE                GET /v1/runtimes/foundation;
                             POST /v1/runtimes/foundation/select;
                             POST /v1/runtimes/foundation/realize;
                             POST /v1/runtimes/foundation/verify;
                             kultrun runtimes foundation|select|realize
                             |verify --selected;
                             Console Select foundation / Use AUTO /
                             Realize selected.
DEBT ENTRIES                 No new IDs for FoundationCandidate,
                             HostCapabilityProfile,
                             EnvironmentRealization,
                             VerifiedRuntimeCapabilityProfile,
                             EnvironmentProvider, recipe DSL, or
                             SelectionFramework.
                             K-66, K-77, K-33/K-75/K-91, K-56/K-80,
                             K-87, K-86 remain authoritative.
MUST NOT                     Reopen 1.6B/1.6C/1.6D; generic
                             SelectionFramework; new Foundation
                             domain; EnvironmentProvider hierarchy;
                             weighted optimizer; model-selection
                             rewrite; ResourceManager changes;
                             managed Python; container GPU;
                             silent fallback; collapse COMPATIBLE
                             with VERIFIED; overload RuntimePolicy.mode
                             as FoundationSelection.mode.
DEPTH                        Accepted: minimum + architectural seams.
                             Recommendation = hard gates + existing
                             1.6B lexicographic rank + reuse of the
                             same fresh VERIFIED candidate identity.
                             No speculative scores.
```

### Stage 1.6F brief

```text
CURRENT STAGE                Runtime-aware eligible model view.
                             Migrate runtime/model compatibility
                             onto the selected verified foundation.
PREDECESSOR OUTPUTS          Stage 1.6E CLOSED L1
                             (`bd9cdee29f385e3f284f5782443c31cf85d21438`).
THIS STAGE'S REQUIRED OUTPUT EligibleModelView CURRENT|STALE|UNAVAILABLE;
                             RuntimeEligibleModelCandidate
                             ELIGIBLE|BLOCKED|UNRESOLVED;
                             ModelEligibilityService;
                             vLLM 0.28.0 interpreter;
                             GET /v1/models/eligible;
                             kultrun models eligible;
                             Console Eligible models panel;
                             planning/admission consume eligibility
                             tokens instead of catalog∩runtime lists.
CORE CONTRACTS AFFECTED      runtime.eligible_model_view@1;
                             runtime.eligible_model_candidate@1.
                             No DeploymentFoundation class.
                             No CompatibilityFramework.
                             No ModelMetadataV2.
ADAPTERS AFFECTED            adapters/runtime/vllm
                             (VllmModelCompatibility).
PERSISTED STATE              None. View is derived. Catalog and
                             inventory are not mutated.
MUTATION / FAILURE BOUNDARY  GET /models/eligible never persists,
                             acquires, or admits.
CANCELLATION / CLEANUP       None. Read-only recomputation.
ACCEPTANCE LEVEL             L1 CLOSED. T0/T1 plus T2 clean-wheel
                             fixture chain. T3 not required.
ADMIN SURFACE                GET /v1/models/eligible;
                             kultrun models eligible;
                             Console Eligible models.
DEBT ENTRIES                 K-87 RETIRED. K-94 planning composition
                             shim. K-55, K-66, K-77, K-80, K-86 remain.
MUST NOT                     Reopen 1.6B–1.6E; remap ModelRequirement
                             or Capacity; redesign ModelSelector;
                             acquire/delete artifacts; score
                             foundations; write eligibility into
                             ModelMetadata; treat UNKNOWN as ELIGIBLE;
                             consult RAM/VRAM/reservations.
DEPTH                        Accepted: minimum + a little depth.
                             First concrete interpreter: vLLM 0.28.0.
```

### Stage 1.6G brief

```text
CURRENT STAGE                ModelRequirement + Capacity migration.
                             Eligible view + selected VERIFIED runtime
                             → ModelRequirement → CapacityAssessment.
PREDECESSOR OUTPUTS          Stage 1.6F CLOSED L1
                             (`804c2bd3761918b802683c7fe83718fe6acfcc97`).
THIS STAGE'S REQUIRED OUTPUT ModelRequirement from ELIGIBLE candidate;
                             selected runtime as estimator identity;
                             CapacityAssessment from remapped
                             requirement; GET /v1/models/requirements;
                             kultrun models requirements;
                             Console capacity verdict; K-94 RETIRED.
CORE CONTRACTS AFFECTED      model.requirement@1 optional provenance
                             fields. No ModelRequirementV2.
                             No CapacityPlannerV2. No DeploymentPlan.
ADAPTERS AFFECTED            None. Estimator ports unchanged.
PERSISTED STATE              None. Requirement/capacity are derived.
MUTATION / FAILURE BOUNDARY  GET /models/requirements never admits
                             or acquires.
CANCELLATION / CLEANUP       None. Read-only recomputation.
ACCEPTANCE LEVEL             L1 CLOSED. T0/T1 plus T2 clean-wheel
                             fixture chain. T3 not required.
ADMIN SURFACE                GET /v1/models/requirements;
                             kultrun models requirements;
                             Console selection capacity labels.
DEBT ENTRIES                 K-94 RETIRED. K-55, K-66, K-77, K-80,
                             K-86 remain.
MUST NOT                     Reopen 1.6B–1.6F; redesign ModelSelector;
                             create DeploymentPlan authority; remap
                             ResourceManager or InferenceInstance;
                             estimate BLOCKED as compatible; treat
                             UNRESOLVED as FEASIBLE; use
                             supported_runtimes[0] as identity.
DEPTH                        Accepted: minimum + a little depth.
```

---

# PART VI — FINAL SEQUENCE

```text
0.  Contracts that are expensive to retrofit
        ↓
1.  A real request reaching a real model, proven on real hardware   ← the gate that was never reached
        ↓
2.  Storage that tells the truth, and acquisition that cannot corrupt it
        ↓
3.  Choosing well, and explaining the choice — evidence, not first existence
        ↓
4.  Several workloads coexisting safely
        ↓
5.  Governed access: identity, routing, federation
        ↓
6.  Administrable without a shell            ← infrastructure exoskeleton complete
        ↓
7.  Permission-aware knowledge
        ↓
8.  Company Brain and Team Brain             ← first Company Brain complete
        ↓
9.  Controlled outbound boundary and entitlements
        ↓
10. Installable and commercially releasable  ← shippable product
        ↓
11. Evidence-based capacity and effectiveness
        ↓
12. Intelligent routing and portfolio optimization
        ↓
13. Team Brain adaptation
        ↓
14. Multi-host and organisational coordination
```

These are architectural dependencies, not a calendar.

The measure of this roadmap is not how much architecture exists at any
point. It is whether, at every point, the platform **works end to end
and tells the truth about what it can safely do** — and whether each
step makes the next one cheaper rather than more expensive.
