# Rukan v0.3 real-user acceptance playbook

This is the later campaign for Daniel. Do not run it until a customer
host and a business-side intake exist. This document does not provision
either and does not spend money.

The test uses a frozen wheel. It does not need a repository checkout
and it does not need Node.

## Topology

```text
customer host
  Rukan Admin on 127.0.0.1:8765
  telemetry agent inside that process
  directory.sqlite and rukan-telemetry.sqlite

Daniel's browser
  ssh -L 8765:127.0.0.1:8765 <user>@<customer-host>
  open http://127.0.0.1:8765/

business host
  Command Center on 127.0.0.1:8780
  intake HTTPS on a reachable address, port 8781

customer telemetry
  machine-authenticated HTTPS
  POST /v1/telemetry/reports
```

Admin stays on loopback. The SSH tunnel is the administrator path.
Do not bind Admin to a public address.

## Install the frozen wheel

On each host, in a fresh virtual environment:

```text
python3 -m venv /opt/rukan-venv
/opt/rukan-venv/bin/pip install <frozen-wheel>
```

Confirm `PYTHONPATH` is empty. Confirm `python -c "import machi"` works
without a source checkout.

## Preconditions

```text
python -m machi.main acceptance preflight \
  --wheel <frozen-wheel> \
  --data-dir <command-center-dir> \
  --cert <cert> \
  --key <key> \
  --endpoint https://<business-host>:8781/v1/telemetry/reports \
  --admin-port 8765 \
  --ui-port 8780 \
  --intake-port 8781 \
  --json
```

Expect `result PASS`. A `BLOCKED` line names the exact missing piece.
The command does not open a listening service and it does not spend money.

The product cadence default is Production, every 6 hours (21600 seconds).
This acceptance test must select Development, every 2 minutes (120 seconds),
in Admin Settings before enabling reporting. A wheel built from a
development tree does not inherit that 2-minute cadence.

Evidence belongs outside git:

```text
acceptance-evidence/
  customer-host/
  command-center/
  screenshots/
  report-ids.txt
  usage-summary.json
  checklist.md
```

Do not commit hostnames, addresses, secrets, or screenshots that show them.

## Commands

Customer host:

```text
python -m machi.main admin serve \
  --store-dir <store> \
  --journal-dir <journal> \
  --port 8765
```

Do not pass `--static-dir`. The wheel serves the packaged Admin UI.
Expect `bind 127.0.0.1:8765`.

Business host:

```text
python -m machi.main command-center serve \
  --data-dir <cc-dir> \
  --port 8780

python -m machi.main command-center intake \
  --data-dir <cc-dir> \
  --host <reachable-address> \
  --port 8781 \
  --cert <cert> \
  --key <key>

python -m machi.main command-center credential issue \
  --data-dir <cc-dir> \
  --install-id <install-id>
```

The credential command prints the secret once. Copy it into Admin
Settings with the key id and the HTTPS endpoint. Set the profile to
Development and enable reporting. Leave loopback test HTTP off.

Tunnel from the operator machine:

```text
ssh -L 8765:127.0.0.1:8765 <user>@<customer-host>
```

Then open `http://127.0.0.1:8765/`.

## Expected observations

1. Admin Overview loads from the packaged UI. There is no live-health score.
2. System shows stored facts. Unknown stays unknown.
3. Models show artifact or digest identity. There is no Recommended row.
4. Only enabled controls are used. There is no extra deploy button.
5. One operator inference records input tokens, output tokens, and latency
   in Admin usage. The prompt and response are not stored.
6. People can create two users and two teams, edit a name, add and remove
   a membership, archive a team, and save per-capability intent.
   Effective access shows a provenance per capability. The banner says
   employee login and chat are not enabled.
7. A user platform deny makes inference, model selection, and agent builder
   deny even when those intents are allow.
8. A test report appears in Command Center. The secret is not in the URL
   or the Command Center database.
9. Development heartbeats arrive about 120 seconds apart. The report shows
   profile `development` and `120` seconds. Production stays 21600 unless
   that profile is selected.
10. Changing the profile sends a settings report and does not wait for the
    old interval.
11. Stop, then release, produce separate reports. Stop does not release
    the reservation by itself.
12. Stopping intake leaves Admin inference working. The outbox stays queued.
    Usage recorded while intake is down appears once after the ACK.
13. Restoring intake acknowledges the queued report. The same report is
    not applied twice.
14. Command Center has no email, display name, prompt, or response.
15. SIGINT or SIGTERM stops Admin, Command Center, and intake without a
    traceback. Restart keeps People, the outbox, and accepted reports.

## systemd examples

These are notes, not product units, and they are not installed by this
repository.

```text
# rukan-admin.service
ExecStart=/opt/rukan-venv/bin/python -m machi.main admin serve --store-dir /var/lib/rukan/store --port 8765
# rukan-command.service
ExecStart=/opt/rukan-venv/bin/python -m machi.main command-center serve --data-dir /var/lib/rukan/command --port 8780
```

## Cleanup

Delete only the test store directory, the command-center data directory,
and `acceptance-evidence/` created for this campaign. Do not run Steward
reclaim as a substitute.
