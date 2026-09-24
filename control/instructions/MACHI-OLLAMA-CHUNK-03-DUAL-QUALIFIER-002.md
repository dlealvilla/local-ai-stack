# CURRENT LEAD DEVELOPER INSTRUCTION

**Instruction ID:** `MACHI-OLLAMA-CHUNK-03-DUAL-QUALIFIER-002`  
**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Chunk:** 3 of 6 — MODEL + SPECIALIST FEASIBILITY BRIDGE  
**Starting source:** `180a4e898c5fcd46ae54a6d1c8aa8acfe84c66e6`  
**Mode:** LOCAL IMPLEMENTATION / NO PHYSICAL SERVER  
**Model downloads:** FORBIDDEN  
**Real provider model load/inference:** FORBIDDEN in this increment  
**Chunk 4:** FORBIDDEN

Read first:
- `control/OLLAMA-CHUNK-03-DUAL-QUALIFIER-DECISION.md`
- `control/OLLAMA-CHUNK-03-QUALIFIER-BOUNDARY.md`
- `control/OLLAMA-CHUNK-02-CLOSED.md`
- `control/CORE-VS-COMMODITY-POLICY.md`
- authoritative Product Vision / Strategy / Machi Architecture / M6 / telemetry docs
- current native qualification / Plan / Admit implementation
- exact Ollama v0.34.3 API and scheduler source

# 1. Goal

Implement the **local control-plane and adapter seams** required for dual
qualification analytics without downloading or loading a real model.

At the end, a fixture Ollama candidate must be able to flow through:

```text
Ollama catalog fixture
 -> normalized Ollama candidate
 -> Machi shadow evaluation
 -> qualification/probe authorization seam
 -> fake Ollama specialist qualifier
 -> authoritative Ollama qualification evidence
 -> comparative analytics record
```

Real physical Ollama qualification is a later bounded acceptance increment.

# 2. Preserve separate model catalogs

Do NOT create a default Machi ModelArtifact -> Ollama model conversion flow.

Add provider-neutral or Ollama-adapter contracts only as needed to represent:
- an Ollama catalog candidate by name + digest + public metadata;
- normalized facts used by Machi shadow evaluation.

The Ollama digest is the immutable provider model identity for this macropath.
The name/tag is a reference/display name and must not be treated as immutable
proof.

Do not mutate Block-6 Model Warehouse semantics to pretend Ollama models are
warehouse artifacts.

If existing generic model contracts cannot represent a provider-owned candidate
without lying, add the smallest separate provider-candidate seam rather than
overloading `ModelArtifact`.

# 3. Ollama API adapter — fixture/local only

Implement a bounded provider adapter interface covering the v0.34.3 public
capabilities Chunk 3 needs:
- list local models (`/api/tags`);
- show model metadata (`/api/show`);
- inspect loaded models (`/api/ps`);
- qualification load/generate/unload operations as an interface, with fake/test
  implementation in this increment.

Do not start a daemon or make network calls in ordinary unit tests.
Do not expose Ollama private Go scheduler APIs to the Python/core domain.

Exact private scheduler algorithms remain provider-owned.

# 4. Machi shadow evaluator

Implement a **non-authoritative shadow evaluation** for Ollama candidates.

Requirements:
- consume normalized public Ollama facts only;
- consume current Machi CapacityEnvelope/current reservation truth;
- reuse generic Machi estimation/evaluation functions where their inputs are
  semantically valid;
- do NOT use `refine_vllm`;
- unknown provider facts remain unresolved;
- no guessed architecture/config values;
- no Ollama-private `PredictServerVRAM` reimplementation;
- shadow result cannot affect the authoritative Ollama outcome.

Define a small versioned contract for shadow result, with:
- candidate/provider identity;
- capacity evidence;
- policy version;
- fit state: FIT / NO_FIT / UNRESOLVED;
- estimated accelerator/host/storage bytes as Maybe values;
- typed reason/evidence/provenance.

# 5. Authoritative Ollama qualifier adapter

Implement an `EmpiricalQualifier`-compatible or equivalently bounded adapter
seam whose **provider result is authoritative for the Ollama macropath**.

For this local increment use fakes that model:
- provider FIT/load/inference PASS;
- provider NO_FIT/load refusal;
- provider host failure;
- digest mismatch;
- loaded model missing from /api/ps;
- real-token proof missing;
- unload failure recorded separately.

It must map provider results into durable Machi QualificationEvidence without
pretending Machi's shadow decision caused the result.

Provider evidence must preserve:
- Ollama model digest;
- Ollama version/Foundation generation;
- hardware/execution environment;
- context/concurrency;
- actual provider outcome;
- provider-reported `size_vram` as its own sourced metric;
- load/generation/token metrics when present.

If the current QualificationEvidence schema cannot cite provider-owned model
identity truthfully because it requires a Machi artifact id/revision, do NOT
stuff fake warehouse identifiers into it. Introduce the smallest backward-
compatible provider identity extension/version or companion evidence contract,
with migration/read compatibility for native vLLM evidence.

This is a schema-change gate inside the implementation:
- if two materially credible contract designs remain after repository inspection,
  STOP with `DECISION_REQUIRED_QUALIFICATION_IDENTITY_SCHEMA`;
- otherwise use the smallest backward-compatible design and explain it.

# 6. Probe Plan / ResourceManager

Reuse the accepted native qualification precedent.

First inspect whether current `probe=True` + normal Plan/ResourceRequest +
ResourceManager can truthfully authorize the Ollama qualification attempt.

Preferred behavior:
- one ResourceManager ledger;
- qualification purpose remains distinguishable in plan fingerprint/evidence;
- no prior DeployableModels qualification coverage required for a qualification
  probe;
- normal deployment path unchanged.

You MAY replace the boolean with a typed PlanPurpose only if it materially
improves correctness/inspectability and all native tests/evidence semantics
remain intact. Do not refactor merely for style.

Add regression tests proving native:
- normal plan still requires qualification;
- probe qualification still does not require prior coverage;
- ResourceManager accounting is unchanged;
- existing Serve authorization invariants remain unchanged.

# 7. Comparative analytics contract

Create a versioned local operational contract such as
`model.qualification_comparison/1`.

It must contain enough identity to compare the two evaluators over the same
case without customer content.

Required fields/categories:
- comparison identity;
- provider/macropath;
- provider version/Foundation generation;
- provider model digest + display name;
- normalized candidate id;
- capacity evidence id;
- hardware class/execution environment fingerprint;
- context/concurrency;
- Machi shadow policy/version + fit state;
- Machi estimated accelerator/host/storage bytes as Maybe;
- Machi typed reason;
- Ollama authoritative outcome/failure;
- Ollama reported size + size_vram as Maybe;
- load/generation/token metrics as Maybe;
- comparison classification:
  AGREE_FIT,
  AGREE_NO_FIT,
  MACHI_FALSE_NEGATIVE,
  MACHI_FALSE_POSITIVE,
  MACHI_UNRESOLVED;
- VRAM delta/ratio only when both operands have compatible semantics;
- metric availability/provenance.

Be conservative about VRAM comparison:
- Machi estimated required accelerator bytes vs Ollama `size_vram` may be
  analytically useful but they are not identical measurement semantics;
- mark the comparison as estimate-vs-runtime-reported, never
  estimate-vs-observed-peak.

No prompts, responses, filesystem paths, user identities, or model content.

# 8. Normalized analytics vocabulary

Reuse `MetricAvailability`:
- OBSERVED;
- DERIVED;
- ESTIMATED;
- HIDDEN_INTERNAL;
- NOT_EXPOSED;
- NOT_APPLICABLE;
- UNSUPPORTED;
- UNRESOLVED.

Where useful, factor a generic metric shape only if doing so does not force a
Foundation-specific ontology onto Model analytics.

Provider-native raw facts and normalized comparison facts remain separate.

# 9. Tests

At minimum prove:
1. Ollama catalog candidate identity is digest-based, not tag-based.
2. Separate Ollama catalog does not create Machi ModelArtifact records.
3. Shadow FIT + Ollama PASS -> AGREE_FIT.
4. Shadow NO_FIT + Ollama PASS -> MACHI_FALSE_NEGATIVE and Ollama still wins.
5. Shadow FIT + Ollama NO_FIT -> MACHI_FALSE_POSITIVE and Ollama still refuses.
6. Shadow UNRESOLVED + Ollama PASS/FAIL -> MACHI_UNRESOLVED.
7. Ollama digest mismatch refuses authoritative qualification.
8. /api/ps missing expected digest refuses authoritative qualification.
9. readiness/load without a real token does not PASS.
10. `size_vram` is labeled runtime-reported, not peak.
11. analytics contains no prompt/response/path content.
12. native qualification/plan/admit/serve tests remain green.
13. shadow evaluator cannot influence provider-authoritative result.
14. no vLLM-specific refine logic is imported into Ollama shadow adapter.
15. unknown model facts remain unresolved rather than guessed.

# 10. Documentation

Update product/architecture/M6/telemetry docs only where needed to state:
- catalog separation by macropath;
- dual evaluator rule;
- provider authority per macropath;
- Machi shadow-learning role;
- comparative analytics purpose;
- no automatic policy retuning in Stage 1;
- later Ollama residency/eviction authorization debt.

Do not expand into UI, warehouse analytics infrastructure, learned routing,
automatic retuning, or cross-customer telemetry.

# 11. Industry / Product Vision gate

This design is already approved.

If implementation encounters:
- a new mandatory dependency;
- a need to import/private-link Ollama internals;
- a breaking native qualification schema migration;
- a second resource ledger;
- a requirement to merge the model catalogs;
- a change that makes shadow Machi authoritative for Ollama;

STOP with the appropriate DECISION_REQUIRED status.

Otherwise no additional solution-selection gate is needed.

# 12. Gates

Run:
- targeted Chunk-3 tests;
- full `tests/machi`;
- architecture checks;
- ruff;
- strict mypy;
- clean wheel;
- isolated-wheel verification ending `verify_ok`.

Push exact clean HEAD to `origin/automation/ollama-macropath`.
Prove local == origin.
Do not move the Chunk-2 recovery checkpoint.
Do not start a server or download/load a real model.
Do not begin Chunk 4.

# 13. Mandatory paste-back

==================== BEGIN PASTE BACK — OLLAMA CHUNK 3 DUAL QUALIFIER ====================

A. STATUS  
B. Starting/final SHA  
C. Separate catalog implementation  
D. Ollama candidate identity contract  
E. Machi shadow evaluator behavior  
F. Ollama authoritative qualifier adapter behavior  
G. Qualification identity/schema treatment  
H. Probe Plan / ResourceManager treatment + native regression result  
I. Comparative analytics contract  
J. Agreement/disagreement classification examples  
K. Metric provenance/availability treatment  
L. Tests/gates  
M. Wheel build ID/SHA256  
N. Isolated verify_ok  
O. Docs/debt changes  
P. Local/origin equality  
Q. Exact support claim  
R. What remains for physical Ollama qualification  
S. Final status

End exactly:
`STOP — OLLAMA CHUNK 3 DUAL QUALIFIER LOCAL COMPLETE. WAIT FOR LEAD REVIEW.`

or typed FAIL / DECISION_REQUIRED.

==================== END PASTE BACK — OLLAMA CHUNK 3 DUAL QUALIFIER ====================

Do not begin Chunk 4.
