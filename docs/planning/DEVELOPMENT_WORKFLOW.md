# AI DEPLOYMENT PROJECT — WAYS OF WORKING

**Status:** Authoritative operating contract
**Scope:** How Cursor, ChatGPT and Daniel work together
**This is not a product architecture document.** For architecture see
[`docs/source/COMPANY_BRAIN_PLATFORM.md`](source/COMPANY_BRAIN_PLATFORM.md) and
[`docs/COMPANY_BRAIN_TECHNICAL_ROADMAP_V2.md`](COMPANY_BRAIN_TECHNICAL_ROADMAP_V2.md).

---

## 1. PURPOSE

The project is developed primarily on remote servers through Cursor over SSH.

Servers are disposable. The physical server may change from day to day.

Development must therefore assume:

- today's server may disappear;
- tomorrow's CPU may differ;
- tomorrow's RAM may differ;
- tomorrow's NVIDIA GPU model and VRAM may differ;
- storage volume, provider or capacity may differ;
- local caches may disappear;
- installed runtimes may disappear;
- downloaded models may disappear.

Accepted source code must never depend on a particular development server continuing to exist.

The product itself is designed around the same principle:

> A supported server should be able to receive the product and become operational with minimal intervention.

The current validated reference implementation may be NVIDIA/Linux, but:

> Reference implementation != architectural dependency.

Core interfaces must remain capable of later supporting AMD/ROCm, Intel, Apple Silicon/Metal/unified
memory, CPU-only execution, and additional runtimes and executors through appropriate adapters.

---

## 2. PRIMARY DEVELOPMENT LOOP

The normal loop is:

```text
Daniel / ChatGPT
→ decide next bounded objective
→ ChatGPT writes Cursor instruction
→ Daniel pastes instruction into Cursor
→ Cursor executes on remote server
→ Cursor returns structured PASTE BACK
→ Daniel pastes PASTE BACK into ChatGPT
→ ChatGPT reviews evidence
→ approve / reject / request bounded correction
→ next objective
```

Cursor must not silently proceed into the next module after satisfying the current task.

Every instruction ends with an explicit STOP boundary.

---

## 3. EXOSKELETON-FIRST RULE

Default every implementation to the MINIMUM functionality required for the next module or
end-to-end product workflow to function.

Before implementation, the decision process is:

### Minimum / Exoskeleton

What is the smallest safe implementation that allows the next vertical capability to work?

**This is the DEFAULT.**

### Rabbit-hole add-ons

Identify optional sophistication such as: optimization; additional abstraction; advanced recovery;
benchmarking; predictive behaviour; generalized frameworks; extra platforms; policy engines;
elaborate UI; broad provider support; performance tuning.

These are NOT included by default. Daniel explicitly decides whether any rabbit-hole add-on should
be included. If Daniel does not request it: **DEFER IT.**

Standing question:

> Does the platform need this to complete the next end-to-end customer workflow?

If NO: defer it. If YES: implement the smallest safe version.

---

## 4. ARCHITECTURAL RULE

**Core owns concepts. Adapters own implementations.**

Core concepts include:

- HostCapabilityProfile
- CapacityEnvelope
- ModelRequirement
- FeasibilityResult
- ModelEvaluationEvidence
- ModelSelectionResult
- Model acquisition intent
- Inference Instance
- lifecycle state
- resource reservations

Adapters may own:

- NVIDIA/CUDA, AMD/ROCm, Intel accelerator behaviour, Apple Metal/MLX
- vLLM, llama.cpp, MLX
- Docker, Podman, native process execution
- model registries, transfer providers
- llmfit and future external intelligence providers

Do not introduce an adapter merely for symmetry. Add an interface only where it protects a genuine
replaceability boundary.

---

## 5. SERVER-FIRST / DISPOSABLE-HOST DISCIPLINE

The remote server is an execution environment, not the source of truth. The server may be destroyed
at any time.

### Accepted work

Accepted source belongs in GitHub.

### Unreviewed unique work

Unique uncommitted work must NOT exist only on a server working tree, `/workspace`, a temporary
filesystem, or a local Cursor session.

Before shutdown, server replacement, or risky work, unreviewed unique work must be made
independently recoverable. Preferred methods, in order:

1. **Accepted work** — commit and push to the active development branch.
2. **Unreviewed work** — dedicated GitHub WIP/backup branch.
3. **Optional patch/checkpoint** — useful for recovery, but not a substitute for remote Git
   persistence.

A server should eventually contain nothing unique that the project cannot recover.

---

## 6. GIT AUTHORITY

GitHub is authoritative for accepted source.

Current normal pattern:

| Branch | Meaning |
| --- | --- |
| `main` | stable earlier baseline |
| `phase9` | active accepted Phase-9 development branch |
| `backup/<bounded-work>-pending-review` | preserved unreviewed work |

Backup branches preserve unreviewed work, do NOT imply acceptance, and must not be merged into the
active branch without review.

Do not force-push accepted history. Do not rewrite stable history casually.

---

## 7. BOUNDED CHANGE DISCIPLINE

Every Cursor task should have: an authoritative predecessor; one narrow objective; explicit scope;
explicit exclusions; an acceptance level; test expectations; and a STOP boundary.

Normal sequence:

1. inspect existing seam;
2. confirm predecessor;
3. run baseline/focused tests where useful;
4. implement smallest change;
5. run focused tests;
6. run relevant regressions;
7. run real-host acceptance if required;
8. report PASTE BACK;
9. STOP;
10. commit only after approval unless the instruction explicitly authorizes commit.

Do not opportunistically fix adjacent issues. Record adjacent problems instead.

---

## 8. ACCEPTANCE LEVELS

### Level 1 — Unit / Contract

For contracts, normalization and pure logic. Requires focused tests, relevant regression tests, and
no unnecessary real-host operation.

### Level 2 — Real Host

Level 1 plus execution on the actual remote Linux/server environment, with real
hardware/runtime/environment evidence where relevant.

### Level 3 — Live Inference

Requires a real compatible model, a real runtime, a real inference request, relevant GPU/resource
state, and a clean stop.

### Level 4 — Integrated Stack

For major product milestones. May include control plane, gateway, ResourceManager, inference
instances, concurrency, health, and clean final state.

**Use the lowest acceptance level sufficient to prove the current contract.**

---

## 9. START LINK / END LINK TOKENS

Every accepted bounded development step should be linkable to its predecessor and successor.

At the start of a task, record `PREDECESSOR` — normally an accepted Git commit SHA, or the previous
checkpoint token where relevant.

At completion, create an END LINK / checkpoint token identifying at minimum:

- task
- predecessor commit
- resulting commit or WIP state
- phase
- acceptance level
- important evidence
- next action

The completion token becomes part of the evidence chain for the next task.

Do not depend on old server-local checkpoint files as the only evidence source. Git history is
authoritative for accepted source; checkpoint/link tokens provide engineering traceability.

When old checkpoint files disappear with a server, do NOT recreate the entire historical chain
unless genuinely required. Resume the evidence chain from the current authoritative Git state.

---

## 10. PASTE BACK CONTRACT

Cursor must finish each bounded task with a compact structured PASTE BACK using prominent
delimiters:

```text
# ================================================================================
# =========================== PASTE BACK START ===================================
# ================================================================================

TASK:
STATE:                 PASS | FAIL | DECISION_REQUIRED
PHASE:
STEP:
ACCEPTANCE_LEVEL:
PREDECESSOR:
CURRENT_COMMIT:
CHANGES:
EVIDENCE:
BEHAVIOR:
TESTS:
SCOPE:
GIT:
CHECKPOINT:
QUESTIONS / DECISIONS:
NEXT:

# ================================================================================
# ============================ PASTE BACK END ====================================
# ================================================================================
```

The exact fields may vary by task. The PASTE BACK should contain decision-relevant evidence, not a
long narrative of every command executed.

---

## 11. DECISION_REQUIRED RULE

Cursor should NOT stop for trivial implementation choices.

Cursor SHOULD stop for:

- materially different architecture choices;
- scope expansion;
- invariant changes;
- new product behaviour;
- destructive or expensive action not already authorized;
- evidence contradicting the requested contract;
- need to modify another subsystem outside the approved scope;
- a true business or product decision;
- safety ambiguity that could corrupt state.

Do not ask Daniel to decide naming, formatting, local refactors or equivalent low-level
implementation choices unless they materially affect architecture.

---

## 12. INTERRUPTIONS / EXTERNAL FAILURES

Cursor/provider failures, SSH drops and temporary model-provider errors are not automatically
product failures.

After interruption, DO NOT blindly restart the task. First inspect:

Git HEAD; origin branch state; working tree; active worker; active probe; active transfer/download;
storage lock; staging files; inventory; runtime processes; GPU state; ports; ResourceManager state.

Then resume from the last safely persisted boundary.

Never start a duplicate expensive probe or download without confirming another is not already
running.

---

## 13. BACKGROUND WORK

Do not rely on opaque background work as the normal development model.

If Cursor delegates work:

- current activity must remain inspectable;
- expensive probes and downloads must have visible state;
- source work must remain recoverable;
- do not start duplicate workers;
- STOP boundaries still apply.

If an external AI or provider error interrupts a worker, reconcile real host state before resuming.

---

## 14. FRESH-SERVER STARTUP PROTOCOL

At the start of a new development day, assume the server may be completely different. Do not assume
yesterday's GPU, VRAM, RAM, CPU, volume, model, cache or runtime installation.

Minimum startup sequence:

1. connect to fresh server;
2. obtain canonical source from GitHub;
3. checkout/fetch active development branch;
4. verify expected milestone/tag/commit;
5. run product-owned preparation: `./ai prepare`;
6. dynamically detect OS, architecture, CPU, RAM, accelerator, accelerator memory,
   driver/runtime capability, storage identity;
7. provision or reuse required platform-managed tools;
8. run bounded readiness/smoke tests;
9. verify no stale platform state;
10. recompute capacity for THIS host;
11. discover existing models/artifacts if storage persisted;
12. reevaluate artifacts against THIS host;
13. reuse compatible artifacts;
14. reacquire or select if missing or unsuitable;
15. resume development at the recorded NEXT step.

The startup process must become progressively more product-owned and plug-and-play.

---

## 15. PLUG-AND-PLAY PRODUCT PRINCIPLE

The product maturity target is:

```text
fresh supported server
→ product available
→ one product-owned command
→ detect host
→ provision required dependencies
→ characterize capacity
→ inspect model candidates
→ evaluate feasibility
→ select appropriate model
→ safely acquire/reuse model
→ start runtime
→ validate health
→ expose inference endpoint
```

Current development should continuously move toward this vertical path. The development process
itself should test this portability by regularly using replacement servers.

---

## 16. CAPACITY / MODEL FLOW

Preserve this ordering:

```text
fresh server
→ prepare/detect host
→ characterize safe CPU/RAM/accelerator/storage
→ CapacityEnvelope
→ online model catalogue metadata
→ ModelRequirement
→ feasibility
→ model evaluation/ranking
→ selection
→ acquisition
→ runtime/inference
```

### HOST storage characterization

Understands what the machine can safely offer BEFORE model selection. Contributes to
CapacityEnvelope and model feasibility.

### TRANSACTION storage characterization

Proves a specific mutation or acquisition is safe at commit time. It is NOT HOST capacity and must
never be promoted into a field that claims an independently characterized host ceiling.

TRANSACTION verification complements HOST characterization; it does not replace it.

---

## 17. MODEL INTELLIGENCE

llmfit is currently the first model-evaluation provider. It is an adapter, not core authority.

Platform-owned capacity and C5 feasibility remain authoritative.

llmfit may contribute fit, quality, speed, context and ranking evidence. llmfit cannot override an
unsupported C5 result.

If llmfit is unavailable or unusable, the platform may fall back to the simple closest-safe-primary-
memory selection rule.

Future providers must be replaceable without redesigning the selector core.

---

## 18. RESOURCE / MODEL REUSE

Never redownload or rebuild blindly. Use:

```text
check → reuse valid → repair/provision missing → verify → continue
```

This applies to runtimes, tools, models, model revisions, capacity evidence where valid, and
platform state.

A persisted model is reusable only if it remains compatible with the CURRENT host.
**Persistence does not imply suitability.**

---

## 19. END-OF-DAY SHUTDOWN PROTOCOL

Before terminating or discarding a server:

### Source

Confirm accepted work is committed; pushed to GitHub; `HEAD == origin` active branch; working tree
clean OR all unreviewed work remotely backed up; no unique work only on the server.

### Milestone

Record current commit; current phase/step; checkpoint/end-link token; exact NEXT action; useful
acceptance evidence; known deferred issues. Use a Git tag for important end-of-day milestones where
appropriate.

### Runtime cleanup

Confirm: no active development worker mutating product state; no active storage probe; no active
download; storage lock free; staging clean; no incomplete artifact; inference stopped unless
intentionally retained; GPU has no unexpected workload; ResourceManager has no stale
workload/reservation; relevant ports closed.

### Preserve useful state

Do NOT unnecessarily delete valid models, managed runtimes, durable capacity evidence, checkpoints,
or caches that can safely accelerate tomorrow.

### Flush

After all writes are complete, sync the filesystem as appropriate. Then:

```text
SAFE_TO_STOP_SERVER = YES
```

Only then should the pod or server be terminated.

---

## 20. END-OF-DAY / NEXT-DAY LINK

Every shutdown checkpoint must explicitly record `NEXT`.

The next session begins by reading and verifying: the current Git milestone; the previous
END/checkpoint token; the previous NEXT; and current host capabilities.

The new server's host facts replace yesterday's host facts.

**Product and architecture decisions persist. Hardware assumptions do not.**

---

## 21. SECURITY / DESTRUCTIVE ACTIONS

Do not:

- delete a model;
- destroy checkpoints;
- rewrite Git history;
- remove persistent state;
- kill unrelated processes;
- overwrite evidence;
- force push;
- weaken admission;
- disable safety checks;

unless explicitly authorized or required.
