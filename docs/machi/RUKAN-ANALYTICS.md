# Rukan analytics hub v0.2

Rukan is the product name. `machi` remains the internal package.

## Planes

Customer-local analytics stay on the deployment. Rukan Admin reads that
journal and store directly. The vendor export is a separate allow-list
bundle. Command Center imports that bundle, or a support snapshot, from
an inbox. It does not own customer host truth and it is not live.

## Transport

```text
deployment analytics export
    -> manual file copy
    -> Command Center inbox
    -> Refresh deployments
```

There is no automatic deployment-to-vendor transport.

## Commands

```text
python -m machi.main analytics export \
  --store-dir <store> --journal-dir <journal> --output bundle.jsonl

python -m machi.main command-center serve \
  --data-dir <dir> --port 8780
```

The data directory holds `command.sqlite` and `inbox/`. Place
`*.json` support snapshots or `*.jsonl` analytics bundles in the inbox,
then press Refresh deployments. The same file hash is skipped. A
different serialization of the same bundle id or snapshot id is also
skipped, so it does not add a second import row. A bad file is recorded
and does not block a valid one. Every record in a bundle must use the
manifest install id; a mismatch rejects the whole file before SQLite
changes. Remove local copy deletes that installation's imported rows
and its import provenance. It does not delete inbox files, and Refresh
imports those files again. Removing one installation leaves the others
in place.

Development UI: `cd ui/command-center && npm run dev` proxies `/v1` to
`127.0.0.1:8780`. Admin analytics uses the existing Admin seam on
`127.0.0.1:8765`.

## Bundle

`rukan.analytics_bundle` version 1 is JSONL. The first record is
`kernel.analytics_manifest`. Later records are a support snapshot,
`kernel.analytics_event` envelopes, and `kernel.analytics_inference`
proof facts. Counts on the manifest must match. Event payloads are not
included. `public_ops` and `operational` events are eligible.
`restricted` and `customer_content` are not exported.

## Gap table

| Designed future metric | Active Rukan source |
|---|---|
| input tokens | missing on the native inference proof; not invented |
| TTFT | qualification may measure it; not a request analytic here |
| queue time | not persisted |
| historical request latency | not persisted; the Admin tester elapsed time is not history |
| cost | not persisted |
| user, team, or application usage | not persisted |
| model routing reason | not persisted |
| utilization percentages | not persisted |
| SLA or availability | not persisted |

Completion tokens are included only when a stored proof reports them.

## Connected reporting

A deployment can also compose `kernel.operational_report` version 1.
The product default cadence is production: 21600 seconds, with a stable
phase of 0–900 seconds. Development, 120 seconds, is explicit.
Material lifecycle, model, runtime, capacity, and telemetry-setting
changes coalesce into one report. The report carries usage rollups and
cumulative counters, not prompts or responses. Upload uses HTTPS and a
per-deployment bearer credential. Loopback HTTP exists only in explicit
local-test mode. The receiver is write-only. A report age is not an
online or offline claim. See
[RUKAN-CONNECTED-MONITORING-V0.3.md](RUKAN-CONNECTED-MONITORING-V0.3.md).
