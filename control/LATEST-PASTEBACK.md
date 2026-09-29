# PASTE BACK

A. Terminal status

`RUKAN_V0_3_SERVER_CAMPAIGN_NOT_READY`

## Gate A

Gate A status: `RUKAN_V0_3_PRODUCTION_CANDIDATE_READY_FOR_SERVER_ACCEPTANCE`

- Starting SHA: `5aaa43d81645c8266f3cad11b91aa57e93d59b96`
- Correction SHA: `6dcc91239750e8390530963bb6508e79545a0798`
- Branch: `rukan/connected-monitoring-v0.3`, pushed
- Wheel SHA256: `898643b7d77c106819f25bd4881203f72835ab3f5fb4524a21d544107e19c95c`
- Build: `0.1.0+6dcc91239750`, size 559449, clean source, `verify_ok`

Corrected accountability:

- Cumulative usage is a compacted base plus retained rows. Retention does not shrink the total.
- A report acknowledges only a usage-sequence prefix that fits in 32 rollup groups. The remainder stays pending and is marked `usage_backlog`.
- Legacy rows receive unique sequences. Rows strictly before the old window start are treated as delivered. The migration sets `legacy_usage_migration_uncertain` because a timestamp window is not an exact cursor, and accounting is degraded.
- Command Center cursors are keyed by install and stream. A new stream becomes current when its first accepted report is sequence 1. Older streams stay history. Raw bodies are retained by receiver time.

QA: `tests/machi` and `tests/acceptance_lab` exited 0. ruff passed. mypy strict on `src/machi` passed. Admin Vitest 4 and Command Center Vitest 5 passed, with production builds. Development soak exited 0: eight periodic reports, gaps about 120 seconds, intake outage, Admin restart, People canary absent from Command Center.

## Gate B

Diagnostic D1 only. Confidence runs were not started.

- Pod `l6x2ct2u5soz9b`, NVIDIA L40S, secure, CUDA 13.0, `$1.09/hour`
- Created `2026-09-29T07:10:39Z` and terminated in this session. `get-pod` now returns 404.
- No other pod was mutated.
- Balance before creation: `$42.48`. Estimated GPU time is under 15 minutes.
- Source for the server install: `6dcc91239750e8390530963bb6508e79545a0798`
- Same wheel hash as Gate A

Proved on the host from the wheel:

- Install `inst_abaecaee737eb5be`
- Packaged Admin and Command Center HTML
- TLS intake, GET 404, test report accepted with certificate verification and `local_test` false
- Development cadence 120 seconds
- People platform deny forces inference deny with `platform_parent`
- At least three periodic reports plus foundation and capacity event reports
- Foundation `fgen_5c0c9e472c4371a4` verified vLLM 0.18.0

Not proved:

- Clean-wheel model acquire. The first attempt returned `source_unavailable` because `huggingface_hub` is not declared. A test-only install of that library then stored `mart_7ff1b147d6c56cd6`. That install is not the product fix.
- Plan, admission, Serve start, three inference requests, stop, and release
- C1, C2, and C3

Campaign branch `rukan/v0.3-server-campaign` is pushed at `7a17b3b346e7c36cdc087b206e34b6a3c86dc4e7`. The note is `docs/machi/RUKAN-V0.3-SERVER-CAMPAIGN.md`. `origin/machi` was not moved. The owned pod is terminated.

B. Why this is not a pass

The accountability correction is ready for server acceptance. The campaign itself did not reach two clean diagnostic iterations or three confidence runs, and it did not complete a real inference admission chain.

C. STOP

STOP for Lead review.
