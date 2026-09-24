# Ollama Chunk 2 — Freeze Run Lead Review

**Reviewed HEAD:** `919ab7e547967d6f552507fea617646410b3f0bd`  
**Assigned freeze work:** PASS  
**Chunk 2 closure:** HOLD FOR ONE MICRO-CORRECTION  
**Architecture:** ACCEPTED / FROZEN

## Confirmed

The freeze run correctly implemented:
- pre-stage SAFE refusal before owned staging is created;
- recipe length + bounded copy + digest checks;
- parent-directory fsync between rename and registry mutation;
- invalid UTF-8 registry as typed RECONCILE_REQUIRED;
- parsed positive ownership proof;
- full gates including isolated `verify_ok`;
- exact origin/local equality.

## Blocking issue: decompressor watchdog semantics

`SystemZstdDecompressor` defaults to `timeout_seconds=5.0`.
`_TimedChild` starts that timer when zstd starts and kills the child when the
deadline expires.

That makes five seconds a hard wall-clock limit for the **entire streaming
decompression/preflight or extraction pass**, not merely for a hung-process
cleanup step.

The frozen official Ollama archive is approximately 1.4 GB compressed and the
product targets heterogeneous customer hardware. A fixed five-second total
deadline is therefore not a truthful production bound. The synthetic hang test
proves hanging is bounded; it does not prove the real artifact can complete
within that bound.

This must be corrected before describing the managed-prefix path as ready for
the next model-qualification chunk.

## Required industry pattern

Use a **progress/inactivity watchdog**, not an arbitrary tiny total-operation
deadline:

- active streaming progress may continue for as long as needed within the
  enclosing provisioning policy;
- if no decompressed bytes are observed for a bounded inactivity interval while
  the child remains alive, kill and reap it;
- optionally retain a separate generous caller/policy total provisioning
  timeout if one already exists, but do not invent a new five-second archive
  deadline;
- stderr must continue to be drained safely/boundedly during the process;
- timeout/inactivity remains a typed provisioning failure.

The watchdog should be adapter-local. Do not add a new dependency or generic
subprocess framework unless repository inspection shows a mature existing
project dependency already solves this cleanly.

## Small consistency correction

The pre-stage SAFE check should cover the known owned staging bytes it writes
immediately, including the staging marker, rather than accepting
`safe_bytes == artifact_bytes` and then writing marker + artifact.

Keep this bounded and explicit. No attempt to estimate filesystem inode/block
metadata is required.

## Scope

No architecture decision, provider decision, model work, physical server,
model pull/load/inference, or AUTO fallback.

After this micro-correction and normal gates, Chunk 2 can close.
