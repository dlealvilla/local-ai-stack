# RUKAN-DUAL-UI-V0.1-001

## A. EXACT STATUS

RUKAN_DUAL_UI_V0_1_LOCAL_PASS

## B. TL;DR

Rukan Admin now stops the current managed instance through the existing Serve services and releases only through ResourceManager after stop eligibility. Native reattachment uses the stored start stamp and serve identity token, not the pid alone. Both local UIs are easier to read. Command Center stays import-only and still does not claim a deployment is live. No physical host was created.

## C. STARTING / FINAL SHA

- Canonical baseline: `7ff3dff6972f69ba38214a6d30f7a19f272318e0`
- Final SHA: `add9ac3f5acb2d9f4bc335dedc49a274df4d4193`

## D. BRANCH / WORKTREE / ORIGIN

- Branch: `rukan/dual-ui-v0.1`
- Origin: `origin/rukan/dual-ui-v0.1` = `add9ac3f5acb2d9f4bc335dedc49a274df4d4193`
- Branched from `origin/machi` at `7ff3dff6972f69ba38214a6d30f7a19f272318e0`
- `origin/machi` was not moved
- Untracked `docs/machi/proposals/` was not committed

## E. LIFECYCLE OWNERSHIP ANALYSIS

The Admin process rebuilds `ServeService`, `ProviderServeService`, and one `ResourceManager` from the same store. Native `VllmServeProvider` already reconstructs a `SpawnedProcess` from persisted pid, start stamp, identity token, and argv fingerprint. `NativeProcessRunner.view` treats a different start stamp or `MACHI_SERVE_IDENTITY` as not our process, and `terminate` does not signal that process. Provider stop unloads by catalog name and digest, then proves absence. That is the existing re-entry contract, so no new daemon was added.

## F. STOP IMPLEMENTATION

`POST /v1/lifecycle/stop` refuses a body that contains `pid`, `provider`, `port`, or `runtime`, and refuses an instance id that is not the current chain. Otherwise it calls native `ServeService.stop` or provider `ProviderServeService.stop`. A second native stop converges with `stop already recorded`. A failed stop leaves the reservation held. The projection reads the latest serve transition, so the UI shows `stopping` or `stopped` after refresh.

## G. RELEASE IMPLEMENTATION

Release is refused while the instance is starting, ready, or stopping. After a confirmed native stop, `ServeService.release_after_stop` calls `ResourceManager.release`. A provider instance is released on that same manager only when its state is STOPPED. A second release converges with `release already recorded`. STOP does not release.

## H. NATIVE LIFECYCLE TESTS

`tests/machi/test_rukan_lifecycle.py` starts a local probe through the real `ServeService`, then a separate `LifecycleOwner` reattaches and stops it. Covered: stop of the READY instance, idempotent second stop, wrong instance refused, pid override refused, release while READY refused, release after STOPPED, second release, failed stop keeps the reservation and the process, identity mismatch does not signal.

## I. OLLAMA LIFECYCLE DISPOSITION

The provider path uses `ProviderServeService.stop` against the catalog port, then the same ResourceManager. A local fake catalog proves unload-then-release and that release is refused while the instance is READY. No Ollama daemon was started.

## J. ADMIN OVERVIEW CHANGES

The first screen now leads with whether the deployment is usable, then the active model, how it is running, the reservation, SAFE memory, and pending physical coverage. Build and ids sit behind disclosure. There is no health score.

## K. ADMIN INFERENCE CHANGES

Multiline prompt, max tokens limited to 1..64, Send disabled while a request is in progress, Clear, typed refusal text, completion tokens only when reported, and elapsed seconds measured around that request. The reply is still not stored. The browser still cannot choose the runtime.

## L. ADMIN DEPLOYMENT CHANGES

The chain is Foundation, Model, Plan, Reservation, Instance, Inference evidence, Witness, each with a short meaning and a technical disclosure. Stop and Release show the returned outcome. Release stays disabled until stop eligibility.

## M. MODELS / SYSTEM REFINEMENT

Models label warehouse artifacts and provider digests separately and say when an operation is not attached. System separates observed hardware from SAFE capacity and shows human-readable bytes with the exact byte count in detail. Unresolved and not_recorded stay as recorded. No utilisation chart.

## N. COMMAND CENTER DEPLOYMENTS CHANGES

Search covers install id, version, OS, accelerator, macropath, model, and Witness. Rows sort by latest `exported_at`, show snapshot count, evidence exported time, and snapshot age. Snapshot age is not last-seen or online.

## O. SNAPSHOT HISTORY

Multiple snapshots for one install stay retained. Detail can select an older snapshot by export time, version, Witness, and macropath. No diff engine was added.

## P. SUPPORT EVIDENCE CHANGES

The support view titles the structured envelopes and states that payloads and customer content are omitted. Raw logs were not added.

## Q. VISUAL / ACCESSIBILITY CHANGES

Existing shared theme. Added headings, search label, history select label, status text, and disabled-operation reasons. Focus outlines were already in the theme. No new design-system dependency.

## R. SCREENSHOTS / DEMO EVIDENCE

No screenshot tool was introduced. Local proof is `tests/machi/test_rukan_lifecycle.py`, Admin and Command Center vitest, and the documented commands in `docs/machi/RUKAN.md`. Run Admin with `python -m machi.main admin serve --store-dir <store> --port 8765` and `cd ui/admin && npm run dev`. Run Command Center with `cd ui/command-center && npm run dev`.

## S. SECURITY / PRIVACY REVIEW

Loopback binding is unchanged. Inference text is still not journaled. Snapshot export still rejects prohibited content keys. Command Center remains import-only and non-authoritative. The banner says imported evidence is not live deployment status.

## T. FULL QA

- `tests/machi`: pass, including architecture, privacy, and lifecycle tests
- `tests/acceptance_lab`: pass, run separately because the two suites share a `test_cli` module name
- ruff: pass
- mypy --strict `src/machi`: pass, 185 files
- Admin vitest: 4 passed. Command Center vitest: 5 passed
- Both production Vite builds and `tsc --noEmit` passed

## U. BUILD ARTIFACTS

- Wheel: `machi-0.1.0-py3-none-any.whl`
- Build id: `0.1.0+add9ac3f5acb`
- Commit: `add9ac3f5acb2d9f4bc335dedc49a274df4d4193`
- Clean: true
- SHA256: `0140ab465da303e0f61cdb178184efa3622878312fc861ef03c2d502ab5709de`
- Size: 350937
- Isolated verify: `verify_ok`
- Admin and Command Center production bundles built under `ui/*/dist`

## V. REMAINING LIMITATIONS

Admin must be the process that calls stop. It can reattach a native process only when the stored stamp and identity token still match. It does not adopt an unrelated pid. Provider stop needs the loopback provider API. Command Center storage is still this browser profile. Physical AMD, macOS/Ollama, and Ampere/N1 coverage stay pending. No remote fleet, auth, Knowledge, registry, or Dynamo.

## W. RECOMMENDED NEXT UI ITERATION

Show the stop and release outcome on the Deployment page against a real READY instance the operator already started, and keep the Command Center import-only. Do not add fleet connectivity in that pass.

## X. GIT STATE

- `rukan/dual-ui-v0.1` equals `origin/rukan/dual-ui-v0.1` at `add9ac3f5acb2d9f4bc335dedc49a274df4d4193`
- `origin/machi` remains `7ff3dff6972f69ba38214a6d30f7a19f272318e0`
- Working tree clean except untracked `docs/machi/proposals/`

## Y. STOP

STOP. Waiting for Lead review. Remote fleet, authentication, Knowledge, licensing, the Runtime Artifact Registry, Dynamo, LibreChat, and physical testing were not started.
