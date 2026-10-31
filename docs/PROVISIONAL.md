# Provisional Implementation Register

This file records assumptions, temporary defaults, incomplete modules,
and shortcuts that must be revisited as the AI Platform matures.

The purpose is to allow development of the complete platform architecture
without losing track of lower-level work that still needs improvement.

---

## Performance defaults

### Context length

Current value:

8192 tokens

Status:

PROVISIONAL

Why:

A conservative context size that has previously worked with the current
local GPU configurations.

Future:

Should be derived from model metadata, available VRAM, and workload
profile rather than a hard-coded default.

---

### GPU memory utilization

Current value:

0.90

Status:

PROVISIONAL

Why:

Leaves some headroom for other processes and avoids OOM on first start.

Future:

Should be configurable and possibly auto-tuned based on measured free
VRAM and concurrent workloads.

---

### Concurrency

Current value:

1

Status:

PROVISIONAL

Why:

Simplest safe default for a single-user local stack.

Future:

Should be planned from workload profile and available resources.

---

## Log management

Current status:

PROVISIONAL

Native service stdout/stderr is stored in local text files under:

logs/

Current CLI:

./ai logs
./ai logs inference
./ai logs frontend
./ai logs -n 5
./ai logs --lines 100 inference

The CLI currently displays the most recent lines only (default 40; override with -n / --lines).

Future improvements may include:

- structured logging
- timestamps and severity normalization
- searchable logs
- log rotation and retention policies
- streaming / follow mode
- metrics and trace correlation
- Admin UI log viewer
- external observability integrations

The platform-level concept of service logs should remain stable.
