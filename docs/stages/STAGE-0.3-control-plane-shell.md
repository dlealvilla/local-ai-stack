# Stage 0.3 — Control plane shell

**Milestone 0 — Architectural kernel.** Final stage; closing it closes the
milestone.

This file holds the **brief**, in the format of `docs/ROADMAP.md` Part V.
The output package is appended when the stage closes.

Status: **CLOSED.** Brief below, output package at the end.
**Closing this stage closes Milestone 0.**

---

## CURRENT STAGE

Stage 0.3 builds the platform state, the Platform API skeleton, local
administrator identity, and — added by the module-map review — the
`Approval` contract and the `HealthSource` port.

The stage's purpose is not the endpoints. It is to make three things true
from now on, each of which is expensive to introduce later:

1. **Every subsequent stage has somewhere to put its API surface.**
   `docs/ROADMAP.md` Part II §4.6 makes a Platform API surface part of the
   definition of done for every stage, so that the Admin surface and the
   Admin Agent never need a private back channel. That is only affordable
   if the surface exists from here and grows by a handful of lines at a
   time. The previous attempt's admin surface was a late project.
2. **Every subsequent stage has somewhere to put its reconciliation.**
   One startup path, one ordered set of phases, one report. Stage 6.3 then
   *completes* that path rather than inventing it.
3. **The platform starts with nothing installed.** The previous attempt hit
   a bootstrap deadlock — the platform needed a model to start, but
   choosing a model needed the platform — and spent four commits
   dismantling it. Here the empty state is the default case and there is a
   test for it.

## PREDECESSOR OUTPUTS

`PlatformContracts v1`, Stage 0.2, checkpoint
`checkpoints/STAGE-0.2-platform-contracts.json`, contract surface token
`db09f9ba1665bcfa`. Verified, not assumed:

| Consumed | From |
|---|---|
| `Contract`, `@contract`, the kind registry, the codec | `kernel/schema.py` |
| `Store` port and the file-backed implementation | `kernel/persistence.py`, `adapters/persistence` |
| `Result` and `ErrorDetail` | `kernel/results.py` |
| `ConfigSchema` and `Configuration` | `kernel/config.py` |
| `AdapterRegistry` | `kernel/registry.py` |
| `Subject`, `PrincipalKind` | `identity/contracts.py` |
| 36 registered contracts, for the catalogue endpoint | the whole tree |

## THIS STAGE'S REQUIRED OUTPUT

`PlatformState v1 + ControlPlaneShell v1`, which together with the previous
two stages completes `PlatformContracts v1 + PlatformState v1 +
ControlPlaneShell v1`.

### `platform` — tier 8

| Module | Owns |
|---|---|
| `platform/contracts.py` | `PlatformState`, `Approval`, `HealthReport`, `StartupReport` |
| `platform/ports.py` | `HealthSource`, `ReconcilePhase` |
| `platform/state.py` | Loading, creating and persisting platform state |
| `platform/startup.py` | The single ordered startup and reconciliation path |
| `platform/health.py` | Aggregation across registered health sources |
| `platform/approval.py` | Recording and reading administrator approvals |

### `api` — tier 8

| Module | Owns |
|---|---|
| `api/contracts.py` | `ApiRequest`, `ApiResponse` |
| `api/router.py` | The route table, dispatch, and uniform error rendering |
| `api/routes.py` | The Stage 0.3 endpoints |

### `main` — tier 11

The composition root. Builds configuration, resolves adapters, assembles
the object graph, runs startup. It is the only module that names a concrete
adapter alongside a core type, and until now that job has been done by the
test suite.

### `adapters/http` — tier 10

An HTTP server over the router, on the standard library. **This is a
module-map change and `docs/ARCHITECTURE.md` is edited in the same commit**,
per Part II §10.

### Endpoints

Read-only, all of them. The gate says the Platform API answers from
platform state, and at this stage there is nothing to mutate.

```text
GET /v1/health          aggregated health across registered sources
GET /v1/platform        installation identity, version, administrator
GET /v1/contracts       every registered contract kind and version
GET /v1/config          effective configuration by section
GET /v1/startup         the last startup and reconciliation report
GET /v1/approvals       recorded administrator approvals
```

## CORE CONTRACTS AFFECTED

Four new contracts, and one decision that shapes all of them.

**The HTTP server is an adapter; the API is not.** `api` owns the route
table, the handlers and the error rendering, and every handler is a
function from a request to a result — no sockets, no framework. The server
that carries them is `adapters/http`. Two reasons. Part II §9 requires that
no third-party component own a platform concept, and a web framework that
owns routing owns the API. And it means the whole surface is testable by
calling the router, which is what keeps the `L1` gate honest instead of
requiring a live port to prove anything.

**`PlatformState` is small and is not a junk drawer.** Installation
identity, platform version, when it was initialized, and the local
administrator. Domain state belongs to domains — `docs/ARCHITECTURE.md`
Part IV says `platform` must not own state a domain should own, and a
control-plane state object is exactly where that rule erodes first.

**`Approval` records a decision, not a workflow.** Who asked, for what,
who decided, when, and until when the decision stands. Risk classification
and the approval *flow* are Stage 6.2. What must exist now is the record,
because Stage 1.5 is the first mutating workflow and a mutation whose
approval was never recorded cannot be audited afterwards.

**`HealthReport` distinguishes three states, not two.** Healthy,
degraded and unknown. A source that has not reported since startup is not
healthy and is not failing, and `docs/ROADMAP.md` Part II §6 requires
unknown to stay unknown rather than resolve to a pass.

## ADAPTERS AFFECTED

- `adapters/http` — new. A standard-library server bound to loopback.
  Replaceable by anything that can call a router.
- `adapters/persistence` — unchanged, now assembled by `main` rather than
  by the test suite. That transition is the point of a composition root.

## PERSISTED STATE

First stage that holds any.

| Record | Key | Reconciliation |
|---|---|---|
| `PlatformState` | `current`, singleton | Loaded on startup; created on first run |
| `Approval` | approval id | Loaded on demand; never rewritten |

**Reconciliation on restart.** The startup path runs ordered phases and
produces a `StartupReport`. At this stage there are two phases: the store
reconciles itself, sweeping interrupted writes and reporting unreadable
records, and platform state is loaded or created. Every later stage
registers a phase here rather than adding a startup path of its own.

A defect reported by the store does not, by itself, stop startup — the
store returns facts and policy decides. The policy at this stage is to
surface defects in the report and continue, because refusing to start over
an unreadable record would make the platform impossible to diagnose through
its own API. That is a deliberate choice and it is recorded as debt, since
the right answer changes once records authorize things.

## MUTATION / FAILURE BOUNDARY

The only mutation is writing platform state on first run, through the
atomic path the kernel already provides.

What fails closed:

- an unreadable platform state record — refused, not recreated, because
  silently minting a new installation identity would orphan every record
  that referenced the old one;
- a route that does not exist — a structured `not_found`, never a guess;
- a handler that raises — rendered through the uniform error path with its
  stable code, never a stack trace on the wire;
- an unknown configuration key — already refused by the kernel.

## CANCELLATION / CLEANUP

Startup is idempotent and interruptible: it holds no lock, and a partial
run leaves either the previous platform state or none. The only orphan is
the kernel's temporary file, already swept by the store's own
reconciliation, which is the first phase.

The HTTP server binds a port. Failing to release it on shutdown would be a
real orphan, so the server is a context manager and there is a test that
the port is free afterwards.

## ACCEPTANCE LEVEL

**L1 — Contract**, which is the Milestone 0 gate. The stage touches no
hardware, no runtime and no capacity domain.

Evidence required to close:

- the API answers every endpoint from platform state, by calling the router
  directly;
- **startup succeeds on an empty state root with nothing installed**, and
  the resulting platform reports healthy;
- a second startup reuses the same installation identity rather than
  minting a new one;
- startup surfaces a store defect in its report and still serves;
- an unreadable platform state record refuses rather than recreating;
- unknown routes and raising handlers render as structured errors;
- the HTTP adapter serves the router and releases its port;
- the architecture harness passes with two new packages and the first
  composition root, and still forbids anything but `main` importing
  `adapters`;
- ruff and mypy strict clean.

**Milestone 0 also closes here**, which requires more than this stage: the
consolidation checkpoint comparing module count against concept count, and
a debt review. Both are part of this stage's output package.

## ADMIN SURFACE

This stage *is* the Admin surface's beginning. From here every stage adds
its endpoints to `api/routes.py`, and Stage 6.1 assembles a console over a
surface that already exists rather than commissioning one.

Two properties are set now and inherited. Every failure renders from a
kernel error code, so the API's error vocabulary is the platform's error
vocabulary. And every response is a `Result`, so a client parses one shape.

## DEBT ENTRIES

Expected:

| Item | Label | Retire when |
|---|---|---|
| No authentication; the local administrator is implicit and the API binds to loopback | `PROVISIONAL` | Stage 1.7 adds authentication hooks; Stage 5.1 makes identity real. **Must retire before the API is reachable off-host** |
| Startup continues despite store defects | `PROVISIONAL` | A record can authorize something — Milestone 2 — at which point an unreadable record must fail closed |
| Standard-library HTTP server, single-threaded, no TLS | `WORKING` | Concurrent administration is needed, or the API leaves loopback |
| No pagination on list endpoints | `DEFERRED` | A list can exceed a screen — the model catalogue at Stage 2.5 |

The first is the one that matters. An unauthenticated API is safe only
because it is bound to loopback, and that is a property of deployment
rather than of the code.

## DEFERRED ITEMS

- **Authentication and authorization enforcement** — hooks at Stage 1.7,
  real identity at Stage 5.1.
- **The approval workflow** — risk classification and the request-approve
  cycle are Stage 6.2. Only the record exists now.
- **The audit sink** — `AuditEvent` exists; emission begins at Stage 1.5
  with the first mutating workflow.
- **Structured logging and tracing** — deferred from Stage 0.1 to here, and
  deferred again: the correlation identifier that makes it useful exists,
  but nothing yet produces enough events to justify the machinery.
- **Mutating endpoints, pagination, API versioning beyond a prefix.**

---

## OUTPUT PACKAGE

**Output:** `PlatformState v1 + ControlPlaneShell v1` ·
**Acceptance:** `L1`, 233 tests ·
**Checkpoint:** `checkpoints/STAGE-0.3-control-plane-shell.json`

### What exists

| Module | Owns |
|---|---|
| `platform/contracts.py` | `PlatformState`, `Approval`, `HealthReport`, `ComponentHealth`, `StartupReport`, `PhaseReport`, `PlatformSettings` |
| `platform/ports.py` | `HealthSource`, `ReconcilePhase` |
| `platform/state.py` | Load-or-initialize, and the refusal to regenerate identity |
| `platform/startup.py` | The single ordered path, and the store's own phase |
| `platform/health.py` | Worst-status aggregation |
| `platform/approval.py` | The append-only decision log |
| `api/contracts.py` | `ApiRequest`, `ApiResponse`, `Method` |
| `api/router.py` | Dispatch, status mapping, the one error-rendering point |
| `api/routes.py` | Six read-only endpoints |
| `adapters/http/server.py` | A standard-library transport over the router |
| `main.py` | The first composition root |

### The check found a real violation in the first code written after it

`PlatformState` was written with `administrator: Subject` — an entity from
`identity` embedded directly. The reference-by-identifier check added in
Stage 0.2 rejected it, correctly: two packages would have owned one thing's
shape.

The fix was not to weaken the rule but to follow it, and following it
produced a better design. The administrator is now stored as its own
`identity.subject` record and referenced by `administrator_id`, which is
what Stage 5.1 needs anyway when subjects gain a directory. Startup writes
the subject *before* the state that points at it, since a state record
referencing a record that was never written is worse than no state at all,
and there is a test for the missing-subject case.

This is the strongest evidence available that the architecture tests earn
their keep: the first substantial code written after the check existed
violated it, and nobody noticed by reading.

### Decisions

**The HTTP server is an adapter; the API is not.** A handler is a function
from request to value. The router renders results and errors; the transport
only moves bytes. Two consequences: no web framework can come to own
routing, which Part II §9 forbids, and the whole surface is testable by
calling the router — so the Milestone 0 gate is proven at `L1` without
binding a port. The HTTP adapter is tested too, but for the things only it
can get wrong: serving, status mapping, and releasing its port.

**One error-rendering point.** No handler builds an error body, so no
handler can invent a code, and the API's error vocabulary is exactly the
kernel's. An unexpected exception renders as `internal` with its detail
withheld, because an error from inside a subsystem is as likely to carry a
filesystem path as anything a caller can use — there is a test that a leaked
path does not reach the wire.

**Startup reports; it does not adjudicate.** A phase that finds a defect
records it and the platform serves anyway, because the API is the surface an
administrator diagnoses through and refusing to start would remove it. That
is right while no record authorizes anything and wrong afterwards, so it is
`K-09` with Milestone 2 as its retirement condition rather than a permanent
choice.

**The installation identity is never regenerated.** An unreadable state
record refuses. Minting a fresh identity would orphan every record that
referenced the old one, silently, while the platform looked healthy.

**Health has four states and aggregates to the worst.** Unknown outranks
healthy, because a component nobody has asked has not passed; failing
outranks unknown, because a known failure is more actionable. A source whose
own health check raises is reported failing rather than dropped.

### Acceptance evidence

`L1`, 233 tests, ruff clean, mypy strict clean across 72 files.

The gate has three parts and each has a test. *Contracts serialize without
importing a runtime or provider library* — the kernel-purity and contract-isolation
tests. *The Platform API answers from platform state* — six endpoints, each
called through the router. *Contracts are minimal and boundaries are
intentional* — the consolidation census below, plus the tier, non-edge,
reference and host-scoping checks.

Beyond the gate, the tests worth naming: the platform starts with nothing
installed and reports healthy; a second start reuses the installation
identity and the administrator; an unreadable state record refuses rather
than recreating; a store defect is surfaced and the platform still serves; a
raising handler renders through its stable code; an unexpected exception
does not leak its detail; and the HTTP adapter releases its port, verified by
rebinding the same port afterwards.

### Milestone 0 close

**Consolidation checkpoint.** 18 packages, 35 modules, no near-synonymous
pairs. Every domain package holds exactly `contracts`; `kernel` holds its ten
declared concepts; `platform` holds six and `api` three, each a distinct
concept. For comparison, the previous attempt's `core/` reached 152 files
with eleven `storage_*` modules for one concept. The census test would have
failed on the day the second appeared.

**Debt review.** Eleven open entries, `K-01` to `K-11`. **None authorizes a
mutation**, so the burn-down gate in Part II §8 is satisfied and Milestone 0
closes clean. Two carry hard conditions: `K-03`, no migration engine, before
the first `schema_version` bump; `K-08`, no authentication, before the API is
reachable off-host.

**Roadmap amendments made during the milestone**, all recorded in
`docs/ROADMAP.md` in the commit that made them: Stage 0.1 gained the
unresolved-value semantic, the bytes unit rule, event correlation and the
architecture harness; Stage 0.2 gained `StoragePool`, `AuditEvent` and the
host-scoping rule; Stage 0.3 gained `Approval` and `HealthSource`; Stage 1.3
gained the component seam; Stage 1.5 begins audit emission. One module-map
amendment: `adapters/http`, added to `docs/ARCHITECTURE.md` in this commit.

### What Milestone 0 does not prove

Everything so far is `L1`. Thirty-one domain contracts describe hosts,
models, pools and instances that nothing has looked at. The control plane
starts, reconciles and answers questions about itself — and about nothing
else, because there is nothing else yet.

The next stage is the first that can be wrong in a way a test on this
machine cannot detect. Stage 1.1 runs host detection on the reference host
at `L2`, and from there to the Milestone 1 gate every claim is checked
against hardware. That gate — a real request reaching a real model and
returning an answer — is the one the previous attempt never reached after
58,706 lines.
