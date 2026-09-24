==================== BEGIN PASTE BACK — OLLAMA BUNDLE 06 ====================

A. STATUS / actions executed
Executed `MACHI-OLLAMA-BUNDLE-06-CLOSURE-FALLBACK-001` from `ebfabe56b2ae09b916e5e70ea4d2b1c028f48af6`.
Closed the provider Serve identity check, separated `renv_` from `fgen_`, added sequential schema migration with FileStore rewrite-on-read, hardened STOP reconciliation, ran local gates, re-proved the corrected chain on one owned NVIDIA A40, and implemented local AUTO preference. Did not start physical live failover, model translation, AMD, Dynamo, or UI work.

B. Starting SHA / physical passing SHA / final SHA
Starting integration HEAD: `ebfabe56b2ae09b916e5e70ea4d2b1c028f48af6`
Physical passing source: `9813f72797875f21eaf68e43bb570784d8c37580`
Physical wheel: `0.1.0+9813f7279787` SHA256 `6e8068c81eeb2c3e124487c568c468c1d599d7948990403654a5594df1e1461b` size 327666
Final source: `92555da8e3465cd1596098eb33579d31e1a12ae6`
Final wheel: `0.1.0+92555da8e346` SHA256 `f6e94a0f7969237461435af32b2cac0ee089dd4b3c847e0c7f1970e4e919b759` size 327667
The final commit adds the physical record and program status only. It does not change Python. `origin/automation/ollama-macropath` equals the final SHA.

C. Product outcome achieved
A provider Plan/Serve deployment on the tested A40 was bound to the verified foundation generation `fgen_66a0af2ac4ba618c` and digest `2d470404841a51320639b2c2418c7ad8643cccbbcb88c2a242b211ae83bf46a9`. Historical qualification v1 stays readable and does not cover a current plan. Local AUTO prefers healthy/supported native vLLM and selects an independent Ollama chain only when native vLLM is unavailable by policy.

D. renv vs fgen reconciliation result
`renv_` is `runtime_environment_id()` of the managed artifact. `fgen_` is `ollama_generation_id()` on the verified substrate. Bundle 05 qualification and Plan cited `renv_ceedac1939fecd21` as the generation. That was the runtime-environment id, read from the code path, not from the prose. The corrected path records both. New provider plans refuse a generation id that does not start with `fgen_` and refuse a foundation id that starts with `renv_`. Serve refuses a verified runtime id that is not an `fgen_`. Historical records that already stored `renv_` still decode.

The execution fingerprint cannot contain the `fgen_` it creates, because the generation hash includes the fingerprint. `runtime_bound_execution_fingerprint` names the `renv_` input as a runtime environment id and reuses the existing hasher. On this A40 that produced the same `exe_7efc404ce831bb9bbfa4606bcfbfe224` as Bundle 05. The plan generation is the separate `fgen_`.

E. Bundle-05 evidence disposition
The A40 lifecycle in `docs/machi/OLLAMA-BUNDLE-05-PHYSICAL.md` remains provider-functional, including exact context 2048 and the STOP/restart/release sequence. It is not generation-bound. The checkpoint field that was labeled a generation is now `runtime_environment_id`, with `foundation_generation_id` `not_recorded`. Bundle 04 is labeled the same way. `checkpoint/ollama-authorized-serve-2026-09-24` was not moved and still points at `ebfabe56b2ae09b916e5e70ea4d2b1c028f48af6`.

F. Serve actual-Foundation binding implementation
`ProviderServeService.start` takes `VerifiedProviderRuntime` (provider, generation id, execution-environment fingerprint, ready). Before residency refresh it requires ready, the same provider, an `fgen_` generation equal to the plan, and the same execution fingerprint, plus the existing reservation and coverage checks. `start_ollama` builds that value from the already verified `OllamaAssessment`. Serve does not re-run Foundation verification and does not contain the Ollama token.

G. Wrong/stale Foundation refusal QA
Local tests refuse a wrong generation, a wrong execution fingerprint, an unready runtime, an unresolved assessment, the same digest on another generation, and a `renv_` runtime id, all before residency refresh. On the A40, after a proven stop, `service.start` with generation `fgen_stale_not_this_host` returned `foundation_mismatch`. The daemon was not edited. A later start after explicit release returned `reservation_released`.

H. Schema migration mechanism / Kernel behavior
`register_upgrade` stores one step from version n to n+1. `from_dict` migrates before decode. Unknown kinds and versions fail closed. An upgrade must advance exactly one version and must not change kind. FileStore, on get of an older file, replaces that file with the current contract and appends one line to `_schema_migrations.jsonl` (kind, key, from version, to version). A second read does not append another line. The journal is not rewritten. In-memory `from_dict` does not rewrite the source file.

I. Ollama qualification v1 -> current migration truth
Shipped v1 had no `context_binding` and no `provider_fit`. The upgrade sets `schema_version` 2, `context_binding` `not_sent`, and `provider_fit` `unresolved`. Digest, outcome, token proof, and the other recorded fields are copied. A migrated PASS stays a PASS and does not cover a provider plan, because coverage still requires schema 2, `context_binding` `requested`, and provider fit `FIT`. Current v2 evidence with `requested` and `FIT` still covers.

J. Inventory of all current versioned contract bumps
Registered kinds above version 1 are only `model.qualification@2` and `model.ollama_qualification@2`. Both have a v1 to v2 upgrade. `model.qualification` v1 becomes v2 with `execution_environment_fingerprint` `not_recorded`, and `covers()` rejects that sentinel. No other kind has a shipped older persisted shape, so no other upgrade is registered.

K. K-03 disposition and evidence
K-03 stays OPEN. The functional path now exists: registered upgrades, rewrite-on-read, and a migration note. The retire-when text required that path before the first schema bump. Those two bumps already shipped, so the timing condition cannot be met retroactively. The ledger says so. It is not marked RETIRED.

L. Provider STOP/reconciliation behavior
STOP still unloads and polls for absence for a bounded time. If absence is not proved, the instance stays STOPPING, the reservation stays reserved, and success is not claimed. `reconcile()` re-reads only STOPPING instances. Absence becomes STOPPED without release. Wrong identity, unresolved provider state, or a still-resident digest is reported and does not become STOPPED. Release remains an explicit ResourceManager action. Local tests cover lagged absence and a wrong identity that stays STOPPING.

M. Local functional QA
Targeted tests covered generation/fingerprint refusal, v1 readback and non-coverage, v2 coverage, migration idempotence, unknown version/kind, renv/fgen separation, STOP reconciliation without release, native and provider regression through the existing suite, and AUTO cases 1–9. `pytest tests/machi` passed on the physical source. One archive-progress test failed once under load with an empty extract and passed on rerun; it was not changed. Architecture checks are inside that suite. `ruff check` passed. `mypy --strict src/machi` passed, 177 files. Customer prompts are absent from the decision and proof records under test.

N. Candidate wheel build/SHA/isolated verify
Physical candidate: clean source, `verify_ok`, SHA256 `6e8068c81eeb2c3e124487c568c468c1d599d7948990403654a5594df1e1461b`.
Final docs candidate: clean source, `verify_ok`, SHA256 `f6e94a0f7969237461435af32b2cac0ee089dd4b3c847e0c7f1970e4e919b759`.
Untracked `docs/machi/proposals/` stayed uncommitted and was parked only while the tree was required to be clean for the wheel.

O. RunPod preflight / owned Pod
`runpodctl user` balance `15.5042969845`, spend limit 80, existing spend 0.113 per hour from resources that were not touched. Secure A40 stock was LOW at CUDA 13.0 in EU-SE-1 and CA-MTL-1, secure price $0.49 per hour. Created only `machi-b06-identity` (`34kxih08i7lo5x`), secure, CUDA 13.0, EU-SE-1, disk 40 GB, no network volume. No pre-existing pod was started, stopped, or terminated.

P. Physical host / renv / fgen / execution fingerprint
NVIDIA A40, compute 8.6, driver 580.159.03, host CUDA 13.0. SAFE host `49463128064`. SAFE accelerator `48037363712`. Runtime environment `renv_ceedac1939fecd21`. Foundation generation `fgen_66a0af2ac4ba618c`. Selection `fsel_66a0af2ac4ba618c`. Fingerprint `exe_7efc404ce831bb9bbfa4606bcfbfe224`. Daemon ready, version 0.34.3, cloud disabled.

Q. Context-2048 qualification result
Tag `smollm2:135m-instruct-q8_0`. Digest `2d470404841a51320639b2c2418c7ad8643cccbbcb88c2a242b211ae83bf46a9`. Generation `fgen_66a0af2ac4ba618c`. Binding `requested`. Fit `FIT`. Outcome `PASS`. Runner `-c 2048` and `n_ctx_slot` 2048. Shadow unresolved. Classification `MACHI_UNRESOLVED`. `load_seconds` unresolved. Probe `qprb_8b4816fb997f0e11`, reservation `rsv_6c5fd204aba3b7f0`, release `rel_394957677b8c7802`. Event `evt_7a6e415a54a6d523`.

R. Corrected provider Plan/Admit result
Plan `plan_c84309834a08c096` cited `fgen_66a0af2ac4ba618c`, not the runtime environment id. Admission `admitted` as `rsv_bc98167eb167e0b5` on the same ResourceManager ledger, full cited SAFE host and accelerator bytes, persistent 0.

S. Corrected Serve exact runtime+digest proof
Start ready, instance `pin_e4aba1a070c2a081`, generation `fgen_66a0af2ac4ba618c`. Proof `pprf_ca1bffebb777028f` proven. Same digest. 8 output tokens. 0.031081 seconds. 257.3919758051543 tokens per second. `size_vram` 205384580, runtime-reported. No prompt or response text stored.

T. STOP / absence / release proof
STOP outcome `stopped`. Reservation still reserved at that point. Stale generation then refused with `foundation_mismatch`. Explicit release `rel_38c15f1aa140926c`. Later start refused `reservation_released`. Active reservations empty.

U. Pod termination proof
`delete-pod` for `34kxih08i7lo5x` returned 204. Subsequent `get-pod` returned 404.

V. AUTO fallback control-plane design
`decide_runtime` in `foundation/fallback.py` records `foundation.runtime_choice` version 1, policy `m5.fallback.1`. AUTO selects vLLM when primary support is READY or SUPPORTED. AUTO selects Ollama only when primary is UNSUPPORTED, UNAVAILABLE, BLOCKED_BY_PREREQUISITE, INSUFFICIENT_CAPACITY, PROVISIONING_FAILED, or VERIFICATION_FAILED, and Ollama is READY or SUPPORTED. CONDITIONALLY_SUPPORTED and RECONCILE_REQUIRED do not fall back. Explicit modes do not consult the other engine. An Ollama AUTO selection sets recompute to `foundation,model,plan,admit,serve`. `execute_runtime_choice` dispatches to injected callables and does not retry inside Serve. `FoundationSelection` remains the macropath decision.

W. AUTO healthy-vLLM preference proof
AUTO with primary READY or SUPPORTED selects vLLM, recompute `none`, and the local test does not call the Ollama callable.

X. AUTO vLLM-unavailable -> Ollama fresh-chain proof
AUTO with primary UNSUPPORTED and Ollama READY selects Ollama and requires the full recompute chain. The local test composes a provider plan, admits it on the same ResourceManager, and starts provider Serve. The native reservation is released explicitly before that admission because a provider plan reserves the full cited SAFE ceiling. The fallback function itself does not release.

Y. Explicit VLLM/OLLAMA fail-closed proof
Explicit vLLM with primary UNAVAILABLE refuses and records fallback support `not_consulted`. Explicit Ollama with VERIFICATION_FAILED refuses and records primary support `not_consulted`. Executing a refusal raises. Neither available refuses. Unresolved Ollama support refuses.

Z. Proof fallback does not reuse stale model/Plan/reservation/instance
The local Ollama chain produced a different plan id, reservation id, and instance id from the native admission. Catalogs stay separate. No native model id is written into the provider digest.

AA. Decisions/deviations from recommendations
The recommended shapes were used: a small verified-runtime value, a per-kind upgrade registry, and a decision seam above Serve. The adapter owns the Ollama mapping because the serve package must not contain that token. v1 Ollama evidence gains `provider_fit` `unresolved` because that field did not exist; it is not set to FIT. K-03 was not retired. The fingerprint helper still feeds `renv_` into the existing hash slot under a name that says it is not an `fgen_`. Physical proof omitted the Bundle 05 restart/re-infer loop and kept start, proof, stop, stale refusal, release, and post-release refusal.

AB. Architecture amendments encountered, if any
No product-policy amendment and no second macropath object. `docs/machi/ARCHITECTURE.md` now states the accepted AUTO rule and that `foundation.runtime_choice` is not a substitute for `FoundationSelection`. The roadmap status matches that scope and does not mark the macropath closed.

AC. Exact support claim earned
Machi can physically bind an Ollama provider Plan/Serve deployment to the actual verified Foundation generation and exact model digest on the tested NVIDIA environment, preserve historical provider qualification evidence across schema evolution without strengthening it, and locally enforce a deterministic AUTO policy that prefers healthy/supported native-vLLM and selects an independently valid Ollama fallback path only when the primary Foundation is unavailable by policy.

Not claimed: physical automatic live failover, runtime switching after arbitrary inference failure, automatic equivalent-model translation, NVIDIA-wide Ollama support, production HA, or multi-host/fleet fallback.

AD. Remaining debt / Chunk-6 work not yet closed
K-03 remains OPEN because the migration path landed after the first bumps. M-5-OLLAMA-01, M-5-OLLAMA-04, M-6-OLLAMA-01, M-6-03, M-9-02, and M-5-AMD-01 stay open. Model pull is still operator lab setup, not product acquisition. Physical AUTO failover is not implemented. The Ollama macropath is not fully closed.

AE. Full final gates / local==origin / checkpoint
`pytest tests/machi`, architecture checks, ruff, and strict mypy passed on the physical source. Both wheels were clean and `verify_ok`. Final HEAD `92555da8e3465cd1596098eb33579d31e1a12ae6` equals `origin/automation/ollama-macropath`. New recovery branch `checkpoint/ollama-generation-bound-serve-2026-09-24` points at that final SHA and was pushed. `checkpoint/ollama-authorized-serve-2026-09-24` remains `ebfabe56b2ae09b916e5e70ea4d2b1c028f48af6`. `checkpoint/native-vllm-partial-pass-2026-09-24` was not moved.

AF. Final status
STOP — OLLAMA BUNDLE 06 COMPLETE. WAIT FOR LEAD REVIEW.

==================== END PASTE BACK — OLLAMA BUNDLE 06 ====================
