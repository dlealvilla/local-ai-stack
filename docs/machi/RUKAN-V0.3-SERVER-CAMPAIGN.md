# Rukan v0.3 server campaign

## D1 product-gap architecture review

D1 omitted `huggingface_hub` because the HUB adapter imports it lazily and the
Machi wheel declared an empty dependency list. A clean install therefore
reported `source_unavailable` even though Acquire is a supported product
action. The control-plane dependency stays separate from the managed vLLM
environment.

Deployment coordination belongs in a Rukan adapter, not in React and not in
Plan, ResourceManager, or Serve. Model still owns the stored artifact and
compatibility. Foundation owns the verified generation. Capacity owns the
envelope. Plan owns `DeploymentConfiguration`. ResourceManager is the only
admission authority. Serve owns the process. The coordinator only sequences
those calls, stores references, and maps failures.

The browser may send an `artifact_id`, a request key, and nothing that names
a plan, fingerprint, reservation, port, pid, provider, or capacity figure.
The backend loads the stored artifact, verifies its hashes, recomputes
capacity, and uses the foundation-cited envelope. A live accelerator ceiling
that is lower than that envelope refuses the deploy. An unresolved live
accelerator does not replace the cited envelope and does not invent bytes.
If stored qualification does not cover the artifact, the coordinator earns
it with one reserved Serve proof and releases that hold before the
deployment admission. The qualification id comes from `qualification_identity`.
The same request key returns the same operation. A different intent with
that key is refused. A failed operation stays failed until a new key is
used. A second replica is not created while one deployment is READY.

Before admission, failure leaves no reservation and no process. Admission
rejection does not start Serve. If Serve fails after a reservation exists,
the coordinator stops through Serve and releases through ResourceManager only
when the process is stopped. Otherwise the reservation stays and the
operation is `recovery_required`. STOP and RELEASE stay separate.

Restart reads the operation record and the Serve store. It does not mint a
second server because memory was lost. Native vLLM is the path this
coordinator starts. Provider unload remains on the existing lifecycle owner.

D2 must prove the frozen wheel can acquire the public small model with no
extra pip install, deploy through the Admin HTTP API to READY, run at least
three inferences, stop, and release.

Master instruction: `RUKAN-V0.3-CLOSURE-AND-SERVER-CAMPAIGN-001`

Terminal status of this run: `RUKAN_V0_3_SERVER_CAMPAIGN_NOT_READY`

## Gate A

Closed the four Lead-review accountability defects on
`rukan/connected-monitoring-v0.3`.

- Source: `6dcc91239750e8390530963bb6508e79545a0798`
- Wheel: `machi-0.1.0-py3-none-any.whl`
- SHA256: `898643b7d77c106819f25bd4881203f72835ab3f5fb4524a21d544107e19c95c`
- Build: `0.1.0+6dcc91239750`
- `verify_ok`
- `tests/machi` and `tests/acceptance_lab` exited 0
- ruff and strict mypy passed
- Admin and Command Center Vitest, typecheck, and production builds passed
- Development soak exited 0 with eight periodic reports and gaps of about 120 seconds

Gate A status: `RUKAN_V0_3_PRODUCTION_CANDIDATE_READY_FOR_SERVER_ACCEPTANCE`

## Gate B diagnostic D1

One campaign-owned pod was created and then terminated.

- Pod: `l6x2ct2u5soz9b`
- GPU: NVIDIA L40S, secure cloud, CUDA 13.0
- Price stated before creation: `$1.09/hour`
- Created: `2026-09-29T07:10:39Z`
- Terminated after the evidence below
- No pre-existing pod was started, stopped, or deleted
- Live balance before creation: `$42.48`
- No network volume

What the frozen wheel proved on that host:

- Artifact-only install into `/opt/rukan`
- Install record `inst_abaecaee737eb5be`
- Packaged Admin on `127.0.0.1:8765` returned HTML
- Packaged Command Center on `127.0.0.1:8780` returned HTML
- Intake on `127.0.0.1:8781` with a campaign certificate; GET returned 404
- People smoke: platform deny closed inference with provenance `platform_parent`
- Monitoring was set to Development, 120 seconds, with `local_test` false
- The test report was accepted over verified HTTPS
- Three periodic reports and foundation/capacity event reports were stored
- Foundation generation `fgen_5c0c9e472c4371a4` verified vLLM `0.18.0`

What did not finish:

- `model acquire` on the clean wheel returned `source_unavailable` because
  `huggingface_hub` is not a declared wheel dependency
- After a test-only install of that library, acquire stored
  `mart_7ff1b147d6c56cd6` for SmolLM2-135M-Instruct
- Plan, ResourceManager admission, Serve start, and inference requests were
  not completed. The shipped Admin seam stops and releases an existing
  instance. It does not compose a plan or admit one.
- Confidence runs C1, C2, and C3 were not started

The test-only library install is not the accepted product fix.

## D2 candidate wheel

Built from a clean tree after the deployment closure.

- Source: `f08b46ff1d37a28e95c041ddc1da4d77b6068d9b`
- Wheel: `machi-0.1.0-py3-none-any.whl`
- SHA256: `a337167aa04dfa48bf35d634254193631b4a979eca72d2ca9cdce612617f921f`
- Size: 571293
- Build: `0.1.0+f08b46ff1d37`
- `clean` true
- Isolated install imported `huggingface_hub` 0.36.2 with no extra pip install
- Inspect of SmolLM2-135M-Instruct resolved revision `12fd25f77366fa6b3b4b768ec3050bf629380bac`
- Acquire on this Mac, which has no managed vLLM interpreter, returned `runtime_capability_unresolved` rather than `source_unavailable`

## Diagnostic D2

Clean. Streak is 1. The next diagnostic is D3 on the same wheel.

- Pod `nr2agrcigvr43k`, NVIDIA L40S, secure, CUDA 13.0, US-MO-1
- Price stated before creation: `$1.09/hour`
- Created `2026-09-29T09:50:56Z`, terminated after the evidence below
- Install `inst_0ace142e715584a2`
- Foundation generation `fgen_7b2b244f9a4e7043`, vLLM `0.18.0`, torch `2.10.0+cu130`
- Artifact `mart_7ff1b147d6c56cd6`, revision `12fd25f77366fa6b3b4b768ec3050bf629380bac`
- Admin acquire stored that artifact with no extra pip install
- Deploy operation `dop_dd0b79ed9a8231f3` reached `ready`
- Plan `plan_327f3025d4dfdd51`
- Reservation `rsv_2c817e2752ff5fe2` was `RESERVED` after STOP and `released` after RELEASE
- Serving instance `sin_9fd71986914d7dd1`; both recorded pids were absent after STOP
- Qualification `qev_ae3caf57009d3ea5`
- Three inference requests on that instance: 3 input tokens, 8 output tokens, latency about 0.03–0.037 seconds
- The same deploy request returned the same operation and instance
- Admin restart reconstructed that same ready operation
- Command Center stored the deployment as `vllm` / `mart_7ff1b147d6c56cd6`
- Usage rollup: 3 requests, 9 input tokens, 24 output tokens
- Development cadence 120 seconds; the installed production interval remains 21600
- Reports included `deployment_ready`, four `periodic` reports, then `deployment_stopped,reservation_released`
- The Command Center database did not contain the test prompt
- No manual database repair and no manual dependency install

## Diagnostic D3

Clean. Streak is 2. The frozen candidate is the D2 wheel. Confidence runs use that artifact and no other.

- Pod `kvf30h5fv6u1o0`, NVIDIA L40S, secure, CUDA 13.0, EU-NL-1, `$1.09/hour`
- Created `2026-09-29T10:12:17Z`, terminated after the evidence below
- Install `inst_a1a0922f146dbc80`
- Deploy operation `dop_7f8429602f2bc43a` reached `ready` on the same wheel
- Plan `plan_ce0875479ef374e5`
- Reservation `rsv_f77cf1297fb8da11` stayed reserved after STOP and was released after RELEASE
- Instance `sin_e19d376e973fa3c6`; recorded pids were absent after STOP
- Qualification `qev_2bf63adeedf7a811`
- Three inferences: 3 input tokens, 8 output tokens
- Admin restart kept that ready operation
- Reports: `deployment_ready`, three `periodic` reports, then separate `deployment_stopped` and `reservation_released`
- Command Center usage was 3 requests, 9 input tokens, 24 output tokens
- The test prompt was not in the Command Center database

## Frozen confidence candidate

That candidate was invalidated by C1. It is not the confidence wheel.

- Source: `f08b46ff1d37a28e95c041ddc1da4d77b6068d9b`
- Wheel SHA256: `a337167aa04dfa48bf35d634254193631b4a979eca72d2ca9cdce612617f921f`
- Build: `0.1.0+f08b46ff1d37`

## Confidence C1

Not clean. The confidence streak is 0. The clean diagnostic streak is 0. The next step is a corrected wheel and diagnostic D4.

- Pod `fm4lse85w8orj2`, NVIDIA L40S, secure, CUDA 13.0, US-MO-1, `$1.09/hour`
- Created `2026-09-29T10:29:18Z`, terminated after the defect below
- One create attempt returned HTTP 500 and left no pod; the retry created this pod
- Install `inst_3d636d9d1d833d43`
- Deploy `dop_7cd87d2aba85f5b8` reached `ready` on the frozen wheel
- Plan `plan_5cdc5e61594163d0`
- Deployment reservation `rsv_662c098855459fd4` was still `RESERVED` after the product RELEASE
- The product RELEASE acted on probe reservation `rsv_221147b6a8639676` because the stopped chain chose the lexicographically greater instance id
- Instance `sin_7b6bdb1a6b1196fe` was confirmed dead after STOP
- Three inferences completed
- Intake was stopped, the next send recorded `Connection refused` with one report queued, and restoring intake delivered later periodic reports
- The test prompt was not in the Command Center database

Violated invariant: after STOP, RELEASE must free the deployment reservation. A finished qualification probe must not become the chain merely because its instance id sorts later.

## Corrected wheel

- Source: `77923d0587a7ca4519a1a90dd5097a89ca4844e2`
- Wheel SHA256: `6c5482508806facf0d1b19d13325387ccdc2fd1bbc8ca24bba36ac89e27aeb33`
- Build: `0.1.0+77923d0587a7`
- Clean streak after C1: 0. D4 is the next diagnostic.

## Diagnostic D4

Clean on the corrected wheel. Streak is 1. Next is D5 on this same wheel.

- Pod `2kc05bh8umsytx`, NVIDIA L40S, secure, CUDA 13.0, US-TX-4, `$1.09/hour`
- Created `2026-09-29T10:56:56Z`, terminated after the evidence below
- Install `inst_5cb1ca809d89c788`
- First deploy `dop_3255ab5443cf799e`, reservation `rsv_4b2a5cce97937d11`
- After STOP the chain still named that reservation and it stayed reserved
- RELEASE freed that reservation. No active hold remained
- Second deploy `dop_7d12e3c700d93369`, reservation `rsv_db2109103171ac49`, instance `sin_992726a53676e728`
- Admin restart kept that ready operation
- STOP left that second reservation held; RELEASE released it
- Three inferences on the first deployment: 3 input tokens, 8 output tokens
- Development cadence 120. Reports included `deployment_ready`, `deployment_stopped`, `reservation_released`, and three `periodic` reports
- Command Center usage was 3 requests, 9 input tokens, 24 output tokens
- The test prompt was not stored

## Diagnostic D5

Clean on the same corrected wheel as D4. Streak is 2. Confidence starts again from zero on that wheel.

- Pod `2gnvk17pysp5l3`, NVIDIA L40S, secure, CUDA 13.0, `$1.09/hour`
- Created `2026-09-29T11:19:15Z`, terminated after the evidence below
- The first placement attempt found no instance; the retry created this pod
- Install `inst_da8bc8a893a00829`
- Deploy `dop_4eb54fdab63a56ff` reached `ready`
- Plan `plan_3f5c1b171cf22494`
- Reservation `rsv_dfc8b14dff003471` stayed reserved after STOP and was released after RELEASE
- Instance `sin_d4dab59e45d90a37`; recorded pids were absent after STOP
- Qualification `qev_ec1815d856631259`
- Three inferences: 3 input tokens, 8 output tokens
- Admin restart kept that ready operation
- Development cadence 120
- Reports included `deployment_ready`, four `periodic` reports, and `deployment_stopped,reservation_released`
- Command Center usage was 3 requests, 9 input tokens, 24 output tokens
- The test prompt was not stored

## Frozen confidence candidate

- Source: `77923d0587a7ca4519a1a90dd5097a89ca4844e2`
- Wheel SHA256: `6c5482508806facf0d1b19d13325387ccdc2fd1bbc8ca24bba36ac89e27aeb33`
- Build: `0.1.0+77923d0587a7`
- D4 and D5 both used this wheel. Do not rebuild it for C1, C2, or C3.

## Confidence C1

Clean on the frozen wheel. Confidence streak is 1. C1 included the intake outage.

- Pod `gmwt3z2qiujx4m`, NVIDIA L40S, secure, CUDA 13.0, US-MO-1, `$1.09/hour`
- Created `2026-09-29T11:51:42Z`, terminated after the evidence below
- Install `inst_9881a22ecc8be565`
- Deploy `dop_98a5278e8bc10fec` reached `ready`
- Plan `plan_14ead074541306eb`
- Reservation `rsv_aa822ce8149dca33` stayed reserved after STOP and was released after RELEASE
- Instance `sin_3b5841cb05afcc33`; recorded pids were absent after STOP
- Qualification `qev_7925ea0c58e9180b`
- Three inferences: 3 input tokens, 8 output tokens
- Admin restart kept that ready operation
- Intake was stopped, the next send recorded `Connection refused` with one report queued, and restoring intake cleared the error and delivered later reports
- Reports included `deployment_ready`, five `periodic` reports, `deployment_stopped`, and `reservation_released`
- The test prompt was not stored

## Confidence C2 and C3

C2 and C3 were not run. Secure L40S and RTX 6000 Ada both returned no instance during the last placement window, and the following catalog read showed both `NONE`. No pod id was created. That is provider stock, not a product failure. Their status is `DEFERRED_PROVIDER_STOCK_PHYSICAL_CONFIDENCE`.

## Bounded acceptance

Status: `RUKAN_V0_3_IMPLEMENTATION_ACCEPTED_PHYSICAL_CONFIDENCE_PENDING`

This is not `RUKAN_V0_3_SERVER_CAMPAIGN_PASS`.

Local regression on this branch, with the frozen wheel left unchanged:

- `ruff check src/machi tests/machi tests/acceptance_lab` passed
- `mypy --strict src/machi` passed
- `tests/machi` passed
- `tests/acceptance_lab` passed
- Admin and Command Center tests, typecheck, and production builds passed
- on-disk wheel SHA256 remains `6c5482508806facf0d1b19d13325387ccdc2fd1bbc8ca24bba36ac89e27aeb33`
- commits after `77923d0587a7ca4519a1a90dd5097a89ca4844e2` change only this campaign note

The implementation may be merged for downstream development. Two further confidence servers remain physical-confidence debt. A later v0.4 campaign that re-runs the full v0.3 path does not rewrite this history.
