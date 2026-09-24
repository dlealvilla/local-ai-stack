SERVER NEEDED NEXT: NO

Instruction: MACHI-OLLAMA-CHUNK-01-001
Program: MACHI-OLLAMA-MACROPATH-001
Chunk: 1 of 6

STATUS=OLLAMA_CHUNK_1_READY_FOR_LEAD_REVIEW

TL;DR

- Ollama stays a continuous local execution tunnel inside FoundationSelection. It is not a second control plane and not a flag inside vLLM.
- Machi keeps host truth, SAFE capacity, policy, provenance, DeployableModels, Plan, ResourceManager, proof, support claims, and the normalized analytics vocabulary.
- Ollama may own the local daemon, model store, runner, placement, pull/load/unload, local scheduling, and the serving implementation.
- There is no official dry-run fit API. Disk identity and license text appear after the model is local. VRAM and processor placement appear only after load, on GET /api/ps.
- A tag is not an artifact identity. The binding is the requested name plus the SHA-256 digest from /api/tags or /api/ps.
- First coverage should be Linux/NVIDIA, loopback, cloud disabled. Verified-existing Ollama is the smaller Chunk-2 path. A managed install that writes /usr or systemd is a Lead decision.
- Current Plan code refuses any engine other than vLLM. That is an implementation limit, not a reason to create a new admission authority.
- API health is not InferenceProof. A proof needs a completed generate or chat with output tokens and a matching digest.
- Official release used for this review: Ollama v0.34.3, published 2026-09-19, MIT license.

ARCHITECTURE MAP

```text
Machi outer control
  Install, Discover, Steward, SAFE Capacity
  FoundationSelection
  coarse policy and storage eligibility
  ResourceRequest and ResourceReservation
        |
        ENTER local Ollama tunnel
          daemon on 127.0.0.1:11434
          store, digest, runner, placement
          pull, load, local schedule, serve
        EXIT
        |
  digest check
  InferenceProof
  normalized analytics
  empirical_case
```

WHAT JUST HAPPENED

This chunk compared the six-chunk program, the current Machi contracts, and the official Ollama docs and v0.34.3 release. No product file, server, or model weight was changed.

WHERE WE ARE

Native vLLM has a partial physical pass on one L40S. Ollama is named as the fallback in strategy and is unimplemented in Foundation, Plan, and Serve. Both program refs exist and point at 6e17f4a817d1571e0a708decec405ceda0282c7f.

WHAT'S NEXT

Lead review of the provider and analytics decisions below. Chunk 2 does not start from this review.

HANDOFF

```text
PAST     native vLLM partial pass
PRESENT  Ollama tunnel boundary and provider gate
NEXT     lead review, then Chunk 2 only if approved
```

==================== BEGIN PASTE BACK — OLLAMA CHUNK 1 ====================

## A. STATUS

STATUS=OLLAMA_CHUNK_1_READY_FOR_LEAD_REVIEW

No product implementation was performed. No server was created. No model weights were downloaded. Chunk 2 was not started.

## B. Repository truth / starting point

Working branch at review time: automation/inference-program at 6e17f4a817d1571e0a708decec405ceda0282c7f.

origin/checkpoint/native-vllm-partial-pass-2026-09-24 and origin/automation/ollama-macropath both resolve to that same commit. Neither was moved.

FoundationEngine is only vllm. ExecutorKind is only native_process. Plan composition returns not ready unless the capability engine is vLLM, and the recipe check requires provider vllm. Serve authorizes only provider name vllm and launches a vLLM process. Model selection requires current DeployableModels membership. Qualification reuse requires the execution-environment fingerprint. The acceptance lab is schema version 2 with empirical_case. The native-vLLM program status is NATIVE_VLLM_PARTIAL_PHYSICAL_PASS: N1 blocked, one L40S host passed for two SmolLM2 revisions, and the head-dimension-4 Llama was excluded before weight fetch.

## C. Native-vLLM lessons being transferred

- A class label does not authorize another GPU. The Ollama tunnel must record the same execution-environment fingerprint.
- Selection cannot bypass DeployableModels, including an administrator choice.
- A plan that cites a different capacity snapshot is stale. The N2 campaign hit stale_capacity_input and the product correctly refused it.
- Daemon or process health is not InferenceProof. The vLLM path required a real completion with tokens.
- Served identity must be the Machi artifact identity, not a path or a floating tag.
- Known-bad structure should fail before ordinary weight acquisition when metadata is sufficient.
- One SKU pass is not a class or vendor claim.
- Empirical evidence stays in the existing lab. Do not open a second warehouse.

## D. Ollama current-capability findings from official sources

Reviewed on 2026-09-24 from docs.ollama.com and the GitHub release v0.34.3 published 2026-09-19.

- Latest release is v0.34.3. Linux assets include ollama-linux-amd64.tar.zst and a separate ROCm tarball. The API is not strictly versioned. Docs say it is expected to stay backwards compatible.
- Local base URL is http://localhost:11434. Cloud base URL is https://ollama.com. They are different.
- Local API security is empty. Cloud inference, publishing, and private pulls need sign-in or an API key. Local requests do not.
- Default bind is 127.0.0.1:11434. OLLAMA_HOST can widen it. That must stay loopback for Machi.
- Cloud can be disabled with OLLAMA_NO_CLOUD=1 or disable_ollama_cloud in server.json. Official FAQ says local prompts are not sent to ollama.com. Cloud-hosted models do process prompts.
- GET /api/tags lists local models with name, size, digest, format, family, parameter_size, and quantization_level. remote_model and remote_host mark a remote model.
- POST /api/show, for a local model, returns parameters, license text, details, capabilities, and model_info such as context length and attention counts. Verbose mode exists. The documented show schema does not include the digest. Digest is on tags and ps.
- GET /api/ps, only while a model is loaded, returns size, digest, size_vram, context_length, and expires_at. CLI ollama ps also shows processor as GPU, CPU, or a split.
- POST /api/generate and /api/chat accept keep_alive. 0 unloads after the call. Negative keeps the model loaded. Default residency is 5 minutes. An empty generate or chat preloads. There is no separate documented fit endpoint.
- Final generate fields, in nanoseconds, include total_duration, load_duration, prompt_eval_count, prompt_eval_duration, eval_count, and eval_duration. There is no TTFT field.
- Concurrency is server-owned. OLLAMA_NUM_PARALLEL defaults to 1. OLLAMA_MAX_LOADED_MODELS defaults to 3 per GPU or 3 on CPU. OLLAMA_MAX_QUEUE defaults to 512. Parallel requests multiply context and memory. New GPU models must fit entirely in VRAM to load beside another model.
- Default context is 4096 via OLLAMA_CONTEXT_LENGTH, overridable per request with options.num_ctx.
- NVIDIA support is compute capability 5.0+ with driver 550 or newer, and 570 or newer for 5.0 through 6.2. Placement can be limited with CUDA_VISIBLE_DEVICES. AMD Linux support in the official GPU page requires the ROCm v7 driver and lists MI300X and MI350X among Instinct parts. A separate ROCm tarball exists.
- Official Linux install extracts into /usr and recommends a systemd unit running as user ollama, with models under /usr/share/ollama/.ollama/models unless OLLAMA_MODELS is set. Upgrades re-run the installer. macOS and Windows apps auto-update.
- Model store location is configurable. The software license at v0.34.3 is MIT.

## E. Layer responsibility matrix

| Responsibility | Class |
|---|---|
| SAFE capacity | MACHI_AUTHORITY |
| Foundation candidate and selection | MACHI_AUTHORITY |
| Runtime installation choice and ownership | MACHI_AUTHORITY |
| Runtime environment contents after selection | OLLAMA_DELEGATED for the selected prefix or verified install |
| Service lifecycle of the local daemon | SHARED_WITH_EXPLICIT_BOUNDARY: Machi starts and supervises the owned daemon; Ollama runs it |
| Model identity, provenance, license decision | MACHI_AUTHORITY |
| Model representation and blob store | OLLAMA_DELEGATED |
| Cheap eligibility filters | MACHI_AUTHORITY |
| Exact or specialist fit | OLLAMA_SPECIALIST_EVIDENCE_MACHI_DECIDES |
| Runner and backend selection | OLLAMA_DELEGATED |
| GPU or CPU placement inside the authorized devices | OLLAMA_DELEGATED |
| Acquisition and pull | OLLAMA_DELEGATED after Machi authorizes the pull |
| Load, unload, residency | OLLAMA_DELEGATED |
| Context and local concurrency mechanics | OLLAMA_DELEGATED inside Machi's requested envelope |
| Local scheduling | OLLAMA_DELEGATED |
| DeploymentConfiguration | MACHI_AUTHORITY |
| ResourceRequest | MACHI_AUTHORITY |
| Global admission | MACHI_AUTHORITY |
| ResourceReservation | MACHI_AUTHORITY |
| Serving implementation | OLLAMA_DELEGATED |
| Request inference execution | OLLAMA_DELEGATED |
| Served-model identity verification | MACHI_AUTHORITY using Ollama digest evidence |
| Readiness and inference proof | MACHI_AUTHORITY |
| Normalized analytics schema | MACHI_AUTHORITY |
| Empirical evidence | MACHI_AUTHORITY |
| Support claims | MACHI_AUTHORITY |

## F. Continuous tunnel diagram

```text
Install, Discover, Steward, SAFE Capacity
        -> FoundationSelection (family + engine)
        -> coarse policy, license, storage plausibility
        -> DeploymentConfiguration
        -> ResourceRequest
        -> ResourceReservation
        -> ENTER TUNNEL
             verified local daemon, loopback, cloud off
             bind requested name to digest
             pull only if not already present at that digest
             load with keep_alive
             Ollama chooses runner, GPU/CPU split, and local queue
             POST /api/generate or /api/chat
        -> EXIT TUNNEL
        -> compare response model and /api/ps digest to the bound digest
        -> InferenceProof only if done and eval_count > 0
        -> unload on deployment stop
        -> normalized metric records
        -> empirical_case
```

Do not alternate control back into Ollama between Plan and Admit. Those stay outside the tunnel. The tunnel starts only after a reservation exists.

## G. Exact Foundation/provider decision recommendation

Recommend both seams, with different timing.

1. Verified-existing local Ollama is the Chunk-2 implementation. Require an observed version equal to the pinned line, loopback bind, cloud disabled, and a successful /api/version. Do not trust a unit name or a container tag alone.
2. Machi-managed installation should be designed now and built only after the Lead accepts it. The official installer writes /usr, creates a system user, and installs a systemd unit. That is broader than the ROCm prefix, which stayed under the state root. A managed prefix would extract the pinned v0.34.3 tarball into Machi-owned storage, set OLLAMA_MODELS under that tree, and not register a host-wide service.

First hardware coverage is Linux plus NVIDIA, matching the qualified native-vLLM development reference. AMD Ollama is a later lane. The official ROCm tarball and ROCm v7 driver requirement must not be treated as already qualified.

Pin the first line to v0.34.3, the release reviewed here, until a later pin is accepted. Record the asset digest from the release sha256sum.txt at install time. Do not follow macOS or Windows auto-update.

Native process remains the executor. Docker is documented by Ollama and stays out of this macropath, consistent with deferred ContainerExecutor.

Air-gap: a managed or verified binary can run offline. Pull cannot, unless the blobs are already in OLLAMA_MODELS. Offline pull failure is environment or source failure, not a model incompatibility.

Any happy path that calls https://ollama.com, uses an API key, or selects a model whose tags entry has remote_host is DECISION_REQUIRED and is not recommended.

## H. Model identity and provenance binding

Machi identity remains source, repository or library name, requested revision, immutable revision, license decision, and artifact id.

Ollama identity is the local name plus the digest. The tag, including latest, is only the request. After pull, /api/tags.digest is the immutable revision. A later tag move that changes the digest is a different artifact and invalidates deployability.

Before pull, Machi can know the requested name, a declared license only if it already has one from its own catalog, and coarse size only if a registry manifest was fetched. The local show API is documented for a model that already exists locally. Do not pretend show works before pull.

After pull and show, Machi can record digest, on-disk size, format, family, parameter label, quantization label, license text, capabilities, and model_info context length. License text is evidence. It is not an automatic commercial-use approval.

GGUF and other Ollama formats are Ollama's representation. Machi should not require a safetensors warehouse for this tunnel.

## I. Specialist-fit / DeployableModels design

1. Machi coarse gate: policy, license decision, storage plausibility against SAFE storage, and architecture or quant only when already known. This can reject before pull.
2. Ollama evidence after pull: show details and model_info. This is specialist description, not a fit verdict.
3. Ollama evidence after an authorized load: /api/ps size, size_vram, context_length, and processor placement. This is observed residency, not a pre-load promise.
4. Machi decides DeployableModels only when the observed or explicitly estimated requirement fits the current SAFE envelope and the digest matches. Unknown fit is not membership.
5. ResourceManager still admits the execution. Ollama's queue does not.

There is no documented fit call that returns a verdict without ordinary load. Pull is required before show. Load is required before size_vram. A pre-load estimate may be recorded as ESTIMATED and must not authorize by itself.

Hidden scheduler math, KV cache quantization choice, and flash-attention selection are HIDDEN_INTERNAL. They are not null.

Invalidation: digest change, Ollama version change, execution-environment fingerprint change, num_ctx change, or OLLAMA_NUM_PARALLEL change invalidates fit evidence.

Do not run the vLLM head-size predicate probe against an Ollama model. That probe is vLLM-specific. The tiny-Llama lesson remains: if metadata already proves incompatibility, do not pull. If only Ollama can know, pull is allowed only as acquisition, and load still requires admission.

Models that never appear in /api/ps with size_vram stay UNRESOLVED for specialist memory. They are not deployable.

## J. Plan / ResourceManager boundary audit

DeploymentConfiguration, ResourceRequest, and ResourceManager can remain the wrapper. Ollama must not become a second admission authority.

Current code cannot host that wrapper yet. compose_plan requires FoundationEngine.VLLM, and the vLLM recipe rejects any other provider. Serve refuses a non-vllm provider. Those are implementation gates, not a missing global-admission concept.

Supporting Ollama needs a contract addition for the engine value and a non-vLLM recipe adapter. It does not need a new ResourceManager. I do not recommend new Plan semantics for local scheduling. The requested context and concurrency are Machi envelope fields. Ollama applies them with num_ctx and its own parallel settings inside that envelope.

If the Lead wants a separate macropath object besides FoundationSelection, that would be a new semantic and is not recommended. Architecture already says family plus engine is the decision.

## K. Serve / lifecycle design

START of a deployment means the verified daemon is running on loopback with cloud disabled, and the bound digest is loaded. Preload uses an empty generate or chat, or keep_alive greater than zero. That load is not the inference proof.

The daemon and the model residency are different layers. The daemon can stay up across deployments. Residency is the loaded digest.

STOP of a deployment unloads that model with keep_alive 0. It does not stop the daemon. Stopping the daemon is foundation teardown, not a serving stop.

Restart requires a new or still-held reservation, then load again. A reservation is not held across an unloaded stop unless Admit says it is still reserved. The vLLM rule remains: no reservation, no execution.

Served identity is the response model field plus the digest from /api/ps or /api/tags. Both must match the bound digest. The tag alone is not enough.

Readiness is GET /api/version on loopback, or a successful ps call. InferenceProof is a finished generate or chat with done true, eval_count greater than zero, and the digest match. Store token counts and durations, not the prompt or response text.

## L. Common Macropath Analytics contract

Recommend one normalized record, not a new database. Each metric is a value plus availability, unit, source, and privacy. Availability is one of OBSERVED, DERIVED, ESTIMATED, HIDDEN_INTERNAL, NOT_EXPOSED, NOT_APPLICABLE, UNSUPPORTED, UNRESOLVED.

Collection sits behind a macropath adapter seam. Native vLLM and Ollama fill the same names. The empirical_case table remains the lab spine and gains availability columns rather than an Ollama warehouse.

Privacy for all request text is restricted and is not stored. Durations, counts, digests, and byte sizes are operational.

## M. Metric availability matrix

| Metric | Unit | vLLM now | Ollama official |
|---|---|---|---|
| runtime version | text | OBSERVED from the generation | OBSERVED from /api/version |
| install footprint | bytes | unmeasured for ROCm, ESTIMATED or UNRESOLVED | UNRESOLVED until a prefix is measured |
| install time | seconds | not a lab column | OBSERVED when Machi times provision |
| acquisition bytes | bytes | OBSERVED artifact total | OBSERVED tags.size after pull |
| acquisition time | seconds | not separated | OBSERVED if Machi times pull |
| model digest | text | git revision plus artifact id | OBSERVED tags or ps digest |
| quant and family | text | OBSERVED from config | OBSERVED from details after pull |
| fit verdict | enum | Machi predicates | NOT_EXPOSED as a pre-load verdict |
| estimated requirement | bytes | ESTIMATED | ESTIMATED only if Machi computes one |
| specialist memory | bytes | HIDDEN_INTERNAL inside vLLM | OBSERVED size_vram only after load |
| reserved resources | bytes | OBSERVED reservation | OBSERVED reservation, same Machi record |
| observed RAM and VRAM | bytes | partially sampled | size_vram OBSERVED; host RAM still Machi |
| context | tokens | OBSERVED plan setting | requested num_ctx; running context_length OBSERVED on ps |
| concurrency | count | OBSERVED plan setting | OLLAMA_NUM_PARALLEL is configuration; scheduler behavior HIDDEN_INTERNAL |
| startup and load | nanoseconds or seconds | OBSERVED load_seconds | OBSERVED load_duration |
| readiness | bool | OBSERVED /health | OBSERVED /api/version only |
| input tokens | count | not separately stored | OBSERVED prompt_eval_count |
| output tokens | count | OBSERVED completion tokens | OBSERVED eval_count |
| prompt eval duration | nanoseconds | NOT_EXPOSED | OBSERVED prompt_eval_duration |
| generation duration and rate | nanoseconds and tokens/second | rate DERIVED | duration OBSERVED; rate DERIVED |
| TTFT | seconds | NOT_MEASURED on the vLLM proof | NOT_EXPOSED; DERIVED only from a stream Machi times |
| request latency | nanoseconds | not a separate lab field | OBSERVED total_duration, which includes load |
| errors | text | OBSERVED failure | OBSERVED HTTP or done_reason |
| unload and restart | text | OBSERVED stop and re-infer | OBSERVED if Machi calls keep_alive 0 and loads again |
| cost and run duration | USD and seconds | lab columns exist | same lab columns, provider-neutral |

A hidden Ollama value is stored as HIDDEN_INTERNAL, not as an empty number.

## N. Empirical-lab changes required

Extend empirical_case. Do not add a second database. Chunk 2 or 3 should add nullable text availability columns and, when first needed, prompt_eval and eval durations, digest, ollama_version, and load_duration. Existing vLLM rows remain valid with availability UNRESOLVED or NOT_APPLICABLE for Ollama-only fields.

## O. Security, privacy, and license findings

Ollama v0.34.3 software is MIT. Redistribution in a managed prefix must keep that license notice. Model license strings from /api/show are not the MIT software license and are not automatic commercial approval.

The local API has no authentication. Bind must stay 127.0.0.1. Do not set OLLAMA_HOST to a public address. Do not store OLLAMA_API_KEY. Set OLLAMA_NO_CLOUD=1 for the happy path.

Official upgrades on macOS and Windows are automatic. A pinned Machi generation must not follow that. Linux upgrade is a reinstall. That is a mutation and must be an explicit generation change.

Optional ROCm and MLX tarballs are separate assets. Their license was not separately identified beyond the repository MIT license. Treat an unverified extra asset as review-required before redistribution.

Customer prompts and responses stay out of lab rows. Generate responses used as proof must be reduced to counts, durations, digest, and done_reason.

## P. Canonical docs that are stale or contradictory

No canonical file was edited. These need a later correction if the Lead accepts this gate:

- docs/STRATEGY.md still says current hosts do not ship vLLM product code. The partial L40S pass contradicts that sentence. The vLLM-primary and Ollama-fallback policy itself still matches this review.
- docs/machi/ARCHITECTURE.md says AUTO refuses when vLLM is unsupported and does not substitute Ollama. STRATEGY says AUTO falls back to Ollama. Those two product policies disagree. This review follows STRATEGY for the future macropath and leaves the code on the architecture rule until Chunk 2 is approved.
- docs/machi/ROADMAP.md still says the Ollama path is repositioned and not implemented. That is accurate today. It should not be marked implemented by this chunk.
- The untracked docs/machi/proposals/MACROPATH-*.md files are not canonical. Where they disagree with STRATEGY, STRATEGY wins.

## Q. Exact proposed Chunk-2 implementation scope

Only after Lead acceptance:

- Pin Ollama 0.34.3.
- Linux and NVIDIA only.
- Verified-existing path: observe version, loopback, cloud disabled, and /api/version.
- No model pull and no inference proof in Chunk 2.
- Record install or discovery analytics with explicit availability.
- Do not add FoundationEngine.OLLAMA until the provider decision in section R is accepted.
- Do not extract a tarball into /usr.

Managed prefix, AMD, Docker, and cloud models are outside Chunk 2 unless the Lead explicitly adds them.

## R. Provider Selection Gate decisions requiring Daniel/Lead

1. Accept verified-existing local Ollama as the first implementation, yes or no.
2. Accept a Machi-owned prefix for the official Linux tarball, or forbid managed install because the official path mutates /usr and systemd.
3. Confirm v0.34.3 as the pin.
4. Confirm cloud models and ollama.com are out of the happy path.
5. Confirm AUTO fallback to Ollama is future policy only, and that today's code stays fail-closed until that fallback is implemented.
6. Confirm FoundationEngine may gain an ollama value later without a new macropath type.

None of these were decided by this chunk.

## S. Architecture risks and credible alternatives

Risk: treating /api/ps after an unadmitted load as a free fit probe. That would execute before admission. The recommended alternative is to estimate before admission and treat size_vram as observed evidence only after a reservation.

Risk: equating a tag with a digest. The alternative is to bind the digest immediately after pull and invalidate on mismatch.

Risk: copying the vLLM predicate probe into Ollama. The alternative is to keep that probe on the vLLM adapter only.

A credible smaller alternative is verified-existing only, forever, with no managed prefix. That avoids /usr mutation and still proves the tunnel. It cannot help a host with no Ollama binary.

## T. Future Dynamo compatibility check

The generic names to keep are foundation family, engine, execution-environment fingerprint, DeploymentConfiguration, ResourceRequest, reservation, proof, and metric availability. They do not assume one process, one store, one GPU, or one scheduler.

Do not put Ollama digest, num_ctx, or keep_alive into Core field names. Those stay in the Ollama adapter. Do not put vLLM argv flags into Core. The current plan recipe is already vLLM-specific and should remain an adapter.

Dynamo is not designed here. The tunnel boundary is local. A later fabric would be another engine under the same outer control, with worker topology delegated the way Ollama placement is delegated.

## U. Branch and checkpoint status

- Recovery ref origin/checkpoint/native-vllm-partial-pass-2026-09-24 is 6e17f4a817d1571e0a708decec405ceda0282c7f.
- Integration ref origin/automation/ollama-macropath is the same commit.
- No branch was moved.
- No product, test, evidence, or architecture file was edited.

## V. Exact final state

Chunk 1 is a review. The native-vLLM partial pass is unchanged. The next authorized action is Lead review. Chunk 2 is not started.

NO_PRODUCT_IMPLEMENTATION_PERFORMED
NO_SERVER_CREATED
STOP — OLLAMA CHUNK 1 ARCHITECTURE GATE COMPLETE. WAIT FOR LEAD REVIEW.

==================== END PASTE BACK — OLLAMA CHUNK 1 ====================
