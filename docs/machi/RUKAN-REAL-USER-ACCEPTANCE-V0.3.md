# Rukan v0.3 real-user acceptance playbook

This is the later campaign. Do not run it until a customer host and a
business-side intake exist. This document does not provision either.

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
```

Admin is not published to the internet. The tunnel is the access path
until human authentication exists.

## Preconditions

```text
python -m machi.main acceptance preflight --data-dir <command-center-dir> --cert <cert> --key <key>
```

The command checks that the data directory is writable and that later
certificate paths exist when they are passed. It does not open a port
and it does not spend money.

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

## Commands for the later session

Customer host, from the accepted wheel or checkout:

```text
python -m machi.main admin serve \
  --store-dir <store> \
  --journal-dir <journal> \
  --static-dir ui/admin/dist \
  --port 8765
```

Business host:

```text
python -m machi.main command-center serve \
  --data-dir <cc-dir> \
  --static-dir ui/command-center/dist \
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

Copy the secret once into Admin Settings. Profile stays Development
(120 seconds) for this test. Production is 21600 seconds and is not the
test default.

Tunnel from the operator machine:

```text
ssh -L 8765:127.0.0.1:8765 <user>@<customer-host>
```

## Steps

1. Start Admin from the accepted artifact and open it through the tunnel.
2. Read Overview and System. Confirm there is no live-health score.
3. Open Models. Confirm cards keep artifact or digest identity.
4. Use only controls that the UI enables. Do not invent a deploy button.
5. Run one operator inference. Record input tokens, output tokens, and latency.
6. Open People. Create two users and two teams. Assign a membership.
7. Set a team inference grant and a user deny. Confirm the effective view
   still says gateway enforcement is not available.
8. Pair telemetry. Send a test report. Confirm Command Center shows it.
9. Wait through two development heartbeats. Record generated time and ACK time.
10. Change the reporting profile or custom interval. Confirm a settings report.
11. Stop serving, then release. Confirm those reports.
12. Stop the intake process. Run another inference. Confirm Admin still works
    and the outbox stays queued.
13. Start intake again. Confirm the queued report is acknowledged.
14. Confirm Command Center has no email, display name, prompt, or response.
15. Stop Admin and Command Center with SIGINT.

## systemd examples

These are notes, not product units, and they are not installed by this
repository.

```text
# rukan-admin.service
ExecStart=python -m machi.main admin serve --store-dir /var/lib/rukan/store --port 8765
# rukan-command.service
ExecStart=python -m machi.main command-center serve --data-dir /var/lib/rukan/command --port 8780
```

## Cleanup

Delete only the test store directory, command-center data directory, and
`acceptance-evidence/` created for this campaign. Do not run Steward
reclaim as a substitute.
