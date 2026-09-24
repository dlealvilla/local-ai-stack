# CURRENT LEAD DEVELOPER INSTRUCTION

**Instruction ID:** `MACHI-OLLAMA-CHUNK-02-WATCHDOG-008`  
**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Chunk:** 2 of 6 — WATCHDOG MICRO-CORRECTION  
**Starting HEAD:** `919ab7e547967d6f552507fea617646410b3f0bd`  
**Physical server:** NO  
**Model pull/load/inference:** FORBIDDEN  
**Chunk 3:** FORBIDDEN

Read:
- `control/OLLAMA-CHUNK-02-WATCHDOG-REVIEW.md`
- `control/CORE-VS-COMMODITY-POLICY.md`
- current Ollama archive adapter/tests

The Chunk-2 architecture is frozen. Fix only the watchdog semantics and the
known pre-stage marker accounting.

# 1. Replace 5-second total decompression deadline with progress/inactivity semantics

Current behavior:
- timer starts when zstd starts;
- default 5 seconds;
- child is killed after 5 seconds even when it is making healthy progress.

Required:
- no arbitrary 5-second total wall-clock deadline for the full archive pass;
- track observable decompressed-stream progress;
- reset/update progress timestamp as bytes are consumed;
- kill/reap only when the child is alive and no stream progress has occurred for
  the configured inactivity interval;
- keep bounded concurrent stderr draining so stderr cannot fill its pipe;
- preserve non-zero-exit typed failure;
- preserve timeout/inactivity typed failure;
- no shell;
- no unbounded buffering.

Prefer the smallest adapter-local implementation.

If there is already an accepted generic process/watchdog helper in the repo that
fits without changing semantics, reuse it. Otherwise a bounded adapter-local
progress wrapper/watchdog is acceptable.

Do not add a new library/dependency without triggering the Industry Solution
Selection Gate.

Tests:
- a slow decoder that takes longer than the old 5-second total deadline but
  emits regular progress must PASS;
- a child that stops making progress with pipes open must be killed/refused in a
  bounded interval;
- non-zero exit still refuses;
- normal synthetic zstd path still passes.

Use short test intervals so the suite remains fast; do not literally wait >5
seconds in unit tests if a smaller configured inactivity interval can prove the
semantics.

# 2. Pre-stage known-byte accounting

Before staging creation, initial SAFE requirement must include:
- frozen artifact bytes;
- exact staging marker bytes that Machi immediately writes.

If SAFE is below that known requirement:
- refuse before creating staging state.

Do not attempt speculative filesystem metadata accounting.

Add boundary tests at:
- one byte below required;
- exactly required.

# 3. Preserve everything else

No changes to:
- archive identity;
- two-pass extraction;
- per-member vs aggregate limits;
- registry transaction accounting;
- promotion/fsync ordering;
- corrupt-index handling;
- ownership proof;
- Foundation identity;
- zstd provider choice/debt;
- governance/docs;
- AUTO state.

# 4. Gates

Run:
- targeted Ollama/Foundation tests;
- watchdog tests;
- pre-stage boundary tests;
- full tests/machi;
- architecture tests;
- ruff;
- strict mypy;
- clean wheel;
- isolated-wheel verification ending `verify_ok`.

Push exact clean HEAD to `origin/automation/ollama-macropath`, prove local ==
origin, and STOP. Do not begin Chunk 3.

# 5. Paste-back

==================== BEGIN PASTE BACK — OLLAMA CHUNK 2 WATCHDOG ====================

A. STATUS  
B. Starting/final SHA  
C. Old timeout semantics vs new inactivity semantics  
D. Progress observation mechanism  
E. Hung-process behavior  
F. stderr/non-zero-exit behavior  
G. Pre-stage known-byte formula/boundary tests  
H. Tests/gates  
I. Wheel build ID/SHA256  
J. Isolated verify_ok  
K. Local/origin equality  
L. Final Chunk-2 support claim  
M. Final status

End exactly:
`STOP — OLLAMA CHUNK 2 WATCHDOG CORRECTION COMPLETE. WAIT FOR LEAD REVIEW.`

or typed FAIL / DECISION_REQUIRED.

==================== END PASTE BACK — OLLAMA CHUNK 2 WATCHDOG ====================

Do not begin Chunk 3.
