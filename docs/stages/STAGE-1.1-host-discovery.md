# Stage 1.1 — Host discovery

**Milestone 1 — Walking skeleton.** First stage.

Brief in the format of `docs/ROADMAP.md` Part V. The output package is
appended when the stage closes.

Status: **CLOSED.** `L2` acceptance passed on the reference host, 14/14.

> Revised twice. First, discovery became a **provider architecture** rather
> than a Kultrun-written detector: mature tooling observes, Kultrun
> normalizes, reconciles and decides (`docs/ARCHITECTURE.md` Part IX).
> Second, the stage was **narrowed to one blocking hardware shape** to
> protect the path to first real inference.
>
> **What "too large" meant.** Not binary size, package size or storage
> footprint. Scope and proof obligations before any inference exists. The
> stage had accumulated provider research, provisioning, three hardware
> platforms, two fixture boundaries, normalization, reconciliation,
> fingerprinting and profile classification — a milestone's work before a
> single request reaches a model. The remedy is scope reduction, not
> another subsystem: one blocking reference host, one minimal provider
> path, future-compatible contracts, explicit deferred hooks.

---

## CURRENT STAGE

`HostDiscoveryService` producing normalized `HostCapabilities`, plus the
`DeploymentProfile` that says how much the platform actually knows about a
host of this shape.

**This is the first stage that can be wrong in a way a test on the
development machine cannot detect.** Everything through Milestone 0 was
`L1`: contracts serialized, a control plane started, and nothing described
anything real. From here every claim is checked against hardware, because
the previous attempt's own record is unambiguous that hardware was the only
oracle that mattered — a probe that ran 48 minutes and kept nothing, a
filesystem advertising 239 TB free while a 6.70 GiB install was correctly
refused, a deletion returning 1.1 GB to `df` out of 42,990 MiB. None of
that was visible to a unit test.

**And Kultrun does not write the enumeration.** Discovering CPU topology,
NUMA, PCI devices and accelerators across Linux, macOS, ARM64 and x86_64 is
commodity work that mature projects already do, on more platforms than this
project will ever validate. Building it would be a large proprietary
investment in something no customer would notice. What Kultrun owns is what
those observations *mean*, and what may safely be done with them.

## PREDECESSOR OUTPUTS

`PlatformState v1 + ControlPlaneShell v1`, Stage 0.3, checkpoint
`checkpoints/STAGE-0.3-control-plane-shell.json`, contract surface token
`389bbd938668f5e6`.

| Consumed | From |
|---|---|
| `HostCapabilities` and its six fact contracts | `host/contracts.py` (Stage 0.2) |
| `Basis`, `Confidence`, `Provenance` | `evidence/contracts.py` |
| `Maybe[...]`, so an unreadable value is unknown and not zero | `kernel/unresolved.py` |
| `AdapterRegistry`, the seam by which providers are resolved | `kernel/registry.py` |
| `Store`, for the durable host record | `kernel/persistence.py` |
| `ReconcilePhase`, `HealthSource` | `platform/ports.py` |
| `api/routes.py`, where host endpoints are added | Stage 0.3 |
| The composition root | `main.py` |

**One discrepancy with the predecessor checkpoint, reconciled here.** The
Stage 0.3 checkpoint records that its successor will resolve a
`HostDetector` adapter. That port is now `HostDiscoveryProvider`, and there
are several of them rather than one. The checkpoint is left unedited — a
closed checkpoint is a record of what was true and believed at close, and
rewriting it would destroy the evidence it exists to hold. The rename is
recorded here instead, which is where a successor is supposed to reconcile
what it inherited against what it now needs.

Nothing else is rediscovered. The contract shape was fixed at Stage 0.2;
this stage populates it. The Stage 0.2 review confirmed those contracts
need no change: provenance arrives here as optional fields, compatibly.

## THIS STAGE'S REQUIRED OUTPUT

`HostCapabilities v1 + DeploymentProfile v1 + HostDiscoveryProvider`.

| Module | Owns |
|---|---|
| `host/ports.py` | `HostDiscoveryProvider` |
| `components/…` | `ComponentRequirement`, `ComponentResolution` — what the provider needs, and what was found |
| `install/…` | The minimal preparation path: detect, reuse, else provision once, verify |
| `host/discovery.py` | `HostDiscoveryService` — collect, normalize, reconcile |
| `host/fingerprint.py` | What identifies a host across restarts |
| `host/profile.py` | `DeploymentProfile` and the support matrix |
| `host/inventory.py` | The durable record, its restart reconciliation, health |
| `adapters/host/…` | The smallest provider set the spike proves necessary |

Contract additions, all optional and therefore compatible:
`ProviderReport`, `FieldObservation`, `ObservationConflict`,
`DeploymentProfile`, and `Derivation` in `evidence`.

Plus `GET /v1/host`, `GET /v1/host/profile`, `GET /v1/host/providers`, and
a command that captures the current host to fixtures.

### Scope: blocking versus non-blocking

**BLOCKING — Stage 1.1 does not close without these:**

- the `HostDiscoveryProvider` seam works;
- the smallest practical provider stack is selected and justified;
- a missing provider is resolved through the minimal preparation path;
- the real Linux x86_64 + NVIDIA reference host is observed;
- observations normalize into valid `HostCapabilities`;
- host scoping is correct;
- unknown handling is correct;
- evidence and provenance are preserved;
- reference-host fixtures are captured at both boundaries;
- `L2` acceptance is complete.

**NON-BLOCKING — none of these may hold the stage open:**

Apple Silicon provider or capture · Apple inference · CPU-only capture or
runtime · AMD provider · Intel provider · NFD · Kubernetes · CDI ·
OCI/container execution · any provider beyond what the reference host needs
· a generalized dependency downloader · enterprise mirrors · offline
bundles · support-profile UI · a portfolio of `DeploymentProfile`s.

Capture Apple Silicon and CPU-only **if they are available and cheap**.
Record them in the deferred capability register if not. Both remain
genuinely valuable — unified memory and the zero-accelerator path are real
failure modes — and neither is required for a real server to serve a real
model.

### Step 0 — the provider validation spike

**Bounded, and first.** Not a research project: a short empirical exercise
on the reference host, whose output is a decision and a set of captured
observations.

**Exit condition, so this cannot become open-ended.** The spike ends when
all five hold:

1. the reference host is observable with the smallest practical
   combination of mature providers;
2. those observations normalize into valid `HostCapabilities`;
3. what Stage 1.2's safe-capacity work needs is available, explicitly
   unresolved, or documented as needing a small supplement;
4. there is no demonstrated need for Kultrun to implement commodity
   hardware enumeration itself;
5. remaining provider and hardware gaps are recorded as deferred
   capabilities rather than explored further.

Outcome-bounded, not research-bounded. Once these hold, provider
exploration stops even if interesting questions remain.

The preferred general provider is **optional-preferred**, which sets the
spike's ground rules precisely: it may **not** be assumed already present;
it **may** be installed on development acceptance hosts in order to be
evaluated; how it was obtained and at what version **must** be recorded
with the captured evidence, because a fixture from an unknown version is
not reproducible; and final bundling and installer mechanics are **not**
solved here — that is Milestone 10.

It answers, per available shape:

- what does a general topology tool report here, and what does it miss;
- is it practical to provision — packaged, licensed, installable without
  making the platform hostile to install;
- which vendor or native supplement is *actually required* to answer a
  question capacity will ask, rather than merely available;
- do the outputs normalize cleanly into `HostCapabilities`, and where do
  they conflict or overlap;
- what does the platform do when the tool is absent.

**No custom fallback is written until a real gap is demonstrated on a real
machine.** Documentation says what a tool can do somewhere; only a run says
what it does here. The general provider's own documentation states that
"platforms and/or operating system versions will only report a subset" of
its information, so partial results are the expected outcome and are not by
themselves a gap — a gap is a question capacity needs answered that no
available provider answers.

Then implement the smallest provider stack that acceptance requires. The
expectation, to be confirmed rather than assumed, is a general provider
plus a vendor supplement on the NVIDIA host, and a general provider plus a
small native supplement on Apple Silicon **only if** the supplement proves
necessary. No AMD or Intel provider is written for completeness.

## CORE CONTRACTS AFFECTED

`HostCapabilities` and its fact types exist and do not change shape. Five
decisions govern how they are filled.

**A provider observes; it never decides.** It reports what a machine
appears to contain, records where the observation came from, and may be
partial, stale, slow, absent or wrong. It may not compute safe capacity,
choose a model, select a runtime or authorize a workload. Law 5 in
`docs/ARCHITECTURE.md` makes that structural: a provider inherits tier 2's
import budget and has no path to `model`, `planning`, `resource`, `runtime`
or `inference`.

**The service owns meaning.** It selects providers, collects observations,
normalizes them into Kultrun's vocabulary, reconciles overlaps, preserves
unknowns and surfaces conflicts. Merge rules for this stage: a later
observation never blindly overwrites an earlier one; a vendor observation
may enrich a general one, because richer detail about the same device is
not a conflict; two credible observations that genuinely disagree leave the
value unresolved with both observations and their provenance preserved; a
provider that is absent or fails means *that source was unavailable*, not
that the host is unsupported; what no provider reported stays unknown.

**No global precedence order is implemented, and none is to be added.** Not
"vendor beats general", not any other ordering. Such a rule resolves every
future conflict including the ones where the general tool was right, and
does it silently. A conflict stays a conflict until a *specific field*
earns a documented reconciliation rule from empirical evidence — per field,
carrying the evidence that motivated it, never generalized to the providers
on either side. If this stage finds a field that needs one, the rule and
its evidence go in the output package.

Note the naming: **merging observations is not restart reconciliation.**
They are different operations and live in different modules, because a word
that means two things is how a concept begins to fragment.

**Detection reports; it never interprets and never authorizes.**
`MountFacts.free_bytes` is what a filesystem claims and may be displayed;
it may not authorize a storage mutation. Stage 1.2 is where interpretation
begins and Milestone 2 is where storage evidence becomes credible.

**A probe that fails produces `Unresolved`, never a default.** If a vendor
tool is absent, VRAM is not known — it is not zero, and the host does not
have "no accelerator". The distinction between "this host has no GPU" and
"we could not find out" is the difference between a correct refusal and a
wrong one, and the contracts already carry it.

**The fingerprint covers stable facts only.** This is the decision most
likely to cause trouble later if taken carelessly. The fingerprint is the
key by which cached evidence is judged reusable from Milestone 2 onward, so
it must include architecture, CPU model, accelerator models and count, and
mount identity — and must exclude available memory, free bytes and anything
else that changes minute to minute. A fingerprint over volatile values
invalidates every cached probe on every restart, turning Milestone 2's most
expensive work into something never reused.

It must also exclude **provider-assigned handles**, under the general
invariant in `docs/ARCHITECTURE.md` Part II §6: a provider-local handle is
an adapter implementation detail with an adapter lifetime and never becomes
a Kultrun identity. AMD's own documentation warns that a device handle "may
change after restarting the application, so it should not be considered a
persistent identifier across processes", and the same caution applies to
NVML, Level Zero and comparable APIs.

Where this stage needs identity that survives a restart, it derives one
from stable host-scoped attributes — bus address, serial, model and ordinal,
whatever the platform actually keeps still. Where it cannot, it says so
rather than promoting a handle. A fingerprint built on a handle would be
unstable for a reason nothing in Kultrun could diagnose, and the complete
device-identity algorithm is not designed at this stage — only the
invariant is binding.

### Explainability without an envelope per field

Every value must remain explainable. Wrapping every leaf would double the
size of every contract, so provenance is recorded beside the values, keyed
by the dotted field path that `unresolved_fields` already produces.

`FieldObservation` records path, provider, derivation, confidence and
observation time. `ObservationConflict` records a path and the competing
observations. Both are optional collections on `HostCapabilities`, so this
is a compatible addition rather than a revision.

`Derivation` is added to `evidence`: measured, reported by source, derived,
configured, estimated. It answers *how a value was obtained*, which is a
different question from `Basis` — *which layer of credibility it sits at,
and therefore whether it may authorize anything*. A value can be
`basis=reported, derivation=measured` when a vendor tool read it, and
`basis=reported, derivation=configured` when an administrator typed it;
both are unauthorizing, and only one is evidence.

`Basis` is narrowed to that authorization axis. It is declared today but
used by no field and absent from the committed fingerprint, so this costs
nothing and is not a contract change.

### `DeploymentProfile`, earned rather than declared

`docs/PRODUCT_VISION.md` §89 defines five support tiers so the product can
support broad hardware "without pretending every environment has identical
guarantees." Nothing owned that concept until now.

A tier states **what evidence exists for this host shape**:

| Profile | Meaning | Earned by |
|---|---|---|
| `CERTIFIED` | Extensively validated | `L4` on this shape |
| `SUPPORTED` | Expected to work | `L3` — live inference proven |
| `COMPATIBLE` | Likely to work | `L2` — real detection and capacity, no inference |
| `EXPERIMENTAL` | May work | Captured observation only, or partial detection |
| `UNSUPPORTED` | Known incompatibility | An explicit refusal, with a reason |

A profile applies to a defined hardware, software and environment shape.
One validated NVIDIA system does not certify every NVIDIA system.

An organisation may separately record its **own** support statement, and
that is a different fact stored separately. It may be displayed alongside
the profile and **may never promote it**: no external declaration turns
`EXPERIMENTAL` into `SUPPORTED`, because the profile means "this is the
acceptance level actually reached". The schema for the external statement
is not designed here — it has no consumer until there is a console to show
it.

The classifier matches detected capabilities against a shipped support
matrix. That matrix is data, not logic, and it is the one place a claim
about hardware support is made, so claims cannot scatter.

After this stage the reference Linux host is `COMPATIBLE`: detection is
real, inference is not yet. It becomes `SUPPORTED` at Stage 1.6 and
`CERTIFIED` at the Milestone 1 gate. Written this way, a tier cannot get
ahead of its evidence.

**This stage classifies the reference host and nothing else.** Other shapes
stay unclassified or `EXPERIMENTAL`. Producing a portfolio of profiles is
not Stage 1.1's job, and the deferred capability register in
`docs/DEBT.md` — which separates architecture-readiness from
adapter-implementation from acceptance evidence — is where the others are
tracked until they earn a tier.

**An unsupported profile does not prevent the platform from starting.**
Fail-closed governs mutations, not existence. A platform that refuses to
boot on unusual hardware cannot tell its administrator why, and the
Platform API is the only surface that administrator has.

## ADAPTERS AFFECTED

`HostDiscoveryProvider` is the first port with several real
implementations, which makes it the first genuine test of the adapter
boundary.

- **A general discovery provider** — the spike's first candidate. Portable
  across the shapes we care about, packaged by most distributions, and
  BSD-licensed. Reports topology and device presence; not device memory.
- **A vendor supplement on NVIDIA hosts** — device memory, driver version,
  per-device detail the general tool does not carry.
- **A native supplement on Apple Silicon** — only if the spike shows the
  general provider misses something capacity needs. Apple-specific
  collection stays inside the adapter, and no Apple-specific concept enters
  `HostCapabilities` unless it describes a genuinely cross-platform
  capability. Unified memory does, because it changes how any host's memory
  budget must be computed. A Metal-specific detail does not.
- **A captured-fixture provider** — replays a committed observation. Not a
  mock: it replays a real machine's real answers.

**No provider installs anything.** A provider reports available,
unavailable, failed, partially capable, or missing a prerequisite. It does
not run a package manager, download a tool, alter system configuration or
install a driver. Discovery looks; `install` acts.

**The minimal preparation path**, and only the minimal one: `components`
expresses the requirement, `install` detects an existing compatible
component, reuses it if valid, otherwise provisions it **through the host
distribution's package manager**, verifies it runs, records version and
source, and proceeds.

The package manager is an implementation detail behind `install`. No
distribution and no package-manager name may appear in a core contract, and
a verified-release-artifact mechanism — which would later cover
package-manager gaps, pinned versions, mirrors, offline bundles and other
environments — is deferred, not built. Not multiple package managers, not OCI images, not mirrors, not
offline bundles, not other distributions. The interface must permit those;
this implementation must not attempt them.

**Vendor supplement constraints.** If the general provider cannot answer
something capacity needs, use the smallest mature vendor supplement.
NVIDIA-specific observations must never become required for all accelerator
types — a host with no accelerator must still produce a valid
`HostCapabilities` — and no vendor structure or vocabulary may reach a
downstream domain.

Every provider is advisory with a mandatory internal fallback: if it is
absent, broken or slow, the affected values become unresolved and discovery
still completes. `llmfit` was integrated, found nondeterministic on the
real host and demoted; that outcome is the default assumption.

## PERSISTED STATE

One `HostCapabilities` record per host, keyed by host identifier, plus a
pointer to the current host, plus the last `ProviderReport` set.

**Restart reconciliation** re-runs discovery and compares fingerprints.
Four outcomes, each a fact rather than a decision:

- unchanged — the record stands;
- changed — the record is superseded and the change is reported, which from
  Milestone 2 invalidates cached evidence;
- unchanged shape, fewer providers — the record stands, values the missing
  provider supplied become unresolved, and the loss is reported. A host does
  not lose a GPU because a library stopped loading;
- discovery failed entirely — the stored record is retained and marked
  stale rather than deleted, because a host we cannot currently inspect is
  not a host that has ceased to exist.

The platform starts in all four cases.

## MUTATION / FAILURE BOUNDARY

Discovery performs no mutation. It reads, and it may execute read-only
vendor tools.

What fails closed: an external tool that hangs is abandoned at a timeout
and its values become unresolved; unparseable output yields unresolved,
never a guess; an unrecognised architecture is `UNKNOWN` and profiles as
`EXPERIMENTAL`, never silently treated as x86_64; two credible conflicting
observations leave the value unresolved and record the conflict rather than
picking a winner.

## CANCELLATION / CLEANUP

Discovery is bounded and side-effect free. Each provider call has a
timeout, and abandoning one leaves no artifact and no process — the
executor's PID discipline arrives at Stage 1.3, so this stage spawns
nothing it cannot reap synchronously.

## ACCEPTANCE LEVEL

**`L2` — real host.** `L1` cannot close a stage that touches hardware, and
this is the stage that defines what "touches hardware" means.

**One blocking shape.**

| Shape | Status | Why |
|---|---|---|
| Linux x86_64 + NVIDIA | **BLOCKING** | The reference: vendor tooling, driver versions, per-device memory. Already rented. |
| Apple Silicon, arm64 | non-blocking | Unified memory and ARM64 — a real failure mode, on a free machine. Capture if cheap; defer if not. |
| Linux x86_64, CPU-only | non-blocking | The zero-accelerator path, most likely to be quietly broken by code written on a GPU box. Capture if cheap; defer if not. |
| AMD, Intel, Kubernetes | out of scope | No hardware, no reason yet. Deferred capability register. |

The blocking shape is fully specified: Linux x86_64 with an NVIDIA
accelerator on a rented pod. The exact instance type is an execution detail.

Deferring the other two is a real cost, honestly taken. Both exercise
branches the reference host cannot, and neither is required for a real
server to serve a real model.

### Fixtures at two boundaries

Fixtures are captured **not** because Kultrun must write every detector,
but to permanently test the parts Kultrun does own: provider parsing,
normalization, reconciliation, host scoping, unknown handling, and
compatibility behaviour.

```text
real host → provider raw observation → normalization → HostCapabilities
                    │                                        │
              (A) provider fixture                  (B) normalized fixture
```

Capturing both matters. A provider fixture catches a parsing regression
when a tool's output changes; a normalized fixture catches a change in what
Kultrun *concluded* from identical input. One without the other leaves half
the pipeline untested.

Both boundaries are captured for the **blocking** host. The same approach
applies to any non-blocking shape that is actually run, and to any new real
machine encountered in future development — each becomes a permanent
regression fixture by being observed once.

Do not hand-write a synthetic representation when a real capture is
available. Synthetic fixtures remain acceptable only for edge cases that
cannot practically be produced from hardware.

Fixtures are sanitized: no secrets, no personally identifying machine
information, no customer identifiers, no unstable irrelevant values.
Hardware-relevant evidence is preserved, because that is the entire point.

Every real machine ever encountered can improve regression coverage
permanently by being run once.

### Evidence required to close

On the **blocking** host: discovery completes and is captured at both
boundaries; the accelerator branch reports per-device memory and driver
version; the minimal preparation path obtains or reuses the provider and
records version and source. **Discovery completes with the vendor tool
removed from `PATH`**, with accelerator detail unresolved and the host still
described — that one matters most, because it proves absence is a state
rather than a crash. Two providers reporting the same device merge without
duplication. A synthetic conflict surfaces as a conflict rather than a
silent winner. The fingerprint is stable across restarts and across a
change in available memory, and excludes provider handles. The reference
host classifies as `COMPATIBLE`. `L1` regression across every captured
fixture.

Where a non-blocking shape was captured, the same checks apply to it —
unified memory correctly reported on Apple Silicon, no accelerators and no
unknown-read-as-zero on CPU-only. Where it was not, the deferred capability
register records why.

## ADMIN SURFACE

`GET /v1/host` — capabilities, with unresolved fields shown as unknown
rather than blank, and provenance available per field. `GET
/v1/host/profile` — the deployment profile and the reason for it. `GET
/v1/host/providers` — which providers were consulted, which answered, which
failed and why. The third is what turns "the GPU is missing" into "the
vendor library did not load", which is the difference between a support
ticket and a fix.

## DEBT ENTRIES

Expected:

| Item | Label | Retire when |
|---|---|---|
| AMD, Intel and Windows shapes unproven; no provider exists | `PROVISIONAL` | A deployment needs one; each profiles `EXPERIMENTAL` until then |
| Support matrix is a shipped table, hand-maintained | `WORKING` | It disagrees with observed evidence — Milestone 11 |
| Storage facts are reported only; nothing is credible yet | `WORKING` | Stage 1.2 adds the safe layer; Milestone 2 makes it evidence-backed |
| Preferred provider is optional-preferred; how a customer host obtains it is unsolved | `PROVISIONAL` | Milestone 10 packages product-managed preparation. Until then the spike provisions it on development hosts and records how and at what version |
| Conflicts stay unresolved; no field yet has a reconciliation rule | `WORKING` | Retired per field, never globally: a field earns a rule when empirical evidence justifies one |

## DEFERRED ITEMS

- **Capacity interpretation.** Reported facts only; Stage 1.2 owns the
  three-layer model.
- **Storage pools.** `StoragePool` exists as a contract; deriving pools
  from mounts is Stage 2.1.
- **Container execution and device attachment.** The `ContainerEngine`
  seam is Stage 1.3; an OCI executor and device attachment are later and
  optional. Neither is a source of host facts, and neither consults
  capacity: execution receives an already-authorized allocation
  (`capacity` → `resource` reservation → `inference` derives a
  `DeviceRequest` → `execution` materializes it) and has no vocabulary for
  asking whether it should.
- **Generalized provisioning.** One mechanism for one environment here.
  Package managers in the plural, OCI images, enterprise mirrors, offline
  bundles and other distributions are Milestone 10.
- **Every deferred hardware shape** — Apple, CPU-only, AMD, Intel,
  Kubernetes — each with an entry and a revisit trigger in the deferred
  capability register in `docs/DEBT.md`. Architecture-readiness is recorded
  there and is explicitly not a support claim.
- **Kubernetes and a node-feature provider.** Optional, later, and never
  required: standalone Linux, macOS and native installations must all work
  without it.
- **AMD and Intel providers.**
- **Multi-host.** Contracts are host-scoped and plural already; a fleet
  view is Milestone 14.
- **Live accelerator utilization** — observed capacity, Milestone 11.

---

## OUTPUT PACKAGE

**Output:** `HostCapabilities v1 + DeploymentProfile v1 + HostDiscoveryProvider` ·
**Acceptance:** `L2`, 14/14 on the reference host · 313 tests ·
**Checkpoint:** `checkpoints/STAGE-1.1-host-discovery.json`

### The reference host

Rented at random, which was the point — nothing about it was assumed.

| | |
|---|---|
| Distribution | Ubuntu 24.04.3 LTS, kernel 6.8.0-106-generic |
| Architecture | x86_64, containerized |
| CPU | AMD EPYC 7763, 64 cores / 128 threads, 1 socket, 8 L3 caches, 1 NUMA node |
| Memory | 251.5 GiB total |
| Accelerator | 1 × NVIDIA RTX PRO 4500 Blackwell, 31.9 GiB, driver 580.126.20, PCI `0000:82:00.0` |
| Storage | `/` overlay 30 GiB; `/workspace` fuse network mount, **2.15 PB** |
| Fingerprint | `4d4efedb286baa4beccba3601cb11c70` |

An AMD CPU with an NVIDIA accelerator, which was useful by accident: it
exercised the fact that accelerator vendor and CPU vendor are unrelated.

### The spike, and what it settled

hwloc 2.10.0 from Ubuntu's `apt`. Exit condition met on all five points, and
provider exploration stopped there.

| Provider | Answers | Does not |
|---|---|---|
| **hwloc** | CPU vendor and model, cores, threads, caches, NUMA, total memory, the PCI tree | accelerator memory, driver version, OS release, mounts |
| **nvidia** | accelerator identity, memory, driver, and **which devices are assigned here** | anything not NVIDIA |
| **native-linux** | OS release, distribution, available memory, mounts, occupied ports | topology, accelerators |

The Ubuntu hwloc build ships no NVML or CUDA plugin, so an NVIDIA device
appears as a PCI entry with DRM render nodes and nothing about its memory.
That is the measured gap the vendor supplement closes, and it is the reason
the shape is "general provider plus supplement" rather than one tool.

**No demonstrated need for Kultrun to write commodity enumeration.** Three
mature sources answered everything Stage 1.2 requires, and the only code
Kultrun wrote was normalization — which is the part that is ours.

### Three findings that only real hardware could produce

Each of these passed every local test before the host found it.

**1. PCI enumeration overcounts accelerators in a container.** hwloc found
four NVIDIA devices on the bus; one was assigned to this container. Believing
the enumeration would have claimed roughly 128 GiB of accelerator memory
where 32 GiB exists — a capacity error large enough to make every subsequent
admission decision wrong, and invisible to a unit test.

This is what justifies the single field-specific reconciliation rule:
accelerator presence comes from a provider that reports device *assignment*,
declared through `reports_accelerator_assignment` rather than by naming a
vendor. The three unassigned devices are kept as conflict evidence, because
an operator asking "why only one GPU" needs to see that three others exist
physically.

**2. Not every display controller is an accelerator.** The host carries an
ASPEED management VGA (`1a03`), as most servers do. Mapping PCI display class
to "accelerator" gave it a phantom accelerator entry with unknown vendor and
unknown memory. On a **CPU-only** host — a shape we care about and did not
test here — that would have produced one phantom accelerator with nothing
behind it. hwloc now asserts an accelerator only for a recognised accelerator
vendor; other display devices remain in the raw fixture.

**3. Mount identity was a worse volatility trap than free space.** The host
mounts a tmpfs at `/run/nvidia-ctk-hook<random-uuid>`, and that UUID changes
on every container start. A mount point is a **fingerprint input**, so the
host fingerprint would have changed on every restart — and the fingerprint is
the key by which Milestone 2 judges cached evidence reusable. Nothing would
ever have been reused, and the cause would have been almost undiagnosable.

Free space was the obvious trap and the brief already excluded it. This one
arrived through the identity of the mount rather than its contents. Mounts
are now filtered to candidate storage locations, which on this host leaves
exactly `/` and `/workspace`.

### Architecture

**The harness caught a real violation in my own code.** `host/inventory.py`
imported `platform.contracts` to produce health and phase reports — tier 2
reaching tier 8. That exposed something worth recording: **`platform`'s ports
are only directly implementable by tiers above 8.** Every lower domain must
be adapted.

Rather than move contracts or add a position, the domain now **reports facts**
— which providers answered, what changed — and the composition root grades
them into a `PhaseReport` and a `ComponentHealth`. That is the same division
the record store already uses, and it is arguably better: whether a missing
provider makes the platform "degraded" depends on the whole platform's state,
which is not knowable from inside one subsystem. `docs/ARCHITECTURE.md` is
updated to say so.

Everything else held. No concrete technology appears in a core module, contract
field or signature; a test asserts that literally. Law 5 keeps all three
providers inside tier 2's budget, so none can reach `model`, `planning`,
`resource`, `runtime` or `inference`. Provider handles never became identity —
devices are keyed by PCI bus address, and the two tools' different spellings
of the same address are reconciled inside the adapter.

### Preparation

`hwloc` was **removed from the host** and the run repeated, so provisioning
was genuinely exercised rather than observed: `provisioned version=2.10.0
source=apt`. The following run reported `already_present`, proving reuse. On
a metered host, a platform that reinstalled its dependencies on every start
would also be paying to do it.

Discovery never installs anything. A provider reports available, unavailable,
failed, partially capable or missing a prerequisite; `install` acts.

### Fixtures

Both boundaries, captured from **one reading**. The first attempt captured
them independently and free space moved between the two reads, making the
pair inconsistent — so the normalized fixture is now derived from exactly the
provider output that was saved.

| Fixture | Catches |
|---|---|
| `provider-hwloc.xml` (112 KiB) | topology parsing, and a change in what hwloc reports |
| `provider-nvidia.csv` | vendor CSV parsing and bus-address normalization |
| `provider-native-linux.json` | OS release, memory and mount reading |
| `normalized-host-capabilities.json` | what Kultrun *concluded* from unchanged input |

Sanitized: the pod container id and the storage provider's endpoint were
replaced with placeholders, and distribution boilerplate URLs dropped. Every
hardware-relevant fact is intact, and no fingerprint input was altered — which
the first sanitization pass got wrong and the fixture test caught.

### Acceptance evidence

`L2`, 14/14 on the reference host, covering all ten points the brief
requires plus mount filtering and fingerprint stability. 313 local tests,
ruff clean, mypy strict clean across 91 files.

The test worth naming: **discovery completes with the vendor tool absent.**
That is the one that proves absence is a state rather than a crash, and it is
what will let an AMD or CPU-only host be described before any provider exists
for it.

### Deployment profile

The reference shape — `linux/x86_64/nvidia` — earned **`COMPATIBLE`**.
Detection and normalization are real; inference is not, so it is not
`SUPPORTED`. It becomes `SUPPORTED` at Stage 1.6 and `CERTIFIED` at the
Milestone 1 gate.

Every other shape remains `EXPERIMENTAL`. One validated NVIDIA host does not
certify NVIDIA.

### Non-blocking shapes: not captured

Apple Silicon and CPU-only were not captured. Both remain `DC-01` and `DC-02`
with their revisit triggers unchanged. Honest cost: the CPU-only path is
tested only through the ASPEED regression above, not against real hardware,
and finding 2 shows that is exactly where a false accelerator would hide.

### Amendment at Stage 1.2 — the fingerprint changed, honestly

**The acceptance above stands. This records a later correction to it.**

Stage 1.2 fixed `K-21`: the topology tool reports the CPU model padded to a
fixed width, and `cpu.model_name` is a **host fingerprint input**.
Normalization now strips reported strings, so the fingerprint for this exact
machine moved:

```
4d4efedb286baa4beccba3601cb11c70   as accepted at de9219e
2abe07033e90a057368c2e7a6575251b   after K-21, same machine
```

The provider evidence is untouched; only the conclusion drawn from it
changed. The normalized fixture was re-captured by replaying the committed
provider output — no host was needed, which is what the fixture library is
for. The old value is recorded rather than erased, because a fingerprint
that silently changes is the failure this stage was trying to prevent.

Stage 1.2 also found something this stage should have caught. The container
is limited to **57.7 GiB** of memory while `MemTotal` reports **251.5 GiB**,
and Stage 1.1 observed no memory limit at all — the same class of error as
counting accelerators nobody assigned, and it would have let capacity
authorize four times the memory available. `MemoryFacts.limit_bytes` and the
cgroup reading were added at 1.2. The committed provider fixture predates
the field and replays it as unresolved; it is re-captured at the next
real-host run.

### Retrospective — the last stage accepted from a source tree

Recorded after the fact. **Nothing above is changed and the acceptance
stands.**

Stage 1.1's acceptance ran by copying the source tree to the pod and
executing it in place. That worked, but it left two things unprovable. The
result could not be reproduced once the host was released, and nothing
distinguished "the product does this" from "the product does this when a
source checkout happens to be on the path".

It also produced a near miss worth remembering: the first fixture capture
was internally inconsistent because a harness ran beside the product rather
than being part of it, and the fix was to make the product itself the thing
that reports.

Kultrun therefore adopted artifact-based deployment immediately afterwards:
source changes originate in the development workspace, an installed wheel
carries its own build identity, and a fix that exists only on a test server
is not a fix. From that checkpoint forward, real-host acceptance at `L2` and
above requires an installed artifact traceable to a committed source state.

Stage 1.1 is the boundary: the last stage accepted under the old style, and
the reason for the new one.

### What this stage does not do

No capacity interpretation — reported facts only, and the 2.15 PB mount is
reported precisely so Stage 1.2 can refuse to believe it. No storage pools,
no model work, no runtime, no inference, no container execution, no AMD or
Intel provider, no generalized provisioning.
