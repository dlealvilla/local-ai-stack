# CURRENT LEAD DEVELOPER INSTRUCTION

**Instruction ID:** `MACHI-OLLAMA-CHUNK-02-FINAL-003`  
**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Chunk:** 2 of 6 — FINAL HARDENING  
**Mode:** BOUNDED LOCAL CORRECTION + PACKAGE + PUSH  
**Starting canonical HEAD:** `45b1734936164393c7434ddd09640c7c05e5fb7b`  
**Physical server:** NO  
**Model pull/load/inference:** FORBIDDEN  
**Chunk 3:** FORBIDDEN

Read:
- `control/OLLAMA-CHUNK-02-LEAD-REVIEW-2.md`
- `control/OLLAMA-CHUNK-01-DECISION.md`
- `control/RUNTIME-ARTIFACT-REGISTRY-VISION.md`
- current branch source/docs/tests

This is a narrow final closeout. Do not reopen accepted architecture.

# A. Peak SAFE storage truth

Current implementation may hold compressed artifact + decompressed tar + extracted generation concurrently, while `safe_bytes` only bounds extraction.

Fix the provisioning transaction so **all Machi-owned bytes created by the attempt are covered by explicit SAFE capacity**.

Preferred implementation:
1. caller supplies explicit `safe_bytes` from Capacity authority; missing authority refuses rather than falling back to an arbitrary 8 GiB authorization;
2. stage and verify the compressed artifact;
3. preflight the verified archive by streaming decompression directly into tar parsing without materializing a full decompressed tar file;
4. reopen the same verified compressed artifact and stream-decompress/extract in a second pass;
5. enforce the bound against:
   - staged compressed copy;
   - extracted bytes written;
   - config/manifest/staging overhead;
   - any other Machi-owned temporary bytes created by this transaction;
6. require enough safe headroom for the actual peak owned footprint.

If you retain a decompressed tar file, prove the bound covers its full simultaneous footprint too.

No `safe_bytes=None` path may authorize managed provisioning. An unresolved/missing Capacity input must return a typed refusal.

Add tests for:
- compressed artifact itself larger than safe allowance;
- archive declared payload + staged compressed bytes exceeding safe allowance;
- actual extracted bytes exceeding allowance;
- success when the full peak fits.

# B. Transactional promotion / registry consistency

Fix ordering around:
- generation-local manifest;
- final generation promotion;
- central `foundation/environments/registry.json`.

Requirements:
- no registry row may point at a generation that failed to promote;
- registry update must be atomic (temp file + replace or existing repository pattern);
- a failure after promotion must either safely roll back only the newly promoted positively owned generation or persist a typed reconcile state with proof; prefer bounded rollback for this increment;
- never delete a pre-existing generation;
- add injected failure tests for rename/promotion failure and registry-write/replace failure.

# C. Qualification-stable Foundation identity

Do not include ephemeral daemon port/address in model-qualification identity.

Refactor identity so:
- exact runtime recipe/version/content identity;
- provider mode where materially relevant;
- execution-environment fingerprint;
- cloud/local security mode or endpoint class where material

can invalidate qualification, but:
- a loopback port change alone does not.

Keep the actual endpoint on raw/operational evidence.

Add test:
same runtime/environment on two different loopback ports -> same qualification-relevant Foundation generation identity (or same explicit qualification identity basis).

# D. Verified-existing immutable runtime identity

A verified-existing substrate must establish an immutable observed executable identity before it can support reusable model qualification.

At minimum:
- hash the actual executable bytes when the provider observes it;
- store that executable/content SHA-256 as runtime identity/provenance;
- include it in qualification-material generation identity for verified-existing mode.

If the executable cannot be read/hashed:
- report the substrate as observed/unresolved or non-qualification-capable;
- do not mint qualification-reusable READY identity.

Do not compare executable SHA-256 to the release archive SHA-256.

Add tests for:
- same reported version, changed executable bytes -> different generation/qualification identity;
- missing/unreadable executable identity -> fail closed for qualification-capable READY.

# E. zstd prerequisite truth

The official Ollama v0.34.3 Linux archive requires zstd decompression.

Add explicit decompressor readiness:
- identify the configured decompressor implementation;
- preflight availability before provisioning;
- missing decompressor -> typed prerequisite/unavailable/block reason, not generic package-install failure;
- record provider/decompressor evidence where useful.

Add debt, if not already represented, that the current managed Ollama path depends on an external decompressor and final plug-and-play productization must manage or bundle an approved helper artifact under the future Runtime Artifact Registry / managed-prerequisite supply chain.

Do not install zstd with apt/dnf and do not build the registry here.

# F. Preserve accepted behavior

Do not change:
- Ollama v0.34.3 stable pin/checksum;
- verified-existing + managed-prefix provider strategy;
- loopback-only/cloud-off behavior;
- no global /usr/systemd mutation;
- artifact identity independent of delivery URL;
- common Foundation analytics vocabulary;
- AUTO still disabled;
- no model weights/load/inference;
- no physical server.

# G. Gates

Run:
- targeted Ollama/Foundation tests;
- new peak-storage tests;
- transaction failure-injection tests;
- identity/hash tests;
- zstd prerequisite tests;
- full tests/machi;
- architecture tests;
- ruff;
- strict mypy;
- clean wheel build;
- isolated-wheel verification ending `verify_ok`.

Then:
- clean final commit;
- push exact HEAD to `origin/automation/ollama-macropath`;
- verify local == origin;
- working tree clean except explicitly excluded proposal notes;
- do not move recovery checkpoint.

# H. Mandatory paste-back

==================== BEGIN PASTE BACK — OLLAMA CHUNK 2 FINAL ====================

A. STATUS  
B. Starting/final SHA  
C. Peak-storage design and exact accounting formula  
D. Evidence that missing Capacity cannot authorize provisioning  
E. Streaming/preflight implementation  
F. Transactional promotion/registry behavior  
G. Failure-injection evidence  
H. Foundation qualification identity before/after  
I. Verified-existing executable identity behavior  
J. zstd prerequisite behavior/debt  
K. Files changed  
L. Test/gate results  
M. Clean wheel build ID + SHA256  
N. Isolated `verify_ok`  
O. Debts retained/added  
P. Exact support claim  
Q. Origin/local equality  
R. Proposed Chunk-3 starting point  
S. Final status

End:

`STOP — OLLAMA CHUNK 2 FINAL HARDENING COMPLETE. WAIT FOR LEAD REVIEW.`

or typed FAIL/DECISION_REQUIRED equivalent.

==================== END PASTE BACK — OLLAMA CHUNK 2 FINAL ====================

Do not begin Chunk 3.
