================================================================================
=========================== PASTE BACK START ===================================
================================================================================

TASK: RUKAN-ANALYTICS-HUB-V0.2-FIX-001
STATE: PASS
MILESTONE: Rukan analytics hub v0.2 correction
STAGE: local Command Center provenance
STEP: fix bundle identity, snapshot history, and remove/refresh reimport
PREDECESSOR OUTPUTS: 404858abde45443d91f9a6f17b301754cc8b4276 on rukan/analytics-hub-v0.2
CURRENT_COMMIT: acd91f319b653c8e53a8c1d1eb4a01e26ae08bdf

STATUS: RUKAN_ANALYTICS_HUB_V0_2_LOCAL_PASS

CHANGES:

* src/machi/kernel/analytics.py — a bundle fails closed when a snapshot, event, or inference install id differs from the manifest. The record id is not rewritten.
* src/machi/adapters/rukan/hub.py — events and inferences are stored under their own install id. Snapshot history always records the retained count, and deployment metadata moves forward only when the incoming export is at least as new. Sources are keyed by file hash and by installation plus bundle id or snapshot id. Remove deletes that installation's import provenance and leaves inbox files in place.
* tests/machi/test_rukan_analytics.py — mismatch, history-order, remove/reimport, isolation, and logical-idempotency coverage.
* docs/machi/RUKAN-ANALYTICS.md — documents the identity check, logical skip, and remove-then-refresh behavior.
* Command Center schema version is 2. A version-1 database drops the old sources table and recreates it with install_id and logical_id. Imported facts stay. Inbox files stay, so the next Refresh rebuilds provenance. sha256 remains the exact-file key. UNIQUE(install_id, logical_id) is the logical key.

EVIDENCE:

* focused tests: tests/machi/test_rukan_analytics.py 12 passed, including snapshot, event, and inference install mismatch with empty deployments/snapshots/events/inferences/sources; newer-then-older, older-then-newer, and three shuffled snapshot orders; remove/reimport of a bundle and of a snapshot; deployment B left intact; exact-file refresh imported 0; logical re-serialization added no source row; schema 9 still fails closed; schema 1 upgrades to 2.
* regression tests: tests/machi 616 passed; tests/acceptance_lab 51 passed, collected separately.
* ruff check . passed.
* mypy --strict src/machi: no issues in 189 source files.
* ui/admin vitest 4 passed; tsc and vite build passed.
* ui/command-center vitest 5 passed; tsc and vite build passed.
* wheel: machi-0.1.0-py3-none-any.whl, build id 0.1.0+acd91f319b65, SHA256 afc53d44833509d18c6188d9463e4864caf1c2e46c7ac1fd7d32e28f7b3ec8e7, size 363493, clean_source true.
* isolated verify_machi.py: verify_ok.

SOURCE SIDE (real-host stages):

* predecessor: 404858abde45443d91f9a6f17b301754cc8b4276
* source commit(s): acd91f319b653c8e53a8c1d1eb4a01e26ae08bdf
* files changed: analytics.py, hub.py, test_rukan_analytics.py, RUKAN-ANALYTICS.md
* local tests: listed above
* final source commit: acd91f319b653c8e53a8c1d1eb4a01e26ae08bdf
* artifact / SHA-256 / build id: machi-0.1.0-py3-none-any.whl / afc53d44833509d18c6188d9463e4864caf1c2e46c7ac1fd7d32e28f7b3ec8e7 / 0.1.0+acd91f319b65

DEPLOYMENT SIDE (real-host stages):

* target host and fingerprint: none; local correction only
* transferred hash == local hash: not applicable
* installed build identity: not applicable
* install/upgrade result: not applicable
* commands under acceptance: not applicable
* observations and diagnostics: not applicable
* acceptance result: local only
* attempts, if more than one: one

BEHAVIOR:

* A mismatched snapshot, event, or inference install id rejects the whole bundle before SQLite mutation. No partial rows are written.
* Import order does not change the newest deployment metadata or the retained snapshot count. Older snapshots stay in history.
* Remove local copy, leave the inbox files, then Refresh reconstructs that deployment. Removing deployment A does not change deployment B. Source files are not deleted.
* The same file hash is skipped. A different serialization of the same bundle id or snapshot id does not create a second source row.
* Still local only: loopback Command Center, SQLite authority, inbox plus Refresh, JSON/JSONL, manual transport, Admin analytics, timelines, inference facts, privacy allow-list. No customer content export, no invented future metrics, and no live, online, or healthy claims.
* Not started: remote fleet connectivity, authentication, licensing, Knowledge/RAG, Runtime Artifact Registry, Dynamo, LibreChat/Open WebUI, physical testing.

SCOPE:

* non-goals preserved: the accepted v0.2 surfaces listed above; origin/machi remains c649103f244475f6381ba473f4431e0a7f86f803
* adjacent issues recorded: untracked docs/machi/proposals/ was left untracked and was not committed

GIT:

* branch: rukan/analytics-hub-v0.2
* working tree: untracked docs/machi/proposals/ only
* committed: YES
* pushed: YES (404858a..acd91f3 origin/rukan/analytics-hub-v0.2)

CHECKPOINT:

* path: none
* token/hash: none

QUESTIONS / DECISIONS:

* NONE

NEXT:

* Lead review of acd91f319b653c8e53a8c1d1eb4a01e26ae08bdf
* DO NOT begin it

================================================================================
============================ PASTE BACK END ====================================
================================================================================
