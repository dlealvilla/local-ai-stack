# Kultrun — Debt Ledger

Every approximation, shortcut and deliberate omission in Kultrun is
recorded here, with the condition that retires it.

This replaces the previous attempt's provisional register. That register
was honest and useful — and it grew to 2,187 lines and 54 entries, with
24 refinements still open in a single section, ending up the largest
file in the repository. It had no retirement mechanism. This one does.

Governed by `docs/ROADMAP.md` Part II §8.

---

## Labels

| Label | Meaning |
|---|---|
| `WORKING` | Functional and intended. Not debt. Recorded only where a reader might assume otherwise. |
| `PROVISIONAL` | An approximation in use now, expected to be replaced. Must carry a retirement condition. |
| `DEFERRED` | An architectural slot deliberately not implemented. Must carry the condition that makes it necessary. |

## Rules

1. Every `PROVISIONAL` entry states **what would make it real** and
   **what forces its retirement**.
2. Any `PROVISIONAL` value that **authorizes a mutation** must be
   retired before the milestone that introduced it closes.
   Approximations may inform recommendations indefinitely; they may not
   authorize indefinitely.
3. A stage may not open a new `PROVISIONAL` entry in a subsystem whose
   entry the current milestone's gate is meant to retire.
4. A milestone cannot close while any entry marked *retire before
   milestone close* is open.
5. Ledger size is reviewed at every milestone gate. Growth without
   retirement is a schedule risk, not bookkeeping.
6. Unknown is never recorded as zero. An unmeasured value is
   `unresolved`, and consumers must be able to tell "needs nothing" from
   "we do not know".

## Entry format

```text
### <ID> — <short title>
Label:        PROVISIONAL | DEFERRED | WORKING
Owner stage:  <milestone.stage>
Subsystem:    <subsystem>
Authorizes:   YES | NO        (does this value authorize a mutation?)
What:         what is approximated or omitted
Why now:      why this is acceptable at this stage
To make real: what a real implementation requires
Retire when:  the explicit condition
Status:       OPEN | RETIRED (<stage>, <date>)
```

---

## Open entries

Seven, all from Stage 0.1. None authorizes a mutation, so none is caught
by rule 2. Only `K-03` has a hard deadline.

### K-01 — Identifiers are not time-sortable
Label:        PROVISIONAL
Owner stage:  0.1
Subsystem:    kernel / ids
Authorizes:   NO
What:         An identifier is 64 bits of randomness behind a type prefix,
              so identifiers carry no ordering.
Why now:      Nothing orders by identifier. Events carry `occurred_at`,
              and ordering by a timestamp is correct rather than a
              workaround.
To make real: A time-ordered scheme — UUIDv7 or a ULID equivalent —
              implemented in the standard library, since identity is a
              Kultrun concept and may not be owned by a package.
Retire when:  `UsageEvent` requires a time-ordered scan and a secondary
              index on `occurred_at` is not sufficient. Milestone 9 at
              the latest.
Status:       OPEN

### K-02 — The record store is one JSON file per record
Label:        WORKING
Owner stage:  0.1
Subsystem:    adapters / persistence
Authorizes:   NO
What:         Single writer, no index, no query beyond key and kind. A
              full listing reads every file.
Why now:      Stage 0.3 holds a handful of singleton records. A query
              interface written before a caller exists is the specific
              mistake Milestone 0 warns about.
To make real: A SQLite store behind the same `Store` port.
Retire when:  A second writer process exists, or a lookup by anything
              other than key is required. Expected at Stage 2.5
              (inventory) or Milestone 4.
Status:       OPEN

### K-03 — No migration engine, only version rejection
Label:        PROVISIONAL
Owner stage:  0.1
Subsystem:    kernel / schema
Authorizes:   NO
What:         An unregistered `(kind, schema_version)` is refused. There
              is no path that reads version *n* and produces version
              *n+1*.
Why now:      Every contract is at version 1, so no migration exists to
              write. Building one now would design against an imagined
              shape.
To make real: A registered per-kind upgrade path, plus a store that
              rewrites on read and records that it did.
Retire when:  **Before the first `schema_version` bump ships.** Expected
              Milestone 2. Retire before milestone close.
Status:       OPEN

### K-04 — Configuration records no provenance
Label:        DEFERRED
Owner stage:  0.1
Subsystem:    kernel / config
Authorizes:   NO
What:         The effective value of a setting is reportable; which
              source supplied it — default, file, environment or
              administrator override — is not.
Why now:      Nothing consumes provenance before Stage 6.1, and the
              retrofit is contained to one module because it is loader
              metadata rather than a change to any field's type.
To make real: Record the source per key at load time and expose it
              beside the value.
Retire when:  Stage 6.1 displays automatic settings apart from manual
              overrides, or a recommender writes configuration at
              Milestone 3.
Status:       OPEN

### K-05 — A change of meaning that keeps name and type needs a human
Label:        WORKING
Owner stage:  0.1
Subsystem:    kernel / schema
Authorizes:   NO
What:         The fingerprint catches a renamed field, a retyped field, a
              removed field and a restated meaning. A field whose text
              stays identical while the intent behind it shifts is not
              mechanically detectable.
Why now:      This is the strongest available mechanism, not a shortcut.
              The meaning text is in the fingerprint precisely so the
              diff is reviewable.
To make real: Not achievable by a test. Review of the fingerprint diff
              is the control.
Retire when:  Never mechanically. Reviewed at every milestone
              consolidation checkpoint.
Status:       OPEN

### K-06 — The codec is hand-rolled
Label:        WORKING
Owner stage:  0.1
Subsystem:    kernel / schema
Authorizes:   NO
What:         Encoding, decoding and type checking are implemented on
              `dataclasses` and `get_type_hints` rather than on a
              serialization library.
Why now:      Versioned contract identity, fail-closed decoding, the
              unresolved semantic and the fingerprint are Kultrun
              concepts, and Part II §9 forbids a package from owning one.
              Standard-library-only also makes the Milestone 0 gate
              trivially true.
To make real: If it outgrows the kernel, the codec becomes an adapter
              behind the existing `Contract` boundary — a library would
              then implement serialization without owning the concept.
Retire when:  The codec exceeds roughly a thousand lines, or a second
              wire format is required. No second implementation exists
              today, so the seam is deliberately not built.
Status:       OPEN

### K-07 — No monotonic clock, so no durations
Label:        DEFERRED
Owner stage:  0.1
Subsystem:    kernel / clock
Authorizes:   NO
What:         `Clock` supplies wall-clock instants only.
Why now:      No caller measures elapsed time yet.
To make real: A monotonic source alongside the wall clock, with
              durations typed distinctly from instants.
Retire when:  Any stage measures a duration. Wall-clock arithmetic must
              never be used for one.
Status:       OPEN

---

Two further entries are anticipated by the roadmap and are **not yet
open**, because their stages have not run:

- **Policy-only safe capacity** (Stage 1.2) — headroom policy with no
  empirical evidence. This value *authorizes admission*, so under rule 2
  it must be retired by the close of Milestone 2, when
  decision-directed characterization replaces it.
- **Weights-plus-margin memory estimate** (Stage 1.5) — the prior
  attempt's `artifact_bytes + max(25%, 1 GiB)` heuristic, or its
  successor. Low confidence, planning evidence only. Retired by
  Milestone 3 Stage 3.2 when a conservative internal estimator exists,
  and further improved in Milestone 11.

---

## Retired entries

None yet. Retired entries stay in this file with their retiring stage
and date, because the record of what was approximated and when it was
fixed is itself evidence.

---

## Inherited debt — not Kultrun's, but instructive

These are the previous attempt's open items at abandonment. They are
**not** Kultrun debt; nothing has been built yet. They are listed
because each one is a trap the new build sequence is designed to avoid,
and because several are the reason a given stage exists at all.

| Prior open item | Where the roadmap addresses it |
|---|---|
| No RAM estimator anywhere in the source | Stage 3.1, with the gap explicit until then |
| Memory estimate was weights plus a flat margin | Stage 3.2 internal estimator; Milestone 11 for observed evidence |
| Protected RAM and VRAM values were working defaults, never finalized policy | Stage 1.2 as explicit policy; retired against evidence in Milestone 2 |
| Storage capacity taken from filesystem reporting | Stages 2.1–2.3; raw capacity may never authorize |
| Probe cancellation left a 42,990 MiB orphan file | Stage 2.4, whose acceptance test is exactly this scenario |
| Interrupted calibration persisted nothing after 48 minutes | Stage 2.2, incremental immutable evidence |
| Platform concurrency never mapped to a runtime control | Stage 4.3 |
| Persisted workload and reservation reconciliation never completed | Stage 4.2, and reconciliation is in every stage's definition of done |
| Analytics on one unbounded JSONL file with full-file scans | Stage 1.7 partitioned from the first event |
| Synchronous download, update and lifecycle APIs blocking on model load | Stages 2.6 and 1.6 |
| PID files with no reuse protection | Stage 1.3 |
| Hardware detection Linux and NVIDIA only | Stage 1.1, with synthetic fixtures for other shapes from the start |
| Catalog metadata frequently null (`context_length`, `download_bytes`) | Stage 2.5 explicit nulls; Stage 3.3 pre-acquisition feasibility |
| `llmfit` nondeterministic on the real host | Roadmap Part II §9, advisory with mandatory fallback |
| Frontend required internet access for embedding assets | Stage 7.3, air-gapped bootstrap |
| Tool calling disabled after tool-choice errors | Milestone 8, capability detection per model and runtime |
| Multi-pool storage designed but never exercised | Stage 2.1 contract; Milestone 14 exercises it |
| Unified memory accounting incomplete, failing closed | Stage 1.2 fail-closed; refined in Milestone 11 |
| DEEP characterization, probe isolation, crash recovery deferred | Milestone 11 and beyond; hooks retained in Stage 2.4 |

For the full prior record see `docs/legacy/PROVISIONAL.md`. Treat it as
evidence, never as instructions.
