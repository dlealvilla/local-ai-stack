# CURRENT LEAD DEVELOPER INSTRUCTION

**Instruction ID:** `MACHI-OLLAMA-BUNDLE-04-PHYSICAL-AUTH-001`  
**Program:** `MACHI-OLLAMA-MACROPATH-001`  
**Starting integration HEAD:** `4aa21ccabade398a8f931c5a231baed84bbf45f0`  
**Integration branch:** `automation/ollama-macropath`  
**Package size:** multi-slice execution bundle  
**Physical server:** CONDITIONAL YES — after local gates  
**Chunk 4 full Serve:** FORBIDDEN  
**AUTO fallback:** FORBIDDEN  
**Chunk 5/6:** FORBIDDEN except physical evidence explicitly described here



======================================================================
DIRECTION LEVELS FOR THIS PACKAGE
======================================================================

Interpret the instruction using three levels:

- **BINDING:** Product Vision, authority boundaries, privacy, one global
  ResourceManager ledger, separate model-catalog ownership, provider support
  claims, RunPod safety, evidence/identity rules, and explicit STOP gates.
- **RECOMMENDED:** technical approaches described as preferred or likely best
  fit. Validate them against repository/provider truth. Cursor may use a
  materially better bounded implementation if it preserves all binding
  semantics and explains the deviation.
- **DELEGATED:** ordinary coding structure, helpers, refactors, test-fixture
  mechanics, and other local implementation choices.

Do not treat every Lead technical suggestion as a hard constraint.
Do not treat an architectural invariant as optional merely because another
implementation is convenient.

======================================================================
PRODUCT PURPOSE / FUNCTIONAL OUTCOME
======================================================================

This package is not merely an Ollama API integration exercise.

Its product purpose is to move Kultrun from a locally simulated Ollama
qualification path to a **real, evidence-backed second execution macropath**
that can be compared with native/vLLM under the same Machi control philosophy.

When this package succeeds, Kultrun should be able to truthfully say:

- a real Ollama-backed model can be discovered from Ollama's own catalog;
- Machi can authorize a bounded qualification attempt without surrendering
  global resource authority;
- Ollama can apply its own specialist fit/scheduler logic inside that
  authorization;
- Machi can independently shadow-evaluate the same case;
- Kultrun can prove which exact Ollama model digest was loaded and produced a
  real token;
- Kultrun can persist comparative evidence between Machi's estimate, Ollama's
  fit decision, and the real inference outcome;
- the qualification cleans up safely before resources are returned;
- the next Serve-layer design can be grounded in real provider behavior rather
  than speculation.

This directly supports the Product Vision by:
- keeping the product self-hosted and customer-controlled;
- reusing Ollama rather than duplicating its specialist scheduler;
- preserving Machi/Kultrun ownership of product policy, global authorization,
  evidence, and support claims;
- keeping providers replaceable behind stable concepts;
- building the empirical evidence base needed for future model/runtime
  selection without silently auto-retuning policy in Stage 1;
- preserving a path to offline/air-gapped operation;
- improving the future administrator experience by making model/runtime status
  explainable rather than opaque.

The package must **not** turn Ollama into the global resource authority, merge
the native and Ollama model catalogs, or claim production-grade Ollama Serve.

======================================================================
FUNCTIONAL SCOPE
======================================================================

IN SCOPE:
1. real loopback Ollama v0.34.3 API interaction;
2. truthful provider timing and identity evidence;
3. one small real Ollama model qualification on disposable NVIDIA hardware;
4. Machi shadow evaluation of the same authorized case;
5. durable comparative analytics;
6. safe cleanup/re-entry proof;
7. if physical qualification succeeds, the minimum residency-observation seam
   needed to reason about future long-lived Serve;
8. a product/architecture assessment of the long-lived authorization shape.

OUT OF SCOPE:
- general Ollama model marketplace/product acquisition;
- production multi-model Ollama serving;
- automatic fallback activation;
- broad routing policy;
- UI;
- learned/automatic policy retuning;
- cross-customer telemetry;
- private Ollama scheduler integration;
- full Chunk 4/5/6 implementation.

======================================================================
DELIVERY ACTIONS / HOW TO WORK THIS PACKAGE
======================================================================

Treat this as one coherent delivery cycle:

1. **Inspect and reconcile**
   Confirm repository truth, accepted architecture, exact v0.34.3 API behavior,
   and the current physical-lab rules.

2. **Build**
   Implement the missing real adapter/timing/residency mechanics needed for the
   functional outcome. Cursor owns the coding-level design unless an accepted
   invariant requires a specific shape.

3. **Local QA**
   Prove the real adapter behavior, timing semantics, identity rules, privacy,
   native regression safety, packaging, and isolated installation.

4. **Physical acceptance**
   Use one positively owned disposable NVIDIA host and run the real
   qualification campaign.

5. **Evidence and analytics**
   Persist and inspect the actual comparison between Machi shadow, Ollama fit,
   and real inference.

6. **Fix defects**
   If the accepted architecture is clear and the implementation fails, fix the
   product code locally, rebuild, redeploy, and rerun the affected acceptance.
   Do not escalate ordinary bugs as architecture decisions.

7. **Architecture amendment gate**
   If physical evidence shows that the accepted authority model itself is wrong
   or incomplete—especially around long-lived Serve/residency—stop with a
   structured decision package rather than silently changing the architecture.

8. **Close the package**
   Update docs/debt/evidence, push the exact accepted source, and state the
   precise support claim.

======================================================================
QA / ACCEPTANCE INTENT
======================================================================

Success is not "the tests are green."

Success means we can demonstrate, with reproducible evidence, that:
- the managed Ollama Foundation is the expected frozen generation;
- the selected Ollama model identity is exact and stable;
- Machi authorized the qualification resources;
- Ollama made the provider-specific fit/load decision;
- a real token came from the expected digest;
- Machi's independent shadow result was recorded without influencing Ollama;
- the comparison analytics are durable and semantically honest;
- cleanup returned the system to a truthful resource state;
- native/vLLM behavior still works;
- any next Serve decision is based on observed provider behavior.

======================================================================
FIX VS ARCHITECTURAL AMENDMENT
======================================================================

Fix autonomously and continue when:
- an adapter parses an API response incorrectly;
- timeout/error handling is wrong;
- tests expose a coding defect;
- evidence fields are wired incorrectly;
- cleanup/retry behavior fails while the intended authority model remains clear;
- a bounded internal refactor improves correctness without changing semantics.

STOP for Lead/product decision when a correction would:
- change which subsystem is authoritative;
- change a core contract/ontology used across macropaths;
- introduce a new mandatory dependency or provider;
- merge model catalogs;
- alter privacy/security posture;
- change customer-facing support claims materially;
- require private Ollama scheduler coupling;
- change the accepted long-lived ResourceManager/Serve philosophy.


Read first:
- `control/EXECUTION-BUNDLE-POLICY.md`
- `control/CORE-VS-COMMODITY-POLICY.md`
- `control/OLLAMA-BUNDLE-04-PHYSICAL-AUTH.md`
- `control/OLLAMA-CHUNK-03-LOCAL-ACCEPTED.md`
- `control/OLLAMA-CHUNK-03-DUAL-QUALIFIER-DECISION.md`
- `control/OLLAMA-CHUNK-03-QUALIFIER-BOUNDARY.md`
- `control/OLLAMA-CHUNK-02-CLOSED.md`
- authoritative Product Vision / Strategy / Architecture / M6 / M8 / M9 /
  TELEMETRY / DEBT docs
- current native physical inference evidence
- exact Ollama v0.34.3 public API and scheduler source

The accepted product/architecture decisions in those files are binding.
Do not reopen them unless repository truth shows a contradiction.

======================================================================
SLICE A — REAL OLLAMA PUBLIC API ADAPTER + TIMING TRUTH
======================================================================

## A1. Replace fixture-only gap with a real loopback adapter

Implement a real production adapter behind the existing `OllamaModelApi`
Protocol using Python standard-library HTTP facilities unless the repository
already has a suitable accepted HTTP client adapter.

Requirements:
- accept only the verified managed/private loopback endpoint from Foundation;
- reject non-loopback, credentials-in-URL, missing port, and non-HTTP endpoints;
- no cloud URL;
- no shelling out to curl;
- no new dependency;
- explicit connect/read/request timeouts;
- bounded response body size;
- `stream: false` for qualification requests so final metrics are one JSON
  object;
- typed transport/provider failures;
- malformed JSON / wrong response shape fail closed;
- do not retain response text from the token probe beyond what is necessary to
  prove output token count.

Implement exact public v0.34.3 operations needed here:
- `GET /api/tags`;
- `POST /api/show`;
- empty `POST /api/generate` preload;
- `GET /api/ps`;
- real small `POST /api/generate` token probe;
- empty `POST /api/generate` with `keep_alive: 0` for unload.

Do not import/private-link Ollama Go code or scheduler internals.

## A2. Qualification keep-alive semantics

For qualification preload/token proof:
- use request-level `keep_alive: -1` so the expected model remains resident
  until explicit cleanup;
- cleanup uses empty generate with `keep_alive: 0`;
- `/api/ps` remains the residency/digest proof.

This is provider mechanics inside a temporary Machi qualification reservation.
It is NOT yet the production long-lived Serve policy.

## A3. Correct timing semantics before physical evidence

Exact v0.34.3 final GenerateResponse exposes:
- `total_duration`;
- `load_duration`;
- `prompt_eval_count`;
- `prompt_eval_duration`;
- `eval_count`;
- `eval_duration`.

These durations are nanoseconds on the wire.

Change the adapter/evidence mapping so:
- `OllamaQualificationEvidence.load_seconds` = **initial preload response
  load_duration** converted to seconds;
- token input count = token request `prompt_eval_count`;
- token output count = token request `eval_count`;
- generation_seconds = token request `eval_duration` converted to seconds;
- tokens/sec = eval_count / eval_duration when valid;
- the token request's own `load_duration` is not mislabeled as initial load.

If preserving token-request load duration is useful, keep it as raw/provider
evidence or a bounded companion metric. Do not create a breaking public schema
migration merely to retain it.

Update contract meaning/golden evidence as needed before physical qualification.
This contract has local acceptance but no physical/production claim yet.

## A4. Real public metadata normalization

Build `OllamaCatalogCandidate` from:
- `/api/tags` exact name/digest/size/details;
- `/api/show` metadata/capabilities only.

Only map fields whose public v0.34.3 meaning is explicit and type-valid.
Do not guess dtype, architecture dimensions, or attention shape from names/tags.

Machi shadow may remain `UNRESOLVED` when Ollama does not expose enough public
facts. That is valid analytics.

## A5. Local tests

Use a local stub HTTP server or injected transport to prove:
- exact request paths/methods/bodies;
- loopback-only policy;
- bounded response;
- timeout/transport failure;
- malformed JSON/wrong shape;
- preload `keep_alive:-1`;
- unload `keep_alive:0`;
- nanoseconds -> seconds timing;
- prompt/eval token metrics;
- no prompt/response persistence;
- existing fake adapter and dual-qualifier tests remain valid.

Run targeted + full local gates before any server creation.

======================================================================
SLICE B — BUILD EXACT CANDIDATE + PHYSICAL PRE-FLIGHT
======================================================================

## B1. Build immutable candidate artifact

From the exact local source HEAD after Slice A:
- run targeted tests;
- full `tests/machi`;
- architecture tests;
- ruff;
- strict mypy;
- build clean wheel;
- isolated-wheel verification ending `verify_ok`;
- record build ID and SHA256.

Do not edit source on the physical host.
Physical host receives only the exact built candidate + bounded lab commands/data.

## B2. RunPod safety rules — binding

Use official RunPod skills/MCP/runpodctl only. No custom RunPod API client.

Only manage Pods positively created by this acceptance run.

Limits:
- one Pod at a time;
- NVIDIA maximum $1.50/hour;
- $40/session;
- $80/day;
- stop if live account balance is below $5 or cannot be established;
- max Pod life 90 minutes;
- max 3 provisioning retries;
- no network volumes.

Before creation establish:
- live balance;
- live GPU availability;
- live hourly rate;
- image/region;
- whether the host is single-GPU and Linux/x86_64.

Prefer:
1. exact NVIDIA L40S class used by native N2 when available under limit;
2. otherwise another suitable single NVIDIA host under limit.

Do NOT substitute AMD or Intel.

If authentication, connection, approval, or another user action is required,
STOP and explicitly ask Daniel. Do not guess credentials.

Lifecycle:
- success or terminal product failure -> capture evidence and terminate owned Pod;
- hang -> stop the owned Pod and ask Daniel before termination;
- never touch pre-existing/ambiguous Pods.

## B3. Host preparation

Install the exact wheel candidate.

Use Machi's existing Discover/Capacity/Foundation paths; do not hand-author
capacity values that product code can discover.

For the Ollama managed Foundation:
- use the frozen v0.34.3 managed-prefix recipe;
- preserve loopback-only + cloud-disabled semantics;
- no /usr/global systemd installation;
- use the exact managed generation identity.

If the provisional system `zstd` prerequisite is absent:
- record it first;
- bounded lab installation of zstd is allowed **only as operator lab setup**
  on this disposable host so long as no product support claim hides it;
- keep M-5-OLLAMA-04 open;
- do not represent this as plug-and-play customer-host proof.

## B4. Test model acquisition is lab setup, not product acquisition

Preferred model:
`smollm2:135m-instruct-q8_0`.

Fallback:
`smollm2:135m`.

Before pull:
- establish enough writable storage on the disposable host;
- record the selected tag and source;
- no customer credentials/content.

The pull may use Ollama's own CLI/API **as lab setup only**.
Do not add/claim a product model-pull feature in this package.

After pull:
- query `/api/tags`;
- record exact local name + full digest + size + public details;
- build the Machi `OllamaCatalogCandidate` from that real provider state;
- the digest, not the tag, is identity.

Normalize initial residency:
- require the selected digest to be absent from `/api/ps` before the cold
  qualification;
- if resident, explicitly unload via public API and prove absence;
- do not begin timing while residency is ambiguous.

======================================================================
SLICE C — REAL OLLAMA QUALIFICATION + COMPARATIVE ANALYTICS
======================================================================

## C1. Physical qualification authority

Use the real current CapacityEnvelope and current ResourceManager ledger.

Qualification admission must:
- choose the selected accelerator;
- reserve all currently remaining SAFE accelerator bytes on that device;
- reserve all currently remaining SAFE host-memory bytes;
- use zero model-acquisition storage because the model is already local lab
  setup;
- persist one qualification reservation on the shared ledger.

Then:
1. create Machi shadow result against that exact authorized reservation envelope;
2. re-resolve tag -> expected digest;
3. preload with `keep_alive:-1`;
4. verify `/api/ps` has expected **name + digest**;
5. capture runtime-reported size and `size_vram`;
6. run one bounded synthetic token probe;
7. verify `/api/ps` still has expected name + digest;
8. persist authoritative Ollama qualification evidence;
9. persist `model.qualification.compared`;
10. unload with `keep_alive:0`;
11. verify expected name+digest absent;
12. only then release ResourceManager reservation.

Synthetic prompt:
- fixed non-customer text;
- request only a very small bounded output;
- do not persist prompt text or response text.

## C2. Required physical evidence

Print/archive enough evidence to prove:
- exact wheel/build/SHA;
- Pod provider/region/SKU/rate/lifecycle;
- hardware/device identity;
- driver/CUDA facts;
- SAFE host + accelerator capacity;
- Foundation generation + Ollama exact version;
- model tag + full digest + provider size/details;
- qualification reservation id and exact bytes;
- Machi shadow FIT/NO_FIT/UNRESOLVED + estimates/provenance;
- Ollama provider fit FIT/NO_FIT/UNRESOLVED;
- overall qualification outcome;
- initial preload load_seconds;
- input/output tokens;
- eval/generation seconds and derived tokens/sec;
- `size_vram` explicitly labeled runtime-reported;
- comparison classification;
- unload result;
- reservation release result;
- durable journal event id/readback.

Do not archive prompt/response text, secrets, user identity, or customer paths.

## C3. Cold re-entry / repeat

If the first qualification is a clean PASS and remaining time/budget is safe:
- prove the model is absent from `/api/ps`;
- run one second qualification using the same exact digest and fresh/current
  capacity evidence;
- again prove cleanup and release.

Purpose:
- prove re-entry/idempotent orchestration and stable provider identity;
- collect a second local comparison record;
- do not turn two runs into a benchmark campaign.

If the second run differs materially, preserve both facts; do not average away
the discrepancy.

## C4. Comparison with native evidence

If physical host is the same L40S class as native N2:
- produce a bounded comparison table/evidence artifact containing native
  SmolLM2-135M-Instruct evidence and this Ollama case;
- include runtime, model representation/quantization, context, hardware,
  load_seconds, tokens/sec, and memory semantics;
- explicitly mark that model representations are not byte-identical and memory
  metrics may not be semantically identical.

If hardware differs:
- persist both datasets but do not create a same-hardware direct comparison
  claim.

No automatic model/runtime winner, routing policy, or retuning.

======================================================================
SLICE D — PHYSICAL DISPOSITION
======================================================================

Physical PASS requires:
- managed Ollama Foundation READY on exact host;
- exact provider model digest discovered;
- ResourceManager qualification admission;
- provider FIT or truthful provider NO_FIT/UNRESOLVED;
- if claiming qualification PASS: expected digest before/after token + real
  output token;
- durable comparison event;
- cleanup proof;
- no reservation released while expected model remains resident.

If product code fails:
- capture terminal evidence;
- fix source locally;
- rebuild a new immutable wheel;
- reinstall/upgrade the disposable server;
- rerun only the needed acceptance;
- never edit source on the server.

If physical run is environment-blocked:
- distinguish environment/prerequisite/provider-stock failure from product
  failure;
- do not forge a PASS.

On success/terminal product failure terminate the owned Pod after evidence.

======================================================================
SLICE E — CONDITIONAL CHUNK 4 PROVIDER RESIDENCY SEAM
======================================================================

Execute this slice ONLY if Slice C/D produced a clean physical Ollama
qualification PASS.

This slice is LOCAL ONLY after the physical Pod is terminated.

## E1. Provider-side residency observation/guard

Using public Ollama v0.34.3 API only, implement the smallest provider seam needed
for future long-lived Serve to:
- observe ABSENT / EXPECTED_RESIDENT / WRONG_IDENTITY / UNRESOLVED;
- cite name + digest + size_vram + expires_at where exposed;
- request/refresh expected residency with request-level `keep_alive:-1`;
- request unload with `keep_alive:0`;
- verify state transitions through `/api/ps`.

This seam does not itself authorize resources or become Serve.

## E2. One-model Stage-1 constraint may be tested locally, not silently adopted

The likely first serving shape is one Machi-authorized Ollama model per managed
daemon/reservation. However, making that a product contract affects Serve
semantics.

Do NOT silently make it permanent.

Inspect:
- existing M9/Serve contracts;
- current ResourceManager deployment reservation semantics;
- native DeploymentConfiguration identity;
- provider-owned Ollama model identity;
- public Ollama keep_alive/residency behavior;
- known loopback-local bypass debt.

## E3. Long-lived authorization decision gate

Compare at least:

A. **Provider DeploymentConfiguration / normal deployment reservation**
   - extend/parallelize DeploymentConfiguration so a provider-owned Ollama
     digest can be a truthful deployment identity;
   - same ResourceManager deployment reservation path;
   - Serve verifies provider digest before/after inference.

B. **Purpose-aware generic deployment claim below native Plan**
   - a generic ResourceClaim/DeploymentClaim produces a normal long-lived
     reservation for either native artifact or provider-owned model;
   - Plan remains one producer, Ollama provider deployment another.

C. **Separate Ollama long-lived reservation type on same ledger**
   - provider-specific upstream contract, shared ResourceReservation ledger.

D. **Let Ollama residency itself stand in for Machi authorization**
   - presumptively MISALIGNED.

For A/B/C/D assess:
- Product Vision Alignment;
- relationship to existing native M8/M9 semantics;
- migration/schema impact;
- one-ledger accounting;
- stale capacity protection;
- identity/fingerprint semantics;
- stop/restart/re-entry;
- cleanup/reconciliation;
- future training/indexing/general-workload implications;
- reversibility;
- amount of provider leakage into core.

If exactly one option is clearly a small extension of accepted architecture and
does not materially redefine native contracts, Cursor may implement the
smallest LOCAL skeleton plus tests.

If 2+ materially credible core designs remain, STOP with:
`DECISION_REQUIRED_OLLAMA_SERVE_AUTHORIZATION`

and a complete decision package.

Do not proceed to full Serve while that decision is unresolved.

======================================================================
CRITICAL DECISION / PRODUCT RULES
======================================================================

Cursor may make bounded engineering choices inside accepted architecture.

STOP for a decision if work would:
- change Product Vision;
- merge native/Ollama model catalogs;
- make Machi shadow authoritative on Ollama;
- make Ollama scheduler the global resource authority;
- create a second independent resource ledger;
- add a mandatory non-replaceable dependency;
- import/private-link Ollama scheduler internals;
- change privacy/customer-content posture;
- require a new provider/vendor beyond current NVIDIA physical lane;
- materially break/change native M8/M9 ontology;
- change commercial/licensing direction.

Provider Selection Gate remains mandatory for a new provider.
Industry Solution Selection Gate remains mandatory for a material dependency or
core build-vs-integrate choice.

======================================================================
FINAL GATES
======================================================================

After all executed slices:
- targeted tests for every changed subsystem;
- full `tests/machi`;
- architecture checks;
- ruff;
- strict mypy;
- clean wheel;
- isolated-wheel `verify_ok`;
- exact clean local HEAD pushed to `origin/automation/ollama-macropath`;
- prove local == origin.

Record whether Slice E:
- NOT_REACHED,
- COMPLETED_LOCAL,
- or DECISION_REQUIRED.

Do not begin full Chunk 4 Serve, Chunk 5, Chunk 6 closure, or AUTO fallback.

======================================================================
MANDATORY PASTE-BACK
======================================================================

==================== BEGIN PASTE BACK — OLLAMA BUNDLE 04 ====================

A. STATUS / package slices executed  
B. Starting SHA / final SHA  
C. Carry-forward preload timing correction  
D. Real loopback API adapter implementation  
E. Local API/timing/transport tests  
F. Candidate wheel build ID/SHA256 + isolated verify_ok  
G. RunPod preflight: balance/stock/rate/image/ownership  
H. Physical host exact identity/lifecycle  
I. Managed Ollama Foundation realization/evidence  
J. Lab model setup: tag/full digest/size/details  
K. Initial residency normalization  
L. ResourceManager qualification reservation exact bytes  
M. Machi shadow result  
N. Ollama provider fit + overall qualification result  
O. Preload -> ps -> token -> ps identity proof  
P. Physical timing/token/size_vram metrics + provenance  
Q. Durable comparison event/readback  
R. Cleanup + reservation release proof  
S. Optional second qualification/re-entry result  
T. Native-vs-Ollama comparison artifact, or why not directly comparable  
U. Physical disposition/support claim  
V. Owned Pod termination proof or hang STOP state  
W. Slice-E residency observation/guard result  
X. Long-lived authorization options A/B/C/D + Product Vision Alignment  
Y. Decision gate result / implementation if NO_NEW_CORE_DECISION_REQUIRED  
Z. Full regression/package gates  
AA. Docs/debt/evidence changes  
AB. Local/origin equality  
AC. Exact remaining work  
AD. Final status

Final status must be exactly one of:

`STOP — OLLAMA BUNDLE 04 COMPLETE. WAIT FOR LEAD REVIEW.`

`DECISION_REQUIRED_OLLAMA_SERVE_AUTHORIZATION — WAIT FOR LEAD DECISION.`

`ENVIRONMENT_BLOCKED — WAIT FOR LEAD REVIEW.`

`PRODUCT_FAILURE — WAIT FOR LEAD REVIEW.`

==================== END PASTE BACK — OLLAMA BUNDLE 04 ====================

Do not continue beyond this package.
