# ================================================================================
# =========================== PASTE BACK START ===================================
# ================================================================================

A. EXECUTIVE TL;DR

Machi is a clean-slate Company Brain spine. The accepted implementation line is `automation/ollama-macropath` at `2c12f00286d6e7d6d524baa7a7787099e476bf08`, not the branch named `machi`.

Blocks 0–8 are implemented and physically accepted on NVIDIA for their declared scope. Block 9 native vLLM request inference passed on one L40S for two SmolLM2 models and failed earlier on the stored tiny Llama (NVIDIA-N1). The Ollama macropath is `CLOSED_NVIDIA_STAGE1` on one A40. AMD Foundation qualification is open. Stage 1 is not fully exited. The canonical `machi` branch was never promoted past `1db7646`.

This packet is read-only. No product file, checkpoint, or server was changed.

B. REPOSITORY / BRANCH / HEAD TRUTH

Repository: `https://github.com/dlealvilla/ai-stack.git` (`dlealvilla/ai-stack`).
Workspace HEAD: `2c12f00286d6e7d6d524baa7a7787099e476bf08`
Local branch: `automation/ollama-macropath`, in sync with `origin/automation/ollama-macropath` (0 ahead, 0 behind).
Commit: "Record the NVIDIA Stage-1 Ollama closure on one A40." (2026-09-25 00:08:05 +1000).
Nothing newer than `2c12f00` exists on this branch.
Working tree: clean except untracked `docs/machi/proposals/` (`MACROPATH-FINAL-CONFIRMATION.md`, `MACROPATH-OLLAMA-NATIVE.md`, `MACROPATH-VLLM-PRIMARY.md`). Those files are not adopted. `docs/machi/ROADMAP.md` says they are superseded where they disagree with vLLM-primary / Ollama-fallback.

Authoritative accepted source for the current product: `2c12f00` on `automation/ollama-macropath`, recovered by `checkpoint/ollama-nvidia-stage1-2026-09-24` at the same SHA.
`origin/machi` is `1db764607a5806d080cc138932002760bad113ad`. It is an ancestor of HEAD. `git rev-list --left-right --count origin/machi...HEAD` is `0	79`. `machi` is 79 commits behind and is not the accepted line.
`m9/serve` (`0700e66`), `m6/model` (`840c407`), `m5/foundation` (`796f2ce`), and `automation/inference-program` (`6e17f4a`) are ancestors of HEAD. The spine is inside the Ollama branch, not beside it.
`control/machi-handoff` tip is `8162503` ("control: queue Lead onboarding status instruction"). It is not product history and must not be merged into an implementation branch.
`main` and `phase9` are the pre-Kultrun baseline. `kultrun` is the earlier rebuild lineage. Do not merge those into Machi.

C. AUTHORITATIVE FILE MAP

Strategy / product
- `docs/STRATEGY.md` — why, two tracks, four strategic stages. Does not own component sequence and does not open Stage 2–4 implementation.
- `docs/PRODUCT_VISION.md` — product constitution and the Industry Solution Selection Gate. Kultrun-lineage wording, still the product-vision authority named by the architecture gate.
- `docs/ARCHITECTURE.md` and `docs/ROADMAP.md` — Kultrun lineage. Not the Machi module map or M0–M9 sequence.

Architecture / sequencing
- `docs/machi/ARCHITECTURE.md` — active module map, Block → Capability → Component, adapter law, both gates.
- `docs/machi/ROADMAP.md` — active M0–M9 sequence and strategic placement of components. Some rows are stale; see T.
- `docs/machi/CONTRACTS.md` — named contract chain.
- `docs/machi/TELEMETRY.md` — events, privacy, local storage.
- `docs/machi/KULTRUN.md` — lessons. Not current status.

Operating
- `docs/machi/MACHI_LEAD_DEVELOPER.md` and `.cursor/agents/machi-lead-developer.md` — agent contract. Status paragraphs are stale (see T).
- `.cursor/rules/kultrun.mdc` — standing product rules, including bounded-step and "do not commit to main/phase9".
- `.cursor/rules/machi-handoff.mdc` — GitHub handoff protocol.
- `docs/DEVELOPMENT_WORKFLOW.md` — bounded-step protocol.
- `docs/machi/ACCEPTANCE-LAB.md` — lab harness, not a status board.
- `docs/machi/M2-2.3-NVIDIA-AMD-PHYSICAL-POC-POLICY-5.md` — current RunPod cost policy ($5 floor, NVIDIA ≤ $1.50/h, AMD ≤ $4.00/h, $40/session, $80/day, one pod, 90 minutes, 3 retries, no network volume).

Evidence / history
- `docs/machi/M0` through `M9` notes and their `*-PHYSICAL.md` files — milestone evidence. Later evidence supersedes earlier "not started" sentences.
- `docs/machi/INFERENCE-PROGRAM-005.md` and `checkpoints/MACHI-INFERENCE-EXEC-005.json` — native L40S request-inference partial pass.
- `docs/machi/OLLAMA-BUNDLE-04-PHYSICAL.md` through `OLLAMA-BUNDLE-07-PHYSICAL.md` and `checkpoints/MACHI-OLLAMA-BUNDLE-0{5,6,7}.json` — Ollama evidence. Bundle 04/05 labels were corrected: `renv_` is not a foundation generation.
- `checkpoints/MACHI-9-SERVE.json` — historical NVIDIA-N1 L5 fail. Not the current Ollama closure.

Debt
- `docs/DEBT.md` — provisional register. Status line of an entry wins over a stale "Why now" sentence when they conflict. See M-6-03 in T.

Control plane (not product)
- `.machi-handoff/CURRENT-INSTRUCTION.md` — this task. Local cache, gitignored.
- `origin/control/machi-handoff` files, including `control/STATE.json` and `control/OLLAMA-BUNDLE-07-LEAD-REVIEW.md` — instruction and review ledger. Cumulative JSON fields are history, not a second status board.

Non-authoritative
- `docs/machi/proposals/MACROPATH-*.md` — untracked, not adopted.
- `docs/legacy/` — previous attempt, evidence only.
- `docs/machi/README.md` — index frozen at the 2.3 era. Do not use it as current status.

D. CURRENT WAYS OF WORKING

Loop
Daniel asks Cursor to continue from the Lead Developer handoff.
Cursor runs `python tools/machi_handoff.py sync`, reads the instruction, inspects the repo, does only that instruction, publishes a paste-back, and stops.
The Lead reviews the paste-back and writes the next instruction on `control/machi-handoff`.
Daniel then starts the next Cursor turn. Cursor does not start the next step by itself.

Before coding, inspect HEAD, the instruction's required SHA, architecture ownership, and the predecessor's evidence. Do not rediscover closed facts.

Bounded increments use predecessor, objective, in-scope, non-goals, acceptance, tests, and an explicit stop. Product-first instructions bind customer meaning, authority, privacy, and evidence. Class names and local refactors are Cursor's unless they change a product invariant.

Exoskeleton-first means one thin path through Discover → Capacity → Foundation → Model → Plan → Admit → Serve before deepening a block. Adjacent slices are bundled when a later slice is unsafe without the earlier correction. That is how Ollama Bundles 04–07 were run. Do not deepen Team Brain, Dynamo, or UI to look further along.

Provider Selection Gate (`docs/machi/ARCHITECTURE.md`): before a new provider-backed component, name the generic capability, list providers, recommend a default, and ask Daniel. Do not skip it because the lab machine already has one vendor.

Industry Solution Selection Gate (same file, and `docs/PRODUCT_VISION.md`): stop when two credible libraries or a build-vs-integrate choice would lock in security, privacy, licensing, or a core contract. If there is no real choice, say "No solution decision required" and proceed. The provider gate is the specialization for a concrete provider.

Acceptance modes in `docs/machi/ROADMAP.md`:
- T0 contract/unit
- T1 replayed fixtures
- T2 clean wheel install
- T3 real host, no model required
- T5 live inference
L1 unit evidence never closes a milestone that touches hardware, storage, or a runtime.

Disposable host: build a wheel from a clean tree, install only that wheel, do not edit product source on the server. Fix locally, rebuild, redeploy.

RunPod, from the policy file above: official tooling only; only pods created in the current conversation; one at a time; NVIDIA ≤ $1.50/h; AMD ≤ $4.00/h; balance floor $5; $40/session; $80/day; ≤ 90 minutes; ≤ 3 provisioning retries; no network volume. A hang is stop-and-ask, not a silent terminate. Do not touch pre-existing pods.

Paste-back: what ran, SHAs, evidence, what was not claimed, and one exact terminal status. Statuses used in this program include PASS-style closure, `DECISION_REQUIRED`, `ENVIRONMENT_BLOCKED`, `PRODUCT_FAILURE`, and `AWAITING_REPOSITORY_EVIDENCE`. Do not soften a failed physical proof into a pass.

E. GITHUB HANDOFF PROTOCOL

`control/machi-handoff` stores instructions, state, and paste-backs. It is not an implementation branch. Never merge it into product history.

Sync: `python tools/machi_handoff.py sync` fetches that branch into gitignored `.machi-handoff/`.
Read order: `STATE.json`, `CURRENT-INSTRUCTION.md`, `ARCHITECTURE-STATE.md`, `OPEN-DECISIONS.md`.
Publish: `python tools/machi_handoff.py publish-pasteback <file>` commits only on the control branch as "Machi Cursor Handoff" and pushes `HEAD:control/machi-handoff`.
`published_instruction_id` is the last published paste-back, not necessarily the instruction currently waiting. Before this publication it still said `MACHI-OLLAMA-BUNDLE-07-NVIDIA-CLOSURE-001` while `instruction_id` was already this onboarding task. That is the protocol, not a product contradiction.

Daniel triggers the next turn by telling Cursor to continue from the handoff. He does not paste the instruction when sync works.
After publication the Lead reads `control/LATEST-PASTEBACK.md` on `control/machi-handoff`.

F. FULL BLOCK → CAPABILITY → COMPONENT TREE

From `docs/machi/ARCHITECTURE.md` section 12, which is the module map. Provider adapters sit under the capability. They are not extra blocks.

```text
0 Kernel
  0.1 Contracts
    0.1.1 Contract registry
    0.1.2 Unresolved semantic
  0.2 Record identity
    0.2.1 Typed prefixed IDs
  0.3 Events
    0.3.1 EventRecord envelope
    0.3.2 Append journal
    0.3.3 Non-blocking observers
  0.4 Persistence
    0.4.1 Store port (FileStore adapter; create + get; migration receipt is adapter behavior)
  0.5 Privacy
    0.5.1 Classification + export allow-list
  0.6 Witness
    0.6.1 DeploymentWitness composer          [deferred, M-9-01]
  0.7 Health
    0.7.1 Aggregator                         [deferred]
1 Install
  1.1 Install identity
    1.1.1 InstallRecord
  1.2 State root
    1.2.1 StateRootBinder
  1.3 Self-ownership
    1.3.1 SelfOwnershipMarker
    1.3.2 RegistrySeed
  1.4 InstallRun
    1.4.1 InstallRunStore
2 Discover
  2.1 Environment
    2.1.1 OS/arch adapter
  2.2 CPU / RAM
    2.2.1 Memory observer
  2.3 Accelerator Discovery
    2.3.1 Native accelerator observer
          NVIDIA, AMD, Apple providers; Intel out
  2.4 Mounts
    2.4.1 Mount enumerator (Linux + macOS; Windows unsupported)
  2.5 PrerequisiteReadiness
    2.5.1 Generic cycle
          AmdSmiPrerequisiteAdapter is not a Discover observer
3 Steward
  3.1 Ownership
    3.1.1 Dual-proof classification
    3.1.2 Conflict and legacy detection
  3.2 Occupancy
    3.2.1 Bounded measurement of verified roots
    3.2.2 Backing-store grouping
  3.3 Reclaimability
    3.3.1 Candidate assessment
    3.3.2 Delete executor                    [Tier 3, not implemented]
4 Capacity
  4.1 Pool identity
  4.2 Characterization (specialist port, sonar, corroboration)
  4.3 SAFE envelope
  4.4 Remaining after occupancy
  4.5 Host minimum
  4.6 Recharacterize
5 Foundation
  5.1 Executors — native process; container descriptor deferred
  5.2 Runtime catalogue — vLLM product; Ollama is a separate engine, not a vLLM mode
  5.3 Resolve
  5.4 Provision
  5.5 Verify — RuntimeCapability
  5.6 Select — AUTO / explicit; RuntimeChoice cites FoundationSelection, it does not replace it
6 Model
  6.1 Explicit sources — hub revision, local import
  6.2 Compatibility — installed-engine query
  6.3 Requirement
  6.4 Select
  6.5 Warehouse
      Ollama catalog is a separate authority (digest), not a warehouse artifact
7 Plan
  7.1 Compose — native DeploymentConfiguration and provider plan
  7.2 CURRENT / STALE
  7.3 Recipe
8 Admit
  8.1 Current capacity snapshot
  8.2 ResourceManager — one ledger for native and provider plans
  8.3 Reservation lifecycle — hold survives STOP; release is explicit
9 Serve
  9.1 Instance
  9.2 Execute — native process; provider serve is a sibling path
  9.3 Readiness
  9.4 Request inference
  9.5 Reconcile / stop
  9.6 Usage event
```

G. BLOCK STATUS TABLE (0–9)

| Block | Purpose | Input | Output | Status | Does not own | Open item that matters |
|---|---|---|---|---|---|---|
| 0 Kernel | Shared mechanisms | none | EventRecord, Store | M0 physical; 0.4.1 Store physical; migration receipt landed in Bundle 07; K-03 retired | domain policy, machine identity | 0.6 Witness and 0.7 Health still deferred (M-9-01) |
| 1 Install | Bind this copy to a disk tree | artifact, chosen root | InstallId, ownership marker, InstallRun | 1.2.1–1.4.1 physically accepted | host facts, admission | none for the spine |
| 2 Discover | Observe the machine | host | OS, memory, accelerators, mounts | 2.1–2.4 accepted on their evidence; 2.3 NVIDIA+AMD coverage is an older SHA, not "all later milestones" | SAFE bytes, ownership | Windows mounts unsupported |
| 2.5 PrerequisiteReadiness | Can this host satisfy a named prerequisite | Discover facts plus a checker | readiness report | 2.5.1 physical PASS on MI300X for missing `amd-smi` yaml | discovery, install, admission | host prerequisites are not a managed ROCm tree |
| 3 Steward | Classify ownership and occupancy | Install evidence, mounts | occupancy, reclaim class | Tier 2 accepted. Does not delete | SAFE authorization, deletion | 3.3.2 delete executor not built |
| 4 Capacity | SAFE envelope | Discover + Steward | CapacityEnvelope, host-minimum | Tier 2 accepted. Reported bytes do not authorize | admission, runtime choice | live quota specialists deferred (M-4-01) |
| 5 Foundation | Prove an execution engine | host + SAFE | FoundationSelection, generation, capability | NVIDIA CUDA qualified. Ollama managed prefix verified on NVIDIA. AMD recipe implemented, not production-qualified | model choice, admission, serving | M-5-AMD-01, M-5-OLLAMA-01, M-5-OLLAMA-04 |
| 6 Model | What artifact exists and whether it may be deployed | explicit source + foundation | warehouse artifact or provider digest, qualification | Warehouse path accepted. Native empirical qualification passed later on one L40S for two SmolLM2 models. Tiny Llama is not deployable | serving, a second catalog merged into the first | M-6-03 still OPEN because its retire-when names NVIDIA-N1; M-6-OLLAMA-01 |
| 7 Plan | A deployment request | model + foundation + SAFE | Plan or provider plan, or a typed refusal | Physically accepted on NVIDIA. Provider plans exist and cite `fgen_` + digest | reservation, launch | M-7-01 multi-GPU and general planners still deferred. The phrase "Ollama planners" in that entry is stale; a bounded provider plan exists |
| 8 Admit | Reserve on one ledger | plan + current SAFE | ResourceReservation | Physically accepted as logical authority. Same ledger admits provider plans | serving, OS enforcement | M-8-01, M-8-02. The roadmap row "Serve is not started" is stale |
| 9 Serve | Run a reserved plan and prove inference | reservation + verified foundation + model | instance, proof, stop | Native request inference passed on one L40S. NVIDIA-N1 tiny-Llama L5 failed. Ollama Serve passed on A40, including AUTO fallback. Witness not composed | admission, planning | M-9-01, M-9-02 |

H. AUTHORITY / DEPENDENCY FLOW

```text
Kernel     mechanisms only. No host policy.
Install    binds identity before any host fact is trusted.
Discover   observes. Never authorizes.
2.5        prerequisite readiness. Not discovery and not install.
Steward    classifies occupancy. Does not authorize a mutation.
Capacity   SAFE envelope. The only storage/memory authorization input.
Foundation proves the engine. Does not pick the model or reserve bytes.
Model      artifact or provider digest, plus qualification. Catalogs stay separate.
Plan       requests a deployment. Does not reserve or launch.
Admit      the only ResourceManager. One ledger.
Serve      executes a reservation. STOP does not release. Release is Admit.
```

AUTO sits in Foundation as `RuntimeChoice`. It records which FoundationSelection was consulted. It does not admit and it does not retry inside Serve. A fallback is a new Foundation → model → Plan → Admit → Serve chain.

I. IMPLEMENTATION ROADMAP (M0→M9)

Sequence is `docs/machi/ROADMAP.md`, not Kultrun `docs/ROADMAP.md`.

M0 Kernel — physical acceptance recorded (`m0/0-kernel` `25f6960`, plus 0.4.1 Store).
M1 Install — closed through 1.4.1.
M2 Discover — 2.1.1, 2.2.1, 2.3, 2.4.1, 2.5.1 accepted on their own evidence. 2.3 NVIDIA+AMD coverage is SHA `eaee5c98` era, not a blanket certificate for later blocks.
M3 Steward — Tier 2 accepted.
M4 Capacity — Tier 2 accepted.
M5 Foundation — NVIDIA CUDA development closed and qualified. AMD physical qualification open.
M6 Model — warehouse accepted. Deployable membership now requires runtime qualification. One later program qualified two real SmolLM2 models on an L40S. The original tiny Llama did not become deployable.
M7 Plan — physically accepted on NVIDIA. Does not admit or serve.
M8 Admit — physically accepted on NVIDIA as reservation authority.
M9 Serve — implemented. Native T5 request inference is a partial pass (one L40S), not an N1 pass, and not a witness.

Ollama macropath is an additional Stage-1 exit on top of that spine, not a renumbering of M0–M9. It is `CLOSED_NVIDIA_STAGE1`.

J. STRATEGIC ROADMAP (STAGES 1→4)

`docs/STRATEGY.md` interprets the build. It does not renumber components.

Stage 1 — product spine. One real vLLM inference path, Ollama as an independent fallback, normalized evidence with provenance. Exit text: useful end-to-end inference on vLLM where the host supports it, Ollama available as fallback, and normalized evidence. The fallback is an exit condition, not a reason to skip vLLM.

What is still missing before Stage 1 can be called exited:
- native request inference is proven on one L40S, not on NVIDIA-N1, and not as a class;
- Bundle 07 did not serve a native model on the A40 where AUTO was proven;
- `DeploymentWitness` is not composed (M-9-01);
- comparative records are a written table, not the Stage-2 experiment schema (S-STRAT-01);
- AMD foundation is not qualified, and strategy's "where the host supports it" is not an all-vendor claim, but Stage 1 should not be narrated as vendor-complete.

Stage 2 — empirical lab. Compare Ollama, vLLM, and later Dynamo on coverage, not a Cartesian benchmark. Do not open it by building Dynamo now. Exit: evidence about which infrastructure to use.

Post-spine, parallel, not a Stage 2 replacement: Runtime Artifact Registry. Reproducible delivery of runtimes, interpreters, packages, and offline bundles. Separate from the Model Warehouse. Starts after artifact identity and provisioning contracts are stable. Becomes a prerequisite for scaled Stage 3 and strong air-gap. Ollama still depends on host `zstd` (M-5-OLLAMA-04), which is a registry-shaped debt, not a reason to start the registry before the Lead says the spine is coherent enough.

Stage 3 — other people's installs, real failures, typed organisational nouns, local-by-default customer content. Gateway, Admin UI, and Knowledge attach here, after a dependable serve path.

Stage 4 — organisational intelligence: memory, agents, Team Brain, Company Brain. Downstream of inference, identity, and knowledge. Not the next build.

K. WHAT JUST HAPPENED — OLLAMA BUNDLE 07

Accepted by control as `bundle_07_accepted: true`. Source `2c12f00`. Checkpoint `checkpoint/ollama-nvidia-stage1-2026-09-24`.

What it added
- Ollama is a separate engine and catalog. Digest is identity. Tag is a display name.
- Native/vLLM stays primary when that foundation is READY or SUPPORTED.
- Explicit vLLM and explicit Ollama do not silently switch.
- Fallback is a new chain, not a hidden Serve retry.
- One ResourceManager ledger.
- `RuntimeChoice` v2 cites the FoundationSelection and capacity evidence actually consulted. v1 migrates to `not_recorded` / `not_consulted` and does not become stronger.
- Schema migration writes an intent receipt, then the record, then completion. A crash stays explainable. K-03 is RETIRED, with the missed "before the first bump" timing kept in the entry history.

Physical host
Secure A40, EU-SE-1, driver 580.159.04, CUDA 13.0, $0.49/h, pod `5vckhyhjmjht55`, created `2026-09-24T13:57:37.59Z`, terminate 204, later get 404.
SAFE host 49463128064. SAFE accelerator 48037363712.
Native foundation `fgen_6e4c419798416a74`, selection `fsel_17d3aa41babb8ffa`, vLLM 0.18.0, support ready.
Ollama `renv_ceedac1939fecd21`, `fgen_66a0af2ac4ba618c`, selection `fsel_66a0af2ac4ba618c`.

AUTO while native was ready: decision `fbk_fa5314e89fc227d3` selected vLLM and created no reservation.
A second provision on that same root reused the healthy generation, so it did not induce failure.
A separate owned root with a missing `uv` path returned `provisioning_failed` / `python_provision_failed` (`fsel_9a7247e225d0d653`). The healthy generation was still present. AUTO then selected Ollama (`fbk_d83226b96d76d7e2`) and served a new plan `plan_d24362279180c37c` and reservation `rsv_35c15204781dc933`.

Two Ollama cases, context 2048, FIT, PASS, shadow unresolved:
- `smollm2:135m-instruct-q8_0` digest `2d470404841a51320639b2c2418c7ad8643cccbbcb88c2a242b211ae83bf46a9`
- `smollm2:360m-instruct-q8_0` digest `dfd48b1fa28f91f94d51037458e22eb461591d2f2f92bb44b115c86ac11b560f`
Negative: context 4096 against the 2048 qualification was `qualification_does_not_cover` before serve.

Not proved
- Native model inference on that A40.
- AMD, ROCm, or all-NVIDIA support.
- Live failover after a failed user request.
- Cross-catalog model translation.
- Multi-model concurrent serving, fleet HA, or a matched-SKU performance ranking.
- `size_vram` is runtime-reported, not an external peak.

L. AMD ACCEPTANCE MODEL

```text
HOST-OWNED
AMD GPU, kernel, amdgpu, firmware, /dev/kfd, /dev/dri
compatible OS / glibc
true irreducible host prerequisites

MACHI-OWNED
managed Python
pinned ROCm userspace (rocm700 recipe: vLLM 0.18.0, Python 3.12, ROCm line 7.0)
package cache under the owned root
verification, generation identity, reuse
```

`docs/machi/M5.md`: a host may already have that userspace, in which case it is verified. A host with a compatible `amdgpu` line and no userspace can realize the same recipe under `foundation/environments/<id>`. ROCm 6.1 is refused. Machi does not replace the kernel, firmware, or a customer ROCm tree, and it does not run `ldconfig`.

"No prebuilt ROCm 7 SSH image" is an environment fact about RunPod images. It is not an AMD product failure. The product can provision userspace when the host prerequisites exist.

`M-5-AMD-01` is OPEN. Latest Bundle 07 preflight: secure MI300X availability `NONE` at $2.39/h (inside the $4 cap). No AMD pod was created. Earlier Foundation work rejected ROCm 6.1 before install and did not reach `READY` on MI300X. AMD is a later cross-macropath qualification, not a reason to reopen NVIDIA Stage-1 Ollama construction. `M-5-AMD-02` (OCI image) and `M-5-AMD-03` (unmeasured prefix bytes) stay open beside it.

M. NATIVE M6/M9 FAILURE + REDESIGN HISTORY

Historical failure, still true
M6 on A40 (`docs/machi/M6-PHYSICAL.md`, commit `a91ab2c`) stored `hf-internal-testing/tiny-random-LlamaForCausalLM` revision `9fb191250dd56d0ba7ec9785a025ed29c03d5998`, artifact `mart_01a30fdd655751ed`, about 6.5 MB. Compatibility was `compatible` because the architecture name was in the vLLM registry. That classification did not prove the model could execute.
NVIDIA-N1 L5 (`checkpoints/MACHI-9-SERVE.json`) then failed. One attempt served the warehouse path as the model name (HTTP 404, pod `b5ifw8mmqtbmcf`). The next, on `b51f6b2`, reached a loopback server and returned HTTP 500 (pod `j08kg2tqv14dyf`). Hidden size 16 and 4 heads make head dimension 4. Pinned vLLM 0.18 flex attention requires at least 16. No token. `M-9-02` records that failure and is still OPEN for that artifact.

Redesign
The qualification funnel now refuses an unsupported attention shape before a deployable membership. `covers()` requires a real qualification identity, including execution environment. A plan without coverage is not served.

Later evidence, different artifact and different host
`docs/machi/INFERENCE-PROGRAM-005.md`, status `NATIVE_VLLM_PARTIAL_PHYSICAL_PASS`, branch `automation/inference-program` at `6e17f4a` (ancestor of HEAD).
N1 Ampere did not run: A40 and RTX A6000 stock were `NONE`. No substitute SKU.
N2 ran on one secure L40S, US-MO-1, pod `o2k1u11gp1fnuy`, terminated 404, generation `fgen_071b23a5b1db1192`, vLLM 0.18.0.
Positive: SmolLM2-135M-Instruct `12fd25f77366fa6b3b4b768ec3050bf629380bac` and SmolLM2-360M-Instruct `a10cc1512eabd3dde888204e902eca88bddb4951`. Qualification pass, request inference pass, restart inference pass. Load about 39.86 s and 36.49 s. About 16.47 and 16.32 tokens/sec.
Negative: the same tiny Llama was `attention_configuration_unsupported` before weight fetch.
`DeploymentWitness` is still deferred (`M-9-01`). Native M9 request inference is therefore partially closed on one Ada host and not closed as NVIDIA-N1 or as a witness.

Do not read M6's original "compatible" as current deployable membership. Do not read M-9-02 as "native inference has never produced a token."

N. CURRENT OPEN GATES / RELEVANT DEBT

| Item | Missing | Why it matters | Blocks Stage-1 exit? | Retire when | When |
|---|---|---|---|---|---|
| M-6-03 | NVIDIA-N1 empirical qualification under the new identity | Debt text still says no hardware qualification exists; that sentence is false after the L40S program. The retire-when still names NVIDIA-N1 | Yes, if Stage-1 native proof must include N1. No, if the Lead accepts the L40S pass as the native proof | one NVIDIA-N1 qualification, or the Lead chooses not to run that probe | next decision |
| M-9-02 | tiny Llama still cannot execute on vLLM 0.18 | Historical N1 failure. Later SmolLM2 pass does not rewrite it | Does not by itself block Ollama closure. Blocks any claim that the stored tiny artifact is served | that artifact completes, or an authorized replacement is proven on its own SHA. The L40S program is a different artifact | do not retry the tiny model |
| M-9-01 | DeploymentWitness, auto-restart, multi-instance, public bind | Stage-1 "health and usage" is thin | Witness is part of a full Stage-1 narrative, not of Ollama Stage-1 | a composer reads stored serve records | after the native-proof decision |
| M-5-AMD-01 | Foundation READY on MI300X / gfx942 | AMD lane | No for NVIDIA Stage-1. Yes for any AMD support claim | READY on an approved recipe. Public AMD support still needs that evidence recorded | later, when a host exists |
| M-5-OLLAMA-01 | loopback API has no Machi auth | another local process can bypass Admit | No for the closed NVIDIA lab claim. Yes before multi-user | an isolation boundary, or an explicit acceptance of loopback trust | later security |
| M-5-OLLAMA-04 | host `zstd` is not a pinned artifact | plug-and-play gap | No for Stage-1 lab hosts that already have zstd | registry helper or in-process decoder | artifact-registry era |
| M-6-OLLAMA-01 | Ollama can evict under a hold | reservation and provider residency can diverge | No for the bounded Stage-1 serves, which re-read `/api/ps` | a stated residency rule | later serve depth |
| M-5-OLLAMA-02 | RuntimeCapability v1 wording still says vLLM | readers can misread an Ollama capability | No | a provider-neutral capability schema | later |
| S-STRAT-01 | experiment records beyond the journal | Stage 2 comparisons | No for Stage 1 | a campaign that needs observed-vs-estimated as its own record | Stage 2 |
| Promotion | `machi` is 79 commits behind | the next branch cut from `machi` would drop the spine | Process blocker, not a product gate | Lead promotes or explicitly says not to | before the next implementation branch |
| M-7-01, M-8-01, M-8-02 | multi-GPU, cgroups, CPU gating | later scale | No | a named policy | not next |

Ollama Stage-1 construction should not be reopened to retire M-5-OLLAMA-01, 02, 04, or M-6-OLLAMA-01.

O. WHERE WE ARE NOW — PAST / PRESENT / FUTURE

PAST — Ollama macropath, Block 5 through 9, closed for one NVIDIA scope
1. Purpose: a second execution path that does not own admission.
2. Capability: Foundation Ollama substrate, provider qualification, provider plan, same Admit ledger, provider Serve, AUTO `RuntimeChoice`.
3. Plain language: if native vLLM is healthy, use it; if product code says it is unavailable, build a new Ollama deployment instead of retrying inside Serve.
4. Inputs: verified foundation, provider digest, SAFE envelope.
5. Outputs: `CLOSED_NVIDIA_STAGE1` evidence at `2c12f00`.
6. Status: accepted. Do not rebuild it.

PRESENT — native request-inference scope is the gap, Blocks 6 and 9
1. Purpose: say which native model can actually be served, and on which host that was proven.
2. Capability: 6.2 compatibility plus 9.4 request inference. Witness 0.6.1 is still absent.
3. Plain language: the tiny stored Llama cannot run; two real SmolLM2 models did run on one L40S; Ampere N1 never ran; the A40 Ollama host proved native foundation readiness, not a native token.
4. Inputs: the L40S evidence, M-6-03, M-9-02, M-9-01.
5. Outputs: a Lead decision on whether that L40S pass is the Stage-1 native proof.
6. Next action: Lead decides. Do not start a campaign from this packet.

FUTURE — either an N1 qualification campaign or, if the L40S pass is accepted, witness/registry work that is still Stage-1-adjacent rather than Stage 4
1. Purpose: finish the spine story or start controlled artifact delivery.
2. Capability: 6.2/9.4 on NVIDIA-N1, or 0.6.1 witness, or the post-spine registry.
3. Plain language: do not jump to Company Brain, UI, or Dynamo.
4. Inputs: the decision in V.
5. Outputs: one bounded instruction, branched from `2c12f00` unless the Lead says otherwise.
6. Next action: write that instruction after review. Not now.

```text
Ollama CLOSED_NVIDIA_STAGE1 + L40S native partial pass
    ↓
Lead decides what "native Stage-1 inference" still requires
    ↓
one bounded workstream from 2c12f00
    (N1 qualification, or accept L40S and move to witness / registry)
```

P. RECOMMENDED NEXT WORKSTREAM (ADVISORY ONLY)

There are two viable next product moves. They are not the same decision. This packet does not choose.

Option 1 — Treat the L40S SmolLM2 program as the native Stage-1 inference proof.
Product outcome: M-6-03's "no hardware qualification" sentence is corrected, and the retire-when is explicitly changed so NVIDIA-N1 is coverage rather than the exit. Then the next build can be witness or the artifact registry, not another model hunt.
Predecessor: `INFERENCE-PROGRAM-005` plus Bundle 07.
Blocks: 6 and 9 for the decision; 0.6.1 only if witness is chosen next.
Inputs: existing L40S evidence. No new host required for the decision itself.
Outputs: a debt/roadmap amendment, then a separate instruction.
Retires: the misleading part of M-6-03. Does not retire M-9-02's tiny-Llama fact.
Local work: docs and debt only, after the Lead authorizes the re-scope.
Physical NVIDIA: not for the decision. Later witness work may want a host.
AMD preflight: no.
Provider Selection Gate: no, if no new provider is added.
DECISION_REQUIRED if anyone treats L40S evidence as retiring a debt line that still says NVIDIA-N1.
Out of scope: reopening Ollama, AMD, Dynamo, UI.
After it passes: pick witness or registry as its own instruction.

Option 2 — Run NVIDIA-N1 empirical qualification and request inference with a redesigned-funnel model (SmolLM2 class, not the tiny Llama).
Product outcome: M-6-03 can retire on its written NVIDIA-N1 condition, and native T5 exists on a second hardware class.
Predecessor: same evidence, plus live stock.
Blocks: 6.2, 7, 8, 9.4.
Inputs: a qualified artifact, a verified foundation, one owned NVIDIA-N1 host.
Outputs: qualification evidence and a request-inference proof, or a typed environment block.
Retires: M-6-03 if the probe passes. M-9-02 only if the Lead also replaces that artifact in the debt text; a SmolLM2 pass does not make the tiny Llama executable.
Local work: confirm the funnel still refuses head dimension 4, then a frozen wheel.
Physical NVIDIA: yes, after local gates. Standing cost policy applies.
AMD preflight: only if the instruction also asks for AMD. It should not be a gate for this NVIDIA stream.
Provider Selection Gate: no new provider.
DECISION_REQUIRED if stock is empty and someone proposes a different SKU as "N1".
Out of scope: Ollama rebuild, multi-model scheduling, witness, registry, UI.
After it passes: then decide witness vs registry.

Advisory lean, not a silent choice: Option 1 is the smaller truthful step if the Lead is willing to say the L40S pass is enough for Stage-1 native inference. Option 2 is required if the written M-6-03 retire-when is still binding. Do not start the artifact registry or AMD until that is answered. Do not cut the next branch from `machi`.

Q. PROVIDER / SOLUTION DECISION STATUS FOR THAT NEXT WORKSTREAM

No new provider and no new library are required for either option. vLLM remains the native engine. Ollama remains the fallback already selected.
"No solution decision required" for a library choice.
The Provider Selection Gate does not re-open for vLLM or Ollama.
The decision that is required is product scope (N1 vs accept L40S), which is V, not a provider bake-off.

R. PHYSICAL ACCEPTANCE EXPECTATIONS

Not in this task. No server was created.

If Option 2 is later authorized: T5 on a real accelerator, immutable wheel, no remote source edits, RunPod policy in section D, one owned pod, terminate on success or terminal product failure, hang means stop-and-ask.
If Option 1 is only a debt re-scope: no host.
AMD preflight is not required for a docs re-scope and is not a gate for a NVIDIA-N1 run. It is required again when an instruction includes AMD.
Native inference claims remain T5. Foundation READY alone is T3-class and must not be narrated as tokens.

S. BRANCH / CHECKPOINT / PROMOTION GUIDANCE

Latest accepted source: `2c12f00286d6e7d6d524baa7a7787099e476bf08`.
Branch that points at it: `automation/ollama-macropath` and `checkpoint/ollama-nvidia-stage1-2026-09-24`. Both match `origin`.
`machi` / `origin/machi`: `1db7646`. It is intentionally still the early integration tip. Later milestone commits say "canonical machi is unchanged." That pattern was never closed. Promotion is outstanding. This task did not promote.
Best recovery point for the current product: `checkpoint/ollama-nvidia-stage1-2026-09-24`.
Older Ollama checkpoints, do not move: `checkpoint/ollama-generation-bound-serve-2026-09-24` (`92555da`), `checkpoint/ollama-authorized-serve-2026-09-24` (`ebfabe5`).
Native partial pass, do not move: `origin/checkpoint/native-vllm-partial-pass-2026-09-24` (`6e17f4a`).
`m0`–`m9/*` branches are historical acceptance tips. Their commits are ancestors of HEAD, but the branch tips are not the latest source.
`kultrun`, `main`, `phase9`, `stage/1.6*`, `acceptance/1.6L*`, and `backup/*` are other lineages or safety snapshots. Not the next Machi base.
`control/machi-handoff` is control-only.
If nothing changes before Lead review, the next implementation branch starts at `2c12f00286d6e7d6d524baa7a7787099e476bf08`, not at `machi`.

T. CONTRADICTIONS / STALE DOCUMENTATION

1. `docs/machi/README.md` says the last accepted forward feature is 2.2.1 and status is the 2.3 NVIDIA+AMD coverage close. Win: `ROADMAP.md` plus Bundle 07 evidence and SHA `2c12f00`. README is an old index.
2. `docs/machi/README.md` and the Lead agent both say canonical `machi` is `1db7646`. The ref is true. The implication that it is the accepted product tip is false. Win: `origin/machi` for the branch pointer; `automation/ollama-macropath` for accepted source.
3. `docs/machi/MACHI_LEAD_DEVELOPER.md` and `.cursor/agents/machi-lead-developer.md` say "Next: Model. Not started" and "the fallback runtime is not implemented." Win: ROADMAP Ollama row and Bundle 07. The agent file is operating guidance with a stale status block.
4. `docs/machi/ROADMAP.md` M6 row says "Physical qualification is not run (`M-6-03`)." Win: `INFERENCE-PROGRAM-005.md` for the L40S qualification. M-6-03 stays OPEN only because its retire-when still says NVIDIA-N1.
5. `docs/machi/ROADMAP.md` M8 row says "Serve is not started." Win: M9 row, inference program, and Ollama Bundle 07. The M8 row was not updated when Serve landed.
6. `docs/DEBT.md` M-6-03 "Why now" says no external artifact has a hardware qualification pass. Win: the L40S program. Do not treat that sentence as current. Do not treat the OPEN status as already retired.
7. `docs/DEBT.md` M-7-01 still lists "Ollama planners" among deferred work. Win: provider-plan code and Bundle 07. The rest of M-7-01 (multi-GPU, tensor parallel above 1) still stands.
8. `docs/DEBT.md` M-5-OLLAMA-03 header label still says DEFERRED while Status says RETIRED (bundle 04). Win: the Status line.
9. Control `STATE.json` still carries `bundle_05_source_closed: false` and the three Bundle 05 blocker strings, and `published_instruction_id` lagged this new instruction until paste-back. Win: `bundle_07_accepted`, `ollama_stage1_status: CLOSED_NVIDIA_STAGE1`, and this instruction. The older JSON fields are a cumulative ledger, not the current blocker list.
10. `docs/machi/INFERENCE-PROGRAM-005.md` "Next program" says do not start the Ollama provider-selection gate from that report. That gate has since been passed and the macropath closed. Win: Bundle 07. The inference report's next-step line is historical.
11. Untracked `docs/machi/proposals/MACROPATH-*.md`. Win: `ROADMAP.md`, which marks them not adopted. One of them prefers Ollama as default. That is not policy.
12. `checkpoints/MACHI-6-MODEL.json` records `canonical_machi` as `1db7646` and does not list M-6-03. It is the M6 warehouse checkpoint, not the post-funnel world. Win: later checkpoints for later claims.
13. Bundle 04/05 docs once called `renv_ceedac1939fecd21` a foundation generation. Those files now say it is the runtime-environment id. Win: the corrected banners and Bundle 07, which recorded `fgen_66a0af2ac4ba618c` separately.

U. LEAD DEVELOPER READING ORDER

```text
If you need to understand...
├── where HEAD is .............. git: automation/ollama-macropath @ 2c12f00
├── this task ................... control CURRENT-INSTRUCTION (onboarding)
├── what Ollama closed .......... docs/machi/OLLAMA-BUNDLE-07-PHYSICAL.md
│                                 checkpoints/MACHI-OLLAMA-BUNDLE-07.json
├── what native inference did ... docs/machi/INFERENCE-PROGRAM-005.md
│                                 checkpoints/MACHI-INFERENCE-EXEC-005.json
├── what native inference failed  checkpoints/MACHI-9-SERVE.json
│                                 docs/DEBT.md M-9-02 and M-6-03
├── architecture ................ docs/machi/ARCHITECTURE.md §§5, 12, gates
├── build sequence .............. docs/machi/ROADMAP.md (watch stale rows)
├── strategy stages ............. docs/STRATEGY.md "Four strategic stages"
├── product meaning ............. docs/PRODUCT_VISION.md
├── debt that matters now ....... docs/DEBT.md entries in section N
├── AMD model ................... docs/machi/M5.md and M-5-AMD-01
├── how we work ................. .cursor/rules/machi-handoff.mdc
│                                 docs/machi/ARCHITECTURE.md gates
└── do not treat as current ..... docs/machi/README.md status block
                                  docs/machi/MACHI_LEAD_DEVELOPER.md "Next: Model"
                                  docs/machi/proposals/
```

Second-tier investigation: `M6-PHYSICAL.md`, `M8-PHYSICAL.md`, `M5-PHYSICAL.md`, `OLLAMA-BUNDLE-04` through `06`, `CONTRACTS.md`, `TELEMETRY.md`, `KULTRUN.md`.

V. EXACT QUESTIONS THE LEAD MUST DECIDE NEXT

1. Is the L40S SmolLM2 request-inference pass the native Stage-1 proof, or does M-6-03's written NVIDIA-N1 retire-when still bind the next campaign?
2. Should `2c12f00` be promoted onto `machi` before the next implementation branch, or should `machi` stay a historical integration tip on purpose?
3. After that answer: is the following build witness (`M-9-01`), the Runtime Artifact Registry, or an N1 physical campaign? Do not start more than one.
4. Confirm AMD stays off the critical path until a host with kernel/`amdgpu` prerequisites exists, with Machi-owned ROCm userspace rather than a prebuilt ROCm 7 image as the acceptance model.

No solution-library decision is waiting. No Ollama policy change is waiting.

W. CONFIDENCE / UNRESOLVED FACTS

High: SHAs, branch ancestry, Bundle 07 host facts, L40S inference facts, AMD preflight `NONE`, K-03 retired text, and the `machi` vs HEAD count. Those were read from git and the cited files in this workspace.

Unverified by a new physical run, because this task forbade one: that the A40 vLLM generation still verifies today. The Bundle 07 manifest recorded vLLM 0.18.0 and support ready at the time. That evidence stands until a later instruction reruns it.

Not resolved by the repo: whether the Lead wants NVIDIA-N1 to remain the M-6-03 exit. The debt text and the later L40S evidence disagree, and this task must not retire the debt to hide that.

X. EXACT STATUS

PASS_READ_ONLY_ONBOARDING_COMPLETE

Y. STOP

No product source, tests, architecture, roadmap, debt, checkpoints, or implementation branches were modified.
No server was created. No candidate was built. No model was downloaded. No inference was run.
No next workstream was started.

STOP — WAIT FOR LEAD DEVELOPER REVIEW.

# ================================================================================
# ============================ PASTE BACK END ====================================
# ================================================================================
