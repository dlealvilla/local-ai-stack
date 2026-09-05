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

Eleven: seven from Stage 0.1 and four from Stage 0.3. None authorizes a
mutation, so none is caught by rule 2.

Two carry hard conditions. `K-03` — no migration engine — must retire before
the first `schema_version` bump ships. `K-08` — no authentication — must
retire before the Platform API is reachable off-host, because its current
safety is a property of deployment rather than of the code.

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

### K-08 — No authentication; the API is safe only because it is loopback
Label:        PROVISIONAL
Owner stage:  0.3
Subsystem:    api / platform
Authorizes:   NO
What:         The Platform API performs no authentication. The local
              administrator is implicit, and the server binds to 127.0.0.1.
Why now:      Identity contracts exist but no identity provider does;
              Stage 1.7 adds authentication hooks and Stage 5.1 makes
              identity real. A control plane an administrator reaches from
              the machine it runs on is adequate for Milestone 0.
To make real: Authentication at the API boundary, resolving a Subject, with
              authorization evaluated against an AccessContext.
Retire when:  Stage 1.7 at the earliest. **Must retire before the Platform
              API is reachable off-host** — the current safety is a property
              of deployment, not of the code.
Status:       OPEN

### K-09 — Startup continues despite unreadable records
Label:        PROVISIONAL
Owner stage:  0.3
Subsystem:    platform / startup
Authorizes:   NO
What:         A record the store cannot load is reported in the startup
              report and the platform serves anyway.
Why now:      An administrator diagnoses through the Platform API, so
              refusing to start over an unreadable record would remove the
              only surface available for understanding why. No record yet
              authorizes anything, so continuing costs nothing.
To make real: Classify defects by whether the record could authorize a
              mutation, and fail closed for those.
Retire when:  A record can authorize something — Milestone 2, where storage
              evidence and admission decisions are persisted.
Status:       OPEN

### K-10 — Standard-library HTTP server
Label:        WORKING
Owner stage:  0.3
Subsystem:    adapters / http
Authorizes:   NO
What:         Single-threaded, no TLS, loopback only.
Why now:      The transport is an adapter behind the router, so replacing it
              changes nothing outside one file. A control plane serving one
              administrator does not need more.
To make real: An asynchronous server, TLS, and concurrency, behind the same
              router.
Retire when:  Concurrent administration is required, or the API leaves
              loopback — which is the same condition as K-08.
Status:       OPEN

### K-11 — No pagination on list endpoints
Label:        DEFERRED
Owner stage:  0.3
Subsystem:    api
Authorizes:   NO
What:         List endpoints return everything.
Why now:      The longest list is the contract catalogue at 36 entries.
To make real: Cursor-based pagination on the router's rendering path, so
              every list endpoint inherits it.
Retire when:  A list can exceed what an administrator can read — the model
              catalogue at Stage 2.5.
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

### K-13 — hwloc topology is parsed from CLI XML, not the library

**Stage** 1.1 · **Kind** approximation · **Risk** low

The hwloc provider runs `lstopo-no-graphics --output-format xml` and parses
the result rather than binding to `libhwloc`. Documented stable output and no
compiled dependency, but it costs a process launch per discovery and cannot
reach anything the XML omits.

**Retires when** discovery latency is measured as material, or a needed fact
is only available through the library. Not before: adding a C binding to
avoid one subprocess at startup would be a poor trade.

### K-14 — accelerator memory comes from the vendor CLI, not NVML

**Stage** 1.1 · **Kind** approximation · **Risk** low

`nvidia-smi --query-gpu` rather than NVML directly. Sufficient for identity,
memory, driver and assignment, and it is the interface most likely to exist
on any host with NVIDIA tooling at all. NVML would give richer detail and
per-process accounting.

**Retires when** Milestone 2 needs live utilization or per-process
accounting, which the CLI reports poorly.

### K-15 — the support matrix is a literal in `host/profile.py`

**Stage** 1.1 · **Kind** provisional · **Risk** low

Which shapes have earned which profile is a dictionary in source. Correct
while one shape is validated; it will need to be data an operator can read
once several are, and it cannot currently express "certified for inference
but not for multi-accelerator".

**Retires when** a third shape earns a profile, or a shape needs a
per-capability profile rather than a single tier.

### K-16 — the shape key is coarse

**Stage** 1.1 · **Kind** approximation · **Risk** medium

A profile is keyed on OS family, architecture and accelerator vendor, so one
validated NVIDIA host makes every `linux/x86_64/nvidia` host `COMPATIBLE` —
including hardware with a different driver generation or an accelerator with
materially different capabilities.

Deliberate: a key including the exact model would never match twice and the
ladder would be useless. But this is the place where a support claim can
outrun its evidence.

**Retires when** a host matching a validated shape fails discovery, which is
the evidence that the key is too coarse.

### K-17 — one reconciliation rule, and no framework for a second

**Stage** 1.1 · **Kind** provisional · **Risk** low

Accelerator assignment is resolved by a declared provider capability; every
other conflict leaves the value unresolved. Deliberately un-generalized — a
precedence framework built before a second rule exists would encode guesses.

**Retires when** a second field genuinely needs a rule. Two justify a shape;
one does not.

### K-18 — `apt` is the only provisioning mechanism

**Stage** 1.1 · **Kind** provisional · **Risk** medium

`AptProvisioner` supports Debian-family hosts and one mapped component. A
host with `dnf`, an air-gapped host or an immutable image gets `UNAVAILABLE`
and a degraded platform, and must install hwloc by hand.

It sits behind the `ComponentProvisioner` port, so adding a mechanism does
not change `install`. `DC-07` covers the verified-release path.

**Retires when** a supported environment is not Debian-family, or an
enterprise requires an offline bundle.

### K-19 — CPU topology detail is observed but not carried

**Stage** 1.1 · **Kind** deferred · **Risk** low

hwloc reports NUMA nodes, cache hierarchy and PCI locality; `CpuFacts`
carries vendor, model and two core counts. The reference host has 8 L3
caches and 1 NUMA node, none of which reaches a contract.

Correct under the Stage 0.2 field test — nothing consumes it yet and the raw
fixture preserves it. But NUMA locality is exactly the kind of fact that
matters for large-model placement.

**Retires when** placement or a runtime needs locality. The provider already
sees it; only the contract needs widening.

## Deferred capability register

Distinct from the debt entries above. A debt entry records an approximation
in something that exists; these record **hardware and environment shapes
the architecture accommodates but the implementation does not yet reach**.

They are listed so that future opportunities are deliberately revisited
rather than quietly forgotten, which is the failure mode for anything whose
absence never breaks a test.

**Three statuses, never conflated.** The whole point of the register is
that these come apart:

| Status | Means |
|---|---|
| `ARCHITECTURE-READY` | The current ports and contracts can accommodate it |
| `ADAPTER-NOT-IMPLEMENTED` | The shape is anticipated; no provider exists |
| `REAL-HOST-DETECTION-PROVEN` | `L2` evidence exists on that shape |
| `LIVE-INFERENCE-PROVEN` | `L3` evidence exists |
| `INTEGRATED` / `CERTIFIED` | `L4` evidence exists |

Architecture support is not implementation support, and neither is
acceptance evidence. **Nothing here may be described as "supported"**
because the architecture permits it — that claim belongs to
`DeploymentProfile`, and it is earned.

### DC-01 — Apple Silicon / macOS

**Revisited at Stage 1.1** — not captured. No Apple host was available and
the brief made the shape non-blocking. Trigger unchanged.
Architecture:    ARCHITECTURE-READY
Implementation:  ADAPTER-NOT-IMPLEMENTED
Evidence:        none; may be captured opportunistically, **not Stage 1.1 blocking**
Seam:            `HostDiscoveryProvider`, plus a runtime/executor adapter when inference is wanted
Unproven:        whether a general provider reports enough on Darwin; unified-memory
                 normalization against a real machine; any Apple runtime path
Downstream redesign expected: NO
Revisit:         after the first live inference vertical, or when Apple runtime
                 support becomes a roadmap priority

### DC-02 — CPU-only hosts

**Revisited at Stage 1.1** — not captured on real hardware. Partially
covered by a regression test built from the reference host's ASPEED
management VGA, which is the device that would have produced a phantom
accelerator on a CPU-only machine. Real-hardware confirmation still owed.
Architecture:    ARCHITECTURE-READY
Implementation:  ADAPTER-NOT-IMPLEMENTED
Evidence:        none; may be captured opportunistically, **not Stage 1.1 blocking**
Seam:            `HostDiscoveryProvider`, plus runtime and model selection
Unproven:        the zero-accelerator path against a real machine; a CPU-capable runtime
Downstream redesign expected: NO
Revisit:         after the first live inference vertical, or when CPU-only serving
                 becomes a product priority

### DC-03 — AMD / ROCm
Architecture:    ARCHITECTURE-READY
Implementation:  ADAPTER-NOT-IMPLEMENTED
Evidence:        none
Seam:            `HostDiscoveryProvider` via AMD SMI or equivalent, plus a ROCm runtime adapter
Unproven:        everything; no AMD hardware has been observed
Downstream redesign expected: NO
Revisit:         when AMD enters the validated platform roadmap

### DC-04 — Intel accelerators
Architecture:    ARCHITECTURE-READY
Implementation:  ADAPTER-NOT-IMPLEMENTED
Evidence:        none
Seam:            `HostDiscoveryProvider` via Level Zero / Sysman or equivalent, plus a
                 compatible runtime adapter
Unproven:        everything
Downstream redesign expected: NO
Revisit:         when Intel accelerators enter the validated roadmap

### DC-05 — Kubernetes / Node Feature Discovery
Architecture:    ARCHITECTURE-READY
Implementation:  ADAPTER-NOT-IMPLEMENTED
Evidence:        none
Seam:            `HostDiscoveryProvider`
Unproven:        whether node labels normalize usefully; Kultrun has no reason to run
                 under Kubernetes yet
Downstream redesign expected: NO
Revisit:         when Kubernetes execution or orchestration becomes active scope.
                 Kubernetes must never become required for standalone hosts

### DC-07 — Verified-release-artifact provisioning
Architecture:    ARCHITECTURE-READY — sits behind `install`, alongside the
                 package-manager mechanism, with no core contract change
Implementation:  ADAPTER-NOT-IMPLEMENTED
Evidence:        none
Seam:            `install`, `components.ComponentSource`
Unproven:        everything; the reference environment uses its distribution's
                 package manager
Would later cover: package-manager gaps, Kultrun-pinned versions, enterprise
                 mirrors, offline bundles, environments without a suitable
                 package manager
Downstream redesign expected: NO
Revisit:         when the reference mechanism cannot satisfy a required
                 component, or when a second supported environment appears

### DC-06 — Container execution and device attachment (CDI)
Architecture:    ARCHITECTURE-READY — `ContainerEngine` seam declared at Stage 1.3
Implementation:  ADAPTER-NOT-IMPLEMENTED
Evidence:        none
Seam:            `Executor` (OCI implementation) and `ContainerEngine`; CDI inside the
                 OCI adapter only
Unproven:        the whole path; native execution is the reference
Downstream redesign expected: NO
Revisit:         after the first live inference vertical, when deciding whether an
                 executor should ever be recommended over native

---

## Retired entries

Retired entries stay in this file with their retiring stage and date,
because the record of what was approximated and when it was fixed is itself
evidence.

### K-12 — Approved dependency constraints were enforced only in prose
Label:        PROVISIONAL
Owner stage:  architectural prerequisite, pre-1.1
Subsystem:    tests / architecture harness
Authorizes:   NO
What:         Constraints approved and documented in `docs/ARCHITECTURE.md`
              were absent from `tests/architecture.py`.
Resolution:   All eight approved rules are now enforced, plus two further
              rules found by sweeping every *Must not* line in the module
              inventory: `training ⟂ inference` (Part IV `training`;
              `PRODUCT_VISION` §74) and the `agents` import allow-list,
              whose documentation was self-contradictory and was corrected
              in 4dfc8c2.

              Law 5 is enforced by evaluating an adapter as the domain whose
              port it implements, resolved from its family. An adapter
              family absent from that mapping is itself a violation, so a
              new adapter must declare whose port it implements before it
              may import anything.

              Each rule has a conforming case and a violating case, and the
              harness was verified against a real injected violation — a
              `kultrun.adapters.host` module importing `kultrun.resource` —
              which failed with the rule and the inheritance both named.
Not enforced: `runtime ⟂ capacity` is *recommended* but not implemented.
              The `runtime` entry says it must not "own capacity policy",
              which is weaker than a documented import ban, and enforcing it
              would have been inventing a rule rather than closing a gap.
Status:       RETIRED (2026-09-05, architecture harness enforcement task)

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
| Hardware detection Linux and NVIDIA only | Stage 1.1: discovery becomes a provider architecture over mature tooling, proven and captured on three real shapes |
| Catalog metadata frequently null (`context_length`, `download_bytes`) | Stage 2.5 explicit nulls; Stage 3.3 pre-acquisition feasibility |
| `llmfit` nondeterministic on the real host | Roadmap Part II §9, advisory with mandatory fallback |
| Frontend required internet access for embedding assets | Stage 7.3, air-gapped bootstrap |
| Tool calling disabled after tool-choice errors | Milestone 8, capability detection per model and runtime |
| Multi-pool storage designed but never exercised | Stage 2.1 contract; Milestone 14 exercises it |
| Unified memory accounting incomplete, failing closed | Stage 1.2 fail-closed; refined in Milestone 11 |
| DEEP characterization, probe isolation, crash recovery deferred | Milestone 11 and beyond; hooks retained in Stage 2.4 |

For the full prior record see `docs/legacy/PROVISIONAL.md`. Treat it as
evidence, never as instructions.
