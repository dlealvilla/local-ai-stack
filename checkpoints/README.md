# Stage checkpoints

Machine-readable stage checkpoints required by `docs/ROADMAP.md` §3.

```text
checkpoints/STAGE-XX-<name>.json
```

A checkpoint is the structured form of the stage output package in
`docs/stages/`. The following stage verifies and consumes it instead of
re-deriving its predecessor's facts.

Suggested shape, to be fixed properly by Milestone 0 when the contract
and schema-versioning conventions are defined:

```json
{
  "stage": "1.1",
  "name": "host-capability-detection",
  "output": "HostCapabilities v1",
  "schema_version": 1,
  "status": "WORKING",
  "produced_at": "2026-09-04T00:00:00Z",
  "contracts": ["HostCapabilities"],
  "adapters": [],
  "acceptance": { "passed": 0, "failed": 0 },
  "provisional": [],
  "deferred": []
}
```

Checkpoints record platform state and stage results only. They must never
contain secrets, customer content, prompts, responses or model weights.
