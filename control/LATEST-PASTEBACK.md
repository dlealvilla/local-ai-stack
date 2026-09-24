==================== BEGIN PASTE BACK — OLLAMA BUNDLE 05 SERVE ====================

A. STATUS / slices completed
Context-truth correction, provider Plan/Admit, bounded Ollama Serve, local gates, physical requalification at context 2048, physical Plan → Admit → Serve, digest proof, STOP/restart/re-infer/STOP/release/refusal, evidence, docs, and checkpoint.
AUTO fallback, multi-model serving, and UI were not started.

B. Starting/final source SHA
Starting integration HEAD: ea9cb26a6034eeaca1058d6635ee4008fc833bed
Physical passing source: 9285af1057de2ed06f5d11090ee1459a1787ae1b
Final source HEAD: ebfabe56b2ae09b916e5e70ea4d2b1c028f48af6
Branch: automation/ollama-macropath
The final SHA adds the evidence note and checkpoint record. The host ran the preceding source.

C. Product outcome achieved
On this exact A40 host, Machi qualified smollm2:135m-instruct-q8_0 at context 2048, created a provider-backed plan without a warehouse artifact, admitted it on the shared ResourceManager ledger, served a real token with digest proof before and after, stopped without releasing the reservation, restarted and proved again, stopped, released, and refused a later start.

D. Accepted Option-A implementation shape and any deviation from recommendation
Sibling contracts: ProviderDeploymentConfiguration, ProviderResourceRequest, and ProviderPlanDecision. They do not reuse artifact_id, immutable_revision, or dtype.
Admission is admit_provider on the existing ResourceManager. It writes the existing ResourceReservation and uses the same fit accounting.
Serve evidence is ProviderServingInstance and ProviderInferenceProof, not ServingInstance.artifact_id.
Deviation from the recommended file layout: the architecture check forbids the token "ollama" inside src/machi/serve. The generic lifecycle is ProviderServeService. The Ollama HTTP adapter and the qualification-coverage gate are in adapters/serve/ollama.py. Binding semantics are unchanged.

E. Context-truth correction
Preload and the token probe send options.num_ctx equal to the requested context.
Unload does not send num_ctx.
OllamaQualificationEvidence is schema version 2. context_binding is "requested" only after num_ctx was sent. A pass requires that binding.
qualification_covers accepts only schema 2, binding requested, FIT, PASS, the same digest and generation, concurrency 1, and a requested context at or below the qualified context.

F. Qualification coverage semantics / old Bundle-04 evidence treatment
docs/machi/OLLAMA-BUNDLE-04-PHYSICAL.md is marked historical provider-functional evidence. It is not exact context-2048 coverage, because that run did not send num_ctx and the runner used 8192.
Version 1 evidence cannot cover a provider plan.

G. Provider-backed Plan/configuration identity
The plan fingerprint is salted "provider-plan" and uses the digest, not the display tag.
Fields include plan id, provider, display name, canonical digest, candidate id, foundation, generation, execution fingerprint, capacity evidence, accelerator, context, concurrency 1, qualification id, and settings.
Bytes requested are the cited snapshot's full SAFE host and accelerator ceilings. Persistent bytes are 0 because the model is already local. That matches native single-accelerator reservation sizing and is not admit_probe.

H. ResourceRequest / one-ledger admission behavior
admit_provider refuses a plan that is not planned, a stale capacity id, an unknown device, or a hold that does not fit beside existing reservations.
A native hold and a provider hold are summed on the same ledger. Tests show a native reservation of part of the SAFE ceiling makes a full-ceiling provider request fail with insufficient host memory.
execution_authorized_provider checks plan id, fingerprint, and accelerator identity. Residency is not consulted.

I. Native Plan/Admit regression proof
Native DeploymentConfiguration, ResourceRequest, admit(), and ServeService were not retargeted.
Full tests/machi, including the native admit and serve suites, passed after the provider path was added.

J. Ollama Serve lifecycle implementation
start_ollama requires qualification_covers for the plan digest, generation, context, and concurrency, then ProviderServeService.
Start refreshes residency with num_ctx, then requires /api/ps expected_resident before an instance is recorded.
Prove observes the digest, infers once at the plan context, then observes the same digest.
STOP unloads and polls /api/ps until the digest is absent or a short bound expires. It does not call ResourceManager.release.
A still-reserved plan can start again. A released reservation is refused.

K. Provider identity proof before/after inference
Physical proof digest: 2d470404841a51320639b2c2418c7ad8643cccbbcb88c2a242b211ae83bf46a9
Both the first and the restarted inference returned proven, which is recorded only when the digest is expected before and after the token.
Output tokens on the first proof: 8.

L. STOP vs reservation-release behavior
First STOP outcome: stopped. Reservation rsv_c35b573fb7806719 state after that STOP: reserved.
Release id: rel_72cfb9f0e2dc0a74. Outcome: released.
A start after release was refused with reservation_released. Active reservations: none.

M. Restart/re-entry behavior
After the first STOP, start on the same reservation returned ready.
The second inference returned proven.
The second STOP returned stopped.
The later start after release was refused.

N. Durable Serve/Inference proof and analytics
Journal events included model.qualification.compared (evt_fbaa03f0eae61dee), serve.provider.ready, serve.provider.inference, and serve.provider.stopped for both cycles, then serve.provider.failed only for the post-release refusal.
The inference payload is ProviderInferenceProof. It stores digest, token counts, generation seconds, tokens per second, and runtime-reported size_vram. It does not store prompt or response text.
First proof: generation_seconds 0.057342, tokens/sec 139.5137944264239, size_vram 205384580, semantics runtime_reported.

O. Local QA / functional acceptance
Context is present on preload and token bodies in the HTTP test.
A wider context than the qualification is refused.
Provider plan JSON has no artifact_id, immutable_revision, or dtype.
Stale capacity is refused.
Missing reservation does not serve.
Wrong digest does not infer.
Unload that leaves the model resident does not mark STOPPED and does not release.
A digest that disappears on a later /api/ps read does stop, and the reservation stays reserved.
Released reservation cannot restart.

P. Candidate build ID/SHA256 / isolated verify_ok
Physical wheel that passed on the host:
build 0.1.0+9285af1057de
SHA256 40fb7420db7687a24a13f5ce1883582270e7cadbac4b78af809cd66e7b06e2a4
size 322420
source 9285af1057de2ed06f5d11090ee1459a1787ae1b
clean_source true
isolated verify_ok.
Final wheel after the evidence commit:
build 0.1.0+ebfabe56b2ae
SHA256 d2efb52f978ea938a17d3406eaef60880aef674e7e43531929c6447de115129f
size 322422
source ebfabe56b2ae09b916e5e70ea4d2b1c028f48af6
clean_source true
isolated verify_ok.

Q. RunPod preflight / owned Pod
Balance before create: 15.816683556 USD. Spend limit 80. Existing spend was not this pod.
Secure L40S was out for CUDA 12.8 and 13.0. Two community L40S creates at the probed $0.79 rate did not place.
Third create: secure NVIDIA A40, CUDA 13.0, EU-SE-1, returned cost 0.49 USD/hour, under 1.50.
Pod tt6xs8su1zhn9o, name machi-ollama-bundle-05. No network volume. No other pod was changed.
Image runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404. SSH only.

R. Physical host identity / managed Foundation
NVIDIA A40, compute capability 8.6, driver 580.159.04, CUDA 13.0.
SAFE host 49463128064. SAFE accelerator 48037363712.
Managed prefix generation renv_ceedac1939fecd21. Support ready. Version 0.34.3. Cloud disabled.
Fingerprint exe_7efc404ce831bb9bbfa4606bcfbfe224.
Pinned archive sha256 e83a089fd0cd2f79ee2933cca2085846a2065f497adbc6467c402177c68423f9.
System zstd remained a host tool. M-5-OLLAMA-04 stays open.

S. Context-2048 physical requalification
Cold qualification at context 2048, concurrency 1.
Digest absent before. Provider FIT. Outcome PASS. Shadow unresolved. Cleanup released the qualification hold.
Runner flag -c 2048. n_ctx_slot 2048. context_binding requested.
load_seconds not_measured.

T. Normal provider Plan/Admit physical result
Plan failure none. Admission admitted.
Reservation rsv_c35b573fb7806719. Plan plan_2484830f9776b44b.
Accelerator bytes 48037363712. Host bytes 49463128064. Persistent bytes 0.
This was admit_provider, not admit_probe.

U. Real Serve inference proof
Start ready. Proof proven. Same digest. 8 output tokens.
size_vram 205384580, runtime-reported from /api/ps.

V. STOP -> restart -> re-infer -> STOP -> release -> refusal proof
stopped, reservation still reserved, restart ready, second proof proven, second stop stopped, release released, subsequent start refused with reservation_released, active list empty.

W. Physical analytics / residency / VRAM provenance
Qualification comparison and provider serve events are in the journal named in N.
VRAM is ollama.api.ps size_vram, semantics runtime_reported, not a measured peak.
The first physical attempt's second STOP raced /api/ps and failed closed. The product now waits briefly for absence. The passing run used that fix. The reservation was not released by the failed STOP.

X. Implementation defects found/fixed during run
The second STOP observed the model still resident immediately after a successful keep_alive 0. Stop now polls /api/ps for absence and fails only if the digest remains. Local test covers both the lag and the still-resident refusal.

Y. Architecture amendments encountered, if any
None. Option A semantics were kept. The serve-package naming split is the deviation in D, forced by the existing boundary test, not a change of authority.

Z. Exact support claim earned
On this exact secure NVIDIA A40, driver 580.159.04, CUDA 13.0, Ollama 0.34.3 generation renv_ceedac1939fecd21, and digest 2d470404841a51320639b2c2418c7ad8643cccbbcb88c2a242b211ae83bf46a9 at context 2048 and concurrency 1, Machi created a provider-backed model-serving plan, admitted it through the same ResourceManager ledger as native workloads, served real Ollama inference with digest proof, stopped and restarted under the held reservation, and released resources explicitly.
Not claimed: L40S or NVIDIA in general, other contexts or models, multi-model scheduling, local-process enforcement, AUTO fallback, a runtime winner, AMD, or UI readiness.
This host is not the Bundle 04 L40S.

AA. Remaining debt / non-scope
M-5-OLLAMA-01 loopback authentication stays open.
M-5-OLLAMA-02 RuntimeCapability text stays open.
M-5-OLLAMA-04 system zstd stays open.
M-6-OLLAMA-01 stays open: Serve checks the digest and does not own Ollama's scheduler.
Empty preload still omits load_duration, so load_seconds stays not_measured when the provider omits it.
AUTO fallback, multi-model serving, and UI were not started.

AB. Pod termination proof
delete-pod tt6xs8su1zhn9o returned 204.
get-pod tt6xs8su1zhn9o then returned 404.

AC. Final tests/package gates
mypy --strict src/machi passed, 175 files.
ruff check src/machi tests/machi passed.
pytest tests/machi passed, including native admit/serve and the provider lifecycle tests.
Both wheels above isolated-verified with verify_ok.
docs/machi/proposals/ remains untracked.

AD. Local/origin equality / checkpoint
Recorded after the push in the published control paste-back status.
Recovery checkpoint branch: checkpoint/ollama-authorized-serve-2026-09-24 at the final source SHA.
The native vLLM recovery checkpoint was not moved.

AE. Final status
STOP — OLLAMA BUNDLE 05 SERVE COMPLETE. WAIT FOR LEAD REVIEW.

==================== END PASTE BACK — OLLAMA BUNDLE 05 SERVE ====================
