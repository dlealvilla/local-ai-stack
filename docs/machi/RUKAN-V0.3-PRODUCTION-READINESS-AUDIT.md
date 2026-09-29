# Rukan v0.3 production-readiness audit

Audit of the bounded product on `rukan/connected-monitoring-v0.3`.
A green test is not a classification. Each finding has one class:

- `SERVER_ACCEPTANCE_BLOCKER` — stops the real-server playbook
- `PILOT_BLOCKER` — stops a controlled pilot of this bounded product
- `GA_BLOCKER` — stops general availability, not this playbook
- `DEFERRED_PRODUCT` — outside this product on purpose

No server-acceptance or pilot blocker is left open in this document.
Items that remain are `GA_BLOCKER` or `DEFERRED_PRODUCT`.

## Authority

ResourceManager remains the only admission authority. Plan does not
admit. Serve does not release. STOP leaves a reservation reserved until
an explicit release. Command Center stores reports and never operates
the customer host. Telemetry is one-way. People data and customer
content stay on the customer host. There is no employee login, no
employee inference route, no chat, and no remote control.

## Cadence

`src/machi/kernel/cadence.py` is the only interval table. Production is
21600 seconds. Development is 120 seconds and is selected explicitly.
Custom is an integer from 60 to 86400. The phase is a stable hash of
the install id. The next slot is epoch-aligned. An event report does
not move `next_periodic_at`. A missed slot is skipped rather than
backfilled. The Admin API default profile is `production`. The
acceptance playbook selects Development.

## Usage delivery

Usage rows carry a monotonic `usage_seq`. A report freezes
`usage_seq > ack_usage_seq` through the proposed sequence. Only a
matching ACK advances `ack_usage_seq`. `occurred_at` is analytics time,
not the delivery cursor. A failed usage insert increments
`usage_records_dropped`, leaves the inference response intact, and
marks `usage_accounting_status` as `degraded`.

## Outbox

One queued report is frozen until ACK. Scan and observe ignore trigger
reasons already inside that frozen body, and they do not reread journal
bytes the queued report already proposed. A new reason stays pending
and is composed after ACK. Delivered outbox rows are compacted to the
newest 48. Unacknowledged rows are not deleted. Acknowledged usage is
compacted to the newest 2000 rows. Usage with `usage_seq` above the
ACK cursor is kept.

## Receiver

Exact duplicate report id and body digest is an idempotent ack.
A different body with the same report id is rejected. The same install,
stream, and sequence with a different report id is rejected. A later
sequence does not regress when an older one arrives. Gaps are computed
inside one telemetry stream. Freshness uses receiver `received_at`.
Source clock skew beyond two hours is stored as
`source_clock_ahead` or `source_clock_behind` and is not a rejection.
Command Center schema 5 adds `stream_id` and `clock_skew`. Schema 1
through 4 upgrade to 5. Raw report documents older than the newest 200
per install are cleared. Structured rows stay.

## People

Directory ids are random `usr_` and `team_` tokens. Email is not the
authorization identity. User intent may inherit per capability. Team
intent may not. Platform deny forces the other capabilities to deny
with provenance `platform_parent`. Effective access reports one
provenance per capability. Archived teams grant nothing. The directory
stores an install binding and refuses a conflicting InstallId. Admin
People can search, create, edit, suspend, reactivate, deactivate,
manage memberships, edit intent, and show effective access. Enforcement
remains `gateway_not_available`.

## Packaging and exposure

The wheel build copies the Vite production builds into the package.
Node is build-time only. Admin and Command Center serve those files
when `--static-dir` is omitted. Admin refuses a non-loopback bind.
Foreign Origin is refused. Exceptions return a generic refusal.
Intake is write-only, requires HTTPS off loopback, and compares the
bearer hash with `hmac.compare_digest`. Secrets are not placed in URLs.
POSIX files for telemetry, the directory, Command Center, and
credentials are mode `0600`. Non-POSIX hosts are not given a weaker
mode.

## Findings

| ID | Class | Finding |
| --- | --- | --- |
| PR-01 | GA_BLOCKER | Admin has no human authentication. Loopback plus an SSH tunnel is the server-acceptance path. `R-03-02`. |
| PR-02 | GA_BLOCKER | Windows secure credential storage is not implemented. The pilot host is POSIX. `R-03-03`. |
| PR-03 | GA_BLOCKER | The operational journal is not rotated. A shrink is reported as `journal_truncated` and the cursor does not skip silently. `R-03-04`. |
| PR-04 | GA_BLOCKER | AMD native/vLLM, macOS/Ollama, and NVIDIA Ampere/N1 physical qualification remain outside this software gate. |
| PR-05 | DEFERRED_PRODUCT | No employee authentication, employee inference endpoint, chat, Agent Builder, RAG, licensing, or remote customer control. |
| PR-06 | DEFERRED_PRODUCT | Deployment settings stay read-only. `R-03-01`. |
| PR-07 | DEFERRED_PRODUCT | Command Center is not a public intake product. The playbook uses a configured HTTPS listener for one test. |

## Dependency graph

```text
Install identity
  -> Plan recommendation
  -> ResourceManager admission
  -> Serve execution
  -> local journal and usage rows
  -> telemetry compose / outbox
  -> Command Center intake

People directory -> local Admin only
Command Center -> report store only
```

No observer in that graph authorizes admission, release, or a customer
mutation.

## Review answers

1. A fresh environment can install the frozen wheel without the
   repository on `PYTHONPATH` and without Node.
2. Packaged Admin UI is served from the wheel.
3. Packaged Command Center UI is served from the wheel.
4. Usage delivery is cursor-owned. An outage or restart does not
   double-count acknowledged rows and does not drop unacknowledged rows.
5. Exact replay is idempotent. A conflicting body or sequence is rejected.
6. Ten deployments can report into one Command Center without sharing
   usage totals.
7. People can be created, edited, suspended, reactivated, deactivated,
   and placed on teams from Admin.
8. Effective access is per capability, and platform deny closes the rest.
9. People canaries are absent from telemetry and Command Center.
10. Admin is loopback-only. Intake requires the bearer secret.
11. A foreign Origin is refused.
12. Delivered telemetry, acknowledged usage, directory audit, rejection
    rows, and old report bodies are bounded. Unacknowledged telemetry
    is kept.
13. Command Center schema 1 through 4 upgrade to 5. An unknown schema
    version fails closed.
14. Development cadence is explicit. The product default is Production.
15. Production remains 21600 seconds.
16. The playbook installs a wheel and does not require a checkout.
17. Visible People and monitoring controls call the local APIs.
18. The GA gaps above stay documented and are not treated as pass.

## Debt register

| ID | Class | Blocks server acceptance | Blocks pilot | Blocks GA |
| --- | --- | --- | --- | --- |
| R-03-01 | DEFERRED_PRODUCT | no | no | no |
| R-03-02 | GA_BLOCKER | no | no | yes |
| R-03-03 | GA_BLOCKER | no | no | yes |
| R-03-04 | GA_BLOCKER | no | no | yes |
| M-5-AMD-01 and the other physical lanes | GA_BLOCKER | no | no | yes |
