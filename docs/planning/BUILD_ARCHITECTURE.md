# AI STACK — BUILD ARCHITECTURE

**Status:** Authoritative reasoning document
**Purpose:** Derive the optimal build sequence for AI Stack from first principles, record the design
tensions and the alternatives rejected, and fix the invariants that keep the sequence coherent when
read in either direction.

This document answers **why the build is ordered the way it is**.
[`docs/TECHNICAL_ROADMAP.md`](TECHNICAL_ROADMAP.md) answers **what each stage
builds**.

Inputs:

- [`docs/REBUILD_CONTEXT.md`](REBUILD_CONTEXT.md) — the charter
- [`docs/source/COMPANY_BRAIN_PLATFORM.md`](source/COMPANY_BRAIN_PLATFORM.md) — the constitution
- [`docs/DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md) — the operating contract
- [`docs/source/COMPANY_BRAIN_TECHNICAL_PRODUCT_ROADMAP_V1.md`](source/COMPANY_BRAIN_TECHNICAL_PRODUCT_ROADMAP_V1.md)
  — the prior roadmap, superseded

---

## 1. EVALUATION CRITERIA

A candidate build sequence is optimal only if it satisfies all four criteria simultaneously.

| # | Criterion | Test |
| --- | --- | --- |
| C1 | **Progressive** | Every stage consumes a predecessor's output. No stage waits on a successor. |
| C2 | **Proof of work** | Every stage ends with something a person can run and observe, plus a persisted artifact. |
| C3 | **Modular** | No third-party type crosses a core boundary. Every adapter is replaceable without touching core. |
| C4 | **Coherent in retrospect** | Read backwards from the finished product, every stage looks necessary and correctly placed. No stage exists because of discovery order. |

C4 is the criterion the previous project failed, and it is the reason AI Stack exists. It is also the
hardest to test, so §4 converts it into mechanical invariants.

---

## 2. THE TEN DESIGN TENSIONS

Each tension is a place where two criteria pull against each other. The resolution is what the
roadmap implements; the rejected alternative is recorded so it is not silently revisited.

---

### T1 — Foresight versus proof of work

**Tension.** The charter (§5) requires the entire architectural skeleton to be understood before
deep implementation. C2 requires every stage to produce observable output. A contracts-first kernel
satisfies the first and fails the second: twenty serializable types demonstrate nothing.

**Rejected — enlarge the kernel.** Roadmap V1 put contracts, Admin UI shell, Admin Agent shell and
identity into Milestone 0. Adding the further cross-cutting contracts the platform genuinely needs
would extend the period during which nothing runs. Longer dead phases also invite speculative
interfaces, because contracts written without a consumer encode guesses.

**Rejected — pure vertical slices.** Introduce each contract only when a slice needs it. This
maximizes proof of work but reproduces the previous project's failure: contracts arrive in discovery
order, and the ones that turn out to be cross-cutting arrive last.

**Resolution — separate design from implementation.**

- The complete skeleton is designed **on paper, now, once**. That design is this document plus the
  roadmap. Nothing about it is deferred.
- Each contract is **implemented at its first real consumer**, never before.
- The kernel is therefore not a milestone. It is **folded into the first stage**, so it is shaped by
  a genuine consumer — host inspection — rather than by speculation.

Design foresight is complete from day one. Implementation stays consumer-driven. This is the single
most important structural decision in the document.

---

### T2 — Cross-cutting concerns versus staged delivery

**Tension.** Secrets, egress policy, health, audit, reconciliation, explanation and identity touch
nearly every subsystem. They cannot be a stage, because they are not a slice. They cannot be
retrofitted, because retrofitting them is how the previous project accumulated coupling.

**Rejected — a cross-cutting milestone.** Fails C1 and C2 for the same reasons as T1.

**Rejected — retrofit when needed.** This is precisely charter §8's "hiding state inside
process-specific logic" and "carrying forward accidental coupling".

**Resolution — thin kernel plus per-stage obligations.**

The kernel holds only what the *first* stage already needs:

- identity and schema versioning for every contract;
- the `Decision` envelope (stage one already makes decisions);
- `AccessContext` (every platform call carries one, even with a single local principal);
- the domain event envelope (`AuditEvent` derives from it);
- persistence with versioned migrations;
- the artifact store (see §3).

Everything else becomes a **standing obligation checklist** declared now and discharged by whichever
stage first triggers it:

| If a stage… | It must ship… |
| --- | --- |
| persists state | a reconciler, registered with the reconciliation registry |
| reaches the network | declared and enforced `EgressPolicy` compliance |
| holds a credential | `SecretStore` use, never config or logs |
| runs a service | a `ComponentHealth` registration |
| mutates platform state | an `AuditEvent` and a defined rollback |
| makes a judgement | a `Decision` with reason code, evidence, confidence and remedies |
| produces a spine artifact | schema version and `HostFingerprint` stamping |

The seam appears at first need. The obligation is known from the start. This gives retrofit
resistance without a dead phase.

---

### T3 — Local-first versus early end-to-end value

**Tension.** The full request loop — request, route, infer, respond, record — is the most valuable
early demonstration. It could be reached far sooner by routing to an external provider API, months
before local GPU serving works.

**Rejected — external-provider-first gateway.** It inverts the product premise: AI Stack is
self-hosted and private by default (constitution §5.7). Worse, it violates charter §8 directly — the
gateway would be shaped around external API semantics, making LiteLLM the domain model. The hardest
and most differentiating work is safe local deployment; deferring it defers all the risk.

**Resolution — local-first, but the gateway ships *with* first inference, not after it.**

Roadmap V1 built inference at Milestone 5 and the gateway at Milestone 6. That ordering means the
first successful inference in the project's history is demonstrated by calling the runtime directly.
That establishes a bypass path, and bypass paths become habits and then dependencies. Constitution
§98 forbids exactly this for the Admin Agent.

So the minimal gateway is part of the stage that first serves a request. **The first inference
AI Stack ever performs traverses the platform gateway and emits a UsageEvent.** Identity, policy,
limits and external federation are added later, but no request ever bypasses the seam.

---

### T4 — Safety versus demonstrability

**Tension.** Constitution §5.4 puts safety before optimisation: when capacity is uncertain, deny.
But "the system refused" is a weak demonstration, so evidence discipline tends to select for happy
paths, and the denial logic that actually protects customers goes under-proven.

**Resolution — negative proof is a mandatory, first-class element of every stage's evidence.**

Every stage must demonstrate not only what it does but **what it correctly refuses**, with the
reason code and explanation attached. Storage admission must deny an oversized acquisition. The
Resource Manager must deny an unsafe second workload. Retrieval must deny unauthorised content.
Entitlements must deny an expired feature without killing production inference.

Where a stage mutates state, a **recovery proof** is also mandatory: interrupt the operation, prove
clean reconciliation. The previous project's storage probe orphaned a 42,990 MiB temporary file when
interrupted; that class of defect is found only by testing interruption deliberately.

Every stage's proof of work therefore has four parts:

```text
capability demonstration   what it does, observably
artifact                   the persisted, inspectable contract instance
negative proof             what it correctly refuses, and why
recovery proof             interrupt it, prove clean state (mutating stages only)
```

---

### T5 — Host capacity versus transaction safety

**Tension.** Both answer "is there room?" and both are called storage checks, so they collapse into
one another under implementation pressure. The previous project hit this directly.

**Resolution — two artifacts, never merged.** Per the operating contract §16:

- **HOST characterization** establishes what the machine can safely offer, before any model is
  chosen. It feeds the capacity envelope and model feasibility.
- **TRANSACTION verification** proves one specific mutation is safe at commit time.

A transaction result must never be promoted into a field claiming an independently characterized
host ceiling. They are produced by different stages and stored as different artifacts.

A second lesson applies here. The previous project's host characterization ran roughly 48 minutes
without converging, because it searched for the pool ceiling rather than stopping once evidence
exceeded the requirement. AI Stack's characterization is **decision-bounded from the start**: it
answers a question, stops when the answer is determined, persists partial evidence continuously, and
never runs unbounded work in a request thread.

---

### T6 — Metadata versus weights

**Tension.** Feasibility needs model facts. The obvious way to get exact facts is to download the
model. That inverts the safety order and lets the platform acquire something it cannot run.

Roadmap V1 embodied this inversion: acquisition at Milestone 3, capacity assessment at Milestone 4.

**Resolution — `ModelSource` exposes metadata-only resolution as a distinct capability.**

Configuration, file manifests, sizes, architecture and quantization are all retrievable without
weights. **Weights are never fetched to answer a question.** Feasibility gates acquisition, not the
reverse. This makes the constitution's stated order (§20, §111) actually implementable.

---

### T7 — The Admin Agent bootstrap paradox

**Tension.** Constitution §43 makes the Admin AI Agent a core feature, and §45 has it conduct
conversational onboarding during installation. But onboarding happens before any model exists. The
agent that helps an administrator install their first model has no model to run on — and per §98 it
must not have a backdoor.

**Resolution — `PlatformIntelligenceProvider`, with capability degrading and the contract fixed.**

Three implementations over the platform's life:

1. **Deterministic guided provider** — no LLM. Structured questions, decision trees, and rendered
   `Decision` explanations. Always available, works air-gapped and at first boot.
2. **External provider** — administrator-supplied key, explicit and revocable.
3. **Gateway-backed local provider** — once local inference exists, the agent is just another
   gateway client.

The agent's answers get better; its interface never changes. This works only because every stage
emits proper `Decision` explanations, which is why that envelope is in the kernel: **the agent is
largely a presentation layer over explanations the platform already owes its administrator.**

The paradox bites hardest at the installer stage, not at the agent stage, which is where the
roadmap places the requirement.

---

### T8 — Disposable hosts versus persisted artifacts

**Tension.** The operating contract (§1, §18) says servers are disposable but useful state should be
preserved. Persisted models and capacity evidence accelerate tomorrow. They may also be invalid
tomorrow, because the hardware changed.

**Resolution — validity is derived, never assumed.**

Every artifact is stamped with its schema version and the `HostFingerprint` of the machine that
produced it. On any new host, evidence keyed to a different fingerprint is **stale, not wrong**: it
is retained, revalidated against current facts, and reused only if it still holds.

**Persistence does not imply suitability.** This is why `HostFingerprint` is produced by the very
first host stage — nothing downstream can be safely cached without it.

---

### T9 — Progressive stages versus rework

**Tension.** Progressive building means later stages extend earlier contracts. Extension slides into
restructuring, and restructuring means the earlier stage was wrong — which is exactly the incoherence
C4 forbids.

**Resolution — additive-only contract evolution, and treat a required restructure as a planning
failure, not a task.**

Contracts may gain optional fields and new versions. They may not have fields removed, retyped or
regrouped. If a stage genuinely requires restructuring a predecessor's contract, that is evidence
**the sequence is wrong**. The correct response is to stop, re-plan the order, and record why — not
to patch the contract and continue. This is a `DECISION_REQUIRED` condition under the operating
contract §11.

---

### T10 — Stage granularity

**Tension.** Fine stages give tight proof and heavy ceremony. Coarse stages reduce overhead and
weaken evidence, trending back toward big-bang integration.

**Resolution — a stage is the smallest unit that produces both an independently demonstrable
capability and an artifact some named later stage consumes.**

If it produces an artifact but demonstrates nothing, it is not a stage — it belongs inside one. If it
demonstrates something but produces no consumed artifact, it is a feature, not a spine stage.

---

## 3. THE ARTIFACT SPINE

The mechanism that makes the four criteria hold simultaneously.

**Every spine contract is a real, persisted, versioned, inspectable file.** Not only a type in
memory: an artifact on disk, addressable, diffable, and portable off the host.

```text
ai-stack host inspect      → artifacts/host-capabilities.json
ai-stack storage assess    → artifacts/storage-capacity.json
ai-stack model describe X  → artifacts/model-metadata-X.json
ai-stack model assess X    → artifacts/capacity-assessment-X.json
```

Stage N's proof of work is its artifact. Stage N+1's input is that same artifact. This single
mechanism delivers all four criteria at once:

| Criterion | How the artifact spine satisfies it |
| --- | --- |
| C1 Progressive | The chain is literal. A stage cannot start before its input file exists. |
| C2 Proof of work | The artifact is the evidence. It can be read, diffed and archived. |
| C3 Modular | Artifacts are the seams. Adapters are swappable if the artifact is unchanged. |
| C4 Coherent | The whole chain is auditable end to end at any time. |

Three further properties fall out for free:

- **Replayability.** Any stage can be re-run from its predecessor's artifact, without re-running the
  chain. Expensive work — host probes, model downloads — is never repeated to test something
  downstream.
- **Golden fixtures.** Recorded artifacts from real hosts become test inputs. Apple Silicon, AMD and
  CPU-only paths get tested without owning that hardware.
- **Portable evidence.** Artifacts survive the server. On a fresh host you re-run the chain and diff
  against yesterday's, which is exactly the operating contract §14 startup protocol made concrete.

Artifacts are evidence, not authority. The Resource Manager still decides admission against live
reality at the moment of admission.

---

## 4. INVARIANTS

C4 — coherence in retrospect — becomes mechanical through eight invariants. Each is checkable, and a
violation means the sequence is wrong.

| # | Invariant |
| --- | --- |
| **I1** | **Single producer.** Exactly one stage produces each spine artifact. |
| **I2** | **No orphans.** Every stage output has a named consumer stage. |
| **I3** | **Additive only.** Contracts may gain optional fields; never restructure. |
| **I4** | **No regression.** Once a gate passes, it stays passing. |
| **I5** | **Proof of work.** Every stage delivers capability, artifact, negative proof, and recovery proof where it mutates. |
| **I6** | **No forward dependency.** No stage requires a successor's output. |
| **I7** | **Obligations discharged in-stage.** Reconciler, health, audit, egress and secrets ship with the stage that triggers them. |
| **I8** | **Replaceability.** No third-party type crosses a core boundary. |

### The reverse audit

At every gate, walk the chain **backwards** from the demonstrated capability and confirm each
consumed artifact was produced by exactly one earlier stage in its current shape. If the walk
reaches an artifact produced later, or produced twice, or reshaped since, the sequence has drifted.

This is the operational form of the user requirement that the build reads the same front-to-back and
back-to-front.

---

## 5. WHY THE PHASE ORDER IS WHAT IT IS

The spine order is not a matter of taste; both traversals agree on it.

**Forwards.** You cannot characterize capacity without knowing the host. You cannot judge a model
without capacity. You cannot safely acquire without a judgement. You cannot run without an artifact.
You cannot govern access without something to access. You cannot report usage without requests. You
cannot retrieve knowledge without identity to enforce against.

**Backwards.** Organisational coordination needs Team Brains; those need permission-scoped knowledge
and identity; that needs governed access; that needs a gateway; that needs an endpoint; that needs a
reservation and a running instance; that needs an artifact on disk; that needs a feasibility
judgement; that needs capacity; that needs the host.

Both land on the same order, which is what makes it the spine rather than a preference.

The phases:

| Phase | Proves |
| --- | --- |
| 0 — Foundation | The platform knows the machine it is on, safely and with evidence. |
| 1 — Model knowledge | It can decide what it could run, without downloading anything. |
| 2 — Custody | It can take safe custody of an artifact and recover from interruption. |
| 3 — Execution | It can serve governed inference, concurrently, and refuse what is unsafe. |
| 4 — Governed access | Identity, policy and usage accounting apply to every request. |
| 5 — Operations | An administrator can see, act, restart, and move to another machine. |
| 6 — Knowledge | Company knowledge is reachable and permission-aware. |
| 7 — People | Employees and teams have governed access. |
| 8 — Commercial | It installs, licenses, updates and ships. |
| 9 — Intelligence | It learns from evidence and improves recommendations. |

Phases 0–5 are the exoskeleton. Everything in 6–9 depends on it and nothing in it depends on them.

---

## 6. GATES

Gates are named for what they prove, not for what was built. Each is an acceptance event under the
operating contract §8, and each carries the reverse audit from §4.

| Gate | After | Proves | Level |
| --- | --- | --- | --- |
| **G1 Host Truth** | Phase 0 | The platform's account of the machine is accurate, bounded and evidenced. | L2 |
| **G2 Feasibility** | Phase 1 | It decides what it can run, with explanation and confidence, downloading no weights. | L1/L2 |
| **G3 Custody** | Phase 2 | It acquires safely, refuses unsafely, and recovers cleanly from interruption. | L2 |
| **G4 Exoskeleton** | Phase 3 | A governed request is answered by a locally served model, recorded as usage, with a second concurrent instance running and an unsafe third refused. | L3/L4 |
| **G5 Operability** | Phase 5 | It restarts and reconciles coherently; an administrator can see and act on everything. | L4 |
| **G6 Portability** | Phase 5 | Moved to a different machine, it revalidates artifacts, reuses what still fits, and re-acquires what does not. | L4 |
| **G7 Company Brain** | Phase 6 | Only authorized knowledge reaches the model, for a real user against a real source. | L4 |
| **G8 Product** | Phase 8 | A non-technical administrator installs it on a supported host and reaches working inference. | L4 |

**G6 is the gate the previous project never had**, and under the operating contract's
disposable-host discipline it is arguably the most valuable acceptance test in the project. Restart
on the same machine (G5) proves persistence. Only a different machine proves the architecture is
genuinely capability-based rather than accidentally fitted to one host.

---

## 7. WHAT CHANGED FROM ROADMAP V1, AND WHY

| # | V1 | AI Stack | Driver |
| --- | --- | --- | --- |
| 1 | Milestone 0 defines ~20 contracts, builds nothing runnable | Kernel folded into the first host stage | T1, C2 |
| 2 | Acquisition (M3) precedes capacity assessment (M4) | Feasibility gates acquisition | T6, constitution §20 |
| 3 | `ModelRequirement` single contract in M4, needed in M3 | Split: storage requirement with the supply chain, runtime requirement with capacity | T6 |
| 4 | No selection or ranking stage | `ModelSelectionResult` stage; llmfit as first adapter with deterministic fallback | Operating contract §17 |
| 5 | Gateway at M6, after inference at M5 | Minimal gateway ships with first inference | T3, constitution §98 |
| 6 | `UsageEvent` at Stage 6.3 | In the kernel, emitted from the first request, with cohort fields | Constitution §120 |
| 7 | Secrets, egress, health, audit, policy unplaced | Standing obligation checklist, seams at first need | T2 |
| 8 | Explanation and confidence per subsystem | One `Decision` envelope in the kernel | Constitution §5.5, §27 |
| 9 | `HostFingerprint` referenced, never produced | Produced by the first host stage | T8 |
| 10 | Reconciliation is both Stage 7.3 and a cross-cutting rule | Per-stage obligation; 7.3 becomes orchestration and the restart gate | T2, I7 |
| 11 | Dev bootstrap harness later "converted" to installer | One bootstrapper, two front ends | Operating contract §14, §15 |
| 12 | Exoskeleton proves one inference instance | Proves two concurrent plus a safe refusal | Constitution §13 |
| 13 | No eviction or make-room flow | Explicit administrator-approved stop-to-make-room | Constitution §13 |
| 14 | No portability gate | G6 | Operating contract §1, §14 |
| 15 | Proof of work unspecified per stage | Four-part evidence, negative proof mandatory | T4, C2 |

---

## 8. OPEN DECISIONS

Under the operating contract §11 these are Daniel's, not Cursor's. The first blocks the first stage.

**D1 — Language and process topology. Blocking.**
The model ecosystem — Hugging Face, vLLM, llmfit — is Python, and the previous project validated
Python for the control plane. The unresolved half is the bootstrapper, which wants to be one small
static binary per OS and architecture so a non-technical administrator runs a single file.

- *A: all Python, frozen bootstrapper.* One language and toolchain; heavier, slower-starting
  installer.
- *B: Go or Rust bootstrapper, Python control plane.* Best install experience; two toolchains.
- *C: all Go with subprocess runtimes.* Best distribution; fights the ecosystem constantly.

Recommended: **B**, with the bootstrapper behind a contract so A remains reachable. Charter §8 warns
against hard-coding this into core either way. Also to settle: monolith-with-seams versus separate
services for the control plane. Recommended: **monolith with enforced internal boundaries**, since
the exoskeleton needs no process isolation and the seams preserve the option.

**D2 — Which external provider backs the Admin Agent before local inference exists.**
Affects the installer experience and the first outbound egress declaration.

**D3 — Are embeddings local from day one?**
The exoskeleton gate assumes two concurrent instances, one an embedding model. If embeddings are
deferred, the gate's second instance is a second LLM and the knowledge phase inherits the
concurrency risk instead.

**D4 — First knowledge connector: managed storage or SharePoint?**
Managed storage is faster to prove; SharePoint proves the harder permission-mapping problem earlier.

**D5 — llmfit integration timing.**
Available from the selection stage as the first evaluation provider, or deferred with the
deterministic rule shipping alone first.

**D6 — Reference hardware for gates.**
Which host class G4 and G6 must pass on, and which second host G6 moves to.
