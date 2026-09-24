==================== BEGIN PASTE BACK — OLLAMA BUNDLE 07 CLOSURE ====================

A. STATUS / closure outcome
`CLOSED_NVIDIA_STAGE1`
Executed `MACHI-OLLAMA-BUNDLE-07-NVIDIA-CLOSURE-001` from `92555da8e3465cd1596098eb33579d31e1a12ae6`. AMD preflight failed closed on stock. NVIDIA closure continued and met the mandatory criteria, including a physical AUTO fallback on an isolated owned root.

B. Starting SHA / physical passing SHA / final SHA
Starting integration HEAD: `92555da8e3465cd1596098eb33579d31e1a12ae6`
Physical passing source: `fc216642cd6d3e2f77c8bbaa53f2fe22f6bb658a`
Physical wheel: `0.1.0+fc216642cd6d` SHA256 `f88725b7c87e8a3a10c8eb0f13d696c2116d92a98a2b9e1047943834e103e536` size 329644
Final source: `2c12f00286d6e7d6d524baa7a7787099e476bf08`
Final wheel: `0.1.0+2c12f00286d6` SHA256 `e232a2b1e1b0b39d0ffc0650271d69e38f502adb832a7cf54f83e17994830319` size 329642
The final commit records evidence and program status. It does not change Python. `origin/automation/ollama-macropath` equals the final SHA.

C. Product capability closed
On the qualified NVIDIA A40 configurations, Machi has a verified native/vLLM foundation and a separately qualified Ollama compatibility path. AUTO keeps vLLM when that foundation is ready, and it can select a fresh Ollama plan and reservation when product code reports an approved primary failure. One ResourceManager ledger and separate catalogs remain. AMD is not closed.

D. Migration durability design and recovery proof
FileStore writes a per-record receipt under `_schema_migration/<kind>/<key>.json` with phase `intent`, then replaces the record, then sets phase `complete`. The receipt and the record are separate files. This is not claimed to be cross-file atomic. If the intent write fails, the historical record is left untouched. If the record rewrite fails, the intent remains and a later read finishes the rewrite and the receipt. If completion fails after the record is current, the open intent stays visible and the next read only completes the receipt. A complete receipt does not upgrade a record that is still historical. A second successful read does not rewrite the receipt. Receipts contain kind, key, versions, and phase only.

E. K-03 final disposition
RETIRED (Bundle 07, 2026-09-24). The functional and durability requirements are met. The entry history still says the path landed after the first schema bumps, so the original timing gate was missed.

F. RuntimeChoice concrete Foundation evidence design
`decide_runtime` now takes the FoundationSelection values that were actually consulted. A new choice records each side's engine, support, failure, selection id, and capacity evidence id, plus the observation time. Explicit modes record `not_consulted` for the side they do not read, even if a selection is passed in. The decision id includes those references, so a later selection does not rewrite an existing choice.

G. RuntimeChoice schema compatibility if changed
`foundation.runtime_choice` is now version 2. Version 1 migrates by keeping the recorded mode, supports, outcome, and reason, and by setting the new identity fields to `not_recorded` when that side was consulted and `not_consulted` when it was not. `observed_at` becomes `not_recorded`. Migrated v1 evidence does not gain a real selection id. Policy version stays `m5.fallback.1` because the selection rule did not change.

H. Local AUTO/regression closure QA
`pytest tests/machi` passed. Architecture checks are in that suite. `ruff check` passed. `mypy --strict src/machi` passed, 177 files. Local tests cover healthy vLLM preference, unresolved refusal, approved unavailable fallback with a new plan and reservation, explicit fail-closed modes, historical runtime-choice migration, migration interruption at intent, record rewrite, and completion, and refusal of a false complete receipt.

I. Candidate wheel / SHA256 / isolated verify
Physical candidate and final docs candidate both built from a clean tree and returned `verify_ok`. Hashes are in section B. Untracked `docs/machi/proposals/` stayed uncommitted.

J. AMD RunPod preflight facts
Balance `15.4042087098`. Spend limit 80. Existing spend 0.113 per hour from resources that were not touched. Secure MI300X availability `NONE`, price $2.39 per hour, inside the $4 AMD cap. Secure MI350 availability `NONE`, price $5.49 per hour, outside that cap. A 45-minute MI300X run would have fit the balance floor if stock had existed. No AMD pod was created.

K. AMD optional attempt/result, or exact reason not attempted/successful
`NO_STOCK`. The approved MI300X target had no secure pod stock. AMD qualification was not attempted. `M-5-AMD-01` stays open. This did not block NVIDIA closure.

L. NVIDIA host ownership/price/lifecycle
Created only `machi-b07-closure` (`5vckhyhjmjht55`), secure A40, EU-SE-1, CUDA 13.0, disk 80 GB, no network volume, $0.49 per hour. Created `2026-09-24T13:57:37.59Z`. SAFE host `49463128064`. SAFE accelerator `48037363712`. Driver 580.159.04.

M. Real native Foundation observation
Product provision returned ready. Selection `fsel_17d3aa41babb8ffa`. Generation `fgen_6e4c419798416a74`. Capacity evidence `cap_ollama_b07`. Manifest: vLLM 0.18.0, Python 3.12.3, torch 2.10.0+cu130, backend runtime 13.0. The support state was not hand-authored.

N. Real Ollama Foundation observation
Runtime environment `renv_ceedac1939fecd21`. Foundation generation `fgen_66a0af2ac4ba618c`. Selection `fsel_66a0af2ac4ba618c`. Fingerprint `exe_7efc404ce831bb9bbfa4606bcfbfe224`. Support ready. Capacity evidence `cap_ollama_b07`.

O. Physical AUTO healthy-primary decision evidence
Decision `fbk_fa5314e89fc227d3` requested `auto`, selected `vllm`, reason "native vLLM is healthy or supported", recompute `none`. It cited primary selection `fsel_17d3aa41babb8ffa` and fallback selection `fsel_66a0af2ac4ba618c`. Active reservations were unchanged, so no Ollama plan or admission was created.

P. Optional native selected-path inference result
Not run. The verified native foundation was ready and AUTO selected it. This host had no warehouse model loaded for a native serve, and starting one was outside the bounded selection proof.

Q. Physical fallback-selection attempt method and safety rationale
A second provision on the healthy root reused generation `fgen_6e4c419798416a74`, so that call did not make vLLM unavailable. The successful attempt used a new owned root, `/var/machi-lab/fail-state`, and the product provisioner with `uv` pointed at `/var/machi-lab/missing-uv`. The provisioner returned `provisioning_failed` / `python_provision_failed` for selection `fsel_9a7247e225d0d653`. The healthy generation remained. Host drivers, the GPU, and system Python were not changed.

R. Physical fallback result, or PHYSICAL_AUTO_FALLBACK_NOT_SAFELY_INDUCED
Physical fallback was induced and selected Ollama. Decision `fbk_d83226b96d76d7e2`. Primary support `provisioning_failed`. Fallback support `ready`. Recompute `foundation,model,plan,admit,serve`.

S. Proof of fresh Ollama fallback chain if physically executed
Tag `smollm2:135m-instruct-q8_0`. Digest `2d470404841a51320639b2c2418c7ad8643cccbbcb88c2a242b211ae83bf46a9`. Generation `fgen_66a0af2ac4ba618c`. Plan `plan_d24362279180c37c`. Reservation `rsv_35c15204781dc933`. Start ready. Proof proven. Same digest. 8 output tokens. Stop stopped. Release released. Active reservations empty. The plan and reservation are not `plan_bd9c83c38656c40d`, `plan_9bbf3fa49c0ff004`, `rsv_fb869dbd283770ee`, or `rsv_7854c1b5344d8896`.

T. Second positive Ollama model tag/digest/qualification/Serve result
`smollm2:360m-instruct-q8_0` was present in the provider catalog after the lab pull. Digest from the catalog: `dfd48b1fa28f91f94d51037458e22eb461591d2f2f92bb44b115c86ac11b560f`. Context 2048, binding `requested`, fit `FIT`, outcome `PASS`, generation `fgen_66a0af2ac4ba618c`. Runner `-c 2048` and `n_ctx_slot` 2048. Plan `plan_9bbf3fa49c0ff004`. Reservation `rsv_7854c1b5344d8896`. Proof proven. 8 tokens. 0.059204 seconds. 135.12600499966217 tokens/sec. `size_vram` 492254002, runtime-reported. Stopped and released. Shadow unresolved. Classification `MACHI_UNRESOLVED`.
The 135m case on the same host was also PASS at context 2048, plan `plan_bd9c83c38656c40d`, reservation `rsv_fb869dbd283770ee`, 8 tokens, 0.070258 seconds, 113.86603660793077 tokens/sec, `size_vram` 205384580.

U. Meaningful negative/excluded case
The 360m qualification at context 2048 does not cover a plan at context 4096. Compose returned `qualification_does_not_cover` and did not produce a servable configuration.

V. Comparative native-vLLM vs Ollama closure summary
No winner. Native N2 was an L40S in US-MO-1, vLLM 0.18.0, SmolLM2-135M-Instruct bfloat16, load 39.86 seconds, 16.47 tokens/sec, SAFE accelerator 48037363712. This Ollama proof is an A40, Ollama 0.34.3, GGUF Q8_0 at two sizes, context 2048, single 8-token proofs, and runtime-reported `size_vram`. The SKUs and representations differ, so the rates are not averaged and `size_vram` is not an external peak. Later lab work still needs matched SKU, representation, context, and memory semantics.

W. Provider/resource/privacy invariants rechecked
One ResourceManager ledger. Provider plans cite `fgen_` and the catalog digest. Explicit modes do not switch. Fallback builds a new plan and reservation. No customer prompt or response was stored. The migration receipt has no record body.

X. Implementation defects found/fixed
The Bundle 06 migration note could be lost after the record rewrite. The receipt phase now keeps that gap recoverable. The same-root fallback attempt reused a verified vLLM generation; the isolated-root attempt is the one that produced a real unavailable state.

Y. Architecture amendments/decision gates encountered
None. vLLM stays primary when ready. Ollama stays the fallback. No second ledger, no catalog translation, and no Serve-internal retry. `RuntimeChoice` cites Foundation selections. It does not replace `FoundationSelection`.

Z. Exact NVIDIA support claim
On the bounded NVIDIA A40 environment and the exact runtime and model configurations physically qualified in this Stage-1 campaign, Machi has two working execution macropaths: native/vLLM as primary and Ollama as a separately qualified compatibility/fallback path. Machi preserves one global admission authority, keeps model catalogs separate, can explain AUTO runtime choice from concrete Foundation evidence, and can construct a fresh Ollama deployment chain when fallback is selected.

AA. Explicitly unclaimed capabilities
AMD support, ROCm support, all-accelerator support, physical live failover after an inference failure, runtime switching after an arbitrary request failure, cross-catalog model equivalence, multi-model concurrent serving, fleet HA, production HA, and NVIDIA-wide Ollama support are not claimed.

AB. Remaining AMD/fallback/HA debt
`M-5-AMD-01` stays open. `M-5-OLLAMA-01`, `M-5-OLLAMA-04`, `M-6-OLLAMA-01`, `M-6-03`, and `M-9-02` stay open. Model pull remains operator lab setup. Live request-failure failover remains out of scope. K-03 is retired.

AC. Pod termination proof(s)
`delete-pod` for `5vckhyhjmjht55` returned 204. Subsequent `get-pod` returned 404. No AMD pod was created. No pre-existing pod was started, stopped, or terminated.

AD. Full final gates / local==origin
Targeted tests, full `tests/machi`, architecture checks, ruff, and strict mypy passed on the physical source. Both wheels were clean and `verify_ok`. Final HEAD `2c12f00286d6e7d6d524baa7a7787099e476bf08` equals `origin/automation/ollama-macropath`.

AE. Recovery checkpoint / program status
New branch `checkpoint/ollama-nvidia-stage1-2026-09-24` points at the final SHA and was pushed. `checkpoint/ollama-generation-bound-serve-2026-09-24` remains `92555da8e3465cd1596098eb33579d31e1a12ae6`. `checkpoint/ollama-authorized-serve-2026-09-24` remains `ebfabe56b2ae09b916e5e70ea4d2b1c028f48af6`. The roadmap records `CLOSED_NVIDIA_STAGE1` for the qualified A40 cases and leaves AMD and live failover open.

AF. Final status
STOP — OLLAMA MACROPATH CLOSED_NVIDIA_STAGE1. WAIT FOR LEAD REVIEW.

==================== END PASTE BACK — OLLAMA BUNDLE 07 CLOSURE ====================
