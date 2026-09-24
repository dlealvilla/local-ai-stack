# CURRENT LEAD DEVELOPER INSTRUCTION

**Instruction ID:** `MACHI-OLLAMA-CHUNK-02-FREEZE-007`  
**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Chunk:** 2 of 6 — FINAL FREEZE PATCH  
**Starting HEAD:** `31dca110271805545cc2ba60c9095c25f357b27d`  
**Physical server:** NO  
**Model pull/load/inference:** FORBIDDEN  
**Chunk 3:** FORBIDDEN

Read:
- `control/OLLAMA-CHUNK-02-FREEZE-REVIEW.md`
- `control/CORE-VS-COMMODITY-POLICY.md`
- current source/tests

The prior correction PASS is accepted. Fix only the remaining freeze blockers.

# 1. Pre-stage SAFE authorization

Before creating the owned staging directory or marker:
- read the source archive's current byte size;
- validate the recipe-declared artifact size is coherent with the candidate;
- require SAFE capacity to cover the initial bounded staging requirement;
- if it cannot fit, refuse with INSUFFICIENT_CAPACITY and create no staging state.

During copy/hash:
- enforce a maximum authorized byte count;
- abort if source bytes exceed the expected/authorized size;
- require final staged byte count to match the frozen recipe artifact size;
- require SHA-256 to match as already implemented.

Do not trust source stat alone against a file that can change during copy.

Add tests:
- SAFE below source artifact size -> no staging directory/file created;
- source grows or copy exceeds expected length -> bounded refusal;
- artifact length mismatch with otherwise fixture-valid metadata -> refusal.

# 2. Durable promotion ordering

After same-filesystem `generation.replace(final)`:
- fsync `final.parent` immediately;
- only after that begin registry/index transaction.

Add a bounded injectable/test seam proving order:
`rename -> parent fsync -> registry update`.

A failure of parent fsync must not report successful installation or registered state.

# 3. Invalid UTF-8 registry is corrupt registry

Catch invalid encoding as registry corruption alongside invalid JSON/wrong shape.

Tests:
- invalid UTF-8 registry -> typed VERIFICATION_FAILED + RECONCILE_REQUIRED;
- inspection reports corrupt without exception;
- bytes remain unchanged.

# 4. Deadlock-safe decompressor completion

Replace blocking stderr-drain-before-wait behavior with a standard bounded
completion mechanism that cannot bypass timeout.

Requirements:
- timeout is authoritative;
- child is killed and reaped on timeout;
- diagnostics remain bounded;
- non-zero exit remains typed failure;
- no shell;
- no unbounded in-memory output;
- tar stream remains streaming.

A small adapter-local helper is fine. Do not add a dependency or generic process framework.

Tests:
- successful zstd path;
- non-zero exit with diagnostic;
- child that emits valid/partial stream then hangs with stderr open -> bounded typed failure, not hang.

# 5. Positive ownership proof for reconciliation

Replace substring matching of manifest ownership with parsed proof:
- JSON object;
- `owner == "machi"`;
- `owned is true`;
- manifest environment_id equals containing directory name.

Malformed, spoofed-string, wrong-owner, or mismatched-id manifests are not
positively owned and must not be returned by `unregistered_owned_generations`.

No destructive cleanup is added.

# 6. Gates

Run:
- targeted Ollama/Foundation tests;
- all new freeze tests;
- full tests/machi;
- architecture tests;
- ruff;
- strict mypy;
- clean wheel;
- isolated wheel verification ending `verify_ok`.

Then push exact clean HEAD to `origin/automation/ollama-macropath` and prove
local == origin. Do not move recovery checkpoint. Do not begin Chunk 3.

# 7. Paste-back

==================== BEGIN PASTE BACK — OLLAMA CHUNK 2 FREEZE ====================

A. STATUS  
B. Starting/final SHA  
C. Pre-stage SAFE authorization and bounded copy  
D. Artifact length + digest verification  
E. Promotion durability ordering  
F. Invalid-UTF8 registry behavior  
G. Deadlock-safe decompressor timeout behavior  
H. Positive ownership-proof behavior  
I. Tests/gates  
J. Wheel build ID/SHA256  
K. Isolated verify_ok  
L. Local/origin equality  
M. Exact Chunk-2 support claim  
N. Final status

End exactly:
`STOP — OLLAMA CHUNK 2 FREEZE PATCH COMPLETE. WAIT FOR LEAD REVIEW.`

or typed FAIL / DECISION_REQUIRED.

==================== END PASTE BACK — OLLAMA CHUNK 2 FREEZE ====================

Do not begin Chunk 3.
