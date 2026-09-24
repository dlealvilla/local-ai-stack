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

Open entries continue from kernel through Stage 1.5A. Most do not authorize
a mutation. `K-29` and `K-34` start real work (storage reservation; the
reference process) and are tolerable only because the API is loopback
(`K-08`).

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

### K-20 — a deployed instance cannot be configured  ·  RETIRED

**Stage** workflow adoption · **Kind** provisional · **Risk** medium

`kultrun host` and `kultrun serve` call `build()` with no configuration, and
`PlatformSettings.state_root` defaults to `./.state`. So the state location
of an installed instance depends on the directory it happens to be run
from, and two invocations from different directories build two unrelated
state stores.

`kernel/config.py` loads from a mapping or a file and has no environment
overlay, so there is currently no way to point a deployment target at, say,
`/var/lib/kultrun`. Found on the first artifact deployment: an env var was
set on the command line and silently did nothing, which is worse than
failing.

Harmless while acceptance runs are single commands from a known directory.
Not harmless once the platform holds reservations or models, and definitely
not once it runs as a service.

**Retired** as a Stage 1.2 prerequisite. The composition root now resolves
`KULTRUN_STATE_ROOT`, makes the root absolute once at startup, hands the
resolved path down, and warns when an installed artifact has fallen back to
a working-directory default. No domain reads the environment for itself.
Proven by `tests/test_deployed_state.py` and on the reference host through
an installed artifact. The general precedence question became K-22.

### K-21 — a CPU model name carries the provider's padding  ·  RETIRED

**Stage** 1.1, found at workflow adoption · **Kind** approximation · **Risk** low

hwloc reports `CPUModel` as `"AMD EPYC 7763 64-Core Processor                "`
with trailing padding, and normalization passes it through unstripped. It is
cosmetic in the `kultrun host` output but `cpu.model_name` is a **host
fingerprint input**, so if the padding ever changes between hwloc versions
the host identity changes with it and cached evidence is discarded for no
real reason.

The same class of latent instability as the `/run/nvidia-ctk-hook<uuid>`
mount found during Stage 1.1, and less likely to trigger.

Not fixed here because stripping it changes the accepted Stage 1.1
fingerprint and its committed fixture, which this workflow task must not
reopen.

**Retired at Stage 1.2.** Normalization strips reported strings, so padding
cannot reach a fingerprint input, and two providers reporting the same value
with different padding are now recognised as agreeing. The reference host's
fingerprint honestly moved from `4d4efedb…` to `2abe0703…`; the normalized
fixture was re-derived by replaying committed provider evidence with no host
involved, and both values are recorded in the Stage 1.1 package.

### K-22 — one environment override, not a configuration system

**Stage** Stage 1.2 prerequisite · **Kind** provisional · **Risk** low

`KULTRUN_STATE_ROOT` is the only environment override. Every other setting
— API address, port, whether provisioning is permitted — can be set
programmatically or in a TOML file but not from the environment of a
deployed instance.

Deliberate. A general `KULTRUN_<SECTION>__<KEY>` overlay has to settle type
coercion, nested tables, precedence and unknown-key behaviour, and
`kernel/config.py` fails closed on unrecognised keys by design. That is a
configuration design decision, and inventing it to fix a state-root bug
would have been the larger mistake.

Also open: nothing yet looks for a configuration file at a conventional
path, so a deployed instance is configured only through the environment or
by a caller.

**Retires when** a second setting genuinely needs to differ per deployment
— most likely the API address once the platform is reachable off-loopback,
or a capacity headroom policy an operator must tune.

### K-23 — headroom values are chosen, not measured

**Stage** 1.2 · **Kind** approximation · **Risk** medium

Every figure in `capacity/policy.py` is conservative judgement. The 25%
memory and accelerator fractions come from the only number with operational
history — the previous attempt's 0.75 weight budget — and the floors and the
storage fraction are reasoned rather than observed.

Deliberately biased toward reserving too much. A conservative policy can be
tightened once real workloads provide evidence, with old decisions still
explicable through `policy_version`. One tuned to look generous cannot be
loosened safely, because what it already admitted is running.

**Retires when** Milestone 3 has real runtime memory evidence, or a real
workload is refused by a reserve that measurement shows to be too large.

### K-24 — the unverified pool ceiling is a policy number, not a bound

**Stage** 1.2 · **Kind** provisional · **Risk** medium

A pool whose reported size is not credible has effective capacity bounded at
64 GiB. That is not a claim about the pool — it is a limit on how much may
be believed having verified nothing.

The consequence is real: a genuinely large network volume is usable only up
to 64 GiB until Stage 2.2 can verify a reservation. Correct for Milestone 1,
where one model is placed by hand, and wrong for a customer with a 10 TB
volume and forty models.

A pool whose reported size is not credible has **effective** capacity
bounded at 64 GiB for display. Stage 1.6L stopped copying that ceiling
into authorizing SAFE. ResourceManager spends `safe_bytes` only from
Storage Sonar authorizing evidence (trusted native, probe, empirical, or
a hard bound). The 64 GiB figure remains a belief bound.

**Retires when** empirical/provider probes produce authorizing bounds so
the belief ceiling is only a display starting point.

### K-25 — accelerator memory is never aggregated, and nothing tests otherwise

**Stage** 1.2 · **Kind** deferred · **Risk** low

Each accelerator is layered separately and never summed. Correct — and
untested against reality, because the reference host has one assigned
device. Whether an interconnect ever permits treating two devices as one
budget is unanswered, and any aggregation written now would be untested by
construction.

**Retires when** a host with more than one assigned accelerator is
available (`DC-08`), or model placement across devices is implemented.

### K-26 — capacity has no live utilization

**Stage** 1.2 · **Kind** deferred · **Risk** low

The envelope describes capacity, not occupancy. It does not subtract what is
currently in use, by Kultrun or anything else, so on a busy host the safe
figure describes what the resource *is* rather than what is free right now.

Intentional: capacity and utilization are different questions, and conflating
them is how a momentary dip becomes a structural refusal. But admission at
Stage 1.5A will need both, and unmanaged external usage is exactly the case
the roadmap warns about.

**Retires when** Stage 1.5A needs to admit against live availability, or
Stage 11.1 fuses observed evidence.

### K-27 — storage sanity runs only when asked

**Stage** 1.2A · **Kind** provisional · **Risk** low

The 1.2A `posix_fallocate` sanity probe still runs only when asked.
Nothing schedules it. Stage 1.6L Storage Sonar is a separate path: cheap
native + mandatory compatible probes at characterization; empirical fallback
only before mutation on a live host, never on GET and never on fixture
replay.

Deliberate for the 1.2A probe: Kultrun must not run a long filesystem
operation on a background thread — that is how the previous implementation
orphaned a 42,990 MiB probe file.

**Retires when** an executor can own a cancellable background job with
cleanup, or when 1.6L physical storage validation schedules Sonar under
that executor.

### K-28 — one reservation primitive, POSIX only

**Stage** 1.2A · **Kind** provisional · **Risk** medium

`posix_fallocate` is the only genuine reservation mechanism, so a sanity
check on macOS reports `UNSUPPORTED` and gathers nothing. The policy bound
stands unchanged, which is the correct fail-closed outcome — but it means
the subsystem cannot verify anything on a developer machine.

The tempting substitute is `truncate` or a sparse write. Both would succeed
instantly at any size and "verify" a petabyte on the very mounts this
exists to distrust, so no evidence beats fake evidence.

**Retires when** macOS or Windows becomes a supported deployment target and
a genuine platform primitive is wired — `F_PREALLOCATE` on Darwin.

### K-29 — the sanity mutation is unauthenticated and unaudited

**Stage** 1.2A · **Kind** deferred · **Risk** medium

`POST /v1/storage/sanity-check` reserves real space and is reachable by
anyone who can reach the API. Tolerable only because the API binds to
loopback and there is no authentication anywhere yet (`K-08`), so this adds
no exposure that did not already exist.

It also writes no `AuditEvent`, though it is a deliberate operator action
against a real resource — exactly the shape audit exists for.

**Retires when** authentication arrives, or when Stage 1.5A makes mutating
endpoints pass through admission and audit. Whichever comes first.

### K-30 — the console has no automated visual regression

**Stage** 1.2A · **Kind** deferred · **Risk** low

Two real defects were found by looking at the rendered page and by nothing
else: a relative asset path that blanked every panel, and a capacity note
that called a replayed reservation genuine. Both now have tests, but both
were found by eye.

There is no screenshot comparison, no DOM assertion beyond served markup,
and no check that a panel actually displays the value the API returned.

**Retires when** the console carries something a customer relies on. Until
then, looking at it is part of the acceptance ritual and cheaper than the
infrastructure would be.

### K-31 — process identity cookie residual
Label:        PROVISIONAL
Owner stage:  1.3
Subsystem:    execution
Authorizes:   NO
What:         Native launch persists an adapter-owned cookie
              (`ExecutorHandle.external_identity`: boot id, start token,
              process group, grace, execution id) plus `KULTRUN_EXECUTION`
              in the child environment. A later control-plane process that
              can match that cookie reacquires `OWNED` and may signal the
              process group. A live PID whose cookie is missing or
              unreadable is `UNVERIFIED` and is never signalled. Capture
              is file-backed; that is not this debt.
Why now:      PID reuse is still lying. Cookie match is the minimum strong
              identity; pidfd does not survive the launching CLI.
To make real: Windows process identity; treat unverified leftovers with a
              later reservation lease (K-44).
Retire when:  native, container, and future executors all reacquire with an
              adapter-owned identity on every supported OS.
Status:       OPEN

### K-32 — execution health is UNKNOWN
Label:        PROVISIONAL
Owner stage:  1.3
Subsystem:    execution
Authorizes:   NO
What:         `ExecutionHealth` is a separate field from observed state,
              and v0 always reports `UNKNOWN`. A live PID is not a
              functioning inference API.
Why now:      Stage 1.3 has no application-level probe. Collapsing health
              into RUNNING would have to be undone at Stage 1.6.
To make real: A probe appropriate to the workload (later, an inference
              endpoint health check) that can be unhealthy while the
              process is still running.
Retire when:  Stage 1.6 introduces a real instance health check.
Status:       OPEN

### K-33 — ContainerEngine GPU and multi-engine depth
Label:        DEFERRED
Owner stage:  1.6A
Subsystem:    execution
Authorizes:   NO
What:         `ContainerExecutor` exists behind the generic `Executor`
              port. Docker CLI is the first `ContainerEngine`. Stage
              1.6A T3 proved Linux host-network v0 against Docker
              Engine; GPU/CDI exposure, bridge/publish networking,
              additional engines, image management and Kubernetes are
              not implemented.
Why now:      Stage 1.6A needed one second execution mechanism and a
              truthful capability profile. Claiming NVIDIA container
              inference would be a lie. T3 left accelerator exposure
              UNKNOWN.
To make real: implement and verify device attachment separately; add
              engines as adapters; keep Docker out of generic contracts.
Retire when:  a later stage accepts GPU-in-container or additional
              engines with their own evidence, or the product decides
              those paths unused.
Status:       OPEN

### K-34 — the runtime mutation is unauthenticated and unaudited
Label:        DEFERRED
Owner stage:  1.3
Subsystem:    api / execution
Authorizes:   YES (starts/stops only the reference workload on loopback)
What:         `POST /v1/runtime/execution` and `/stop` start and stop a
              real process and are reachable by anyone who can reach the
              API. They accept no arbitrary argv. They write no
              `AuditEvent`.
Why now:      Same bound as K-08 and K-29: the API binds to loopback and
              there is no authentication anywhere yet. The workload is
              the product-controlled acceptance harness, not a shell.
To make real: Authentication, or Stage 1.5A admission and audit on
              mutating endpoints. Whichever comes first.
Retire when:  authentication arrives, or mutating execution endpoints pass
              through admission and audit.
Status:       OPEN

### K-35 — live Hub listing is optional and not compatibility authority
Label:        DEFERRED
Owner stage:  1.4A / 1.6L
Subsystem:    adapters / model_source
Authorizes:   NO
What:         Product default `model_source_mode=offline` (`KULTRUN_MODEL_SOURCE_MODE`)
              uses the packaged catalog only and does not require network
              access. `live` may call optional `huggingface_hub` listing
              and Safetensors metadata behind the existing
              `HuggingFaceSource` / `SafetensorsWeightEvidenceProvider`
              seams. Hub failure keeps the curated catalog and records
              typed `source_failure`. Remote tags and app hints are
              discovery filters, never Kultrun compatibility or
              availability. File acquisition remains a separate adapter.
Why now:      v0 must remain usable offline. Whole-Hub search, pagination
              and ranking stay out of scope (K-97).
To make real: Pagination, ranking, and a metadata cache when a catalog-
              ingest stage claims them.
Retire when:  that ingest is an accepted stage output, or product policy
              requires live Hub metadata as the only catalog.
Status:       OPEN

### K-36 — ModelRequirement v0 estimates are curated and conservative
Label:        PROVISIONAL
Owner stage:  1.4A
Subsystem:    model
Authorizes:   NO
What:         Weight, RAM, overhead and KV components on the curated
              original six remain coarse packaged estimates with method
              `curated`. Expanded 1.4B variants use `formula_v0`. They
              are not measured runtime evidence. For native vLLM, the
              Kultrun estimator recomposes those components with
              requested context, batch size, and an explicit engine
              workspace allowance; the packaged `estimated_vram_gib`
              total is catalog data, not the serving demand used for
              feasibility. Compared with llmfit `plan` minimum, Kultrun
              VRAM is typically conservative; some 20% / 100% band
              crossings remain expected calibration gaps, not unit bugs.
              Do not rewrite production estimates to match llmfit.
Why now:      Stage 1.4B needs *some* host-independent requirement to
              filter against capacity. Inventing a precise measured
              estimator now would be untested intelligence.
To make real: Runtime-specific estimation (seam now) plus Stage 1.6
              predicted-vs-actual evidence. Load-bearing unknowns stay
              unresolved rather than filled.
Retire when:  Stage 3.1 / 1.6 evidence replaces the curated v0 method
              for the fields that authorize a later admission.
Status:       OPEN

### K-37 — llmfit is an optional requirement estimator
Label:        DEFERRED (optional extra)
Owner stage:  1.4B
Subsystem:    adapters / estimators
Authorizes:   NO
What:         llmfit is not a Kultrun hard dependency. Default mode is
              AUTO (llmfit primary, Kultrun fallback on typed failure
              only). For native vLLM on a discrete GPU, a successful
              llmfit `plan` is refined into serving demand (K-96);
              AUTO does not fall back merely because the plan minimum
              is smaller than Kultrun composition. Strict `llmfit`
              does not fall back when the executable is missing —
              estimation is unavailable/unresolved. Strict `kultrun`
              does not require llmfit. AUTO fallback is not estimate
              shopping and is not a product reconciler.
Why now:      T0/T1 must not require the binary; T2 proves it from a
              clean install with the optional extra. K-03 forbids a
              `schema_version` bump, so `config.platform@1
              .model_requirement_estimator` meaning was restated in
              place (K-05 review) when the default became AUTO.
To make real: The optional extra `estimators` now pins `llmfit==1.1.14`
              (MIT). Operator runbook still needed.
Retire when:  a release actually ships the extra and an operator runbook
              names the pin, or llmfit is dropped.
Status:       OPEN

### K-38 — llmfit ram_gb uses a coarse floor
Label:        PROVISIONAL
Owner stage:  1.4B
Subsystem:    adapters / estimators / llmfit
Authorizes:   NO
What:         `llmfit plan` `minimum.ram_gb` often reports 8 GiB even for
              sub-2B models. VRAM figures track parameter/quant/context
              more closely. Comparison against Kultrun RAM will LARGE-
              DIFFERENCE on small models for this reason, not a unit bug.
Why now:      We must not rewrite llmfit. Document and compare; do not
              treat the floor as Kultrun SAFE RAM.
To make real: Use a finer llmfit field if one appears, or ignore ram_gb
              for GPU placement when VRAM is the limiting resource.
Retire when:  llmfit publishes a host-independent RAM requirement without
              the floor, or Kultrun stops consuming ram_gb for GPU fits.
Status:       OPEN

### K-39 — acquisition has no download scheduler
Label:        DEFERRED
Owner stage:  1.4C
Subsystem:    model / acquisition
Authorizes:   NO
What:         v0 acquires one artifact synchronously. There is no pause,
              cancel, bandwidth throttle, parallelism, or custom resume
              engine. Hugging Face may reuse its own cache; Kultrun does
              not claim byte-range resume.
Why now:      The first vertical needs stored artifacts, not a download
              platform. Storage Sonar taught us not to spawn unmanaged
              work.
To make real: An acquisition manager with jobs, limits and cooperative
              cancel, after a mutation/job lifecycle exists.
Retire when:  a later stage owns scheduled or resumable acquisition.
Status:       OPEN

### K-40 — no shared model warehouse or content-addressed dedup
Label:        DEFERRED
Owner stage:  1.4C
Subsystem:    model / storage
Authorizes:   NO
What:         Each STORED artifact is a directory under the Kultrun
              model store. Identical files across revisions are not
              shared. No network warehouse or multi-host replica.
Why now:      Plural inventory is the required proof. Dedup is
              optimization.
To make real: Content-addressed blob store and a warehouse port.
Retire when:  Stage 2.6 or a later storage-mutation stage requires it.
Status:       OPEN

### K-41 — no automatic conversion or quantization
Label:        DEFERRED
Owner stage:  1.4C
Subsystem:    model / acquisition
Authorizes:   NO
What:         Acquisition stores the selected variant as-is. It does not
              convert, quantize, or rewrite weights.
Why now:      Silent format change would falsify artifact identity.
To make real: An explicit derivation workflow with its own artifact id.
Retire when:  a stage owns derived artifacts.
Status:       OPEN

### K-42 — gated/private credential UX and license enforcement
Label:        DEFERRED
Owner stage:  1.4C
Subsystem:    adapters / acquisition
Authorizes:   NO
What:         Tokens come from the environment (`HF_TOKEN` or a named
              ref). They are never persisted. There is no credential UI
              and no commercial-license policy engine. Inventory retains
              known license metadata from 1.4A.
Why now:      Public models and typed auth failures are enough for v0.
To make real: Secret references plus a license policy owner.
Retire when:  enterprise/gated acquisition is a product requirement.
Status:       OPEN

### K-43 — huggingface_hub is an optional acquisition extra
Label:        DEFERRED (optional extra)
Owner stage:  1.4C
Subsystem:    adapters / acquisition
Authorizes:   NO
What:         `huggingface_hub>=0.23,<1` (Apache-2.0) is extra
              `acquisition`. Fixture acquisition does not require it.
              Product default provider is `huggingface`; missing package
              is `provider_unavailable`.
Why now:      Offline T0/T1 must stay installable. T2 installs the extra.
To make real: Release extra + operator pin, or drop the Hub adapter.
Retire when:  a release ships the extra with an operator runbook.
Status:       OPEN

### K-44 — reservation has no lease or TTL
Label:        DEFERRED
Owner stage:  1.5A
Subsystem:    resource
Authorizes:   NO
What:         ACTIVE reservations stay ACTIVE until explicit release.
              There is no heartbeat, expiry, or reclamation daemon.
Why now:      No running instance exists to renew a lease.
To make real: Instance/restart reconciliation after 1.5B.
Retire when:  a later stage owns reservation leases.
Status:       OPEN

### K-45 — ports are a seam, not an allocator
Label:        DEFERRED
Owner stage:  1.5A
Subsystem:    resource
Authorizes:   NO
What:         ResourceRequest.port_count is unused. No port reservation,
              discovery, proxy, or gateway routing. Stage 1.6L added a
              small InferenceInstance loopback allocator
              (`allocate_loopback_port`) with collision retry; it is not
              a ResourceManager port grant.
Why now:      The first vertical needs an exclusive loopback port, not
              a network orchestration platform.
To make real: Resource-level endpoint reservation, discovery, proxy, or
              gateway routing when more than one local bind strategy
              exists.
Retire when:  endpoint/port reservation is a ResourceManager concern or
              a dedicated network seam owns it.
Status:       OPEN

### K-46 — no scheduler, queues, or preemption
Label:        DEFERRED
Owner stage:  1.5A
Subsystem:    resource
Authorizes:   NO
What:         Admission is now or not. No waiting queue, fairness,
              priority, bin packing, or retry daemon.
Why now:      The first vertical needs a yes/no grant, not a scheduler.
To make real: After several concurrent instances exist.
Retire when:  a stage owns scheduling policy.
Status:       OPEN

### K-47 — no enterprise quotas
Label:        DEFERRED
Owner stage:  1.5A
Subsystem:    resource
Authorizes:   NO
What:         No user/team/department pools or license limits.
Why now:      Host SAFE minus ACTIVE is the only ledger.
To make real: Identity and entitlement stages.
Retire when:  quota policy has an owner.
Status:       OPEN

### K-48 — no physical resource enforcement
Label:        DEFERRED
Owner stage:  1.5A
Subsystem:    resource
Authorizes:   NO
What:         Reservations are control-plane accounting. No cgroups,
              CUDA quotas, namespaces, or container limits.
Why now:      Physical realization belongs to later runtime/execution.
To make real: When an instance must be prevented from exceeding its grant.
Retire when:  a stage owns enforcement adapters.
Status:       OPEN

### K-49 — CPU and incremental storage are non-load-bearing
Label:        DEFERRED
Owner stage:  1.5A
Subsystem:    resource
Authorizes:   NO
What:         CPU counts remain non-load-bearing. Incremental storage
              **is** load-bearing for `RUNTIME_PROVISIONING` and
              `MODEL_ACQUISITION` as of Stage 1.6L, per named pool.
              Inference admission still treats storage as optional extra.
Why now:      Runtime install and model fetch are multi-gigabyte mutations.
To make real: CPU requirements with evidence; inference scratch if needed.
Retire when:  a trusted CPU requirement exists; storage for inference is
              already in the 1.6L ledger.
Status:       OPEN

### K-50 — runtime-specific readiness is reference-only
Label:        DEFERRED
Owner stage:  1.5C
Subsystem:    runtime
Authorizes:   NO
What:         The reference-serving adapter owns `/health` and the ready
              marker. Native vLLM readiness (process alive + `/health` +
              `/v1/models` served-name match) exists in Stage 1.6L.
              llama.cpp and MLX readiness are not implemented.
Why now:      The first product serving path is native vLLM only.
To make real: Stage per additional production runtime adapter.
Retire when:  every product runtime that can launch owns its readiness
              translation.
Status:       OPEN

### K-51 — real model load and inference
Label:        DEFERRED
Owner stage:  1.5B
Subsystem:    runtime
Authorizes:   NO
What:         Native vLLM non-streaming text generation is physically
              proven in Stage 1.6L (T5 `ba04df2`). llama.cpp, MLX,
              CUDA/ROCm load outside this path, chat, completions
              streaming, and token APIs beyond the bounded contract
              are not implemented (K-112, K-95).
Why now:      One vertical was enough to prove serving; other runtimes
              and request types stay later.
To make real: later stages for other runtimes and streaming.
Retire when:  a real Kultrun request reaches a real vLLM model on real
              hardware (Stage 1.6L CLOSED L3). Remaining runtimes and
              streaming are then separate entries.
Status:       CLOSED — T5 physical `ba04df2`; remaining runtimes are K-112

### K-52 — no shared execution cache
Label:        DEFERRED
Owner stage:  1.5B
Subsystem:    inference
Authorizes:   NO
What:         Stored path is not assumed to be the permanent execution
              location, but no NVMe staging, eviction, or cache tier
              exists.
Why now:      One host, reference serving, artifacts stay where stored.
To make real: When local execution cache or network-to-NVMe staging is
              required.
Retire when:  a stage owns the cache/eviction workflow.
Status:       OPEN

### K-53 — no automatic model switching
Label:        DEFERRED
Owner stage:  1.5B
Subsystem:    inference
Authorizes:   NO
What:         No idle unload, LRU eviction, or automatic active-model
              replacement. Operators compose stop → release → reserve
              → start.
Why now:      Lifecycle mutations stay explicit.
To make real: After several concurrent instances and a scheduler owner.
Retire when:  a stage owns deactivate/switch-model policy.
Status:       OPEN

### K-54 — no verified RuntimeCapabilityProfile
Label:        DEFERRED
Owner stage:  1.5C
Subsystem:    runtime
Authorizes:   NO
What:         Stage 1.5C adds declared `RuntimeSupportDescriptor` and
              host-scoped `ExecutorCapabilityProfile` only. There is no
              provisioning plan, no verifier, and no persisted verified
              operational profile.
Why now:      Boundary reconciliation must not become a provisioner.
To make real: Later 1.6 letters under a separate brief.
Retire when:  a verified `RuntimeCapabilityProfile` is accepted evidence.
Status:       OPEN

### K-55 — model selection is not yet runtime-first  ·  RETIRED
Label:        DEFERRED → RETIRED
Owner stage:  1.6H
Subsystem:    planning
Authorizes:   NO
What:         The 19-model funnel ranked from catalog + host capacity.
              Stage 1.6H ranks only currently feasible candidates
              derived from EligibleModelView + remapped requirement +
              CapacityAssessment, and persists bounded AUTO|MANUAL
              ModelSelection. Acquisition remains the warehouse STORE
              path until DeploymentPlan gating.
Why now:      1.5C must not remap selection before a verified runtime exists.
To make real: Implemented in Stage 1.6H.
Retire when:  normal executable selection consumes runtime eligibility
              and capacity against the selected verified foundation.
Status:       RETIRED (1.6H, 2026-09-08)
Note:         `SelectionService.recommend()` remains for isolated
              estimator tests. Product authority is `rank_feasible()`
              via `ModelSelectionService`. `plan_from` in the selection
              payload remains a provisional recommendation artifact
              (`plan_authoritative: false`); demoted in 1.6I. It does
              not supply execution resource values. Acquisition
              `--recommended` now consumes the CURRENT DeploymentPlan.
              STORE_ONLY catalog acquire remains independent of the plan.

### K-56 — Runtime performance-aware ranking
Label:        DEFERRED
Owner stage:  1.6B
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6B:  No
What:         Stage 1.6B ranking is deterministic/static: compatibility,
              support tier, executor availability, policy order, then
              name. It does not consume latency, throughput, tokens/sec,
              startup time, or memory efficiency. 1.6R0 added a separate
              product preference (`RuntimePreferencePolicy`) after hard
              feasibility. That is family choice, not measured ranking.
Why now:      Resolution only establishes technical plausibility.
To make real: A future RuntimeRankingPolicy behind verified operational
              evidence after inference exists. Do not collapse it into
              ResourceManager or into 1.6R0's 64 GiB SAFE band.
Retire when:  multiple verified runtime choices exist for the same workload
              and ranking consumes measured evidence.
Status:       OPEN. Product preference exists; measured ranking does not.

### K-57 — Runtime version optimization
Label:        DEFERRED
Owner stage:  1.6B
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6B:  No
What:         Candidates carry at most one provisional version token.
              There is no version-range solving, index lookup, or
              multi-version ranking.
Why now:      Pinning and verification belong to provisioning stages.
To make real: Compare available versions after an index/provisioner exists.
Retire when:  a later stage accepts version selection with evidence.
Status:       OPEN

### K-58 — Native vs container performance/cost comparison
Label:        DEFERRED
Owner stage:  1.6B
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6B:  No
What:         Native-process is preferred over container-docker only by
              configured name order, not measured cost or performance.
Why now:      Neither path is a verified serving runtime yet.
To make real: Compare verified native and container serving of the same
              workload.
Retire when:  cost/performance evidence is an accepted ranking input.
Status:       OPEN

### K-59 — Runtime fallback policy
Label:        DEFERRED
Owner stage:  1.6B
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6B:  No
What:         Ranking is not automatic fallback. A later provisioning or
              verification failure must re-resolve/re-plan explicitly.
Why now:      Silent try-next would hide why the preferred path failed.
To make real: An explicit post-verification fallback policy.
Retire when:  failed provision/verify has a declared, tested fallback rule.
Status:       OPEN

### K-60 — Multi-host runtime resolution
Label:        DEFERRED
Owner stage:  1.6B
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6B:  No
What:         Resolution is current-host only.
Why now:      Fleet placement is Milestone 14-shaped work.
To make real: Host-scoped candidates across a FleetState.
Retire when:  multi-host resolution is an accepted stage output.
Status:       OPEN

### K-61 — Rich accelerator/backend ranking
Label:        DEFERRED
Owner stage:  1.6B
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6B:  No
What:         Accelerator matching is family presence (e.g. nvidia) vs
              declared support. No CUDA/ROCm/Metal scoring.
Why now:      Compatibility, not backend optimization.
To make real: Backend-specific evidence after real inference.
Retire when:  backend ranking has measured inputs and tests.
Status:       OPEN

### K-62 — Learned runtime recommendations
Label:        DEFERRED
Owner stage:  1.6B
Subsystem:    runtime / intelligence
Authorizes:   NO
Blocks 1.6B:  No
What:         No telemetry- or cohort-driven runtime recommendation.
Why now:      Intelligence must not start early.
To make real: After analytics and verified runtimes exist.
Retire when:  a learned recommender is an additive, non-authorizing input.
Status:       OPEN

### K-63 — Runtime marketplace/plugin discovery
Label:        DEFERRED
Owner stage:  1.6B
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6B:  No
What:         Descriptors are registered in-process. No third-party runtime
              plugin discovery.
Why now:      One product family descriptor is enough to prove resolution.
To make real: A discovery port that cannot own runtime semantics.
Retire when:  plugin/runtime marketplace is an accepted capability.
Status:       OPEN

### K-64 — Multi-container-engine resolution
Label:        DEFERRED
Owner stage:  1.6B
Subsystem:    execution / runtime
Authorizes:   NO
Blocks 1.6B:  No
What:         Container paths assume Docker CLI as the first engine.
              Podman/containerd are not distinct resolution axes.
Why now:      Stage 1.6A implemented one engine. Resolution reuses that.
To make real: Additional ContainerEngine adapters with truthful profiles.
Retire when:  multi-engine candidates are tested.
Status:       OPEN

### K-65 — Runtime benchmark evidence integration
Label:        DEFERRED
Owner stage:  1.6B
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6B:  No
What:         Verified operational/benchmark evidence is not an input to
              RuntimeCandidate ranking.
Why now:      Nothing is installed or verified in 1.6B.
To make real: After RuntimeVerifier and real inference produce evidence.
Retire when:  benchmark evidence is a ranking input with tests.
Status:       OPEN

### K-66 — Managed Python / Interpreter Provisioning
Label:        DEFERRED — REQUIRED PRE-COMMERCIAL DEPLOYMENT CAPABILITY
Owner stage:  later runtime / onboarding (after first runtime path is
              provisioned, verified, and exercised end-to-end)
Subsystem:    runtime / components
Authorizes:   NO
Blocks 1.6C:  No
Current seam: `kultrun.runtime.python.locate_python`
What:         Stage 1.6C locates an already-present host Python 3.12 and
              never installs one. Missing Python is a prerequisite
              failure for this reference proof. The commercial product
              must not require the customer to preinstall a specific
              Python version. Future: determine the required interpreter
              from the selected runtime path; reuse a compatible existing
              interpreter where appropriate; otherwise acquire a trusted
              Kultrun-managed interpreter; verify provenance/integrity;
              install beneath Kultrun-managed state; never modify system
              Python; hand the exact interpreter identity to
              RuntimeProvisioner; persist and remain idempotent; integrate
              with onboarding/bootstrapper.
Why now:      The first physical vLLM install must complete before
              interpreter acquisition is designed. Implementing K-66
              inside 1.6C would expand the stage into OS/package
              management.
To make real: A dedicated interpreter provisioner port. Never apt, brew,
              or pyenv inside VllmNativeProvisioner.
Retire when:  managed Python is an accepted pre-commercial capability
              with tests, and a commercial install no longer requires a
              customer-supplied interpreter.
Status:       OPEN

### K-67 — Alternative installer backend (uv)
Label:        DEFERRED
Owner stage:  1.6C
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6C:  No
Current seam: `VllmNativeProvisioner` / `python -m pip`
What:         The first product installer is stdlib venv + pip. `uv` is
              not an architectural requirement.
Why now:      Keep the provisioning mechanism explicit and replaceable.
To make real: A second RuntimeProvisioner adapter using uv, selected by
              composition, with the same plan contract.
Retire when:  an alternative installer adapter is an accepted stage output.
Status:       OPEN

### K-68 — Offline / air-gapped runtime bundles
Label:        DEFERRED
Owner stage:  1.6C
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6C:  No
Current seam: PyPI as package source on RuntimeProvisioningPlan
What:         Provisioning expects network access to the package index.
              Pre-resolved offline bundles are not produced.
Why now:      First proof is an exact online pin, not air-gap logistics.
To make real: Vendor-prepared wheels/bundles with the same plan schema.
Retire when:  offline runtime install is an accepted capability.
Status:       OPEN

### K-69 — Fully locked runtime dependency manifests
Label:        DEFERRED
Owner stage:  1.6C
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6C:  No
Current seam: pip install report hashes captured when present; never
              fabricated; not enforced against a lockfile
What:         Transitive dependency hashes are recorded when the installer
              reports them. There is no maintained lock of every vLLM
              dependency.
Why now:      A manual hash list would be stale the day it shipped.
To make real: A generated lockfile/hash policy that fails closed.
Retire when:  locked/offline bundles (K-68) need hash enforcement.
Status:       OPEN

### K-70 — Runtime package cache / mirror
Label:        DEFERRED
Owner stage:  1.6C
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6C:  No
Current seam: installer uses the default package index
What:         No customer-local or vendor-managed artifact cache.
Why now:      One PyPI install is enough to prove isolated provisioning.
To make real: A configured index/cache that the provisioner can consume.
Retire when:  a cache/mirror is required for air-gap or repeat installs.
Status:       OPEN

### K-71 — Runtime upgrade
Label:        DEFERRED
Owner stage:  1.6C
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6C:  No
Current seam: one pin per plan; older installations may remain stored
What:         Installing a newer runtime version and deliberately promoting
              it is not implemented. Version *selection* remains K-57.
Why now:      This stage proves one exact install, not version management.
To make real: An explicit upgrade workflow that creates a new plan and
              installation without mutating the old receipt.
Retire when:  upgrade is an accepted mutating workflow with tests.
Status:       OPEN

### K-72 — Runtime rollback
Label:        DEFERRED
Owner stage:  1.6C
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6C:  No
Current seam: RuntimeInstallation remains INSTALLED regardless of later
              verification
What:         Returning to a prior installed version is not implemented.
Why now:      Rollback without a verified second install is theatre.
To make real: After side-by-side installs exist (K-74) and verification
              can name which installation to serve.
Retire when:  rollback is an accepted mutating workflow with tests.
Status:       OPEN

### K-73 — Runtime uninstall / garbage collection
Label:        DEFERRED
Owner stage:  1.6C
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6C:  No
Current seam: failed staging is deleted; successful installs stay
What:         Safe removal and disk reclamation of INSTALLED runtimes
              is not implemented.
Why now:      Cleanup of success would look like rollback and is easy
              to get wrong around later verification.
To make real: An explicit uninstall path constrained to Kultrun state.
Retire when:  uninstall/GC is an accepted mutating workflow with tests.
Status:       OPEN

### K-74 — Side-by-side version management
Label:        DEFERRED
Owner stage:  1.6C
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6C:  No
Current seam: path `runtimes/<family>/<version>/<installation-id>/`
What:         Multiple versions of the same family may already occupy
              disk, but there is no product policy for serving, listing
              as current, or choosing among them.
Why now:      One pin is the 1.6C proof.
To make real: A current-installation marker that is not verification.
Retire when:  side-by-side serving is an accepted capability.
Status:       OPEN

### K-75 — Containerized runtime provisioning
Label:        DEFERRED
Owner stage:  1.6C
Subsystem:    runtime / execution
Authorizes:   NO
Blocks 1.6C:  No
Current seam: is_provisionable rejects non-native-process candidates
What:         vLLM images through ContainerExecutor are not provisioned.
              Container candidates remain resolution-only (K-33 GPU
              exposure still unknown).
Why now:      Native isolated venv is the first product installer.
To make real: A container provisioner adapter that does not put Docker
              fields on generic plans.
Retire when:  containerized vLLM install is an accepted stage output.
Status:       OPEN

### K-76 — CUDA / toolkit dependency management
Label:        DEFERRED
Owner stage:  1.6C
Subsystem:    runtime / components
Authorizes:   NO
Blocks 1.6C:  No
Current seam: unresolved driver/toolkit facts are non-provisionable
What:         The runtime provisioner does not install CUDA toolkit or
              matching userspace libraries.
Why now:      That is system administration, not isolated package install.
To make real: A separate prerequisite manager, if ever needed, outside
              VllmNativeProvisioner.
Retire when:  toolkit management is an explicit product decision with tests.
Status:       OPEN

### K-77 — Privileged Accelerator Driver Remediation
Label:        DEFERRED — REQUIRED PRE-COMMERCIAL DRIVER BEHAVIOR
Owner stage:  later host / onboarding
Subsystem:    host / components
Authorizes:   NO
Blocks 1.6C:  No
Current seam: NVIDIA driver facts come from Host Discovery; the provisioner
              never mutates them. A working driver is a Stage 1.6C host
              prerequisite.
What:         Prefer an existing adequate driver. Do not upgrade merely
              because a newer version exists. Detect and explain
              missing/insufficient drivers. Affected runtime candidates
              remain BLOCKED until remediation succeeds; a theoretically
              installable driver is not a selectable override.
              Future validated behavior, only on specifically supported
              host/distribution combinations, may: offer remediation →
              require explicit administrator approval → install a
              vendor-supported driver → reboot if required → rerun Host
              Discovery → rerun Runtime Resolution → recompute
              compatibility/feasibility. Silent AUTO driver mutation is
              forbidden. Unsupported platforms may initially get guided
              vendor-approved operator remediation rather than automation.
              No promise to install every driver on every OS.
Why now:      Isolated package install is not kernel/driver administration.
              Commercial/non-technical readiness still needs a deliberate
              missing-driver behavior (validated automatic remediation
              and/or clear guided remediation).
To make real: An explicit privileged-remediation workflow outside
              VllmNativeProvisioner, with mandatory rediscovery after
              any host-wide change.
Retire when:  missing/insufficient driver behavior is an accepted
              pre-commercial product path with tests.
Status:       OPEN

### K-78 — Concurrent / background provisioning jobs
Label:        DEFERRED
Owner stage:  1.6C
Subsystem:    runtime / platform
Authorizes:   NO
Blocks 1.6C:  No
Current seam: `ProvisioningLock` serializes one control plane; INSTALLING
              returns conflict
What:         No job queue, progress, pause, or resume. Provision is
              synchronous. Duplicate INSTALLING is a conflict, not a
              second worker.
Why now:      A scheduler would hide failure and retry semantics.
To make real: A job contract that cannot authorize a different plan.
Retire when:  background provisioning is an accepted control-plane feature.
Status:       OPEN

### K-79 — Signed runtime artifacts / supply-chain verification
Label:        DEFERRED
Owner stage:  1.6C
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6C:  No
Current seam: installer report path + SHA-256 of the report bytes
What:         Provenance is the pip install report and package metadata.
              There is no signature verification of wheels or indexes.
Why now:      First proof is isolated install + metadata version.
To make real: Signed artifacts and index policy as commercialization
              hardening, without making PyPI the semantic owner.
Retire when:  signed runtime artifacts are an accepted security control.
Status:       OPEN

### K-80 — Richer recommendation scoring
Label:        DEFERRED
Owner stage:  later planning
Subsystem:    runtime / planning
Authorizes:   NO
Blocks 1.6C:  No
Current seam: 1.6E uses hard gates + 1.6B lexicographic rank + reuse
              of the same fresh VERIFIED candidate identity. No
              weights. RuntimeResolver ranking remains static (K-56).
What:         Explainability, confidence fusion, benchmark
              performance, expected throughput/latency, catalog-size
              scores, learned reliability, and cost optimization.
Why now:      Those inputs are not yet trustworthy. Pretending to
              score them would collapse verification into ranking.
To make real: After measured evidence exists. Link K-56 and K-62
              rather than duplicating them. Do not add
              FoundationCandidate or SelectionFramework debt.
Retire when:  a later stage accepts scored recommendations with tests.
Status:       OPEN

### K-81 — Override governance
Label:        DEFERRED
Owner stage:  later platform / identity
Subsystem:    platform / audit
Authorizes:   NO
Blocks 1.6C:  No
Current seam: 1.6E persists AUTO|MANUAL with recommended ≠ selected.
              Override reason, actor provenance, expiry, and
              two-person approval do not.
What:         Operator-supplied override reason, mandatory reasons for
              sensitive changes, approval workflows beyond existing
              meaningful-action approval, override expiry, richer audit.
Why now:      The selection identity exists; governance UX can wait.
To make real: After operators need audited MANUAL reasons.
Retire when:  override governance is an accepted mutating workflow.
Status:       OPEN

### K-82 — Return-to-AUTO selection mode
Label:        WORKING
Owner stage:  1.6E
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6C:  No
Current seam: `FoundationSelectionService.select_auto` persists AUTO,
              follows the current recommendation, and marks
              downstream_stale when the selected identity changes.
              Richer actor/reason history remains K-81.
What:         Removing a manual constraint and returning to AUTO.
Why now:      1.6E requires return-to-AUTO without silent execution
              of another foundation.
To make real: Already implemented for foundation selection.
Retire when:  1.6E T0 covers return-to-AUTO (this file closes with
              that test).
Status:       CLOSED

### K-83 — Generic selection / dependency-graph engine
Label:        DEFERRED
Owner stage:  later
Subsystem:    planning / platform
Authorizes:   NO
Blocks 1.6C:  No
Current seam: Control plane coordinates when; domains own how
What:         No `SelectionFramework<T>`, reactive dependency engine,
              scoring DSL, or configuration optimizer. Incremental
              recomputation, impact previews, and automatic plan-repair
              are also out.
Why now:      Generalizing before two concrete domains share behavior
              would erase domain validation semantics.
To make real: After runtime selection and runtime-aware model selection
              both exist and duplication is measured.
Retire when:  a shared value object is justified by implemented domains.
Status:       OPEN

### K-84 — Override and recommendation analytics
Label:        DEFERRED
Owner stage:  later analytics
Subsystem:    analytics
Authorizes:   NO
Blocks 1.6C:  No
Current seam: UsageEvent / AuditEvent exist; recommendation-vs-selection
              telemetry does not
What:         Acceptance rate, override frequency, override outcomes,
              headroom-risk analytics, team/org override patterns.
Why now:      Nothing is selected from a verified feasible set yet.
To make real: After bounded selection exists and privacy boundaries for
              this telemetry are explicit.
Retire when:  recommendation-versus-selection telemetry is accepted.
Status:       OPEN

### K-85 — Organisational preference policies
Label:        DEFERRED
Owner stage:  later policy
Subsystem:    policy / planning
Authorizes:   NO
Blocks 1.6C:  No
Current seam: SelectionPolicy is utilization-band bounds, not org taste
What:         Organisation, team, application, or department defaults
              and configurable recommendation priorities.
Why now:      Milestone 1 must not grow a preference hierarchy.
To make real: After bounded AUTO/MANUAL exists on verified paths.
Retire when:  preference policy is an accepted, non-authorizing input.
Status:       OPEN

### K-86 — DeploymentPlan freshness / stale-plan seam  ·  RETIRED
Label:        DEFERRED → RETIRED
Owner stage:  1.6I
Subsystem:    planning
Authorizes:   NO
Blocks 1.6C:  No
Current seam: Authoritative `DeploymentPlan` is the host-scoped current
              deployment decision. GET overlays CURRENT vs STALE vs
              UNAVAILABLE from `plan_basis`. Recommended vs selected
              provenance is recorded; MANUAL is not replaced.
What:         VALID vs STALE/REQUIRES REPLAN when host, runtime, model,
              capacity, or policy inputs change after plan generation.
              Recommendation vs selected provenance on the plan.
Why now:      Closed 1.6H produced bounded ModelSelection.
To make real: Implemented in Stage 1.6I.
Retire when:  plan invalidation/versioning has tests.
Status:       RETIRED (1.6I, 2026-09-08)
Note:         Full plan history / version graph is out of scope.
              Acquisition, ResourceManager, and InferenceInstance still
              do not consume DeploymentPlan; that is the next-stage
              ledger, not a duplicate K-86.

### K-87 — Eligible-model view vs global catalog  ·  RETIRED
Label:        DEFERRED → RETIRED
Owner stage:  1.6F
Subsystem:    runtime / model / planning
Authorizes:   NO
Blocks 1.6C:  No
Current seam: `EligibleModelView` is the authoritative runtime/model
              compatibility path for the selected verified foundation.
              Catalog metadata is not stamped. Inventory is not mutated.
What:         Host/runtime-specific eligible, blocked, and unresolved
              model views, recomputed from FoundationSelection +
              installation + fresh VERIFIED RuntimeCapabilityProfile.
Why now:      Closed 1.6E produced the selected verified path.
To make real: Implemented in Stage 1.6F.
Retire when:  the eligible view is the only runtime/model compatibility
              authority (planning no longer intersects catalog runtimes).
Status:       RETIRED (1.6F, 2026-09-08)
Note:         Resource-fit / ModelRequirement / Capacity migrated in
              1.6G. ModelSelector and bounded ModelSelection migrated
              in 1.6H. Authoritative DeploymentPlan migrated in 1.6I.

### K-88 — Runtime verification scheduling / background revalidation
Label:        DEFERRED
Owner stage:  later runtime
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6D:  No
Current seam: Verification runs only on an explicit POST/CLI/Console
              action. GET may present STALE. Startup does not probe.
What:         Periodic or event-driven re-verification of installed
              runtimes.
Why now:      Milestone 1 needs an explicit verify path, not a scheduler.
To make real: After 1.6D/1.6E, if operators need automatic refresh.
Retire when:  scheduled revalidation has tests and does not auto-kill
              running workloads.
Status:       OPEN

### K-89 — Deep / model-backed runtime qualification
Label:        DEFERRED
Owner stage:  later runtime / inference
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6D:  No
Current seam: 1.6D verifies import, backend, and a tiny accelerator
              operation. No model is loaded.
What:         Engine initialization or validation workloads against a
              real model beyond host/backend verification.
Why now:      Model loading mixes architecture, format, quantization,
              acquisition, and capacity into verification.
To make real: After first real inference; keep model eligibility separate.
Retire when:  a later stage owns model-backed runtime qualification.
Status:       OPEN

### K-90 — Empirical capability-matrix characterization
Label:        DEFERRED
Owner stage:  later runtime intelligence
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6D:  No
Current seam: RuntimeCapabilityProfile has no quantization, context,
              concurrency, or model-family fields.
What:         Empirical qualification of quantization/context/concurrency
              /model-family combinations on a verified runtime.
Why now:      1.6D verifies the runtime, not every model it might serve.
To make real: Combine descriptor + verified profile + model metadata.
Retire when:  eligibility consumes an empirical matrix rather than
              declared support alone.
Status:       OPEN

### K-91 — Container runtime verification
Label:        DEFERRED
Owner stage:  later execution / runtime
Subsystem:    runtime / execution
Authorizes:   NO
Blocks 1.6D:  No
Current seam: First product verifier is native-process vLLM. K-75 covers
              containerized provisioning.
What:         Real vLLM verification through ContainerExecutor including
              GPU exposure.
Why now:      1.6D proves the native path. Container GPU attach is later.
To make real: After container provisioning (K-75) exists on a real host.
Retire when:  a container verifier has L2 evidence.
Status:       OPEN

### K-92 — Verification evidence history / attestation
Label:        DEFERRED
Owner stage:  later runtime / audit
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6D:  No
Current seam: One current profile per installation. Failed/stale details
              are bounded on that record.
What:         Immutable historical attempts, signatures, attestations,
              richer audit of every verify.
Why now:      MVP seam needs current status, not an evidence ledger.
To make real: When operators need attempt history beyond last outcome.
Retire when:  historical verification records have tests.
Status:       OPEN

### K-93 — Multi-host verification orchestration
Label:        DEFERRED
Owner stage:  later fleet
Subsystem:    runtime / platform
Authorizes:   NO
Blocks 1.6D:  No
Current seam: Profiles are host-scoped. K-60 covers multi-host
              resolution.
What:         Orchestrating verification across a fleet of hosts.
Why now:      Milestone 1 is a single reference host.
To make real: After multi-host runtime resolution (K-60) is in play.
Retire when:  fleet verification is an accepted control-plane path.
Status:       OPEN

### K-94 — Planning CompatibilityVerdict composition shim  ·  RETIRED
Label:        PROVISIONAL → RETIRED
Owner stage:  1.6G
Subsystem:    platform / planning
Authorizes:   NO
Current seam: Product ranking, admission, and isolated `evaluate()`
              always receive an explicit `CompatibilityVerdict`.
              Missing mapping is `UNRESOLVED`, never `COMPATIBLE`.
              Estimator runtime identity is the selected verified
              foundation, never `supported_runtimes[0]`.
              `platform.eligibility` still copies EligibleModelView
              statuses into planning tokens because `planning` cannot
              import `runtime`. That copy is the composition root, not
              a compatibility default.
What:         Remove omit-mapping COMPATIBLE defaults and the catalog
              runtime-hint estimator path.
Why now:      1.6G remaps ModelRequirement and Capacity.
To make real: Implemented in Stage 1.6G.
Retire when:  no product path defaults missing eligibility to COMPATIBLE,
              and estimator identity is the selected runtime.
Status:       RETIRED (1.6G, 2026-09-08)
Note:         `plan_for_entry` still estimates numeric ResourceRequest
              amounts for the residual artifact-id reservation path
              (`POST /resources/reservations?artifact_id=`). That path
              is not InferenceInstance authority and is not normal
              deployment execution. Normal deployment admission uses
              `request_from_plan`. Removal trigger: retire the
              artifact-id reservation API.

### K-95 — vLLM serving deferred depth
Label:        DEFERRED
Owner stage:  1.6L
Subsystem:    runtime / inference
Authorizes:   NO
What:         The first native vLLM vertical does not implement
              streaming, request cancellation, automatic crash
              recovery, request queues/backpressure, richer
              concurrency controls, advanced health/reconciliation,
              harder-than-runtime GPU memory enforcement, or richer
              inference observability. Prompts and responses stay
              transient. Baseline mapping of admitted VRAM into vLLM
              `--gpu-memory-utilization` is in Stage 1.6L; that flag is
              a runtime budget control, not a kernel cgroup limit.
Why now:      One bounded prompt → generated text path is the product
              proof. Those depths are not required to close 1.6L.
To make real: Later stages that own each concern separately.
Retire when:  the named depth is an accepted stage output.
Status:       OPEN

### K-96 — llmfit plan minimum is not native vLLM serving demand
Label:        PROVISIONAL
Owner stage:  1.6L
Subsystem:    adapters / estimators
Authorizes:   NO
What:         Captured `llmfit plan` for Qwen2.5-7B-Instruct-AWQ at
              context 8192 reports a minimum of about 4.75 GiB VRAM
              (fp16 KV 0.4375 GiB). Native vLLM serving needs weights,
              KV for the requested context, runtime overhead, optional
              activation, and engine/workspace remainder. The llmfit
              adapter therefore refines plan components through Kultrun
              vLLM composition (overhead treated as 0 so the engine
              workspace is not double-counted) rather than authorizing
              the plan minimum as the serving total. AUTO does not
              shop llmfit versus Kultrun and pick the larger. Strict
              llmfit stays unresolved on typed provider failure.
              llmfit `minimum.vram` is base-model evidence; KV and
              runtime-extra are composed separately. Measured
              RuntimeMemoryProfile calibration is the vLLM Available
              gate; it is not an advisory overlay on static membership.
              The first post-calibration fresh-host T3 proved calibrated
              bytes through plan, ResourceRequest, and reservation, and
              launched a healthy vLLM process, but Kultrun did not
              persist RUNNING. That start-completion defect is fixed
              locally; it does not close this entry.
Why now:      Fresh-host T3 admitted 8.0 GiB from the packaged Kultrun
              total after llmfit was unavailable; the runtime then
              lacked KV for context 8192. Do not hard-code that host's
              observed remainder. Root cause of that 8 GiB figure was
              catalog `estimated_vram_gib=8.0` used when llmfit was
              absent, not a mapped llmfit field.
To make real: Measured highest-pressure vLLM runtime-memory
              calibration is now the Available gate (this
              continuation). Close K-96 when a new GPU host (not
              `216.81.151.62`) proves READY using the calibrated
              serving total, not the disproven static 10.37 GiB
              figure. Local lineage tests are not closure.
Retire when:  that serving total is the product estimate for vLLM
              after real T3, or llmfit is dropped for this runtime
              family.
Status:       OPEN

### K-97 — exhaustive Hub listing and remote ranking
Label:        DEFERRED
Owner stage:  1.6L
Subsystem:    adapters / model_source
Authorizes:   NO
What:         Remote discovery is a bounded injectable listing seam.
              There is no Hub pagination optimizer, large-scale search
              ranking, or distributed metadata cache. Absence of a vLLM
              app tag does not drop a curated catalog model.
Why now:      Stage 1.6L needs the funnel order, not Hub ingest.
To make real: A later catalog-ingest stage with explicit pagination,
              ranking, and cache policy.
Retire when:  that ingest is an accepted stage output.
Status:       OPEN

### K-98 — live Accelerate skeleton analysis
Label:        DEFERRED
Owner stage:  1.6L
Subsystem:    adapters / model_source
Authorizes:   NO
What:         `AccelerateStructuralProvider` may run empty-skeleton
              analysis when `model_source_mode=live` and the optional
              `analysis` extra is installed. Product default remains
              offline and does not import torch/transformers/accelerate.
              The analyzer uses `init_empty_weights` and never
              `load_checkpoint_and_dispatch` or silent
              `trust_remote_code=True`. When Safetensors already
              resolved the cheap bound, Accelerate is not invoked.
              Accelerate never marks a model AVAILABLE; vLLM feasibility
              remains ModelRequirement vs CurrentCapacitySnapshot.
Why now:      Torch + Transformers + Accelerate are not control-plane
              dependencies. Offline T2 must not require them.
To make real: Drop the extra, or a later stage that treats structural
              placement as a documented cheap input without expanding
              Accelerate into a selector.
Retire when:  that policy is an accepted stage output, or the extra
              is dropped.
Status:       OPEN

### K-99 — native process capture files are not rotated
Label:        DEFERRED
Owner stage:  1.6L
Subsystem:    execution
Authorizes:   NO
What:         `NativeProcessExecutor` writes child stdout/stderr to
              unlinked anonymous files and copies only an
              `output_limit_bytes` prefix into the handle. A long-running
              serving process can grow those inodes until it exits.
              There is no rotation, retention, or operator log surface.
Why now:      The launching CLI must not stay resident to drain pipes.
              Rotation/retention would be a logging platform, outside
              Option 2 of the capture-lifetime fix.
To make real: executor-owned bounded logs with rotation, or a durable
              supervisor that owns capture across control-plane
              restarts.
Retire when:  a later stage owns process logs or durable supervision.
Status:       OPEN

### K-100 — Windows physical storage probes
Label:        DEFERRED
Owner stage:  1.6L3
Subsystem:    storage
Authorizes:   NO
What:         `GetDiskFreeSpaceExW` is implemented as a native-class
              source (live only on win32). NTFS quota is not parsed.
              L2 on a Windows host is not done.
Why now:      Linux/POSIX is the reference path; Windows coverage is
              architectural.
To make real: NTFS quota adapter plus L2 on a Windows deployment target.
Retire when:  Windows is a supported deployment target with L2 evidence.
Status:       OPEN

### K-101 — macOS physical APFS/quota probes
Label:        DEFERRED
Owner stage:  1.6L
Subsystem:    storage
Authorizes:   NO
What:         `MacosCapacityProbe` is fixture-tested. Native source is
              `statvfs`. `F_PREALLOCATE` remains **K-28**.
Why now:      Developer Macs must not be treated as verified entitlements.
To make real: APFS/quota adapter plus genuine reservation primitive.
Retire when:  macOS is a supported deployment target.
Status:       OPEN

### K-102 — filesystem-specific quota parse (XFS/ZFS/Btrfs)
Label:        DEFERRED
Owner stage:  1.6L3
Subsystem:    storage
Authorizes:   NO
What:         linux-quota now parses classic `quota -w` user/group
              remaining (1 KiB blocks). XFS project quota and Btrfs
              qgroups are not parsed. ZFS dataset quota is a separate
              P0 adapter (fixture L1); physical ZFS L2 is not done.
Why now:      Optional tools must not become mandatory; fail closed.
To make real: XFS project and Btrfs qgroup parsers when those hosts exist.
Retire when:  a stage owns remaining filesystem-specific quota depth.
Status:       OPEN

### K-103 — NFS rquota numeric parse
Label:        DEFERRED
Owner stage:  1.6L
Subsystem:    storage
Authorizes:   NO
What:         NFS probe is a seam; helper presence is not a quota figure.
Why now:      rquota tooling is optional and often GPL.
To make real: Numeric rquota adapter, still optional.
Retire when:  NFS deployments need authorizing probe bytes.
Status:       OPEN

### K-104 — SMB/CIFS quota adapter
Label:        DEFERRED
Owner stage:  1.6L
Subsystem:    storage
Authorizes:   NO
What:         SMB/CIFS is identified as non-credible; no bytes probe.
Why now:      Not on the reference path.
To make real: Optional SMB quota adapter.
Retire when:  a customer deployment needs it.
Status:       OPEN

### K-105 — MooseFS mfsgetquota numeric parse
Label:        DEFERRED
Owner stage:  1.6L3
Subsystem:    storage
Authorizes:   NO
What:         `mfsgetquota -n` is parsed (realsize, then size, then
              length). Missing binary is a typed miss. Physical L2 on
              a host that has `mfsgetquota` is not done.
Why now:      GPL tooling is never bundled; live table layout may still
              differ from fixtures.
To make real: L2 on a MooseFS host with the optional client tools.
Retire when:  MooseFS is a supported storage backend with L2 evidence.
Status:       OPEN

### K-106 — CephFS / Ceph quota adapter
Label:        DEFERRED
Owner stage:  1.6L3
Subsystem:    storage
Authorizes:   NO
What:         `ceph.quota.max_bytes` xattr walk is implemented. Physical
              CephFS L2 is not done. Cluster-free is not an entitlement.
Why now:      P0 fixture path; not a live Ceph deployment.
To make real: L2 on a CephFS volume with directory quota.
Retire when:  a stage owns Ceph deployments with L2 evidence.
Status:       OPEN

### K-107 — Kubernetes CSI/PVC quota
Label:        DEFERRED
Owner stage:  1.6L
Subsystem:    storage
Authorizes:   NO
What:         Overlay is treated as credible container-local storage.
              CSI volumes need provider/PVC facts.
Why now:      Host mounts are the v1 topology.
To make real: Kubernetes-aware evidence adapter, still not semantic owner.
Retire when:  multi-node/K8s placement is in scope.
Status:       OPEN

### K-108 — cloud/provider quota adapters
Label:        DEFERRED
Owner stage:  1.6L
Subsystem:    storage
Authorizes:   NO
What:         Provider configured quota (RunPod, cloud disks) is an
              architectural source, not implemented as an adapter.
Why now:      Core must not contain provider logic.
To make real: Replaceable provider evidence adapters + internal fallback.
Retire when:  a named provider is a supported deployment target.
Status:       OPEN

### K-109 — shared model warehouse / cache relocation / migration
Label:        DEFERRED
Owner stage:  1.6L
Subsystem:    storage / model
Authorizes:   NO
What:         No content-addressed warehouse, NVMe cache relocation,
              or storage migration. Install cache is `--no-cache-dir`.
Why now:      Ownership and truthful capacity come first.
To make real: Managed reusable cache with ownership and pool binding.
Retire when:  a later stage owns warehouse/cache policy.
Status:       OPEN

### K-110 — bounded 10% storage replan loop
Label:        CLOSED (superseded)
Owner stage:  1.6L / 1.6L5
Subsystem:    platform / planning / storage
Authorizes:   NO
What:         Formerly `storage.reduction` multiplicative 10% footprint
              ceilings (100/90/81/72.9, integer floor, max 3).
              1.6L5 replaced the executable policy with universal 20%×5
              (100/80/64/51.2/40.96/32.768, original plus five reductions)
              in `storage.reduction` and `platform.storage_replan`.
              The loop still sequences rediscovery, Available Models
              recompute, AUTO reselection of a real smaller candidate,
              a new DeploymentPlan basis, and dry-run ResourceManager
              admission. MANUAL is blocked with alternatives. Unresolved
              capacity is last-resort manual evidence, not a reduction.
              Low-space and non-capacity failures do not reduce.
Why now:      Helper-only 30% policy could not recompute the control
              plane. The 10% loop unblocked control-plane replan; the
              approved G-REPL schedule is now the running policy.
To make real: Physical T3 on constrained storage after a frozen
              integration wheel. Not this task.
Retire when:  local tests prove the 20%×5 loop; physical proof is later.
Status:       CLOSED. Executable 10%×3 behavior removed in 1.6L5.
Evidence:     `tests/test_storage_reduction.py`,
              `tests/test_storage_replan.py`; composition in
              `src/kultrun/platform/storage_replan.py`.

### K-111 — Storage Capacity V2 remainder (manual, G-REPL)
Label:        PARTIAL
Owner stage:  1.6L5 / 1.6L4b
Subsystem:    storage / planning
Authorizes:   NO
What:         1.6L2 persist, 1.6L3 P0 specialist parsers, 1.6L4
              Sonar V2, 1.6L4a specialist corroboration, 1.6L5 last-resort
              `AdministratorCapacityBound` (`sca_*`; CLI/API
              `storage capacity set` / POST `/storage/administrator-bound`)
              and executable G-REPL 20%×5 exist locally. 1.6L4b binds
              each empirical probe to the StoragePool it claims and
              hardens reserve-first EDQUOT/ENOSPC recovery locally.
              Remaining: physical specialist validation; physical Sonar L2
              on a FUSE/quota host after the 1.6L4b artifact (duration on
              FUSE; tests must not write production GiB); optional later
              >256 GiB Sonar exploration. The V2 256 GiB ceiling is not a
              reason to distrust a specialist above 256 GiB.
              Physical defect found on runtime-breadth acceptance
              (`36820d7` wheel): overlay Sonar wrote under `/workspace`
              (`probe_workspace=state_root`); EDQUOT ~47 GiB did not
              finish as CAPACITY or clean owned probe/reserve.
Why now:      Specialist + Sonar unblock truthful FUSE numbers.
              Manual is only when capacity itself is unresolved.
To make real: Physical L2 in
              `docs/investigations/STORAGE-RUNTIME-BREADTH-SEQUENCE.md`.
              Do not implement `required_bytes *= 0.8`. Do not ask for
              a larger manual number after a failed fit. Do not claim
              physical Sonar closed from local tests.
Retire when:  physical Sonar/specialist gates close, or 1.6L5's local
              remainder is split into a later debt item.
Status:       OPEN remainder is physical validation, not the local
              last-resort / G-REPL / pool-binding path.

### K-112 — llama.cpp and MLX are declared, not executable
Label:        DEFERRED
Owner stage:  1.6R0 / later Track R
Subsystem:    runtime
Authorizes:   NO
What:         1.6R0 registers llama.cpp and MLX as FUTURE support
              descriptors. AUTO excludes them. `is_provisionable` is
              false. Launch, provision, verify, and inference refuse.
              vLLM remains the only product-executable foundation.
Why now:      The architecture must name the families without faking
              support. Product preference and the one-active invariant
              need those names.
To make real: R1 llama.cpp CPU (provisioner, verifier, GGUF, launch);
              then R4 MLX on Apple Silicon. Do not mark PRODUCT until
              verification exists.
Retire when:  each family has a verified executable path and physical
              acceptance on its intended host class.
Status:       OPEN

### K-113 — vendor cloud telemetry export is a seam, not a service
Label:        DEFERRED
Owner stage:  9.1–9.2
Subsystem:    vendor
Authorizes:   NO
What:         `config.vendor` and `ProductTelemetryExporter` exist.
              Default is disabled. The only adapter is a no-op.
              Enabling the section does not send anything off-host.
              Deployment never depends on export. Local operational
              facts remain in `platform.OperationalFact`.
              `sanitize_fact` is the privacy boundary: exact paths,
              hostnames, PIDs, prompts, responses, and token counts
              are not in `TelemetryRecord`. Token counts stay local.
              No cloud ingestion API exists (this entry).
Why now:      Physical acceptance and Admin diagnostics need a product
              journal now. A cloud ingestion service is not required to
              close the installation → inference vertical.
To make real: a real exporter adapter, consent/privacy review, and
              the vendor ingestion service. Never include prompts,
              responses, documents, or named personal content.
Retire when:  Stage 9.x implements outbound product telemetry with
              an air-gapped default that still works.
Status:       OPEN

### K-114 — unnamed unique-SAFE storage remains for diagnostic callers
Label:        WORKING
Owner stage:  1.6L / closing the vertical
Subsystem:    storage / model / planning
Authorizes:   NO (unnamed multi-pool stays unresolved)
What:         `safe_storage(envelope, None)` and unnamed
              `deployment_capacity` still resolve when **exactly one**
              pool has resolved SAFE. Consume paths (runtime plan,
              calibration acquire, Available Models, DeploymentPlan,
              ResourceRequest) pass an explicit `StoragePool` mount
              derived from `state_root`. Several resolved SAFE pools
              stay unresolved unless named.
              Remaining unnamed callers: `SelectionService.recommend`
              (isolated ranking; unused on the product path),
              `assess_entry` when capacity is omitted, and
              `plan_from` (non-authoritative recommendation projection).
Why now:      Cheap diagnostic reads (`kultrun host`, some tests)
              should not invent a destination. The physical defect
              was consume-path callers omitting the mount they already
              knew.
To make real: not required. The unique-pool heuristic is intentional
              for unnamed diagnostics. Product consume paths pass a
              mount derived from `state_root`.
Retire when:  every remaining unnamed caller is classified as
              diagnostic, or the heuristic is removed after an audit.
Status:       OPEN

### K-115 — Product reclaim on a blocking host still unproven
Label:        WORKING
Owner stage:  1.6L bounded pre-llama.cpp closure
Subsystem:    storage / platform / vendor
Authorizes:   NO
What:         Lifecycle cleanup of cleanup-eligible dual-owned state is
              the product rule even when current SAFE already covers the
              peak (`cleanup_required_by_lifecycle` vs
              `cleanup_required_for_capacity`). Realize no longer copies
              `foundations[0]` into selected runtime. `unique_occupancy`
              must not let a weaker UNKNOWN ancestor hide stronger
              descendant artifacts. After actual reclaim, occupancy-
              conditional Sonar may re-run when SAFE still blocks.
              Customer-facing simplified deployment UX is not built.
              llama.cpp / MLX remain FUTURE (K-112). Do not merge to
              authoritative `kultrun` from this closure.
Why now:      The previous closure inventoried 5.9 GiB reclaimable
              sibling models and skipped delete because SAFE fitted.
Physical:     host_4abec3f2e600e339 / drun_c84d8a065b69bbf9.
              Product classified 19.5 GiB sibling models/runtimes as
              CLEANUP ELIGIBLE and deleted them (no operator `rm`).
              Trigger on this host was `cleanup_required_for_capacity`
              (authorizing 16 GiB < 24 GiB peak), not lifecycle-only.
              After delete, min still failed until occupancy-conditional
              Sonar raised authorizing to 32 GiB. Guided report at
              `b12ce09` answers the journey: Layer 2 19.5 GiB reclaimed;
              Layer 3 realize PASS vs post-install remaining; Layer 5
              selected `vllm/native-process` FEASIBLE not FILTERED.
To make real: a host where SAFE already covers peak and reclaimable
              siblings still exist, if lifecycle-only always-clean
              must be proven separately from the blocking-host path.
Retire when:  product-owned reclaim + recharacterization are accepted
              for this host class, and any remaining lifecycle-only
              proof is either captured or explicitly deferred.
Status:       PHYSICALLY CLOSED for blocking-host reclaim,
              occupancy-conditional Sonar, and guided report.
              Lifecycle-only (SAFE already covers peak) not exercised
              on this host.

Stop of a serving process continues to release the GPU process while
leaving `ResourceReservation` ACTIVE for restart. That is the product
contract, not a gap. Process identity stays in `execution`;
ResourceManager must not grow lifecycle logic.

## Runtime-first migration ledger (after 1.6K)

Not a second architecture. Existing components still to migrate, in
order. Do not begin automatically.

| Component | CURRENT INPUT | TARGET INPUT | WHAT MUST MIGRATE | SHIM | ORDER |
|---|---|---|---|---|---|
| Runtime/model compatibility | `EligibleModelView` / `RuntimeEligibleModelCandidate` | same | done in 1.6F | composition copy of eligibility → `CompatibilityVerdict` (planning ⟂ runtime) | ✅ |
| ModelRequirement | `RuntimeEligibleModelCandidate` + fresh VERIFIED profile + selected runtime | same | done in 1.6G | none | ✅ |
| CapacityAssessment | remapped `ModelRequirement` + current available (`ResourceSummary` = SAFE minus ACTIVE) | same | done in 1.6G; 1.6L binds snapshot instead of SAFE-only | none | ✅ |
| ModelSelector | `AvailableModelView` members only (`FeasibleModelCandidate[]` ranked inside that set) | same | done in 1.6H ranking; 1.6L binds Available Models first | `SelectionService.recommend()` isolated tests only | ✅ |
| Bounded model selection | host-scoped `ModelSelection` AUTO\|MANUAL; recommended ≠ selected | same | done in 1.6H | none | ✅ |
| Authoritative DeploymentPlan | current foundation + VERIFIED runtime + ModelSelection + READY requirement + feasible capacity | same | done in 1.6I; CURRENT vs STALE from `plan_basis` | `plan_from` demoted (`plan_authoritative: false`) for recommendation display | ✅ |
| Acquisition | CURRENT DeploymentPlan identity for normal executable acquire; STORE_ONLY catalog path preserved | same | done in 1.6J | STORE_ONLY remains plan-independent | ✅ |
| ResourceManager | `ResourceRequest` from `DeploymentPlan.resource_request` + exact artifact_id | same | done in 1.6J; ResourceManager stays generic | `plan_for_entry` residual on artifact-id reserve only; not instance authority | ✅ |
| InferenceInstance | `DeploymentPlan` + exact `ModelArtifact` + matching `ResourceReservation` | same | done in 1.6K; settings from plan | low-level `InstanceService.create` remains a test helper | ✅ |
| Real vLLM serving | selected foundation + acquired artifact + reservation + real `RuntimeLaunchSpec` | same | done in 1.6L T0/T1/T2; exact installation; local artifact; loopback; readiness | none | ✅ T5 physical `ba04df2` |
| Real inference | generic `InferenceRequest` / `InferenceResponse` through instance API/CLI | same | done in 1.6L T0/T1/T2; T5 physical restart vertical `ba04df2` | reference-serving remains fixture-only | ✅ |

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

`Fixture` is tracked separately again, because a captured fixture proves
only that current code still understands evidence from that machine — never
that the code works on it today. `docs/TESTING_STRATEGY.md` explains the
distinction; `tests/fixtures/hosts/shapes.json` is the machine-readable
index, kept honest by `tests/test_shape_registry.py`.

### DC-01 — Apple Silicon / macOS

**Revisited at Stage 1.1** — not captured. No Apple host was available and
the brief made the shape non-blocking. Trigger unchanged.
Fixture:         none. Capture is the cheapest useful step and needs no Apple provider
Architecture:    ARCHITECTURE-READY
Implementation:  ADAPTER-NOT-IMPLEMENTED (MLX is a FUTURE declaration in 1.6R0, not executable)
Evidence:        none; may be captured opportunistically, **not Stage 1.1 blocking**
Seam:            `HostDiscoveryProvider`, plus a runtime/executor adapter when inference is wanted
Unproven:        whether a general provider reports enough on Darwin; unified-memory
                 normalization against a real machine; any Apple runtime path
Downstream redesign expected: NO
Revisit:         after physical vLLM acceptance through 1.6R0, then MLX implementation

### DC-02 — CPU-only hosts

**Revisited at Stage 1.1** — not captured on real hardware. Partially
covered by a regression test built from the reference host's ASPEED
management VGA, which is the device that would have produced a phantom
accelerator on a CPU-only machine. Real-hardware confirmation still owed.
Fixture:         none. Partial: the ASPEED regression built from the reference host
Architecture:    ARCHITECTURE-READY
Implementation:  ADAPTER-NOT-IMPLEMENTED
Evidence:        none; may be captured opportunistically, **not Stage 1.1 blocking**
Seam:            `HostDiscoveryProvider`, plus runtime and model selection
Unproven:        the zero-accelerator path against a real machine; a CPU-capable runtime
Downstream redesign expected: NO
Revisit:         after the first live inference vertical, or when CPU-only serving
                 becomes a product priority

### DC-03 — AMD / ROCm
Fixture:         MI300X / MI300A `amd-smi` JSON fixtures in Machi 2.3
Architecture:    ARCHITECTURE-READY
Implementation:  ADAPTER-IMPLEMENTED for Discover (`AmdAcceleratorProvider`);
                 runtime/ROCm serving not implemented
Evidence:        physical MI300X Discover PASS on SHA `eaee5c98…`
                 (`erun_7ef504e9f5b47d94`) after host PyYAML remediations
                 for stock `amd-smi`; XCP/SR-IOV/consumer still unproven
Seam:            Machi Discover via `amd-smi` JSON. No `rocm-smi`, sysfs/DRM,
                 or `amdsmi` SDK. Capacity/runtime remain later
Unproven:        XCP/partition; SR-IOV; consumer Radeon/iGPU coverage;
                 serving on ROCm
Downstream redesign expected: NO for Discover contract; Capacity must not
                 treat unified HBM as dedicated VRAM
Revisit:         remaining AMD classes (XCP, SR-IOV, consumer); serving on ROCm

### M-2.3-01 — AMD XCP / partition topology
Label:        DEFERRED
Owner stage:  2.3
Subsystem:    discover / amd
Authorizes:   NO
What:         Compute-partition / XCP hierarchy is not modeled.
Why now:      First MI300X POC is one visible GPU per `amd-smi` GPU entry.
To make real: explicit physical/logical topology contract after empirical
              partition output exists
Retire when:  a validated host exposes partitions that Discover must name
Status:       OPEN

### M-2.3-02 — AMD SR-IOV
Label:        DEFERRED
Owner stage:  2.3
Subsystem:    discover / amd
Authorizes:   NO
What:         SR-IOV virtual functions are not enumerated.
Why now:      Not required for the first physical MI300X server.
Retire when:  a deployment needs VF-visible identity
Status:       OPEN

### M-2.3-03 — AMD fallback sources
Label:        DEFERRED
Owner stage:  2.3
Subsystem:    discover / amd
Authorizes:   NO
What:         No `rocm-smi`, sysfs/DRM, PCI vendor scan, or Python `amdsmi`.
Why now:      Missing `amd-smi` must stay `unavailable`, not a guessed zero.
Retire when:  a supported host has GPUs but no `amd-smi` and product policy
              accepts a second source
Status:       OPEN

### M-2.3-04 — Command output size limit
Label:        DEFERRED
Owner stage:  2.3
Subsystem:    discover / command
Authorizes:   NO
What:         `run_command` does not bound stdout size.
Why now:      Ordinary NVIDIA CSV and AMD JSON for ≤64 devices is small.
              Silent truncation would be worse than the current bound.
Retire when:  a generic fail-closed output cap is tested against real
              multi-GPU JSON
Status:       OPEN

### M-2.3-05 — Broader AMD Radeon / iGPU coverage
Label:        DEFERRED
Owner stage:  2.3
Subsystem:    discover / amd
Authorizes:   NO
What:         Consumer Radeon and typical iGPUs are not claimed as covered.
Why now:      First server target is MI300X; generic devices may still parse.
Retire when:  a product requirement names those SKUs
Status:       OPEN

### M-2.3-06 — Vendor CLI prerequisite readiness
Label:        DEFERRED
Owner stage:  PrerequisiteReadiness (after 2.3 close)
Subsystem:    readiness / environment
Authorizes:   NO until that component exists
What:         Stock ROCm images can ship `amd-smi` that fails solely
              because PyYAML is missing. 2.3 Discover stays read-only;
              lab remediations installed PyYAML on the host interpreter
              only. The product still lacks a generic inspect → diagnose
              → plan → optionally remediate under policy → verify path.
Why now:      2.3 proves observation given a functioning vendor CLI.
To make real: a non-PyYAML-specific PrerequisiteReadiness capability;
              Discover remains read-only
Retire when:  PrerequisiteReadiness is implemented at Tier 2 and can
              diagnose this class without special-casing yaml
Status:       RETIRED (2.5.1, 2026-09-21)

### M-2.5-01 — Privileged driver installation
Label:        DEFERRED
Owner stage:  PrerequisiteReadiness Tier 3 / pre-commercial
Subsystem:    readiness / drivers
Authorizes:   NO
What:         Installing or replacing GPU drivers and kernel modules.
Why now:      Tier 2 remediates interpreter dependencies only.
Retire when:  a product requirement names privileged driver remediation
Status:       OPEN

### M-2.5-02 — Multiple remediation strategies
Label:        DEFERRED
Owner stage:  PrerequisiteReadiness Tier 3
Subsystem:    readiness
Authorizes:   NO
What:         Alternate strategies for one diagnosis (local wheel vs
              network vs managed cache vs OS package).
Why now:      One allowlisted interpreter-dependency action is enough.
Retire when:  a second strategy is required for a real adapter
Status:       OPEN

### M-2.5-03 — Remediation rollback
Label:        DEFERRED
Owner stage:  PrerequisiteReadiness Tier 3
Subsystem:    readiness
Authorizes:   NO
What:         Transactional undo of a prerequisite mutation.
Why now:      Failed mutation already fails closed and re-inspects.
Retire when:  a mutation that cannot be re-diagnosed needs undo
Status:       OPEN

### M-2.5-04 — Dependency graph / order
Label:        DEFERRED
Owner stage:  PrerequisiteReadiness Tier 3
Subsystem:    readiness
Authorizes:   NO
What:         Ordered multi-package / multi-target graphs.
Why now:      One allowlisted pin is the first instance, not a solver.
Retire when:  an adapter must remediate more than one ordered target
Status:       OPEN

### M-2.5-05 — Managed offline prerequisite artifact cache
Label:        DEFERRED
Owner stage:  PrerequisiteReadiness Tier 3
Subsystem:    readiness / air-gap
Authorizes:   NO
What:         Product-owned cache of prerequisite artifacts.
Why now:      Source kinds (network / local_artifact / managed_cache /
              unavailable) are represented; cache is not implemented.
Retire when:  air-gapped remediation is a required product path
Status:       OPEN

### M-2.5-06 — CUDA / ROCm full prerequisite preparation
Label:        DEFERRED
Owner stage:  PrerequisiteReadiness Tier 3 / Foundation
Subsystem:    readiness / runtime
Authorizes:   NO
What:         Installing complete CUDA or ROCm stacks.
Why now:      Out of Tier 2 mutation boundary.
Retire when:  Foundation or a later adapter requires stack preparation
Status:       OPEN

### M-2.5-07 — Cross-platform package-manager abstraction
Label:        DEFERRED
Owner stage:  PrerequisiteReadiness Tier 3
Subsystem:    readiness
Authorizes:   NO
What:         apt/dnf/brew/pip generic package-manager product.
Why now:      Would become a package-management platform.
Retire when:  architecture explicitly accepts that product expansion
Status:       OPEN

### M-2.5-08 — Organization policy templates
Label:        DEFERRED
Owner stage:  PrerequisiteReadiness Tier 3 / Admin
Subsystem:    readiness / policy
Authorizes:   NO
What:         Org-wide observe/plan/remediate templates.
Why now:      Invocation policy plus inspectable settings suffice.
Retire when:  Admin / command center consumes the typed settings
Status:       OPEN

### M-2.4-01 — Native quota specialists
Label:        DEFERRED
Owner stage:  Capacity / storage Tier 3
Subsystem:    discover / capacity
Authorizes:   NO
What:         Reading kernel quota (quotactl / project quota / FUSE
              quota) into hard/soft/usage bytes.
Why now:      2.4 records advertised-unread or unsupported status.
              Specialist reads belong with Capacity, not topology.
To make real: platform-specific quota adapters behind Capacity evidence.
Retire when:  Capacity consumes native quota evidence as a distinct
              layer from filesystem-reported free
Status:       OPEN

### M-2.4-02 — Storage Sonar / bounded capacity proving
Label:        DEFERRED
Owner stage:  Capacity 4.2
Subsystem:    capacity
Authorizes:   NO
What:         Empirical write-to-limit characterization of a pool.
Why now:      2.4 forbids fill-until-failure. A tiny probe is not Sonar.
To make real: pool-bound Sonar with admission-safe limits.
Retire when:  Capacity 4.2 ships and cannot treat reported free as SAFE
Status:       OPEN

### M-2.4-03 — FUSE-specific handlers
Label:        DEFERRED
Owner stage:  Capacity / storage Tier 3
Subsystem:    discover / capacity
Authorizes:   NO
What:         Per-FUSE-type classification and capacity semantics.
Why now:      2.4 classifies known FUSE names; unknown FUSE stays
              virtual/unknown.
Retire when:  a supported FUSE store is a product target
Status:       OPEN

### M-2.4-04 — Remote storage specialists
Label:        DEFERRED
Owner stage:  Capacity / storage Tier 3
Subsystem:    capacity
Authorizes:   NO
What:         NFS/CIFS/object-store capacity and identity specialists.
Why now:      2.4 classifies network mounts and does not benchmark them.
Retire when:  remote pools are a Capacity input
Status:       OPEN

### M-2.4-05 — Storage performance profiling
Label:        DEFERRED
Owner stage:  later
Subsystem:    capacity
Authorizes:   NO
What:         Throughput/latency of a mount.
Why now:      Out of scope for topology observation.
Retire when:  placement policy needs measured performance
Status:       OPEN

### M-2.4-06 — Automatic storage-root selection
Label:        DEFERRED
Owner stage:  later composition / Admin
Subsystem:    discover / install
Authorizes:   NO
What:         Choosing state/runtime/model roots from mount topology.
Why now:      2.4 does not infer roots from names. Setting exists empty.
Retire when:  composition consumes suitability plus Steward ownership
Status:       OPEN

### M-2.4-07 — Storage-placement optimization
Label:        DEFERRED
Owner stage:  Plan / optimizer later
Subsystem:    plan
Authorizes:   NO
What:         Optimizer placement across storage classes.
Why now:      Suitability is descriptive, not a recommendation engine.
Retire when:  Plan has a storage-placement consumer
Status:       OPEN

### M-2.4-08 — Storage cleanup / reclamation
Label:        DEFERRED
Owner stage:  Steward 3.3
Subsystem:    steward
Authorizes:   NO
What:         Reclaim of Machi-owned bytes.
Why now:      Discover is read-only. Probe cleanup is not reclaim.
Retire when:  Steward reclaim ships with dual proof
Status:       OPEN

### M-2.4-09 — Container-host backing reconciliation
Label:        DEFERRED
Owner stage:  Capacity / storage Tier 3
Subsystem:    discover / capacity
Authorizes:   NO
What:         Mapping overlay/container visible mounts onto host pools.
Why now:      2.4 records overlay class and namespace context only.
Retire when:  container deployments need host-pool identity
Status:       OPEN

### M-2.4-10 — Full quota exhaustion modeling
Label:        DEFERRED
Owner stage:  Capacity
Subsystem:    capacity
Authorizes:   NO
What:         Modeling EDQUOT vs ENOSPC as distinct remaining.
Why now:      Historical mismatch is a design constraint, not 2.4 logic.
Retire when:  Capacity can distinguish reported free from path-limited
              writable capacity
Status:       OPEN

### M-2.4-11 — Storage reservations
Label:        DEFERRED
Owner stage:  Admit / Capacity
Subsystem:    resource / capacity
Authorizes:   YES (when it ships)
What:         Reserving storage bytes.
Why now:      2.4 must not admit or reserve.
Retire when:  ResourceManager storage reservations exist
Status:       OPEN

### M-2.4-12 — Windows mount reader
Label:        DEFERRED
Owner stage:  Discover 2.4 when Windows is a support target
Subsystem:    discover
Authorizes:   NO
What:         Native Windows volume/mount observation.
Why now:      Current support is Linux required, macOS useful, Windows
              explicit unsupported.
Retire when:  Windows is an accepted Machi host
Status:       OPEN

### S-STRAT-01 — Comparative experiment records
Label:        DEFERRED
Owner stage:  Strategic Stage 2, after one serve path exists
Subsystem:    evidence
Authorizes:   NO
What:         Experiment specification, result, and evidence records
              that keep observed facts distinct from estimates, name
              the foundation family, and carry provenance. Not a
              benchmark warehouse.
Why now:      `EventRecord` and the acceptance lab already hold
              operational and campaign facts. A second schema before
              Steward would be lab scope inside the product spine.
Retire when:  a comparative Ollama / direct / Dynamo campaign needs
              a normalized record the journal cannot express without
              losing observed-versus-estimated
Status:       OPEN

### M-4-01 — Live storage-quota specialists
Label:        DEFERRED
Owner stage:  Capacity Tier 3 / a justified specialist
Subsystem:    capacity
Authorizes:   NO
What:         Executing quotactl, FUSE/MooseFS, NFS, XFS, ZFS, or
              provider-volume entitlement readers.
Why now:      This increment accepts an injected specialist bound and
              uses Sonar when native evidence is inadequate. No live
              specialist is claimed as supported.
Retire when:  a provider-selection decision names a technology and its
              reader is physically proven
Status:       OPEN

### M-4-02 — Tier-3 capacity intelligence
Label:        DEFERRED
Owner stage:  Capacity Tier 3
Subsystem:    capacity
Authorizes:   NO
What:         Placement, predictive memory curves, learned margins,
              fleet capacity, and closed-loop optimization.
Why now:      Tier 2 produces a planning envelope, not an optimizer.
Retire when:  Foundation and Serve exist and evidence asks for it
Status:       OPEN

### S-3-01 — Tier-3 Steward cleanup
Label:        DEFERRED
Owner stage:  Steward Tier 3
Subsystem:    steward
Authorizes:   NO
What:         Automatic garbage collection, pressure-aware cleanup,
              rollback-aware reclamation, retention schedules,
              generation migration, failed-deployment cleanup, cache
              eviction, and organisation retention policies.
Why now:      Tier 2 classifies reclaim candidates and does not delete.
Retire when:  an explicit cleanup policy is authorized to delete a
              verified, unprotected, obsolete object
Status:       OPEN

### M-4-03 — File and driver bind mounts as storage domains
Label:        DEFERRED
Owner stage:  Capacity Tier 3
Subsystem:    capacity
Authorizes:   NO
What:         A GPU container can publish more than a hundred distinct
              tmpfs and driver-file mounts. They remain separate
              domains when their backing ids differ. The envelope cap
              is 512, matching the mount observation cap.
Why now:      Collapsing those mounts would hide topology the host
              actually reported. Foundation only needs one usable
              domain large enough for the managed environment.
Retire when:  a later storage class distinguishes driver file binds
              from planning domains without dropping real tmpfs
Status:       OPEN

### M-5-AMD-01 — AMD MI300X native Foundation physical qualification
Label:        DEFERRED
Owner stage:  Foundation physical qualification
Subsystem:    foundation
Authorizes:   NO
What:         Physically qualify the current approved AMD native-vLLM
              recipe on a real SSH-reachable Linux MI300X / gfx942
              host. The host must provide the kernel, firmware,
              `amdgpu` module, GPU, `/dev/kfd`, and `/dev/dri`.
              Userspace is either verified in place or realized under
              Machi-owned storage. Machi then creates the managed
              Python environment, installs the exact artifact,
              verifies import, version, HIP or backend, and the API
              entrypoint, and reuses the generation. No remote
              repair, no model load, no server.
Why now:      The provider is implemented. ROCm 6.1 is rejected
              before install. A compatible acceptance host was not
              available. That is not permission to call AMD
              production-qualified.
Historical:   Candidate `8f68c6d34a997e05df718f77a233afafeaa2169d`,
              wheel SHA256
              `df23311c0b5a357d02b8c4cb24b6fe9c7eec944e266b98352f2efd0382be81ba`,
              build `0.1.0+8f68c6d34a99`, recipe `vllm-0.18.0-rocm700`
              (ROCm 7.0 line). NVIDIA qualification remains the A40
              proof on `d3b45dd`. If a newer AMD recipe is approved
              before this gate runs, qualify that recipe and keep
              this candidate as history.
Retire when:  the then-approved recipe reaches Foundation `READY`
              on MI300X / gfx942 under the rules above, and public
              or commercial AMD support is still withheld until that
              evidence is recorded
Status:       OPEN

### M-5-AMD-02 — OCI runtime image from the owned userspace manifest
Label:        DEFERRED
Owner stage:  Foundation
Subsystem:    foundation
Authorizes:   NO
What:         A later image builder may package the same component
              set recorded by the managed ROCm prefix. No image is
              built now. No container executor is installed.
Why now:      The native prefix is the default provider. The manifest
              is the input a future builder would copy.
To make real: an image build that consumes the owned manifest and
              still does not own admission or serving.
Retire when:  that builder exists, or the native prefix remains the
              only provider and this seam is explicitly dropped
Status:       OPEN

### M-5-AMD-03 — Managed ROCm prefix bytes are unmeasured
Label:        PROVISIONAL
Owner stage:  Foundation
Subsystem:    foundation
Authorizes:   NO
What:         The 12 GiB persistent budget is the Python generation,
              not the ROCm prefix. Required component sizes are
              unknown, so realization refuses instead of assuming
              the prefix fits.
Why now:      Publishing an invented gigabyte figure would authorize
              storage the host has not been shown to have.
To make real: measure the prefix, the generation, and the transient
              staging directory on a host that can install the
              recipe, then set the SAFE requirement to that sum.
Retire when:  a measured prefix footprint is recorded and capacity
              checks use it
Status:       OPEN

### M-5-OLLAMA-01 — Local API is not hard isolation
Label:        DEFERRED
Owner stage:  Foundation
Subsystem:    foundation
Authorizes:   NO
What:         The Ollama daemon listens without Machi authentication.
              Another process on the same host can call the loopback
              API and bypass ResourceManager. Machi can govern only
              the calls it routes.
Why now:      The first substrate keeps the bind on loopback and
              disables cloud. It does not solve multi-user isolation.
To make real: an isolation boundary that prevents an arbitrary local
              process from using the daemon outside a Machi
              reservation, without widening the bind.
Retire when:  that boundary is enforced, or a later security review
              accepts loopback trust for the deployment model
Status:       OPEN

### M-5-OLLAMA-02 — RuntimeCapability v1 text still names vLLM
Label:        PROVISIONAL
Owner stage:  Foundation
Subsystem:    foundation
Authorizes:   NO
What:         `RuntimeCapability` version 1 field meanings still say
              vLLM. An Ollama substrate stores the Ollama version in
              that same contract and sets the engine to `ollama`.
Why now:      Bumping the contract was not required to add the engine
              value. The Ollama generation record is the specific
              identity.
To make real: a provider-neutral capability schema version.
Retire when:  readers no longer need the v1 wording to interpret an
              Ollama capability
Status:       OPEN

### M-5-OLLAMA-03 — Official Linux prefix is not yet executed
Label:        DEFERRED
Owner stage:  Foundation
Subsystem:    foundation
Authorizes:   NO
What:         Relocation is taken from the v0.34.3 Linux installer,
              which extracts a prefix-relative archive, and from
              `ml/path.go`, which looks for `lib/ollama` beside the
              executable. This workspace did not run that Linux
              binary. Fixture tests prove ownership, checksum, and
              daemon lifecycle only.
Why now:      The development host cannot execute the Linux archive.
              Pretending that a fixture is the official binary would
              overclaim the substrate.
To make real: on a Linux host, unpack the pinned
              `ollama-linux-amd64.tar.zst`, start it from the owned
              prefix, and match `/api/version` to `0.34.3` with cloud
              disabled and no `/usr` write.
Retire when:  that host evidence is recorded
Status:       RETIRED (Ollama bundle 04, 2026-09-24). Owned prefix
              `renv_ceedac1939fecd21` on one NVIDIA L40S reported
              `/api/version` 0.34.3 with cloud disabled. The binary
              was not installed under `/usr`. System zstd remains
              M-5-OLLAMA-04.

### M-5-OLLAMA-04 — External zstd helper is not a managed artifact
Label:        DEFERRED
Owner stage:  Foundation
Subsystem:    foundation
Authorizes:   NO
What:         The managed Ollama prefix streams the official `.tar.zst`
              through a system `zstd` decompressor. That tool is
              preflighted and recorded as provisioning provenance. It
              is not part of qualification identity. The final
              plug-and-play product should ship a pinned helper
              through the Runtime Artifact Registry, or replace it
              with an approved in-process implementation.
Why now:      Official Ollama Linux archives of this pin are zstd.
              Installing the tool with a package manager, or asking
              the customer to install it, is not the product model.
To make real: a pinned decompressor artifact delivered by the future
              registry, or an in-process decoder behind the same port.
Retire when:  realization no longer depends on an unmanaged host
              `zstd` binary
Status:       OPEN

### M-6-OLLAMA-01 — Ollama residency can move under a Serve hold
Label:        DEFERRED
Owner stage:  Serve
Subsystem:    model
Authorizes:   NO
What:         Ollama may evict or keep a resident model on its own
              schedule. Chunk 3 records that behavior as later Serve
              authorization work. It does not constrain Ollama's
              scheduler, and it does not treat a qualification unload
              fault as a deployment policy.
Why now:      A long-lived Machi reservation and Ollama's own
              residency can disagree. Solving that inside qualification
              would redesign scheduling before Serve exists for this
              macropath.
To make real: a Serve authorization rule for Ollama residency and
              eviction that still uses the one ResourceManager ledger.
Retire when:  that Serve boundary is specified and enforced, or an
              explicit later decision accepts Ollama-managed residency
              for the deployment model
Status:       OPEN

### M-9-01 — Deferred witness composer and further serve depth
Label:        DEFERRED
Owner stage:  Serve
Subsystem:    serve
Authorizes:   NO
What:         The Kernel `DeploymentWitness` projection, automatic
              restart, usage metrics beyond the inference event,
              more than one serving instance, and a public endpoint.
Why now:      Native M9 stores the plan, reservation, instance, and
              inference proof. It does not compose a witness or
              restart a dead process.
Retire when:  a witness composer reads those stored records, or a
              later serve decision names restart and usage
Status:       OPEN

### M-9-02 — Pinned vLLM cannot execute the stored tiny Llama
Label:        DEFERRED
Owner stage:  Serve
Subsystem:    serve
Authorizes:   NO
What:         `hf-internal-testing/tiny-random-LlamaForCausalLM`
              revision `9fb191250dd56d0ba7ec9785a025ed29c03d5998`
              has hidden size 16 and 4 attention heads, so the head
              dimension is 4. vLLM 0.18.0 on NVIDIA selects flex
              attention, which crashes with a kernel error that the
              head dimension must be at least 16. Flash attention
              requires a multiple of 8. Triton attention requires at
              least 32. Eager mode does not avoid the crash.
Why now:      NVIDIA-N1 L5 reached a healthy loopback server and then
              a completion request returned HTTP 500. The process was
              stopped and the reservation released. No token was
              produced.
Retire when:  one real completion of this exact artifact succeeds on
              the pinned runtime, or an authorized decision replaces
              the artifact or the vLLM pin and the new candidate is
              proven on its own SHA
Status:       OPEN

### M-8-01 — Deferred enforcement beyond single-host accounting
Label:        DEFERRED
Owner stage:  Admit Tier 3
Subsystem:    admit
Authorizes:   NO
What:         cgroups and other OS enforcement, GPU partition
              enforcement, multi-GPU allocation, multi-host
              scheduling, lease expiry, heartbeats, preemption,
              priority, dynamic rebalance, richer M7 resource
              sizing, and reservation recovery against real
              processes.
Why now:      Tier 2 reserves exact single-accelerator requests
              against SAFE capacity and keeps the hold in the
              store. It does not start a process or police one.
Retire when:  a later decision names the enforcement or placement
              policy and Serve already consumes a reservation
Status:       OPEN

### M-8-02 — CPU is recorded and not capacity-gated
Label:        DEFERRED
Owner stage:  Admit
Subsystem:    admit
Authorizes:   NO
What:         Capacity has no SAFE CPU pool. A reservation records
              the plan's cpu_count. Admit does not invent a pool
              and does not treat an unknown CPU total as zero.
Why now:      M7 always requests one process slot. Host memory,
              accelerator memory, and storage are the dimensions
              with authoritative SAFE bytes.
Retire when:  Capacity publishes a SAFE CPU quantity and Admit
              subtracts unreleased cpu_count from it
Status:       OPEN

### M-7-01 — Deferred serving plans beyond one accelerator
Label:        DEFERRED
Owner stage:  Plan Tier 3
Subsystem:    plan
Authorizes:   NO
What:         Multi-GPU planning, tensor parallel above 1, pipeline
              parallel, a measured serving-memory model, benchmark
              search, learned optimization, llama.cpp, MLX, and
              Ollama planners, and dynamic LoRA planning.
Why now:      The first plan asks Admit for one accelerator inside
              the cited SAFE budget and writes a bounded vLLM
              recipe. It does not tune or admit.
Retire when:  a later decision names the topology or planner and
              Admit can already reserve the single-accelerator case
Status:       OPEN

### M-6-03 — Empirical vLLM qualification is not yet executed
Label:        DEFERRED
Owner stage:  Model
Subsystem:    model
Authorizes:   NO
What:         A real one-token probe on the verified vLLM generation.
              The local funnel, predicate classification, queue, and
              cache contracts exist. Tests use a fake probe. llmfit
              and Accelerate are not estimators in this path.
Why now:      Architecture recognition admitted a head-size-4 Llama
              that vLLM 0.18 could not execute. The new gate refuses
              that shape before qualification. No external artifact
              has a `model.qualification` pass on hardware.
Retire when:  one candidate is qualified on NVIDIA-N1 with the new
              identity, or the lead chooses not to run that probe
Status:       OPEN

### M-6-01 — Deferred model catalog, conversion, and training
Label:        DEFERRED
Owner stage:  Model Tier 3
Subsystem:    model
Authorizes:   NO
What:         Hub search and marketplace discovery, recommendations,
              automatic quantization and conversion, quality
              benchmarks, learned ranking, S3/OCI/ModelScope and
              other registries, air-gap bundles, fleet inventory,
              content deduplication, fine-tuning, training jobs,
              Team Brain artifacts, adapter serving, and commercial
              distribution.
Why now:      Tier 2 stores an explicit hub revision or a copied
              local tree and assesses it against the installed
              engine. It does not crawl, convert, or rank.
Retire when:  a later decision names the provider or workflow and
              the product spine already serves
Status:       OPEN

### M-5-01 — Deferred foundation executors and engines
Label:        DEFERRED
Owner stage:  Foundation Tier 3
Subsystem:    foundation
Authorizes:   NO
What:         ContainerExecutor (Docker and Podman), Kubernetes,
              Apple/Metal vLLM, Intel, SGLang, TensorRT-LLM, llama.cpp,
              MLX, Dynamo, air-gapped artifact bundles, binary mirrors,
              automated upgrades, rollback, environment garbage
              collection, and fleet-wide foundation orchestration.
Why now:      This increment provisions one native vLLM generation for
              CUDA or ROCm through NativeProcessExecutor. A later
              container path must use the same Foundation semantics.
Retire when:  a provider-selection decision names the executor or
              engine and physical evidence accepts it
Status:       OPEN

### S-STRAT-02 — Dynamo foundation family
Label:        DEFERRED
Owner stage:  Strategic Stage 2
Subsystem:    foundation
Authorizes:   NO
What:         Treating NVIDIA Dynamo as a distributed-fabric family
              under `FoundationSelection`, after measured comparison
              with direct vLLM and with Ollama.
Why now:      Dynamo is not a product-spine dependency and must not
              be modeled as a vLLM optimizer or as a replacement for
              the direct path.
Retire when:  evidence answers scale, overhead, vendor coverage, and
              whether KV-aware routing or prefill/decode split pays
Status:       OPEN

### DC-04 — Intel accelerators
Fixture:         none
Architecture:    ARCHITECTURE-READY
Implementation:  ADAPTER-NOT-IMPLEMENTED
Evidence:        none
Seam:            `HostDiscoveryProvider` via Level Zero / Sysman or equivalent, plus a
                 compatible runtime adapter
Unproven:        everything
Downstream redesign expected: NO
Revisit:         when Intel accelerators enter the validated roadmap

### DC-05 — Kubernetes / Node Feature Discovery
Fixture:         none
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
Fixture:         none
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

### DC-08 — a host with more than one assigned accelerator

Architecture:    ARCHITECTURE-READY — `accelerators` has been plural since v1
Implementation:  no work needed; capacity and placement have not consumed it
Fixture:         none
Evidence:        none. The reference host had four accelerators **visible** and one
                 **assigned**, which exercised reconciliation thoroughly but proves
                 nothing about multi-device capacity, aggregation or placement
Seam:            none new; `HostCapabilities.accelerators` and `CapacityEnvelope`
Unproven:        per-device capacity arithmetic across several devices; whether an
                 interconnect ever permits aggregation; placement across devices
Downstream redesign expected: NO
Revisit:         Milestone 1 Hardware Breadth Review, or when a multi-accelerator
                 host is available — Stage 1.2 must not aggregate before then

### DC-09 — training and adaptation hardware

Architecture:    training is already a distinct workload class, not an inference variant
Implementation:  ADAPTER-NOT-IMPLEMENTED
Fixture:         none
Evidence:        none
Seam:            executor and runtime; a training job is not an `InferenceInstance`
Unproven:        everything. Training creates a **new** hardware-sensitive boundary
                 with different memory, duration and failure characteristics
Downstream redesign expected: NO, provided training resource execution is kept
                 apart from inference testing rather than folded into it
Revisit:         when training becomes an active milestone. Training orchestration
                 and lineage remain hardware-independent (T0/T1); only resource
                 execution needs real hosts (T3/T4)

### DC-10 — placement across multiple hosts

Architecture:    `HostCapabilities` is host-scoped and plural-ready
Implementation:  NOT IMPLEMENTED — single host only
Fixture:         none. Would need several host records captured together
Evidence:        none
Seam:            `resource` and `planning`
Unproven:        heterogeneous capability comparison; placement decisions; stale
                 host evidence; a host disappearing mid-reservation; reservations
                 spanning hosts
Downstream redesign expected: unknown — this is the one deferred shape that
                 might genuinely reach classification E at a breadth review
Revisit:         only if multi-host placement enters the roadmap. Explicitly not
                 brought forward

### DC-14 — a genuine reservation primitive beyond POSIX

Architecture:    ARCHITECTURE-READY — `StorageSanityProbe` is the seam
Implementation:  ADAPTER-NOT-IMPLEMENTED for anything but `posix_fallocate`
Fixture:         n/a
Evidence:        none. A sanity check on Darwin reports UNSUPPORTED, which
                 leaves the policy bound standing and lowers nothing
Seam:            `kultrun.storage.ports.StorageSanityProbe`
Unproven:        whether `F_PREALLOCATE` on Darwin gives comparable evidence
Downstream redesign expected: NO
Revisit:         when macOS or Windows becomes a supported deployment target.
                 Never by substituting a sparse write: it would succeed at any
                 size and verify a petabyte that is not there

### DC-11 — automated ephemeral hardware acceptance

Not a hardware shape: **development infrastructure.** Recorded here so it is
revisited rather than forgotten.

Today a real host is created by hand when a stage needs it. The concept is
CI building the artifact, allocating a host, installing, running acceptance,
capturing evidence and destroying the host.

No vendor chosen. Criteria in `docs/TESTING_STRATEGY.md`: cost, hardware
diversity, CI integration, provisioning latency, reliability, security,
artifact transfer, evidence capture, commercial dependence.

**Must never enter the product architecture.** No cloud-runner, test-farm or
GPU-scheduler domain.

Revisit:         Milestone 1 Hardware Breadth Review

### DC-12 — rotating compatibility matrix

Also development infrastructure. Once more than one shape is validated,
different shapes should run at different cadences rather than all of them on
every commit or none of them ever.

Cadence deliberately undefined: with one validated shape there is nothing to
rotate, and a schedule invented now would be fiction.

Revisit:         after the first live inference, at the breadth review

### DC-13 — customer and support diagnostic fixture capture

A product-owned command — conceptually `kultrun diagnostics capture-host` —
producing a sanitized evidence bundle that a customer on unusual hardware
could send back, which Kultrun then converts into a permanent regression
fixture.

Would contain provider observations, normalized capabilities, OS and
architecture, accelerator capabilities, tool and driver versions, storage
shape and provenance. Never prompts, responses, customer files, secrets,
named individuals or proprietary content.

This is how the fixture library grows beyond hardware Kultrun can rent, and
it is the natural extension of the capture-once/replay-often principle.

Revisit:         when a support or customer case first meets unfamiliar
                 hardware, or when the Admin surface needs to export evidence

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
