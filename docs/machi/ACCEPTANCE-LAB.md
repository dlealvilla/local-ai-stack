# Machi development acceptance laboratory

Development-only empirical record for NVIDIA + AMD Accelerator Discovery
acceptance. **Not** Machi product state, Kernel persistence, Store, Journal,
or a production dependency.

## What it is

A local SQLite database plus a small Python CLI that records:

- policy snapshots
- Git / candidate identity (exact wheel SHA-256)
- RunPod control-plane preflight
- hardware selection (when it happens)
- requested vs assigned vs observed infrastructure
- host / vendor / Machi observations
- comparisons, failures, fixes, costs, checkpoints
- hashed evidence metadata

## What it is not

- not imported by `src/machi`
- not required by `machi` CLI
- not packaged in the Machi wheel
- not a dashboard, SaaS, or RunPod orchestrator
- not authorization to create or destroy Pods

## Location

Live database (gitignored):

```text
.local/machi-acceptance/lab.sqlite3
```

Raw artifacts (gitignored):

```text
.local/machi-acceptance/artifacts/<campaign>/<run>/
```

Schema and code:

```text
tools/acceptance_lab/
```

## Initialize

```text
python -m tools.acceptance_lab init
python -m tools.acceptance_lab doctor
python -m tools.acceptance_lab import-historical
python -m tools.acceptance_lab schema-version
```

Default DB path is `.local/machi-acceptance/lab.sqlite3` relative to the
repository root. Override with `--db`.

## Migrations

Deterministic SQL files in `tools/acceptance_lab/migrations/`. Version `1`
is `0001_initial.sql`. The ledger table `schema_migration` stores version,
name, SHA-256 of the migration file, UTC apply time, and the git commit of
the tool tree. `PRAGMA user_version` mirrors the ledger and is not the only
evidence.

Re-running `init` verifies hashes and does not duplicate schema.

## Reports

```text
python -m tools.acceptance_lab report --campaign <id>
python -m tools.acceptance_lab report --campaign <id> --format json
```

Reports are generated from the DB. Committed outputs should use repo-relative
paths; the live DB may contain absolute local paths.

## Live DB Git policy

Commit schema, migrations, access layer, tests, and sanitized summaries.
Do not commit `*.sqlite3`, WAL/SHM/journal files, raw logs, or credentials.
`.gitignore` lists `.local/machi-acceptance/`.

## Secret policy

The lab rejects obvious secret field names (`API_KEY`, `TOKEN`, `PASSWORD`,
`AUTHORIZATION`, `COOKIE`, `PRIVATE_KEY`, …) and secret assignments in notes.
This is a guardrail, not DLP. OAuth tokens and private keys must never be
stored. Ownership tokens are lab-generated identifiers, not credentials.

## Ownership model

A Pod is Machi-acceptance-owned only when **all** of these agree:

1. exact RunPod Pod ID
2. campaign id
3. ownership token
4. pod name matching `machi-acceptance-…`
5. `ownership_verified = 1` on the `server_instance` row

The name prefix alone is insufficient (`is_owned_by_name_prefix` always
returns false). Destructive RunPod operations are **not** implemented here.

## Historical import

`import-historical` loads:

- NVIDIA physical acceptance of wheel
  `351cee818c2a41ed84b3c8708e957c950c3676e555e1c32aa1793bfeec1a99f3`
  (implementation `1c774a0`, evidence `636dfa0`)
- RunPod control-plane preflight from
  `STATUS=RUNPOD_CONTROL_PLANE_READY`

Unknown historical fields stay NULL. `historical_import = 1`. That NVIDIA
PASS does not qualify a later NVIDIA+AMD candidate.

## Future RunPod integration

A later controller may create disposable `machi-acceptance-` Pods, record
selection/ownership, and tear down **only** positively owned Pods. This
package still must not become a Machi runtime dependency. Hang policy remains
stop-and-ask. Network volumes remain forbidden.

## CLI

```text
init
doctor
import-historical
campaign-create
policy-show
candidate-show
report
schema-version
```

There is no create/start/stop/terminate Pod command.
