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

**Retires when** Stage 2.2 produces empirical bounds. The ceiling then
becomes the *starting* point for verification rather than the answer, which
is why it matches the previous implementation's per-probe ceiling.

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

A pool is flagged as worth verifying and an operator decides. Nothing
schedules the probe, so a pool can stay unverified indefinitely and its
capacity stays bounded by policy.

Deliberate. Kultrun has no execution or job lifecycle yet, so making it
automatic would mean running a long filesystem operation on a background
thread — precisely how the previous implementation orphaned a 42,990 MiB
probe file when shutdown did not await the daemon thread that owned it.

**Retires when** Stage 1.3's executor exists and can own a cancellable
background job with cleanup that runs.

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

### K-31 — process identity is not reattached across control-plane restarts
Label:        PROVISIONAL
Owner stage:  1.3
Subsystem:    execution
Authorizes:   NO
What:         `NativeProcessExecutor` proves ownership by holding the
              `Popen` object. After a control-plane restart a recorded PID
              that still exists is `UNVERIFIED` and is never signalled.
              There is no start-time check, no `/proc/<pid>/stat` cookie,
              and no supervisor that reaps orphans.
Why now:      Stage 1.3 proves start/observe/stop in one process. Claiming
              a PID we cannot prove is ours would be a false success.
To make real: A durable process cookie (start time, or an equivalent) and
              a bounded reattach path that still refuses to signal
              unverified processes.
Retire when:  the scheduled lifecycle reconciliation stage that owns
              restart of running inference instances, not before.
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

### K-35 — the Hugging Face adapter does not fetch the live Hub
Label:        DEFERRED
Owner stage:  1.4A
Subsystem:    adapters / model_source
Authorizes:   NO
What:         The first `ModelSource` uses Hugging Face identity
              (`source_ref`) and a packaged curated candidate set. It
              does not call `huggingface_hub` or search the Hub.
              File acquisition is a separate adapter
              (`HuggingFaceAcquisitionProvider`).
Why now:      v0 must be T0/T1/T2 without a network or a GPU. Whole-Hub
              search is explicitly out of scope. Packaged metadata is
              enough to prove normalization and the catalog surface.
To make real: An optional live enricher behind the same `ModelSource`
              port, with the packaged catalog as the mandatory fallback
              when the Hub is absent, slow or disagreed with.
Retire when:  a stage claims a real source fetch (L2) or product policy
              requires live Hub metadata.
Status:       OPEN

### K-36 — ModelRequirement v0 estimates are curated and conservative
Label:        PROVISIONAL
Owner stage:  1.4A
Subsystem:    model
Authorizes:   NO
What:         Weight, RAM, VRAM, overhead and KV figures on the curated
              original six are coarse estimates with method `curated`.
              Expanded 1.4B variants use `formula_v0`. They are not
              measured runtime evidence. Compared with llmfit, Kultrun
              VRAM is typically conservative; some 20% / 100% band
              crossings (Qwen 7B AWQ, Phi-3.5 Mini, Qwen 32B Q4) are
              expected calibration gaps, not unit bugs. Do not rewrite
              production estimates to match llmfit.
Why now:      Stage 1.4B needs *some* host-independent requirement to
              filter against SAFE capacity. Inventing a precise
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
              AUTO (llmfit primary, Kultrun fallback on typed failure).
              Strict `llmfit` does not fall back when the executable is
              missing — estimation is unavailable/unresolved. Strict
              `kultrun` does not require llmfit. AUTO fallback is not
              estimate shopping and is not a product reconciler.
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
              discovery, proxy, or gateway routing.
Why now:      The 1.5B reference server binds 127.0.0.1:0 and reports
              the port. Real runtimes will need exclusive ports.
To make real: Stage 1.6 if a production runtime cannot self-report a
              bound endpoint.
Retire when:  endpoint/port reservation is required for instance start.
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
What:         v0 does not invent CPU counts or runtime scratch. Those
              fields stay unresolved unless later evidence supplies them.
Why now:      Current plans do not carry trusted CPU or scratch figures.
To make real: Runtime-specific planning.
Retire when:  a trusted CPU or scratch requirement exists.
Status:       OPEN

### K-50 — runtime-specific readiness is reference-only
Label:        DEFERRED
Owner stage:  1.5C
Subsystem:    runtime
Authorizes:   NO
What:         The reference-serving adapter owns `/health` and the ready
              marker. Inference composes that verdict with executor
              liveness. vLLM, llama.cpp and MLX readiness are not
              implemented.
Why now:      Stage 1.5C moved ownership; it did not add a real runtime.
To make real: Stage 1.6 per production runtime adapter.
Retire when:  a real runtime owns its readiness translation.
Status:       OPEN

### K-51 — real model load and inference
Label:        DEFERRED
Owner stage:  1.5B
Subsystem:    runtime
Authorizes:   NO
What:         No vLLM, llama.cpp, MLX, CUDA or ROCm model load. No
              prompt, chat, completions, or token API.
Why now:      A reference process is enough to prove instance lifecycle.
To make real: Stage 1.6 bounded brief.
Retire when:  a real request reaches a real model.
Status:       OPEN

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

### K-55 — model selection is not yet runtime-first
Label:        DEFERRED
Owner stage:  1.5C
Subsystem:    planning
Authorizes:   NO
What:         The 19-model funnel still ranks from catalog + host
              capacity. Stage 1.6F now supplies runtime compatibility
              tokens from `EligibleModelView`. Acquisition is not gated
              on a DeploymentPlan plus verified runtime. `STORE` remains
              the warehouse path as in 1.4C.
Why now:      1.5C must not remap selection before a verified runtime exists.
To make real: After 1.6G; migrate ModelSelector onto eligible +
              remapped requirement + capacity, then bounded selection.
Retire when:  normal executable selection consumes runtime eligibility
              and capacity against the selected verified foundation.
Status:       OPEN

### K-56 — Runtime performance-aware ranking
Label:        DEFERRED
Owner stage:  1.6B
Subsystem:    runtime
Authorizes:   NO
Blocks 1.6B:  No
What:         Stage 1.6B ranking is deterministic/static: compatibility,
              support tier, executor availability, policy order, then
              name. It does not consume latency, throughput, tokens/sec,
              startup time, or memory efficiency.
Why now:      Resolution only establishes technical plausibility.
To make real: A future RuntimeRankingPolicy behind verified operational
              evidence after inference exists.
Retire when:  multiple verified runtime choices exist for the same workload
              and ranking consumes measured evidence.
Status:       OPEN

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

### K-86 — DeploymentPlan freshness / stale-plan seam
Label:        DEFERRED
Owner stage:  later planning
Subsystem:    planning
Authorizes:   NO
Blocks 1.6C:  No
Current seam: DeploymentPlan v0 is a recommendation artifact, not an
              executable selected configuration with revision
What:         VALID vs STALE/REQUIRES REPLAN when host, runtime, model,
              capacity, or policy inputs change after plan generation.
              Recommendation vs selected provenance on the plan.
Why now:      Executable selected plans come after 1.6E and model remap.
To make real: Preserve selected vs recommended identity when the plan
              becomes authoritative for execution.
Retire when:  plan invalidation/versioning has tests.
Status:       OPEN

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
              1.6G. Planning still receives CompatibilityVerdict
              tokens through composition because it cannot import
              runtime. ModelSelector remains NEXT.

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
              amounts for BLOCKED/UNRESOLVED so 1.5A/1.5B reservation
              arithmetic keeps working. That is ResourceManager remap
              remaining work, not a compatibility default.

## Runtime-first migration ledger (after 1.6G)

Not a second architecture. Existing components still to migrate, in
order. Do not begin automatically.

| Component | CURRENT INPUT | TARGET INPUT | WHAT MUST MIGRATE | SHIM | ORDER |
|---|---|---|---|---|---|
| Runtime/model compatibility | `EligibleModelView` / `RuntimeEligibleModelCandidate` | same | done in 1.6F | composition copy of eligibility → `CompatibilityVerdict` (planning ⟂ runtime) | ✅ |
| ModelRequirement | `RuntimeEligibleModelCandidate` + fresh VERIFIED profile + selected runtime | same | done in 1.6G | none | ✅ |
| CapacityAssessment | remapped `ModelRequirement` + host SAFE envelope | same | done in 1.6G; existing SAFE math | none | ✅ |
| ModelSelector | catalog entries + remapped requirement + capacity + eligibility tokens | feasible eligible candidates + remapped requirement + capacity; bounded AUTO/MANUAL | ranking still capacity-band; do not redesign until next stage | composition tokens; ranking unchanged | 3 — next |
| SelectedDeploymentCandidate | not a persisted identity; recommendation primary | selected vs recommended after bounded model selection | keep recommended ≠ selected | none | 4 |
| DeploymentPlan | recommendation artifact from 1.4B | authoritative selected plan; stale when foundation/eligibility/requirement/capacity change | K-86 freshness | K-86 OPEN | 5 |
| Acquisition | catalog identity + storage envelope; `--recommended` uses remapped ranking | gate on eligible + feasible selected plan | still warehouse STORE path (K-55) | `--recommended` already reads remapped ranking | 6 |
| ResourceManager | `ModelRequirement` + SAFE envelope; product reserve passes eligibility tokens into `plan_for_entry` | ResourceRequest derived from remapped requirement against selected foundation; skip BLOCKED amounts | admission already consumes tokens; request amounts still estimated for blocked/unresolved artifacts | estimate-for-admission until remap | 7 |
| InferenceInstance | admitted reservation + stored artifact | instance against selected verified foundation + eligible model | not remapped; T2 inference passes explicit mapping | none as compatibility default | 8 |
| Real inference | reference serving | selected foundation + acquired artifact + reservation | later 1.6 letter | none | 9 |

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
Fixture:         none
Architecture:    ARCHITECTURE-READY
Implementation:  ADAPTER-NOT-IMPLEMENTED
Evidence:        none
Seam:            `HostDiscoveryProvider` via AMD SMI or equivalent, plus a ROCm runtime adapter
Unproven:        everything; no AMD hardware has been observed
Downstream redesign expected: NO
Revisit:         when AMD enters the validated platform roadmap

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
