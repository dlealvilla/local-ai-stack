==================== BEGIN PASTE BACK — OLLAMA BUNDLE 04 ====================

A. STATUS / package slices executed
SLICE A executed and committed before any pod: real loopback API and preload timing.
SLICE B executed: clean candidate, preflight, one owned NVIDIA pod.
SLICE C executed on that pod after two product fixes and wheel rebuilds.
SLICE D executed: two clean passes, evidence recorded, owned pod terminated.
SLICE E1 executed locally after termination: residency observation only.
SLICE E3 stopped at the authorization gate. No Serve skeleton.
AUTO fallback not started. Chunks 5 and 6 not started.
Slice E record: DECISION_REQUIRED.

B. Starting SHA / final SHA
Starting integration HEAD: 4aa21ccabade398a8f931c5a231baed84bbf45f0
Final source HEAD: ea9cb26a6034eeaca1058d6635ee4008fc833bed
Branch: automation/ollama-macropath
Physical passing source: e8bba2becd9b7e5244e987556c88812bad5895c0
The final SHA adds the non-authorizing residency seam and the evidence note. It is not the wheel that ran on the host.

C. Carry-forward preload timing correction
OllamaQualificationEvidence.load_seconds is the initial empty-preload load_duration converted from nanoseconds.
Token prompt_eval_count, eval_count, and eval_duration map to input tokens, output tokens, and generation_seconds.
The token request load_duration is not stored as initial load.
On the physical host the empty preload response omitted load_duration, so both journal records store load_seconds as not_measured. The token duration was not substituted.

D. Real loopback API adapter implementation
LoopbackOllamaClient in src/machi/adapters/model/ollama_http.py uses the standard library.
It accepts only the Foundation private HTTP loopback, with a required port and no userinfo, path, query, or fragment.
Connect timeout 5s, read timeout configurable, body cap 1048576 bytes.
Operations: GET /api/tags, POST /api/show, empty POST /api/generate preload, GET /api/ps, bounded token POST /api/generate, empty unload.
Qualification preload and token probe send keep_alive -1. Unload sends keep_alive 0.
Response text is dropped after the token count is read.
Catalog mapping uses tags name/digest/size and show family, quantization_level, and format. It does not infer dtype or attention shape.

E. Local API/timing/transport tests
tests/machi/test_ollama_http.py covers paths, methods, bodies, loopback rejection, bounds, timeout, malformed and wrong shape, no_fit, nanosecond conversion, and absence of prompt or response text in the candidate.
Existing fake dual-qualifier tests still pass.
Archive tests now refuse escaping symlinks and hard links, keep an in-prefix soname symlink, and keep a runner executable bit without setuid.

F. Candidate wheel build ID/SHA256 + isolated verify_ok
Physical wheel that produced the clean passes:
build 0.1.0+e8bba2becd9b
SHA256 907e42d9a61d98ca9bb330b7d3370154e483616206fbf2a18294ac2dc8d0415c
size 309608
source e8bba2becd9b7e5244e987556c88812bad5895c0
clean_source true
isolated verify ended serve_ok sin_5c22adc1d8920043 then verify_ok.
Final local wheel after the residency seam:
build 0.1.0+ea9cb26a6034
SHA256 ebd7803a8c3c1b0fdbccd5b1e0ef187cb3ca0b4a066fee93912874104c12c220
size 310897
source ea9cb26a6034eeaca1058d6635ee4008fc833bed
clean_source true
isolated verify_ok.

G. RunPod preflight: balance/stock/rate/image/ownership
Live balance before create: 16.5841709656 USD, above 5.
Spend limit 80 USD/day. Existing account spend was not this pod.
NVIDIA L40S secure stock LOW in EUR-IS-2, US-NC-1, and US-TX-4.
Secure price 1.09 USD/hour, under 1.50.
Image runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404 from official template runpod-torch-v280.
One GPU, Linux x86_64, CUDA 12.8.
No network volume requested.
Only pod created in this run: vlkwr10g1p9faj, name machi-ollama-bundle-04.
No pre-existing pod was started, stopped, or terminated.

H. Physical host exact identity/lifecycle
Provider Runpod secure. Region US-NC-1. SKU NVIDIA L40S. Count 1.
Compute capability 8.9. Driver 570.124.06. CUDA 12.8.
Device GPU-7b845265-a028-4a9f-8d6d-00489cc8e95d.
Python 3.12.3.
Created 2026-09-24T09:27:42Z. Uptime at the pre-delete read was 1772 seconds. Status was RUNNING. Delete returned 204. A following get returned 404.
Container disk 40 GB. The template persistent mount was not used for the prefix. No Runpod network volume was attached by this run.

I. Managed Ollama Foundation realization/evidence
Pinned archive sha256 e83a089fd0cd2f79ee2933cca2085846a2065f497adbc6467c402177c68423f9, size 1427391999.
First install of wheel 474072b refused the archive because it contains 17 in-prefix soname symlinks and no escaping links. Source now allows a relative symlink that stays inside the prefix and still refuses hard links and links that leave the prefix.
Second install, wheel c1368a0, reached Foundation ready but llama-server was mode 0644, so GPU discovery and the preload returned permission denied. Source now preserves an executable bit and strips setuid.
Third install, wheel e8bba2b, generation renv_ceedac1939fecd21, support ready, failure none, version 0.34.3, cloud disabled, fingerprint exe_687af32c8cf62fa273355f81bbc01589.
GPU discovery reported CUDA, compute 8.9, NVIDIA L40S, driver 12.8.
System zstd 1.5.5 was already on the image. M-5-OLLAMA-04 stays open.
M-5-OLLAMA-03 is retired on this host evidence. The binary was not installed under /usr.

J. Lab model setup: tag/full digest/size/details
Preferred tag smollm2:135m-instruct-q8_0. Fallback was not needed.
Digest 2d470404841a51320639b2c2418c7ad8643cccbbcb88c2a242b211ae83bf46a9.
Size 144823793 bytes.
Show details: family llama, quantization Q8_0, format gguf.
Pull used the owned ollama binary as lab setup. No product pull feature was added.

K. Initial residency normalization
Before the passing qualification, /api/ps did not contain that digest.
resident_before was empty.

L. ResourceManager qualification reservation exact bytes
One ledger. admit_probe reserved the remaining SAFE bytes. Persistent bytes 0.
SAFE host 187463127040. SAFE accelerator 48037363712.
First pass reservation rsv_2f420c9e817c52f7: accelerator 48037363712, host 187463127040, persistent 0.
Second pass, after a fresh capacity evaluation, reservation rsv_189c931a33925193: the same byte counts.
The earlier permission-denied attempt admitted rsv_2f420c9e817c52f7 and released it after a host failure. That attempt is not a pass.

M. Machi shadow result
Both passing runs: fit unresolved, reason attention_shape_not_exposed, accelerator bytes unresolved.
Shadow did not veto or upgrade the provider FIT.
Public show details did not expose dtype, layers, heads, or head dimension. Those values were not guessed.

N. Ollama provider fit + overall qualification result
Both passing runs: provider_fit fit, outcome pass, failure none, status clean, classification machi_unresolved.
The permission-denied attempt was provider_fit unresolved, outcome fail_host, failure provider_host_failure. It is not part of the pass claim.

O. Preload -> ps -> token -> ps identity proof
The passing case used the product sequence: re-resolve tag to digest, empty preload keep_alive -1, /api/ps name and digest, token probe, /api/ps again, persist, unload keep_alive 0, /api/ps absence, then release.
Output tokens were 8 on both passes, so a real token was counted.
The runner log for the second pass showed the same model name and a completed eval of 8 tokens.
Requested context was 2048. The runner log reported n_ctx_slot 8192. The product generate body does not send num_ctx. Those numbers are not interchangeable.

P. Physical timing/token/size_vram metrics + provenance
First pass: input 35, output 8, generation_seconds 0.079721, tokens/sec 100.34997052219616, size_vram 374614261, semantics runtime_reported, source ollama.api.ps.
Second pass: input 35, output 8, generation_seconds 0.020248, tokens/sec 395.10075069142636, size_vram 374614261, same semantics.
load_seconds not_measured on both, because the preload response had no load_duration.
No prompt text and no response text were stored.

Q. Durable comparison event/readback
Journal type model.qualification.compared.
First event evt_9eec42f57c46c00c. Second event evt_8e1968b307b58892.
Readback showed classification machi_unresolved, provider_fit fit, and load_seconds not_measured.
No prompt or response field was present.

R. Cleanup + reservation release proof
Both passing runs: unload_failure none, reservation_released true, active reservations empty after each release.
Release happened only after /api/ps no longer showed the expected name and digest.

S. Optional second qualification/re-entry result
The second run used the same digest and a newly observed capacity envelope, evidence id cap_ollama_lab_reentry.
It was also clean, FIT, PASS, released, and journaled.
The token rate changed from about 100/s to about 395/s. Both figures are kept. They were not averaged.

T. Native-vs-Ollama comparison artifact, or why not directly comparable
Artifact: docs/machi/OLLAMA-BUNDLE-04-PHYSICAL.md.
Same SKU class as native N2: NVIDIA L40S, 1.09 USD/hour, SAFE accelerator bytes 48037363712.
Not the same host. Native N2 was US-MO-1, driver 580.178.04, CUDA 13.0, vLLM 0.18.0, SmolLM2-135M-Instruct bfloat16, load 39.86 seconds, 16.47 tokens/sec.
This host is US-NC-1, driver 570.124.06, CUDA 12.8, Ollama 0.34.3, GGUF Q8_0 digest above.
Representations are not byte-identical. Native load time and Ollama size_vram are not the same metric. No runtime was selected.

U. Physical disposition/support claim
Supported for this one host only: managed Ollama 0.34.3 from the owned prefix can be admitted, can return provider FIT, can emit a real token for this digest, can be compared without letting the shadow veto, and can be unloaded before the qualification hold is released.
Not claimed: Ollama as a class, NVIDIA as a vendor, long-lived Serve, AUTO fallback, or a same-machine comparison with native N2.
M-6-OLLAMA-01 stays open. M-5-OLLAMA-01 and M-5-OLLAMA-02 stay open. M-5-OLLAMA-04 stays open.

V. Owned Pod termination proof or hang STOP state
delete-pod vlkwr10g1p9faj returned 204.
get-pod vlkwr10g1p9faj then returned 404, pod not found.
The run was not hung. No other pod was touched.

W. Slice-E residency observation/guard result
COMPLETED_LOCAL after the pod was gone.
src/machi/adapters/model/ollama_residency.py classifies /api/ps as absent, expected_resident, wrong_identity, or unresolved.
A match cites name, canonical digest, size_vram, and expires_at when the provider exposed them.
refresh_residency calls the existing preload, which sends keep_alive -1, then reads /api/ps.
release_residency calls the existing unload, which sends keep_alive 0, then reads /api/ps.
An API failure is unresolved. The seam does not call ResourceManager and does not start Serve.
tests/machi/test_ollama_residency.py covers the four states plus refresh and release.

X. Long-lived authorization options A/B/C/D + Product Vision Alignment
Native facts used for the comparison:
DeploymentConfiguration v1 requires a warehouse artifact id, dtype, and quantization. It is a plan, not a reservation.
ResourceReservation is one ledger record keyed by plan, fingerprint, request, capacity evidence, and device bytes. admit() authorizes deployment bytes. admit_probe authorizes only a qualification hold of remaining SAFE bytes.
Serve today consumes a current native configuration plus a reservation. Ollama identity is a digest. A tag is not identity. Show does not return the digest. The shadow cannot veto.
keep_alive is a provider request. /api/ps is evidence. Neither is a Machi hold. Loopback has no Machi authentication, so another local process can change residency. Ollama may also evict on its own schedule. That is M-5-OLLAMA-01 and M-6-OLLAMA-01.

A. Sibling provider configuration into the existing deployment reservation.
A new or parallel plan contract can name an Ollama digest, generation, and execution fingerprint, then call the same admit() path and the same ResourceReservation. Serve would verify the digest before and after inference.
Product vision: aligned if the contract stays a Machi object and Ollama stays an adapter. Misaligned if artifact_id is filled with a digest, because that makes a warehouse identity lie.
Native M8/M9: the current required artifact, dtype, and quantization fields cannot honestly describe this model. A sibling contract avoids corrupting vLLM plans and still changes what a deployment identity is allowed to be.
Schema: new plan kind or a carefully optional identity. The reservation record can stay as it is.
One ledger: yes, if every long-lived hold is still one ResourceReservation.
Stale capacity: the same current-evidence rule as native. A later Ollama eviction does not update the reservation, so Serve must re-read /api/ps.
Identity: digest plus generation plus execution fingerprint. The tag is display only.
Restart and cleanup: daemon death drops keep_alive. Restart must prove the digest again. Unload failure must keep the hold.
Future workloads: training or indexing would still need their own claims. This option does not give them a home.
Reversibility: a sibling contract can be removed. Overloading artifact_id cannot.
Provider leakage: low when the fields say provider model identity. Higher if Ollama show strings become required plan fields.
This is a credible core design. It is not a small extension of the current DeploymentConfiguration.

B. Generic deployment claim below native Plan.
Plan remains the only producer of native DeploymentConfiguration. A provider deployment is a second producer of a generic claim that admit() turns into the same reservation.
Product vision: aligned with Plan as one producer and ResourceManager as the only authority. It also matches the accepted split between the warehouse catalog and the Ollama catalog.
Native M8/M9: Serve currently requires DeploymentConfiguration. Accepting a second upstream identity changes Serve even if Plan is untouched.
Schema: a new claim with an explicit native-artifact or provider-digest alternative, not one field that means both.
One ledger: yes, if the claim is only a producer of ResourceRequest. Renaming plan_id into a generic subject id changes the reservation meaning.
Stale capacity: the claim must cite capacity evidence. Residency remains a separate observation.
Identity: artifact revision and provider digest stay distinct. Unknown is not rewritten into the other.
Restart and cleanup: same physical duties as A, with two producers to reconcile.
Future workloads: this is the shape that can later carry training or indexing without calling them model plans. That is why it is larger than this package.
Reversibility: high until Serve depends on the claim.
Provider leakage: low if the claim is provider-neutral.
This is a credible core design. Choosing it defines the workload-claim ontology.

C. Separate Ollama reservation type on the same ledger.
A provider-specific hold is stored beside ResourceReservation and both must be summed before any new admission.
Product vision: weaker. The ledger starts to speak Ollama instead of one resource hold.
Native M8/M9: native records stay unchanged, which is attractive, and every later admission must remember the second active set. Forgetting it double-books the GPU.
Schema: a new reservation kind plus a mandatory combined active sum.
One ledger: only if that sum is real. A second type that is not in the sum is a second ledger.
Stale capacity: the new record must still cite capacity evidence. It is easy to confuse the record with /api/ps.
Identity: digest fields sit on the admission record.
Restart and cleanup: native reconciliation does not know how to unload Ollama.
Future workloads: each new workload adds another reservation type.
Reversibility: the type can be deleted, but the accounting rule is easy to get wrong while it exists.
Provider leakage: high.
This remains credible only when the active sum is specified first. It is not uniquely selected by that condition.

D. Let Ollama residency authorize the hold.
Misaligned. ResourceManager is the only admission authority. /api/ps and keep_alive are provider evidence and provider requests. The loopback bypass and the eviction debt exist because residency is not a hold. Not a candidate.

Y. Decision gate result / implementation if NO_NEW_CORE_DECISION_REQUIRED
DECISION_REQUIRED_OLLAMA_SERVE_AUTHORIZATION.
A, B, and C are all materially credible. None is a small extension that leaves native M8/M9 contracts unchanged. D is misaligned and was not implemented.
No long-lived Serve path, no reservation-type change, and no DeploymentConfiguration change was made.
The only Slice E code is the observation seam in W.

Z. Full regression/package gates
Targeted archive, HTTP, and residency tests passed.
ruff check src/machi tests/machi passed.
mypy --strict src/machi passed, 171 files.
pytest tests/machi passed, including the three residency tests.
Architecture coverage is inside tests/machi and passed with that run.
Final wheel isolated verify_ok as recorded in F.
Recovery refs were not moved. docs/machi/proposals/ remains untracked and uncommitted.

AA. Docs/debt/evidence changes
docs/machi/OLLAMA-BUNDLE-04-PHYSICAL.md records the host, the two passes, and the bounded native comparison.
docs/DEBT.md retires M-5-OLLAMA-03 on this host evidence.
M-5-OLLAMA-01, M-5-OLLAMA-02, M-5-OLLAMA-04, and M-6-OLLAMA-01 remain open.
No customer content, prompt, response, secret, or address was written into the repo.

AB. Local/origin equality
git rev-parse HEAD and origin/automation/ollama-macropath are both ea9cb26a6034eeaca1058d6635ee4008fc833bed.
Push was a fast-forward from 4aa21ccabade398a8f931c5a231baed84bbf45f0.

AC. Exact remaining work
Lead choice among A, B, and C for long-lived Ollama Serve authorization.
After that choice: the smallest Serve skeleton, still not AUTO fallback and not chunks 5 or 6.
M-6-OLLAMA-01 stays open until a Serve hold actually constrains residency.
M-5-OLLAMA-04 stays open until zstd is a pinned artifact rather than a host tool.
The qualification context is not yet sent to Ollama. The runner used 8192 while the case recorded 2048.
Empty preload did not report load_duration. A later metric can store it only when the provider sends it.

AD. Final status
DECISION_REQUIRED_OLLAMA_SERVE_AUTHORIZATION — WAIT FOR LEAD DECISION.

==================== END PASTE BACK — OLLAMA BUNDLE 04 ====================
