# CURRENT LEAD DEVELOPER INSTRUCTION

**Instruction ID:** `MACHI-LEAD-ONBOARDING-STATUS-001`  
**Status:** READ-ONLY ONBOARDING / REPOSITORY-TRUTH ORIENTATION  
**Purpose:** Re-onboard the Lead Developer from current repository truth before selecting the next Company Brain workstream.

The previous bounded program is closed:

- Ollama macropath: `CLOSED_NVIDIA_STAGE1`
- Accepted final source: `2c12f00286d6e7d6d524baa7a7787099e476bf08`
- Recovery checkpoint: `checkpoint/ollama-nvidia-stage1-2026-09-24`

This instruction does **not** authorize implementation.

---

# 1. OBJECTIVE

Give the Lead Developer a complete, current, evidence-backed onboarding to Machi as it exists **now**.

Assume the Lead Developer has historical project context but may have stale or incomplete understanding after a chat transition.

Your job is to explain from repository truth:

1. where the project is;
2. what has actually been accepted;
3. what remains open;
4. how the architecture is organized;
5. how the roadmap is intended to progress;
6. how Daniel / Lead Developer / Cursor currently work together;
7. which files are authoritative for which questions;
8. which branches/checkpoints/evidence are current;
9. what the previous Ollama program changed and did not change;
10. what the next valid decision boundary is.

Do not merely summarize one file. Reconstruct the **working development system**.

---

# 2. HARD READ-ONLY BOUNDARY

This is an orientation task only.

Do **not**:

- edit product source;
- edit Machi architecture/roadmap/debt docs;
- create or switch to a new implementation branch for development;
- merge or promote branches;
- change checkpoints;
- modify tests;
- build a new product candidate;
- create/start/stop/terminate a RunPod or any physical acceptance host;
- run paid physical acceptance;
- download a new model;
- provision a runtime;
- start inference;
- retire debt;
- close an acceptance gate;
- begin the next workstream.

Normal read-only git/repository inspection is allowed.

The **only expected write** is publishing the final structured paste-back through the existing Machi GitHub handoff protocol.

If repository inspection itself reveals a contradiction that makes orientation impossible, report it. Do not repair it.

---

# 3. REPOSITORY TRUTH FIRST

Before writing the onboarding, inspect current repository truth.

At minimum establish:

- repository identity;
- current local branch/HEAD if available;
- relevant origin refs;
- current accepted implementation line;
- `machi` branch relationship to the accepted source;
- `automation/ollama-macropath` status;
- `control/machi-handoff` purpose and separation from product history;
- recovery/checkpoint branches;
- whether any newer commits supersede `2c12f002...`;
- clean/dirty working tree if operating from a workspace;
- whether untracked files contain non-authoritative proposals or unique work.

Do not infer authority from a branch name alone.

If repository truth differs from the control-branch state, call that out explicitly.

---

# 4. AUTHORITATIVE FILE MAP

Identify the current authoritative documents and explain **what question each one answers**.

Inspect at least:

- `.cursor/agents/machi-lead-developer.md`
- `.cursor/rules/machi.mdc`
- `.cursor/rules/machi-handoff.mdc`
- `docs/machi/MACHI_LEAD_DEVELOPER.md`
- `docs/machi/ARCHITECTURE.md`
- `docs/machi/ROADMAP.md`
- `docs/machi/CONTRACTS.md`
- `docs/machi/TELEMETRY.md`
- `docs/machi/KULTRUN.md`
- `docs/machi/README.md`
- `docs/STRATEGY.md`
- `docs/PRODUCT_VISION.md`
- `docs/DEBT.md`
- `docs/machi/ACCEPTANCE-LAB.md`
- current M5/M6/M7/M8/M9 notes and physical-evidence files;
- current Ollama Bundle 04–07 evidence/reviews where relevant;
- checkpoint JSON files that define the current evidence chain;
- the GitHub handoff control files.

For each, state whether it is:

- architecture authority;
- sequencing authority;
- strategy/product authority;
- operating/ways-of-working authority;
- evidence/history;
- debt/provisional register;
- current control-plane instruction;
- historical/stale/non-authoritative.

Explicitly identify stale headings, old status text, or documentation that has not caught up with the current accepted line.

Do not silently reconcile contradictions.

---

# 5. WAYS OF WORKING — RECONSTRUCT THE CURRENT CONTRACT

Explain the current development loop in practical terms.

Cover:

## Lead / Daniel / Cursor loop
How a task flows from Lead decision → GitHub control instruction → Cursor sync → repository inspection → bounded work → evidence → publish paste-back → Lead review → next decision.

## Repository truth
What must be inspected before coding.

## Bounded increments
How PREDECESSOR / OBJECTIVE / SCOPE / NON-GOALS / ACCEPTANCE / TESTS / STOP are used.

## Product-first instruction style
Explain the current expectation that Lead instructions define:

- customer/product capability;
- allowed functional scope;
- architectural invariants;
- physical/acceptance gates;
- forbidden shortcuts;
- evidence required;

while Cursor owns ordinary implementation detail unless a genuine product/architecture decision is encountered.

## Exoskeleton-first discipline
Explain how "minimum safe path to the next end-to-end capability" is used, and when adjacent microlayers are bundled rather than atomized.

## Provider Selection Gate
When it applies, what must be presented, and when Daniel must be asked.

## Industry Solution Selection Gate
If currently authoritative, explain when build-vs-integrate or competing mature solutions require Lead/product review.

## Acceptance levels / empirical discipline
Explain T0/T1/T2/T3/T5 and when physical evidence is mandatory.

## Disposable-host discipline
Source workspace vs acceptance server; immutable built artifact; no server-side source patching.

## RunPod ownership/cost discipline
Summarize current authoritative limits and what Cursor may autonomously manage.

## PASTE BACK
Explain what a good paste-back must contain and how exact PASS / FAIL / DECISION_REQUIRED / AWAITING_REAL_EVIDENCE-style states are used.

## GitHub handoff bridge
Explain:
- control branch is not product history;
- sync sequence;
- publish sequence;
- what Daniel has to trigger manually;
- what the Lead Developer should read after publication.

---

# 6. ARCHITECTURE ONBOARDING — BLOCK TREE

Present the complete current core architecture as a text tree:

```text
0 Kernel
├── ...
1 Install
├── ...
...
9 Serve
└── ...
```

For every Block 0–9 include:

- Block purpose;
- major Capabilities / Components;
- primary input;
- primary output;
- current implementation/acceptance status;
- important open debt/gates;
- what it explicitly does NOT own.

Keep provider-specific implementations below the generic capability rather than making the provider look like the architecture.

Also explain the critical authority chain:

```text
Discover
→ Steward
→ Capacity
→ Foundation
→ Model
→ Plan
→ Admit
→ Serve
```

and explain where Kernel / Install fit.

---

# 7. ROADMAP / STRATEGY ONBOARDING

Explain both levels without conflating them:

## Machi implementation roadmap
M0 → M9 and current completion status.

## Strategic stages
Explain the current Stage 1 / Stage 2 / Stage 3 / Stage 4 meaning from `docs/STRATEGY.md`.

Explain:

- what constitutes Stage-1 exit;
- what is still missing before Stage-1 can truthfully close;
- what the Runtime Artifact Registry workstream is and when it starts;
- what Stage-2 empirical infrastructure lab is for;
- when Gateway / identity / Knowledge / Admin UI belong;
- when Company Brain organisational intelligence belongs.

Do not promote deferred work merely because it is strategically interesting.

---

# 8. CURRENT STATE — WHAT JUST HAPPENED

Give a concise but precise account of the most recent accepted program:

**Ollama Stage-1 / Bundle 07**

Cover:

- what capability the macropath added;
- native-vLLM-primary / Ollama-fallback policy;
- one global ResourceManager ledger;
- separate model catalogs;
- real AUTO primary-selection evidence;
- safely induced real native provisioning failure;
- fresh Ollama Plan → Admit → Serve fallback chain;
- two physical Ollama model cases;
- context-bound negative case;
- RuntimeChoice concrete Foundation evidence;
- schema migration durability / K-03 retirement;
- exact accepted SHA/checkpoint;
- physical host used;
- cleanup/termination;
- what was NOT proved.

Preserve the support-claim nuance:

- native/vLLM full inference had prior accepted L40S evidence;
- Bundle 07 A40 proved native Foundation readiness/AUTO selection, not native model inference on that A40;
- Ollama physical Serve/fallback was proven on A40;
- AMD was not physically qualified in Bundle 07.

---

# 9. AMD MODEL — EXPLAIN THE CORRECT CURRENT ACCEPTANCE MODEL

Explicitly explain the post-Bundle-07 clarification.

Separate:

```text
HOST-OWNED
AMD GPU
kernel / amdgpu
device access
compatible OS / glibc
true irreducible host prerequisites

MACHI-OWNED
managed Python
pinned ROCm-compatible vLLM / PyTorch userspace
package/cache generation
verification
Foundation identity
```

Explain why "no prebuilt ROCm 7 image" is not itself an AMD product failure.

State the current status of `M-5-AMD-01`, the latest physical/preflight evidence, and how AMD should be treated relative to the mainline.

---

# 10. CURRENT OPEN ITEMS / DEBT THAT MATTER NOW

Do not dump the entire debt ledger.

Identify the open items that materially affect the **next one or two workstreams**, especially:

- `M-5-AMD-01`;
- `M-6-03`;
- `M-9-01`;
- `M-9-02`;
- relevant Ollama open items that remain future debt but do not reopen Stage-1 Ollama construction;
- any branch/promotion/integration debt;
- any stale-documentation issue that could mislead the Lead Developer.

For each state:

- what is missing;
- why it matters;
- whether it blocks Stage-1 closure;
- retirement condition;
- whether it belongs now or later.

---

# 11. NATIVE M6/M9 HISTORY — GUIDE THE LEAD THROUGH THE FAILURE CHAIN

Explain the native path history around the current gap:

- which model was acquired/stored for M6;
- why its previous compatibility classification was insufficient;
- the physical M9 failures;
- the tiny Llama head-dimension issue;
- how the Model qualification funnel was redesigned as a result;
- whether a real external candidate has now been empirically qualified under the redesigned identity;
- whether the native M9 request-inference proof has subsequently been closed;
- current `DeploymentWitness` status.

This section must distinguish historical failure evidence from current architecture.

---

# 12. WHERE WE ARE NOW

Give the Lead Developer a direct answer:

```text
PAST
what just closed

PRESENT
the exact active architectural/product gap

FUTURE
the next valid workstream after that gap
```

Use the preferred context layers:

For each of Past / Present / Future:

1. Block-level purpose;
2. Capability/Component;
3. simple-language explanation;
4. expected inputs;
5. expected outputs;
6. actual status / next action.

Then include a small handoff diagram:

```text
completed output
    ↓
current input/work
    ↓
next output/workstream
```

---

# 13. NEXT-WORKSTREAM GUIDANCE — DO NOT EXECUTE IT

Based on repository truth, tell the Lead Developer what you believe the **next valid bounded workstream** is.

This is advisory only.

For the recommended next workstream provide:

- product outcome;
- predecessor;
- relevant Block/Capability IDs;
- expected inputs;
- expected outputs;
- which open debt it should retire;
- whether local work is needed;
- whether a physical NVIDIA host is needed;
- whether the standing AMD preflight applies;
- whether a Provider Selection Gate is required;
- what would cause `DECISION_REQUIRED`;
- what must explicitly remain out of scope;
- what should happen immediately after it passes.

If there are two genuinely viable next workstreams with materially different product consequences, present the decision rather than choosing silently.

Do **not** start either workstream.

---

# 14. BRANCH / CHECKPOINT / PROMOTION GUIDANCE

Explain the current branch topology and its semantics.

Specifically answer:

- What is the latest accepted source SHA?
- Which branch points to it?
- What does `machi` currently point to?
- Is `machi` intentionally behind?
- Is there a documented promotion step still outstanding?
- Which checkpoint is the best recovery point?
- Which branches are historical, active, control-only, checkpoint-only, or candidate/integration?
- From which exact source should the next implementation branch start **if nothing changes before Lead review**?

Do not perform promotion.

---

# 15. FILE-READING GUIDE FOR THE LEAD DEVELOPER

Finish the onboarding with a practical reading order.

Example shape:

```text
If you need to understand...
├── product direction ........ read X
├── architecture ............. read Y
├── exact build sequence ..... read Z
├── current evidence ......... read ...
├── open debt ................ read ...
├── current instruction ...... read ...
└── historical rationale ..... read ...
```

Include the smallest set of files necessary to regain full context quickly and a deeper second-tier set for investigation.

---

# 16. CONTRADICTION / STALENESS AUDIT

Before finalizing, explicitly look for and list:

- stale "Next:" statements;
- branch names that no longer reflect current accepted work;
- old statuses in README/Lead Developer docs;
- roadmap text inconsistent with physical evidence;
- control-state text inconsistent with source docs;
- debt entries whose retirement/status differs elsewhere;
- support claims broader than physical evidence;
- untracked proposals that should not be treated as authority.

For each discrepancy state which source should currently win and why.

Do not fix any discrepancy in this task.

---

# 17. FINAL PASTE BACK FORMAT

Return one onboarding packet using this structure:

```text
# ================================================================================
# =========================== PASTE BACK START ===================================
# ================================================================================

A. EXECUTIVE TL;DR
B. REPOSITORY / BRANCH / HEAD TRUTH
C. AUTHORITATIVE FILE MAP
D. CURRENT WAYS OF WORKING
E. GITHUB HANDOFF PROTOCOL
F. FULL BLOCK → CAPABILITY → COMPONENT TREE
G. BLOCK STATUS TABLE (0–9)
H. AUTHORITY / DEPENDENCY FLOW
I. IMPLEMENTATION ROADMAP (M0→M9)
J. STRATEGIC ROADMAP (STAGES 1→4)
K. WHAT JUST HAPPENED — OLLAMA BUNDLE 07
L. AMD ACCEPTANCE MODEL
M. NATIVE M6/M9 FAILURE + REDESIGN HISTORY
N. CURRENT OPEN GATES / RELEVANT DEBT
O. WHERE WE ARE NOW — PAST / PRESENT / FUTURE
P. RECOMMENDED NEXT WORKSTREAM (ADVISORY ONLY)
Q. PROVIDER / SOLUTION DECISION STATUS FOR THAT NEXT WORKSTREAM
R. PHYSICAL ACCEPTANCE EXPECTATIONS
S. BRANCH / CHECKPOINT / PROMOTION GUIDANCE
T. CONTRADICTIONS / STALE DOCUMENTATION
U. LEAD DEVELOPER READING ORDER
V. EXACT QUESTIONS THE LEAD MUST DECIDE NEXT
W. CONFIDENCE / UNRESOLVED FACTS
X. EXACT STATUS
Y. STOP

# ================================================================================
# ============================ PASTE BACK END ====================================
# ================================================================================
```

Use text diagrams/trees where useful.

Be detailed enough that a fresh Lead Developer chat could operate from this packet without rediscovering the project.

Do not bury unresolved contradictions.

---

# 18. STATUS

The only successful terminal state for this instruction is:

`PASS_READ_ONLY_ONBOARDING_COMPLETE`

If a material repository contradiction prevents a reliable onboarding:

`DECISION_REQUIRED`

If required repository evidence is inaccessible:

`AWAITING_REPOSITORY_EVIDENCE`

---

# 19. PUBLISH / STOP

Publish the complete final paste-back through:

`python tools/machi_handoff.py publish-pasteback <path-to-complete-pasteback>`

Then STOP.

Do not execute the recommended next workstream.

# END INSTRUCTION
