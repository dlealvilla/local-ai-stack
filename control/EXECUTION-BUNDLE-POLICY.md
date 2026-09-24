# Lead → Cursor Execution Bundle Policy

**Status:** ACTIVE  
**Applies to:** future Machi/Kultrun implementation instructions  
**Purpose:** increase development velocity without weakening architecture,
evidence, or decision discipline.

## 1. Default work-package size

Future Cursor instructions should normally cover a **small bundle of adjacent
microlayers**, rather than one tiny process or one function at a time.

A normal bundle may include roughly:
- 3–6 closely related implementation slices;
- their contracts/adapters/orchestration;
- local tests and regression tests;
- documentation/evidence updates;
- package/build/verification;
- and, when appropriate, one bounded physical acceptance step.

This is guidance, not a numeric quota. Keep one coherent architectural goal per
bundle. Do not combine unrelated product subsystems merely to make the prompt
larger.

## 2. More scope means more instruction detail, not less

A broader bundle MUST retain or increase specification depth.

Every bundle should explicitly state:
- starting authoritative SHA/checkpoint;
- product goal and exact bounded scope;
- governing Product Vision and architecture principles;
- core vs commodity classification where relevant;
- provider/authority boundaries;
- contracts and invariants to preserve;
- ordered implementation slices;
- forbidden scope;
- critical decision gates;
- expected failure/refusal behavior;
- privacy/telemetry/evidence requirements;
- compatibility/regression requirements;
- local and physical acceptance requirements;
- exact package/build gates;
- mandatory structured paste-back;
- STOP conditions.

Do not replace detailed engineering constraints with vague goals just because a
bundle spans several microlayers.

## 3. Decisions already made are embedded as constraints

Accepted product, architecture and policy decisions should be copied into the
instruction as binding constraints, not repeatedly reopened.

Examples include:
- Core-vs-Commodity / Reuse the Industry; Own the Product;
- Product Vision Alignment;
- one ResourceManager global resource authority;
- provider-neutral core contracts;
- native/vLLM vs Ollama authority boundaries;
- separate model catalogs by macropath where accepted;
- customer content/privacy rules;
- ownership and evidence rules;
- current provider set and physical-lab safety rules.

Cursor should implement inside these boundaries autonomously.

## 4. Critical decision gates remain mandatory

Broader bundles do NOT authorize Cursor to cross a material decision silently.

STOP and return a decision package when work discovers a choice that:
- changes Product Vision;
- changes a core ontology/authority boundary;
- introduces meaningful lock-in;
- adds a mandatory non-replaceable dependency;
- changes privacy/security/customer-data posture;
- materially changes licensing/commercial direction;
- adds a new provider/platform choice covered by Provider Selection Gate;
- would invalidate accepted native or other macropath behavior;
- has two or more credible materially different solutions near the product core.

Use the existing Industry Solution Selection Gate / Provider Selection Gate /
Product Vision Alignment rules.

For bounded implementation details inside accepted architecture, Cursor should
choose the best-supported option and continue.

## 5. Bounded misses are corrected in the next package

Lead review remains mandatory after each package.

A small issue discovered during review does not automatically require a new
single-issue micro-prompt.

If the issue:
- does not make the current checkpoint unsafe to preserve;
- does not invalidate evidence already claimed;
- does not cross a core decision boundary; and
- can safely be fixed before the next affected acceptance step,

record it as **carry-forward correction** and include it near the start of the
next broader package.

Safety, authority, identity, persistence, privacy, destructive-operation, or
evidence-integrity defects that make the checkpoint unsafe still block and may
require an immediate correction.

## 6. Conditional continuation inside a bundle

A bundle may contain sequential slices with internal gates.

Example:
```text
local implementation
 -> local gates
 -> physical acceptance
 -> IF physical PASS: continue to next adjacent local slice
 -> IF terminal product failure / decision gate: STOP
```

This allows more work per Cursor run without bypassing empirical or architecture
gates.

## 7. Exoskeleton-first remains governing strategy

Broader instructions should accelerate completion of coherent end-to-end
capability, not deepen one subsystem indefinitely.

Prefer:
- complete useful vertical paths;
- prove them;
- then deepen where evidence requires.

Avoid:
- speculative abstraction;
- broad feature expansion;
- premature Stage-4 capabilities;
- UI work before stable backend contracts where dependencies say otherwise.

## 8. Paste-back discipline

Even for large bundles, paste-back must remain clearly bounded with:
- exact instruction/work/chain tokens;
- BEGIN/END delimiters;
- stable headings;
- exact final SHA/origin equality;
- build artifact identity/SHA;
- gates and physical evidence;
- decisions encountered;
- carry-forward debt/corrections;
- exact support claim;
- explicit STOP/status delimiter.

More work in one run requires a more complete paste-back, not a shorter one.
