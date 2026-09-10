# Kultrun data warehousing

This directory is the Data Engineering stream. It is separate from
Runtime / Deployment Engineering and from Stage 1.6L documents.

The local telemetry database is part of the Kultrun product. It is an
append-only operational evidence store, not an execution authority.

```text
Kultrun control plane
        ↓
TelemetryRecorder
        ↓
SQLiteTelemetryStore
        ↓
<KULTRUN_STATE_ROOT>/telemetry/kultrun-telemetry.sqlite3
```

Current increment: **Phase 0 — Minimum Viable Local Telemetry**.
Integration acceptance remains pending. Later warehouse phases must not
start from this directory.

Do not begin later phases from this document. See:

- [PHASE-0-LOCAL-TELEMETRY.md](PHASE-0-LOCAL-TELEMETRY.md)
- [DATA-DOMAINS.md](DATA-DOMAINS.md)
- [PHASE-0-HANDOFF.md](PHASE-0-HANDOFF.md)
