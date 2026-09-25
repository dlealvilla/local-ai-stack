# MACHI-STAGE1-SPINE-CLOSURE-001

## A. EXACT STATUS

STAGE1_DEPLOYMENT_SPINE_IMPLEMENTATION_CLOSED_PHYSICAL_BREADTH_PENDING

## B. EXECUTIVE TL;DR

Stage-1 deployment-spine implementation is closed for the scope already proved. No new physical host was created. Kernel 0.6.1 DeploymentWitness projects a native warehouse chain and an Ollama digest chain from cited persisted identities, and it refuses to treat missing, mismatched, or failed evidence as success. AUTO still prefers healthy native vLLM and falls back only under the approved unavailable states, through a fresh Foundation → model → Plan → Admit → Serve chain and one ResourceManager. M-6-03 and the Stage-1 blocker reading of M-9-02 are retired under the Lead's stated conditions. The tiny Llama remains negative evidence. AMD, macOS/Ollama, and NVIDIA Ampere/N1 stay PHYSICAL_PENDING. `machi` was not moved.

## C. STARTING / FINAL SHA

- Starting accepted source: `2c12f00286d6e7d6d524baa7a7787099e476bf08`
- Implementation SHA: `d116696667468494ae2e4327d11c98a6820d33cf`
- Closure record SHA (branch tip): `4cb89622a4cd3a1a37bf6ab44c4414e4287e8934`
- The tip commit records the wheel identity. Python is unchanged after `d116696`.

## D. BRANCH / ORIGIN / WORKTREE

- Branch: `stage1/spine-closure`
- Origin: `origin/stage1/spine-closure` = `4cb89622a4cd3a1a37bf6ab44c4414e4287e8934`
- Recovery ref: `origin/checkpoint/stage1-spine-closure-2026-09-25` at the same SHA
- Not branched from `machi` (`1db7646`)
- Prior checkpoints were not moved
- Untracked `docs/machi/proposals/` left untracked. Not policy.

## E. STAGE-1 ARCHITECTURE AUDIT

PASS. No Block ownership change. No second admission ledger. No second platform ontology. Witness is a Kernel projection and does not import Serve, Admit, Plan, or adapters. Provider-specific engines stay behind the packages that already own them. The audit found stale status text, not a spine defect. Those documents were corrected. No architecture amendment was required.

## F. BLOCK 0–9 FINAL STATUS

| Block | Owns | Does not own | Disposition |
|---|---|---|---|
| 0 Kernel | contracts, events, migration, Witness projection | admission, inference, vendor tools | PASS. 0.6.1 added |
| 1 Install | this installation | host facts | PASS. unchanged |
| 2 Discover | observations | SAFE capacity, readiness policy | PASS. unchanged |
| 3 Steward | ownership and occupancy class | deletion, admission | PASS. unchanged |
| 4 Capacity | SAFE planning ceilings | reservations | PASS. unchanged |
| 5 Foundation | execution-foundation selection, including AUTO | ResourceManager | PASS. unchanged |
| 6 Model | warehouse identity and separate provider qualification | catalog merge | PASS. unchanged |
| 7 Plan | desired configuration | admission, launch | PASS. unchanged |
| 8 Admit | the one reservation ledger | process lifecycle | PASS. unchanged |
| 9 Serve | authorized execution, proof, STOP | planning a fallback, release | PASS. unchanged |

## G. NATIVE / VLLM MACROPATH AUDIT

PASS against current code and the accepted L40S record. Deployable membership requires qualification coverage, including a real execution fingerprint. Predicate mismatch still yields unsupported, so the head-dimension-4 tiny Llama stays out of the deployable set. Plan cannot omit qualification identity. Serve refuses a reservation that does not match. This run did not repeat physical inference.

Accepted evidence: [docs/machi/INFERENCE-PROGRAM-005.md](docs/machi/INFERENCE-PROGRAM-005.md). Secure L40S, compute 8.9. SmolLM2-135M-Instruct `12fd25f77366fa6b3b4b768ec3050bf629380bac`. SmolLM2-360M-Instruct `a10cc1512eabd3dde888204e902eca88bddb4951`. Request inference, stop, re-admission, restart, second request. Tiny Llama refused before normal weight acquisition.

## H. OLLAMA MACROPATH AUDIT

PASS against current code and Bundle 07. Digest is the provider identity. Tag is display. The Ollama store is not the Model Warehouse. No cross-catalog translation. Provider Serve checks `fgen_` and the execution fingerprint. STOP does not release. Residency is evidence, not admission.

Accepted evidence: [docs/machi/OLLAMA-BUNDLE-07-PHYSICAL.md](docs/machi/OLLAMA-BUNDLE-07-PHYSICAL.md). One secure A40. AUTO healthy selected vLLM (`fbk_fa5314e89fc227d3`). Isolated provisioning failure then AUTO Ollama (`fbk_d83226b96d76d7e2`) with a new plan `plan_d24362279180c37c` and reservation `rsv_35c15204781dc933`. Two context-2048 proofs. Context 4096 refused. STOP then explicit release.

## I. AUTO / FALLBACK POLICY AUDIT

PASS. Existing tests in `tests/machi/test_runtime_choice.py` cover the required matrix.

- AUTO + healthy/supported vLLM → vLLM
- AUTO + approved unavailable native + Ollama READY → Ollama
- Approved unavailable states: unsupported, unavailable, blocked by prerequisite, insufficient capacity, provisioning failed, verification failed
- Conditionally supported and reconcile-required do not fall back
- Explicit VLLM failure does not select Ollama
- Explicit OLLAMA failure does not select vLLM
- Fallback recomputes Foundation, model, Plan, Admit, Serve and mints a new plan and reservation
- One ledger sees both paths
- No cross-catalog translation
- Serve does not own the retry
- RuntimeChoice cites the foundation selections consulted
- Historical v1 readback does not invent ids

This is control-plane selection. It is not physical live failover after a request failure.

## J. RESOURCE / LIFECYCLE AUDIT

PASS. ResourceManager remains the only author of execution authorization. A bare plan does not start. Host memory, accelerator memory, and storage stay separate. STOP leaves the reservation RESERVED. Release is an explicit Admit record. Re-entry does not adopt an unrelated process. A stale plan or capacity mismatch cannot mint a new hold. Provider residency cannot override admission. cgroups, GPU partitions, multi-host, lease expiry, and preemption stay deferred (`M-8-01`).

## K. PERSISTENCE / MIGRATION / RE-ENTRY AUDIT

PASS. Bundle 07 intent/complete receipts are unchanged. K-03 stays retired. Shipped bumps remain qualification v2, Ollama qualification v2, and runtime choice v2. Historical sentinels (`not_recorded`, `not_sent`, `not_consulted`) are not upgraded into real ids. Witness is a new version-1 contract with no older shape. The witness document round-trips through schema `to_dict` / `from_dict`. The composer performs no I/O.

## L. PRIVACY / SECURITY-BOUNDARY AUDIT

PASS for this closure. Witness fields are identities, a verdict, and a reason. The event `kernel.witness.composed` is `restricted` and carries witness id, verdict, and plan id. No prompt or response field exists. Local inference does not require outbound telemetry.

Safe only because the current API and runtime are loopback/local: start, stop, admit, and release. A LAN or remote Admin, and any central command center, need an authentication and consent boundary before they may issue those mutations. This package does not add that boundary.

## M. DEPLOYMENTWITNESS IMPLEMENTATION

`src/machi/kernel/witness.py`. Contract `kernel.deployment_witness` version 1. Event `kernel.witness.composed`. Verdicts: supported, incomplete, contradictory, failed. Model identity is either `warehouse_artifact` or `provider_digest`. `compose_witness` reads caller-supplied citations only. Serve policy text now says `witness  projection`.

## N. DEPLOYMENTWITNESS TEST EVIDENCE

`tests/machi/test_witness.py`, 12 tests, included in the passing `tests/machi` run.

- complete native citation chain, deterministic id
- complete provider-digest chain, distinct from the warehouse id
- missing qualification → incomplete
- foundation generation mismatch → contradictory
- instance citing another plan → contradictory
- released reservation with a ready instance → contradictory
- missing inference proof → incomplete
- failed inference → failed
- stopped with the reservation still held → supported; still running → incomplete; released without a release id → incomplete
- unresolved historical fields stay unresolved
- schema round-trip and event privacy
- source contains no adapter, Serve, Admit, Plan, or ResourceManager import

## O. DEBT RETIRED / RECLASSIFIED

- `M-6-03` RETIRED. The retire-when text allows the Lead to skip the NVIDIA-N1 probe. This instruction makes that choice. L40S SmolLM2 qualification is the hardware pass. It is not class-wide NVIDIA support.
- `M-9-02` RETIRED as a Stage-1 acceptance blocker. The Lead replaced the acceptance artifact with the two SmolLM2 models already proved on L40S. The tiny Llama failure stays in the debt text and still does not execute.
- `M-9-01W` RETIRED for the witness projection.
- `M-9-01` remains OPEN for automatic restart, usage metrics, multi-instance, and public bind.
- `M-7-01` no longer lists an Ollama planner as missing. Multi-GPU and the other deferred planners stay open.
- `M-5-OLLAMA-03` header label now matches its retired status.
- `M-5-AMD-01` remains OPEN.
- `M-5-OLLAMA-05` added OPEN / PHYSICAL_PENDING for macOS Ollama.

## P. DOCUMENTATION COHERENCE CHANGES

Updated current-status text in `docs/machi/README.md`, `docs/machi/MACHI_LEAD_DEVELOPER.md`, `.cursor/agents/machi-lead-developer.md`, `docs/machi/ROADMAP.md` (M6, M8, M9 rows), `docs/machi/ARCHITECTURE.md`, `docs/machi/CONTRACTS.md`, `docs/machi/TELEMETRY.md`, and `docs/DEBT.md`. Historical milestone narratives were not rewritten. `machi` at `1db7646` is described as an ancestor, not the product tip.

## Q. ACCEPTED PHYSICAL EVIDENCE INHERITED

- Native: L40S SmolLM2 request and restart inference. Program 005. No new run.
- Ollama: A40 Bundle 07 AUTO fallback and request inference. No new run.
- Tiny Llama NVIDIA-N1 failure remains negative evidence.

## R. PHYSICAL QUALIFICATION LEFT PENDING

Register: `docs/machi/STAGE1-PHYSICAL-BACKLOG.md`.

- AMD native/vLLM
- macOS/Ollama
- NVIDIA Ampere/N1 breadth
- Apple accelerator inference, still deferred from Discover 2.3
- Windows mounts, unsupported rather than zero
- Live request-failure failover, not claimed

## S. AMD PENDING QUALIFICATION

`M-5-AMD-01` OPEN. Claim would be host prerequisites plus a Machi-managed ROCm userspace, then native qualification and one request. NVIDIA evidence cannot be reused. Bundle 07 preflight found no approved stock inside the cap. That preflight is historical. No pod was created in this run.

## T. MACOS / OLLAMA PENDING QUALIFICATION

`M-5-OLLAMA-05` OPEN. The Linux A40 prefix and the pinned Linux archive do not prove macOS. No macOS host was used.

## U. NVIDIA BREADTH PENDING QUALIFICATION

Ampere/N1 is coverage, not a Stage-1 capability blocker. The earlier N1 campaign failed on the tiny Llama. That failure is not a pass, and the L40S pass is not an Ampere pass.

## V. LOCAL QA

- `tests/machi`: pass, including architecture, witness, qualification, plan, admit, serve, Ollama, runtime choice, schema migration, and privacy
- `tests/acceptance_lab`: pass
- ruff: pass
- mypy --strict `src/machi`: pass, 178 files
- No accelerator and no T2 hardware install were required. No physical campaign was run.

## W. WHEEL / BUILD / SHA256 / ISOLATED VERIFY

- Filename: `machi-0.1.0-py3-none-any.whl`
- Build id: `0.1.0+d11669666746`
- Built from: `d116696667468494ae2e4327d11c98a6820d33cf`
- SHA256: `0a34a2390d1f89591e3e2508e04b441de7f8f17315fa7bddddc3b779a0a8fc63`
- Size: 332957
- Clean tree: true (proposals parked for the build, then restored untracked)
- Isolated verify: `verify_ok` (policy line shows `witness  projection`)

## X. STAGE-1 CLOSURE CLAIM — EXACT BOUNDARY

STAGE1_DEPLOYMENT_SPINE_IMPLEMENTATION_CLOSED_PHYSICAL_BREADTH_PENDING

Means: spine 0→9 for the accepted scope, L40S native inference, A40 Ollama fallback, local AUTO semantics, Witness projection, local gates, no known Stage-1 architecture blocker.

Does not mean: AMD, macOS/Ollama, all NVIDIA, live request failover, multi-model scheduling, multi-host, public remote control, or fleet HA.

## Y. STAGE-1 CLOSURE RECORD / CHECKPOINT

- `docs/machi/STAGE1-SPINE-CLOSURE.md`
- `checkpoints/MACHI-STAGE1-SPINE-CLOSURE.json`
- `origin/checkpoint/stage1-spine-closure-2026-09-25` → `4cb89622a4cd3a1a37bf6ab44c4414e4287e8934`
- No fake physical evidence was added.

## Z. MACHI BRANCH PROMOTION READINESS

`origin/machi` `1db764607a5806d080cc138932002760bad113ad` is a strict ancestor of the closure tip. The closure tip is 81 commits ahead and 0 behind. Promotion can be a clean fast-forward. It was not performed. Do not branch new work from `machi` until that fast-forward happens.

## AA. POST-STAGE-1 OPTION A — LOCAL FRONTEND

Best immediate product step. A loopback screen can show Witness, macropath, model identity, SAFE summary, plan, and reservation. It must not own those truths. Start/stop only through existing services. No operator HTTP API exists yet; the CLI is the control surface. A same-machine UI can stay inside the loopback assumption. Memo: `docs/machi/STAGE1-NEXT-OPTIONS.md`. Not implemented.

## AB. OPTION B — CENTRAL COMMAND CENTER

A different plane: inventory, health, version, and support signals across hosts. It must not own host truth, the local ledger, or customer content. Inference must not require it. Build it after a local UI and after authentication and consent. Do not combine it with Option A into one application.

## AC. OPTION C — RUNTIME ARTIFACT REGISTRY

Post-spine, separate from the Model Warehouse. Needed before a scaled or air-gapped installer. The open hook is `M-5-OLLAMA-04` (unmanaged host `zstd`). It can proceed in parallel with a loopback UI. It does not have to block that UI on a machine that already has the runtime.

## AD. OPTION D — NVIDIA DYNAMO

Lab track only, and not yet. Dynamo would be a new Foundation family, not a vLLM optimizer. No named coverage gap in this closure requires a fabric. `S-STRAT-02` stays deferred. The Industry Solution Selection Gate applies before any adapter. Not implemented.

## AE. OPTION E — GATEWAY / AUTH / IDENTITY

Required before LAN/remote Admin or a vendor command center. Not required for a strictly local loopback UI. Not implemented.

## AF. OTHER ROADMAP OPTION IF MATERIAL

No stronger operator-visible step than Option A. A support bundle can ride along with that UI. Installer productization depends on the registry. Usage analytics remain non-blocking (`S-STRAT-01`).

## AG. RECOMMENDED NEXT 2–4 WORKSTREAMS

Advisory. Not started.

1. Loopback operator UI over Witness and current lifecycle commands.
2. Runtime Artifact Registry, far enough to remove the unmanaged `zstd` dependency before a scaled installer.
3. Authentication and consent before any non-loopback control surface.
4. Central command center as a separate plane.

Parallel lab work is the pending physical campaigns (AMD, macOS/Ollama, Ampere/N1), not Dynamo.

## AH. PROVIDER / INDUSTRY DECISION GATES AHEAD

No solution decision required for this closure. vLLM remains primary. Ollama remains the bounded fallback. A later Dynamo, llama.cpp, MLX, SGLang, or TensorRT-LLM proposal must pass the Industry Solution Selection Gate before code. A new OS or accelerator provider must pass the Provider Selection Gate.

## AI. REMAINING NONBLOCKING DEBT

`M-9-01` serve depth, `M-5-AMD-01`, `M-5-AMD-02`, `M-5-AMD-03`, `M-5-OLLAMA-01`, `M-5-OLLAMA-04`, `M-5-OLLAMA-05`, `M-6-OLLAMA-01`, `M-7-01` beyond the bounded provider plan, `M-8-01`, `M-8-02`, `S-STRAT-01`, `S-STRAT-02`.

## AJ. EXACT NEXT LEAD DECISIONS

1. Whether to fast-forward `machi` to `4cb89622a4cd3a1a37bf6ab44c4414e4287e8934`.
2. Which next workstream to authorize: the recommended sequence above, or a different option in the memo.
3. Whether any pending physical campaign is next, and on which host class.

## AK. GIT STATE

- `stage1/spine-closure` equals `origin/stage1/spine-closure` at `4cb89622a4cd3a1a37bf6ab44c4414e4287e8934`
- Checkpoint ref pushed
- `machi` not updated
- Working tree clean except untracked `docs/machi/proposals/`
- Files in the closure range: witness module and tests, schema fingerprint, serve-policy witness line, debt, architecture, contracts, telemetry, roadmap, README, lead-developer docs, closure record, physical backlog, options memo, checkpoint JSON

## AL. STOP

STOP. Waiting for Lead review. The frontend, command center, registry, Dynamo, and further physical campaigns were not started.
