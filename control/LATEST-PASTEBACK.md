# RUKAN-DUAL-UI-V0-001

## A. EXACT STATUS

RUKAN_DUAL_UI_V0_LOCAL_PASS

## B. EXECUTIVE TL;DR

Rukan Admin and Rukan Command Center v0 both run locally as separate planes. Admin is a loopback seam over stored Stage-1 contracts plus a Rukan-owned inference tester. Command Center imports a versioned non-content support snapshot and does not claim a deployment is live. The internal package remains `machi`. No physical host, LibreChat, Dynamo, registry, or remote control was added.

## C. STARTING / FINAL SHA

- Canonical baseline: `4cb89622a4cd3a1a37bf6ab44c4414e4287e8934`
- Final implementation SHA: `cd14b3ed8490f7ceb64db50b17646acc4b18eaa1`

## D. BRANCH / ORIGIN / WORKTREE

- Branch: `rukan/dual-ui-v0`
- Origin: `origin/rukan/dual-ui-v0` = `cd14b3ed8490f7ceb64db50b17646acc4b18eaa1`
- Branched from `origin/machi` after fetch. `origin/machi` is `4cb89622a4cd3a1a37bf6ab44c4414e4287e8934`.
- Local `machi` was fast-forwarded to that same tip before the branch was created.
- Untracked `docs/machi/proposals/` was not committed.

## E. RUKAN NAMING CHANGES

New product docs and both UIs say Rukan. Historical Stage-1 evidence was not rewritten. See `docs/machi/RUKAN.md`.

## F. INTERNAL `machi` NAMESPACE DEFERRED MIGRATION BOUNDARY

Python package, contract kinds, ids, environment variables, state-root names, the handoff branch, and historical checkpoints stay `machi`. The support snapshot records `product_name=Rukan` and `package_name=machi` together.

## G. FRONTEND SOLUTION GATE / CHOSEN STACK

No existing authoritative Machi frontend. Kultrun's console was not reused. No solution decision required. Both apps are TypeScript, React, and Vite, with a small shared folder and no Node server, Next.js, Electron, or Tauri.

## H. TWO-PLANE ARCHITECTURE

- `ui/admin` renders and calls the loopback seam. It does not own host, model, admission, or serve truth.
- `ui/command-center` only imports snapshot files into browser `localStorage`. It does not call Admin and cannot mutate a deployment.
- Shared code is theme, snapshot validation, and the import store. Authority stays in the Python contracts.

## I. LOCAL RUKAN API / CONTROL SEAM

`machi admin serve` binds `127.0.0.1` only. API name `rukan.admin.v1`. Routes: `GET /v1/summary`, `GET /v1/snapshot`, `POST /v1/inference`, `POST /v1/models/inspect|import|acquire`, `POST /v1/lifecycle/stop|release`. Every JSON body has `outcome`. A non-loopback `Origin` is refused. There is no shell passthrough. `0.0.0.0` is refused.

## J. EMBEDDED INFERENCE IMPLEMENTATION

The browser sends `{prompt, max_tokens}` only. The seam uses the single stored READY instance. Zero or several READY instances are a typed refusal and the completer is not called. Native completion uses the stored loopback port and `/v1/completions`. Provider completion uses the configured loopback provider base and the stored catalog name. Text is returned to the browser with `stored: false` and is not written into the store.

## K. LIBRECHAT DECISION

LibreChat is not the Admin inference UI and is not a dependency. A later employee chat client may use a standard endpoint. It must not own deployment semantics.

## L. RUKAN ADMIN — OVERVIEW

Build, Witness verdict and reason, macropath, model identity, instance state, reservation state, SAFE host and accelerator bytes, and the pending physical-coverage register. No uptime, utilisation, SLA, or cost cards.

## M. RUKAN ADMIN — INFERENCE

One prompt, one reply, completion tokens when reported, typed refusal otherwise. Send stays disabled unless the chain basis is `authorised_ready_instance`.

## N. RUKAN ADMIN — MODELS

Lists stored warehouse artifact ids and provider digests. Inspect, warehouse import, and one-revision hub acquire are enabled only when those callables are attached. The CLI attaches them. No marketplace, ranks, or cross-catalog translation.

## O. RUKAN ADMIN — DEPLOYMENT

Shows Foundation, model, plan, reservation, instance, proof, and Witness. Stop and release buttons follow attachment flags. Release stays disabled while the instance is starting, ready, or stopping. The CLI does not attach a live process supervisor, so those actions return `lifecycle runtime is not attached` until a handler is injected. The ordering itself is tested.

## P. RUKAN ADMIN — SYSTEM

OS family, architecture, memory evidence, accelerator summary, mount count, SAFE bytes, capacity observation time, and the product qualification register. Missing records stay `not_recorded` or `unresolved`.

## Q. DEPLOYMENT SUMMARY / SUPPORT SNAPSHOT CONTRACT

`kernel.support_snapshot` version 1, schema name `rukan.support_snapshot`. Deterministic `snap_` id from the cited fields and `exported_at`. `install_created_at` is the install record's creation time. `exported_at` is when the projection was written. `capacity_observed_at` is when that envelope was derived.

## R. SNAPSHOT PRIVACY / REDACTION

Prohibited keys include prompt, response, documents, credentials, and paths. Support events are `public_ops` or `operational` envelopes only. Payloads are omitted. `accept_snapshot` rejects prohibited keys, unknown versions, and documents over 256 KiB.

## S. COMMAND CENTER LOCAL STORE

`localStorage` key `rukan.command.store.v1`. Import groups by install id. The same snapshot id replaces itself. A new snapshot id is retained, and the table shows the latest `exported_at`. Remove deletes only the local copy.

## T. COMMAND CENTER — DEPLOYMENTS

Columns are install id, install created time, Rukan version, OS and accelerator summary, macropath, model identity, Witness verdict, and exported time. No Live, Online, Offline, or Healthy label.

## U. COMMAND CENTER — DEPLOYMENT DETAIL

Install, build, host summary, SAFE bytes, macropath, generation, model and qualification, Witness, physical register, snapshot id, and export time.

## V. COMMAND CENTER — SUPPORT EVIDENCE / LOGS

Structured event envelopes only. Raw runtime logs are not exported.

## W. SECURITY REVIEW

Admin is loopback-only. Command Center does not execute imported JSON and does not open a network service. Neither plane is an admission or serve authority. Remote Admin and fleet telemetry were not added.

## X. TESTS / QA

- `tests/machi`: pass, including architecture and `tests/machi/test_rukan_admin.py`
- `tests/acceptance_lab`: pass
- ruff: pass
- mypy --strict `src/machi`: pass, 184 files
- Admin vitest: 3 passed. Command Center vitest: 3 passed.
- Admin and Command Center `tsc --noEmit` and production Vite builds passed.

## Y. FRONTEND BUILDS / ARTIFACTS

- `ui/admin`: Vite production build succeeded.
- `ui/command-center`: Vite production build succeeded.
- Dev: Admin `127.0.0.1:5173` proxies `/v1` to `127.0.0.1:8765`. Command Center `127.0.0.1:5174` has no API.

## Z. PYTHON BUILD / VERIFY IF CHANGED

- Wheel: `machi-0.1.0-py3-none-any.whl`
- Build id: `0.1.0+cd14b3ed8490`
- Commit: `cd14b3ed8490f7ceb64db50b17646acc4b18eaa1`
- Clean: true
- SHA256: `e8184a68badeda0717dafd6ae51316683de0bf43eddb6734004ee0e98b8e54ff`
- Size: 348976
- Isolated verify: `verify_ok`

## AA. CURRENT FUNCTIONALITY VS DEFERRED MOCKS

Implemented: summary projection, snapshot export/import, inference seam, model operation flags, stop-before-release. Not implemented, and not faked: live fleet status, remote control, marketplace, LibreChat, attached GPU process stop from the Admin process, usage charts.

## AB. STAGE-1 REGRESSION

Existing Stage-1 suites passed after the snapshot contract and Admin seam. Native primary and Ollama fallback policy were not changed. Physical breadth stays pending.

## AC. OPEN DEBT / RISKS

`M-5-AMD-01`, `M-5-OLLAMA-05`, Ampere/N1 breadth, `M-9-01` serve depth, `M-5-OLLAMA-04`, and the other nonblocking Stage-1 items stay open. Admin stop/release need a later attachment to the process that actually owns the runtime. The Command Center store is this browser profile only.

## AD. EXACT NEXT RECOMMENDED UI ITERATION

Attach stop and release to the serving process that owns the READY instance, still through the loopback seam, and show the returned outcome on the Deployment page. Do not start fleet connectivity in that iteration.

## AE. GIT STATE

- `rukan/dual-ui-v0` equals `origin/rukan/dual-ui-v0` at `cd14b3ed8490f7ceb64db50b17646acc4b18eaa1`
- `origin/machi` remains `4cb89622a4cd3a1a37bf6ab44c4414e4287e8934`
- Working tree clean except untracked `docs/machi/proposals/`

## AF. STOP

STOP. Waiting for Lead review and the next UI iteration. Remote Admin, connected telemetry, the Runtime Artifact Registry, Dynamo, Knowledge, identity, licensing, and physical qualification were not started.
