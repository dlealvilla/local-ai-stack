# CURRENT LEAD DEVELOPER INSTRUCTION

**Instruction ID:** `MACHI-OLLAMA-CHUNK-02-CORRECTION-006`  
**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Chunk:** 2 of 6 — SURGICAL CORRECTION  
**Starting canonical HEAD:** `a71c78f46fc70265167d915a367e43105441b6c4`  
**Physical server:** NO  
**Model pull/load/inference:** FORBIDDEN  
**Chunk 3:** FORBIDDEN

Read:
- `control/OLLAMA-CHUNK-02-LEAD-FINAL-REVIEW.md`
- `control/CORE-VS-COMMODITY-POLICY.md`
- current source/tests/docs

# 1. Preserve accepted architecture

Do not redesign:
- explicit SAFE capacity authority;
- two-pass stream preflight/extraction;
- immutable owned generations;
- promoted-unregistered reconcile semantics;
- qualification-stable content identity;
- provisional SystemZstdDecompressor adapter;
- Core-vs-Commodity / Product Vision Alignment governance.

This is a correctness patch only.

# 2. Separate per-member and aggregate archive limits

Current bug:
`_preflight` compares aggregate `declared` bytes with `_MAX_MEMBER`.

Required:
- retain an explicit per-member ceiling only for individual members;
- aggregate declared bytes are governed by SAFE provisioning capacity, not the
  per-member ceiling;
- calculate projected peak before extraction using:
  staged compressed bytes
  + aggregate declared extraction bytes
  + bounded generated manifest/config metadata
  + projected registry transaction temp bytes;
- refuse only when that peak exceeds explicit SAFE capacity or another
  separately named archive-wide security bound that is justified and not
  confused with the per-member bound.

If adding an archive-wide anti-bomb ceiling beyond SAFE capacity is considered,
apply the Industry Solution Selection / Product Vision rule first. Do not invent
one silently.

Tests must prove, without allocating multi-GiB payloads:
- two individually valid members whose aggregate exceeds 2 GiB are not refused
  merely because aggregate > per-member ceiling;
- the same metadata is refused when SAFE peak does not cover it;
- one individual member over the per-member ceiling is refused.

Factor pure accounting/member-validation helpers if useful.

# 3. Count registry transaction bytes truthfully

Before extraction/promotion, compute the projected registry update payload for
this environment id.

Peak accounting must include the additional temporary registry bytes created by
the atomic update.

The existing bounded metadata allowance may cover only bounded generated
manifest/config transaction metadata whose maximum is genuinely controlled.

Do not assume registry.json is <= 64 KiB unless a separate accepted bound exists.

Add a test with a registry payload larger than the internal metadata allowance,
without requiring large files, and prove SAFE accounting includes the projected
temp bytes.

# 4. Require successful decompressor completion

For zstd streams:
- wait for the child process;
- non-zero exit is a typed provisioning failure;
- capture bounded stderr for diagnostics;
- no shell;
- ensure the process is reaped on success/failure/parse exception.

Add a fake/injected decompressor process case that emits enough tar bytes to
exercise parsing but exits non-zero; install/preflight must fail.

# 5. Malformed registry must be typed, not crash or become empty

Do not treat malformed registry JSON as an empty registry.

Required behavior:
- provisioning encountering corrupt registry state returns a typed
  verification/reconcile refusal;
- no new registry replaces the corrupted evidence automatically;
- existing owned generations remain untouched;
- reconciliation inspection either returns typed corrupt-registry evidence or
  otherwise exposes the condition without an uncaught exception.

Add malformed/wrong-shape registry tests.

# 6. Gates

Run:
- targeted Ollama/Foundation tests;
- new aggregate-vs-member accounting tests;
- registry-size peak test;
- decompressor non-zero test;
- corrupt-registry tests;
- full tests/machi;
- architecture tests;
- ruff;
- strict mypy;
- clean wheel;
- isolated-wheel verification ending `verify_ok`.

Then:
- push exact clean final HEAD to `origin/automation/ollama-macropath`;
- prove local == origin;
- do not move recovery checkpoint;
- do not begin Chunk 3.

# 7. Mandatory paste-back

==================== BEGIN PASTE BACK — OLLAMA CHUNK 2 CORRECTION ====================

A. STATUS  
B. Starting/final SHA  
C. Aggregate-vs-member bug before/after  
D. Exact peak-storage formula after correction  
E. Registry transaction byte accounting  
F. Decompressor exit-status handling  
G. Corrupt-registry behavior  
H. Tests/gates  
I. Wheel build ID/SHA256  
J. Isolated verify_ok  
K. Debts changed  
L. Local/origin equality  
M. Exact support claim  
N. Final status

End:
`STOP — OLLAMA CHUNK 2 CORRECTION COMPLETE. WAIT FOR LEAD REVIEW.`

or typed FAIL / DECISION_REQUIRED.

==================== END PASTE BACK — OLLAMA CHUNK 2 CORRECTION ====================

Do not begin Chunk 3.
