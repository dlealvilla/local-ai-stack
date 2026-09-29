# Rukan v0.3 server campaign

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
