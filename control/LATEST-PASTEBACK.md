SERVER NEEDED NEXT: NO

Instruction: MACHI-OLLAMA-CHUNK-02-001
Program: MACHI-OLLAMA-MACROPATH-001
Chunk: 2 of 6

STATUS=OLLAMA_CHUNK_2_PASS

TL;DR

- Ollama is a Foundation engine. AUTO still selects vLLM and still refuses when vLLM is unsupported.
- The frozen stable pin is Ollama 0.34.3, Linux amd64 archive sha256 e83a089fd0cd2f79ee2933cca2085846a2065f497adbc6467c402177c68423f9.
- Verified-existing and a Machi-owned prefix are both implemented. The prefix stays under the state root. The official installer is not used.
- A verified daemon is not a loaded model and not InferenceProof.
- The official Linux binary was not executed here. That limit is M-5-OLLAMA-03.
- Local API bypass is recorded as M-5-OLLAMA-01. ResourceManager does not hard-stop other local processes.

ARCHITECTURE MAP

```text
explicit Ollama request
  -> pinned stable recipe
  -> verified-existing observation
     or owned prefix under state-root/foundation/environments
  -> loopback daemon, cloud disabled
  -> GET /api/version
  -> RuntimeCapability with serving unsupported
  -> generation id
```

WHAT JUST HAPPENED

The substrate, tests, and canonical status notes were committed locally as 073c5daf0baf319abc8b4d0f3f415999aeadf67f. No model was pulled. No GPU server was created.

WHERE WE ARE

Native vLLM behavior is unchanged. Plan still refuses an Ollama capability. The remote integration branch has not been moved.

WHAT'S NEXT

Lead review. Chunk 3 does not start from this result.

HANDOFF

```text
PAST     Chunk 1 tunnel decision
PRESENT  local daemon substrate, both providers
NEXT     lead review before model binding
```

==================== BEGIN PASTE BACK — OLLAMA CHUNK 2 ====================

## A. STATUS

STATUS=OLLAMA_CHUNK_2_PASS

No physical server was created. No model weights were downloaded. No model was loaded. No inference was run. AUTO fallback was not activated. Chunk 3 was not started.

## B. Starting SHA / branch / recovery checkpoint

- Started from origin/automation/ollama-macropath at 6e17f4a817d1571e0a708decec405ceda0282c7f.
- Local branch automation/ollama-macropath is now 073c5daf0baf319abc8b4d0f3f415999aeadf67f.
- That commit is not pushed. origin/automation/ollama-macropath is still 6e17f4a817d1571e0a708decec405ceda0282c7f.
- origin/checkpoint/native-vllm-partial-pass-2026-09-24 is still 6e17f4a817d1571e0a708decec405ceda0282c7f. It was not moved.

## C. Stable Ollama release selected and official provenance/checksum evidence

Read on 2026-09-24 from the GitHub releases API and the release checksum file.

- Latest release tag: v0.34.3
- draft: false
- prerelease: false
- Asset: ollama-linux-amd64.tar.zst
- Size: 1427391999 bytes
- sha256sum.txt line: e83a089fd0cd2f79ee2933cca2085846a2065f497adbc6467c402177c68423f9
- GitHub asset digest: the same sha256
- Source URL: https://github.com/ollama/ollama/releases/download/v0.34.3/ollama-linux-amd64.tar.zst
- Checksum URL: https://github.com/ollama/ollama/releases/download/v0.34.3/sha256sum.txt
- Software license at that tag: MIT
- A different stable tag, a draft, or a prerelease is refused. The generation does not follow a later channel read.

## D. Repository architecture audit

- FoundationEngine was vLLM-only. It now has an ollama value. No new macropath type was added.
- FoundationCandidate, FoundationSettings, and the vLLM provisioner still describe the Python/vLLM path. Ollama does not reuse those fields with dummy values.
- Plan still returns not ready unless the capability engine is vLLM. Serve was not edited.
- Foundation readiness for vLLM is still an import check. Ollama readiness is a separate daemon fact. One generation is not assumed to be one model-serving process.
- The Ollama path does not require a safetensors warehouse.
- ResourceManager was not given a second implementation.
- The foundation domain still may not spawn processes or call model routes. The adapter owns the process and the version request.

## E. Files/contracts changed

- src/machi/foundation/contracts.py — FoundationEngine.OLLAMA
- src/machi/foundation/ollama.py — recipe, generation, raw evidence, metrics, assessment
- src/machi/foundation/__init__.py — registers the new contracts
- src/machi/adapters/foundation/ollama_runtime.py — prefix install and daemon lifecycle
- tests/machi/test_ollama_foundation.py
- tests/machi/architecture.py — the domain may name the engine and still may not pull or infer
- tests/machi/golden/schema_fingerprint.json — six new contract kinds
- docs/STRATEGY.md, docs/machi/ARCHITECTURE.md, docs/machi/M5.md, docs/machi/ROADMAP.md, docs/DEBT.md

New contract kinds: foundation.metric@1, foundation.metric_set@1, foundation.ollama_recipe@1, foundation.ollama_raw@1, foundation.ollama_generation@1, foundation.ollama_substrate@1.

## F. FoundationEngine/provider design

FoundationEngine.OLLAMA is the engine value. The family stays direct. The executor stays native_process. The first lane records AcceleratorBackend.CUDA. AMD, Docker, Windows, and macOS are not selected.

AUTO is unchanged: inspect_foundation still resolves native vLLM and does not substitute Ollama.

Two provider modes exist:

- verified_existing, after an executed binary, exact version, private endpoint, cloud disabled, and /api/version
- managed_prefix, after a checksummed extract under the state root and the same daemon checks

A process name, PATH entry, systemd unit, or container tag is refused.

## G. Verified-existing implementation and tests

assess_existing accepts only identified_by=executed_binary and a path that is not a bare command name. The version text must parse to 0.34.3. Prerelease text is unsupported. A public or unspecified bind is refused. Cloud enabled and cloud unknown are refused. A missing API is "daemon api is unavailable". An API version other than the pin is "daemon version does not match the executable". An install that can auto-update is refused. Nothing on the host is repaired.

Tests cover the pass, the refusals above, and a schema round trip. The round trip keeps engine ollama and server_launch unsupported.

## H. Managed-prefix relocatability result

The official v0.34.3 installer extracts ollama-linux-amd64.tar.zst into a prefix such as /usr. That destination is the installer's choice. The archive members are bin/ollama and lib/ollama relative to the extract root.

v0.34.3 ml/path.go looks for lib/ollama next to the executable and at ../lib/ollama. A tree extracted under a Machi-owned directory satisfies that layout. No relocation patch is required.

This workspace is macOS, so the Linux binary was not executed. Fixture archives with the same layout were extracted and started. M-5-OLLAMA-03 records that limit. The result is not DECISION_REQUIRED_MANAGED_PREFIX.

## I. Managed-prefix implementation and ownership

The prefix is:

```text
<state-root>/foundation/environments/<id>/ollama/
  bin/ollama
  lib/ollama/
  models/          empty
  logs/
  config/server.json
  .ollama/server.json
<state-root>/foundation/environments/<id>/manifest.json
```

The manifest records owner machi, owned true, the recipe id, and the archive sha256. A second install of the same checksum reuses the tree. A different checksum is refused and does not overwrite. Checksum mismatch writes nothing. Members that are absolute, contain .., or are links are refused and the partial tree is removed. A footprint larger than the supplied safe byte limit is removed. The models directory is refused if it already contains a file. The environment does not include OLLAMA_API_KEY. OLLAMA_HOST is 127.0.0.1 only. OLLAMA_MODELS points at the owned models directory. OLLAMA_NO_CLOUD is 1. server.json sets disable_ollama_cloud true.

The official zstd asset is inflated with the zstd tool into memory and then extracted under the prefix. Tests use an uncompressed tar, so that tool path was not exercised on the 1.4 GB asset.

## J. Daemon lifecycle semantics

START runs the owned executable with --version, then argv serve. VERIFY polls GET /api/version only. STOP signals the process this object spawned. RESTART stops and starts the same prefix. A pid this object did not spawn is not signaled.

Foundation verification requires the pinned version, a loopback endpoint, cloud disabled, and a matching /api/version. RuntimeCapability.server_launch stays unsupported. The assessment reason says model residency is not claimed. This is not ReadinessProof and not InferenceProof.

Tests start a fixture process, read only /api/version, restart it, stop it, and leave models empty.

## K. Foundation identity/fingerprint/invalidation

The generation id is a hash of recipe id, provider mode, version, artifact sha256 or the token unresolved, execution-environment fingerprint, cloud mode, and endpoint. Changing provider mode changes the id. qualification_identity changes with that id, so later qualification evidence cannot cover the old generation. The fingerprint is an input. Foundation does not import Model to compute it.

Verified-existing without a measured binary hash stores artifact sha256 as unresolved, and the metric availability is UNRESOLVED.

## L. Security boundary and explicit debt

The daemon is bound to 127.0.0.1. Cloud is disabled in the owned environment. No cloud API key is read or stored. M-5-OLLAMA-01 says another local process can still call the loopback API. Machi does not claim ResourceManager prevents that.

## M. Foundation analytics schema/adapter and availability states

FoundationMetric carries name, value, availability, unit, source, and privacy operational. Availability values are observed, derived, estimated, hidden_internal, not_exposed, not_applicable, unsupported, and unresolved.

The substrate records engine, provider mode, version, checksum, install duration, footprint bytes, startup duration, verify duration, loopback bind, cloud disabled, lifecycle, and failure reason. Missing durations and the verified-existing footprint are unresolved, not zero. OllamaRawEvidence keeps the version text and checksum apart from the normalized rows. No prompt or response text is stored.

## N. Qualification-path compatibility check

A normal deployment still needs DeployableModels coverage. An existing probe plan skips that coverage so a qualification run can earn it. That probe still requires a vLLM capability, so an Ollama probe is not active. The generic reservation records can cite a plan once a later chunk allows this engine on a probe. No second ResourceManager is needed, and no Admit contract was changed. Chunk 2 does not load a model to discover fit.

## O. Canonical doc updates

- STRATEGY no longer says hosts lack vLLM product code. It records the partial NVIDIA result and that AUTO fallback is target policy only.
- ARCHITECTURE says an explicit Ollama substrate can be verified and AUTO does not select it.
- M5 describes the substrate, the loopback and cloud rules, and the two debts.
- ROADMAP says the substrate exists and that pull, Serve, and AUTO fallback do not.
- DEBT adds M-5-OLLAMA-01, M-5-OLLAMA-02, and M-5-OLLAMA-03.

## P. Local test/gate results

- tests/machi/test_ollama_foundation.py: 9 passed
- tests/machi: exit 0, 506 tests
- ruff check src/machi tests/machi: passed
- mypy --strict src/machi: 159 files, no issues
- Architecture boundary tests are inside tests/machi and passed

Isolated wheel verification did not print verify_ok. tools/verify_machi.py reached admit and serve policy, then tools/prove_serve_fixture.py exited with "serve did not become ready: plan_reservation_mismatch". That fixture never sets qualification_id. Serve has refused a plan without that setting since 96bc430, which is an ancestor of this commit. The Ollama files do not change that fixture. Serve unit tests in tests/machi passed.

## Q. Packaging/wheel SHA if built

Built from clean commit 073c5daf0baf319abc8b4d0f3f415999aeadf67f.

- artifact: dist/machi/machi-0.1.0-py3-none-any.whl
- build id: 0.1.0+073c5daf0baf
- clean_source: true
- size: 283016
- sha256: 4f887ab47ef4472351cc397112495e8b7fea92aa4cbf5532c970fd637dbbb2e0

## R. Strategic checks 1–10

1. Yes. The adapter starts the Ollama executable and reads its version API. It does not reimplement the runner, store format, or scheduler.
2. Yes. The generation id is the recipe, provider mode, version, checksum, environment fingerprint, cloud mode, and endpoint.
3. Yes, for the owned prefix. Extraction is confined to the state root. /usr, systemd, and a new host user are not used. The official Linux binary itself has not been run.
4. Yes. Probe plans already exist to earn coverage before DeployableModels membership. This chunk does not open that probe for Ollama.
5. No. Daemon verification leaves server launch unsupported and does not claim model residency.
6. No. M-5-OLLAMA-01 states the loopback bypass. Enforcement is not claimed.
7. Yes. Shared metric names use explicit availability. Unmeasured values stay unresolved. Raw version text is kept separately.
8. The engine enum value is the generic seam. Recipe, digest, cloud mode, and endpoint live on Ollama contracts. RuntimeCapability version 1 text still says vLLM; M-5-OLLAMA-02 records that.
9. Yes. A later engine can use the same family-plus-engine selection, reservation, and metric availability. Ollama serve flags stay in the adapter.
10. Yes. This is a local substrate pass for the frozen pin and fixture lifecycle. It is not a GPU qualification, not a Linux execution of the official archive, and not an inference pass.

## S. Decisions made within bounded authority

- Froze v0.34.3 because it was the latest non-draft, non-prerelease release on the official channel at execution time.
- Treated the Linux archive as prefix-relative from the installer and ml/path.go, and implemented the owned prefix.
- Kept AUTO fail-closed.
- Left Plan and Serve behavior unchanged.
- Recorded unverified Linux execution as debt instead of calling the fixture a physical Linux proof.

## T. DECISION_REQUIRED items

None. Managed prefix relocation is possible from the official layout, so this is not DECISION_REQUIRED_MANAGED_PREFIX.

## U. Debt added

- M-5-OLLAMA-01 — loopback API is not hard isolation. Authorizes nothing.
- M-5-OLLAMA-02 — RuntimeCapability v1 wording still names vLLM. Authorizes nothing.
- M-5-OLLAMA-03 — the pinned Linux archive has not been executed from an owned prefix. Authorizes nothing.

## V. Exact proposed Chunk-3 scope

Do not start it from this result. If accepted, Chunk 3 is the model and specialist-feasibility bridge from the program:

- bind a Machi model identity to an Ollama digest, not a floating tag
- keep license and provenance decisions with Machi
- account for the owned model directory without treating it as the vLLM warehouse
- apply coarse filters before any pull
- record specialist fit evidence only under a future qualification reservation
- keep normal DeployableModels membership after that evidence, not before it
- invalidate evidence when the Ollama generation id changes
- add funnel, pull, and fit metrics with explicit availability

No ordinary deployment load, no inference product path, and no AUTO activation.

## W. Exact branch/HEAD/final state

- Local HEAD: 073c5daf0baf319abc8b4d0f3f415999aeadf67f on automation/ollama-macropath
- origin/automation/ollama-macropath: 6e17f4a817d1571e0a708decec405ceda0282c7f
- origin/checkpoint/native-vllm-partial-pass-2026-09-24: 6e17f4a817d1571e0a708decec405ceda0282c7f
- Untracked docs/machi/proposals/ was not committed
- Working tree has no product modifications besides those untracked notes

NO_MODEL_WEIGHTS_DOWNLOADED
NO_MODEL_LOADED
NO_INFERENCE_RUN
NO_SERVER_CREATED
AUTO_FALLBACK_NOT_ACTIVATED

STOP — OLLAMA CHUNK 2 PASS. WAIT FOR LEAD REVIEW.

==================== END PASTE BACK — OLLAMA CHUNK 2 ====================
