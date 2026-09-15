# Machi full built-system provider / portability audit

**Work token:** `MACHI-FULL-BUILT-SYSTEM-AGNOSTIC-AUDIT`  
**Scope:** M0 → M1 → `2.1.1` → `2.2.1`  
**Forward development:** BLOCKED (`2.3` not started)  
**Physical tests this task:** none (`SERVER_NEEDED_NOW=NO`)  
**Canonical accepted `2.2.1`:** `66e8ee0` (`checkpoint/machi-2.2.1-closed-66e8ee0`)  
**Audit branch:** `architecture/provider-agnostic-audit`  
**Partial audit (do not promote alone):** `cd4b786`

This document is the authoritative architecture baseline for
everything Machi has actually built through Memory Discovery. The
earlier [PROVIDER-AGNOSTIC-AUDIT.md](PROVIDER-AGNOSTIC-AUDIT.md) is
retained as history.

## Verdict

`GENERIC_WITH_NON_BLOCKING_PROVIDER_GAPS`

Kernel, Install, and Discover **contracts** model capabilities.
Concrete OS, filesystem, and hardware access lives in adapters or in
the 1.3.1 local-file writer. Unsupported environments fail closed or
return `Unresolved` / `unsupported`. They do not invent zero, do not
require NVIDIA/Docker/RunPod/sudo, and do not make the first
acceptance host into product policy.

Gaps that remain are unimplemented providers and POSIX exclusive
publish in FileStore and the ownership-marker writer. Those are not
Kernel requirements.

**Does Kernel require POSIX hard links?** `NO`

## End-to-end flow

```text
BuildIdentity
   ↓
InstallRecord  ← Store port ← FileStore (os.link in adapter)
   ↓
StateRootBinding  ← binder; default_root injectable
   ↓
LocalOwnershipMarker  ← 1.3.1 writer (os.link in this component)
   ↓
Registry seed / InstallRun  ← Store port
   ↓
OSArchitectureObservation  ← NativeOSArchitectureObserver (platform.*)
   ↓
MemoryObservation  ← NativeMemoryObserver
                      ├─ LinuxProcMemoryProvider
                      └─ MacOSSysconfMemoryProvider
```

External providers enter at adapters (and at the 1.3.1 marker writer).
Generic domains consume ports and contracts.

```text
Kernel
  ↑
Install
  ↑
Discover
```

Adapters sit beside that chain. `machi.main` wires both sides.
Kernel imports no Install, Discover, adapters, OS provider, hardware
provider, or cloud provider.

## Classification key

- **A** generic / correct
- **B** concrete technology correctly isolated behind a provider
- **C** provider leak into a generic boundary
- **D** hard-coded environment assumption
- **E** implementation coverage gap
- **F** portability risk (works; another environment may expose it)

Severity: **BLOCKING** or **NON_BLOCKING**.

---

## Component input / output map

| Block | Component | Generic input | Generic output | External technology | Port / provider | Verdict |
|---|---|---|---|---|---|---|
| 0 | 0.1.1 Contract Registry | kind + version + dict | typed `Contract` or refuse | JSON-safe dicts (stdlib) | Kernel registry | A |
| 0 | 0.1.2 Unresolved | reason + optional detail | `Unresolved` / `Maybe` | none | Kernel semantic | A |
| 0 | 0.2.1 Typed IDs | none for mint | prefixed opaque id | `secrets.token_hex` | Kernel | A |
| 0 | 0.3.1 EventRecord | Block-owned payload + envelope fields | versioned event document | none | Kernel envelope | A |
| 0 | 0.3.2 Journal port | `EventRecord` | append order + defects | none (directory injected) | `Journal` protocol | A |
| 0 | 0.3.2 JsonlJournal | same | JSONL file | UTF-8 JSONL, `fsync`, LF | Journal adapter | B |
| 0 | 0.4.1 Store port | kind + key + `Contract` | exclusive create / get | none (root injected) | `Store` protocol | A |
| 0 | 0.4.1 FileStore | same | JSON files | POSIX `os.link` + `fsync` | Store adapter | B / E / F |
| 0 | 0.5.1 Privacy | explicit class | `PrivacyClass` | none; no vendor export | Kernel | A |
| 0 | clock / errors / build | — | UTC; typed errors; `BUILD.json` | stdlib | Kernel | A |
| 1 | 1.1.1 InstallIdentity | binding + marker + registry + `Store` + `BuildIdentity` | `InstallRecord` | none | Store port | A |
| 1 | 1.2.1 StateRootBinder | explicit / env / injected default | `StateRootBinding` | `pathlib`, `os.access` | `default_root` injection | A / E |
| 1 | 1.3.1 SelfOwnershipMarker | `StateRootBinding` | local marker evidence | POSIX `os.link` in writer | local file writer | A contract / E writer |
| 1 | 1.3.2 RegistrySeed | binding + marker evidence + `Store` | registry record | none | Store port | A |
| 1 | 1.4.1 InstallRunStore | `InstallRecord` + `Store` + `BuildIdentity` | `InstallRunRecord` | none | Store port | A |
| 2 | 2.1.1 OS/arch | none (observe host) | `OSArchitectureObservation` | `platform.system` / `machine` | `OSArchitectureObserver` → native adapter | A / B |
| 2 | 2.2.1 Memory | OS family | `MemoryObservation` | `/proc/meminfo`; sysconf | `MemoryObserver` → Linux / macOS providers | A / B / E |
| app | `machi.main` | CLI / env | wired services | names FileStore, JsonlJournal, native observers | composition root | A |

---

## Block 0 — Kernel

### 0.1.1 Contract Registry

**Purpose.** Versioned registration and fail-closed deserialization.  
**Input.** `(kind, schema_version)` + JSON-safe dict.  
**Output.** Typed `Contract` or `UnknownKindError` / `UnknownVersionError`.  
**External.** None beyond stdlib JSON types.  
**Finding.** Sizes must be `_bytes`. Unknown is refused, not half-loaded. No OS/vendor.  
**Fix.** None.  
**Status.** A

### 0.1.2 Unresolved

**Purpose.** Represent unknown / unmeasured / unsupported without fake zero.  
**Input.** `UnresolvedReason` + optional detail.  
**Output.** `Unresolved`; no truth value.  
**External.** None.  
**Finding.** Later Blocks use `unsupported` / `not_measured` truthfully (Windows memory).  
**Fix.** None.  
**Status.** A

### 0.2.1 Typed IDs

**Purpose.** Opaque prefixed identifiers.  
**Input.** Entropy from stdlib `secrets`.  
**Output.** Typed ids (`EventId`, `InstallId`, …). `HostId` exists as a type and is not minted yet.  
**External.** CSPRNG, not hostname/path/MAC.  
**Finding.** Environment-neutral.  
**Fix.** None.  
**Status.** A

### 0.3.1 EventRecord

**Purpose.** Generic envelope; Block owns payload meaning.  
**Input.** type, UTC time, privacy, payload contract, optional correlation ids.  
**Output.** `event_record@1`.  
**External.** None.  
**Finding.** `install_id` / `install_run_id` / `host_id` may be `Unresolved`. Privacy required. Paths omitted from public payloads.  
**Fix.** None.  
**Status.** A

### 0.3.2 Journal

**Purpose.** Append-oriented record of what happened.  
**Input.** `EventRecord`.  
**Output.** persisted records + `JournalDefect`s.  
**External.** Port: injected directory only. Adapter: JSONL file.  
**Finding.** Port is generic. `JournalDefect.line_number` wording is JSONL-shaped (**F NON_BLOCKING**); field left stable to avoid a schema restatement. JsonlJournal: UTF-8, LF as JSONL, `splitlines` accepts CRLF, file `fsync`, no flock, no directory `fsync`. `OSError` → `PersistenceError`.  
**Fix.** Port/adapter docstrings; architecture test that the port is not JsonlJournal.  
**Status.** A port / B adapter / F locator field

### 0.4.1 Store

**Purpose.** Exclusive create and typed get of current entity contracts.  
**Input.** caller-owned key + `Contract`.  
**Output.** `StoreCreateResult` / loaded contract.  
**External.** Port: injected root. Adapter: JSON files + POSIX link.  
**Finding.** Port requires exclusive create, **not** `os.link`. FileStore uses temp + `fsync` + `os.link` + directory `fsync`. Unsupported link → `PersistenceError` (fail closed). Kernel event meaning previously said “published a new file”.  
**Fix.** Meaning restated to “created a new record”; Store key docstring no longer defines Store as a filesystem.  
**Status.** A port / B adapter / E non-link backend / F network-FS

### 0.5.1 Privacy Classification

**Purpose.** Explicit event privacy.  
**Input.** chosen `PrivacyClass`.  
**Output.** enum on every event.  
**External.** No telemetry vendor, no export backend.  
**Finding.** Forbidden public_ops keys include secrets/env.  
**Fix.** None.  
**Status.** A

### Kernel cross-cutting

| Piece | Finding | Status |
|---|---|---|
| Clock | UTC; `SystemClock` is stdlib, not a vendor adapter | A |
| Errors | `PersistenceError` wraps OS errors at adapters | A |
| Build identity | `BUILD.json` artifact vs source checkout; no host identity | A |
| Import law | Kernel → no Install/Discover/adapters | A (tested) |

---

## Kernel persistence deep dive

### Journal

```text
Journal (generic port)
    ↓
JsonlJournal (one filesystem / JSONL provider)
```

- No `flock`.
- Append atomicity is “do not rewrite prior lines”, not a POSIX `O_APPEND` guarantee across NFS.
- Crash consistency: file `fsync` after append; parent directory not fsynced (**F NON_BLOCKING** adapter quality).

### Store

```text
Store (generic port: exclusive create)
    ↓
FileStore (one filesystem provider; uses os.link)
```

**Does Kernel require POSIX hard links?** `NO`

On APFS/ext4/XFS with hard links: FileStore works (local + physical evidence on Linux overlay hosts that support link).  
On overlayfs/NFS/SMB/FUSE/NTFS without reliable `os.link`: FileStore must fail closed or a future adapter must be selected (`PROVIDER_SELECTION_REQUIRED`). It must not silently overwrite.

Filesystem exception types do not appear on the Kernel port; adapters raise `PersistenceError` / `ConflictError`.

---

## Block 1 — Install

### 1.1.1 InstallRecord

**Purpose.** Stable installation identity.  
**Input.** `BuildIdentity`, ownership evidence, generic `Store`.  
**Output.** `InstallRecord` keyed by marker id.  
**External.** None.  
**Finding.** No FileStore, no Linux paths, no wheel-layout in the contract. Provenance is creation-build, not current host.  
**Fix.** Architecture tokens forbid `os.link` / `/proc` / nvidia in this module.  
**Status.** A

### 1.2.1 StateRootBinder

**Purpose.** Bind one state-root path.  
**Input.** explicit → `MACHI_STATE_ROOT` (via composition) → `default_root` or `platform_default_state_root()`.  
**Output.** `StateRootBinding`.  
**External.** Filesystem mkdir / writability.  
**Finding.** Binder does not read `os.environ`. Unix XDG-shaped default is **policy**, not a Kernel rule. `default_root` injection is the path-policy seam. Windows path convention is unimplemented (**E**, `PROVIDER_SELECTION_REQUIRED`). Refuses `/` and `/var/lib/kultrun`. `Path.resolve()` follows symlinks. `os.access(W_OK)` is imperfect on ACL-only Windows (**F**).  
**Fix.** None in code; documented. Do not add a path-provider class now.  
**Status.** A semantics / E Windows default / F ACL writability

### 1.3.1 SelfOwnershipMarker

**Purpose.** Local ownership evidence for one bound root.  
**Input.** `StateRootBinding`.  
**Output.** `LocalOwnershipMarker` + establishment flags.  
**External.** Writes `.machi-owner.json` via POSIX exclusive publish.  
**Finding.** Contract is generic (fingerprint, product, marker id). Copied-tree detection is fingerprint of the UTF-8 absolute path string after resolve. Implementation uses the same temp+`fsync`+`os.link` pattern as FileStore. Fail closed. No UID/GID/chmod product policy (`0o644` is the writer mode). No Windows ACL model.  
**Shared filesystem outcome:** **A** (leave independent) **+ C** (future non-link publisher is `PROVIDER_SELECTION_REQUIRED`). A Kernel helper would put POSIX in Kernel. An injected publisher would change accepted 1.3.1 construction without changing fail-closed semantics; that is deferred until a second publisher is actually selected.  
**Fix.** Writer docstring only.  
**Status.** A contract / E+F POSIX writer

### 1.3.2 RegistrySeed

**Purpose.** Control-plane registry half citing the marker.  
**Input.** binding + local establishment + `Store`.  
**Output.** `LocalOwnershipRegistryRecord`.  
**External.** None (Store adapter chosen by composition).  
**Finding.** Dual-evidence remains generic. No FileStore knowledge.  
**Status.** A

### 1.4.1 InstallRunStore

**Purpose.** Durable InstallRun keyed by InstallId.  
**Input.** `InstallRecord` + `Store` + `BuildIdentity`.  
**Output.** `InstallRunRecord`.  
**External.** None.  
**Finding.** Race: `ConflictError` then get winner. No PID, hostname, or flock in this component.  
**Status.** A

### Install filesystem / path

| Topic | Behavior | Class |
|---|---|---|
| Precedence | explicit → env value from composition → default | A |
| Default | `~/.local/state/machi` (Unix shape) | E Windows |
| Env | only `MACHI_STATE_ROOT`; not `XDG_STATE_HOME` | A |
| Normalization | `expanduser` + `resolve`; must be absolute | A |
| Symlinks | resolve to real directory; fingerprint uses resolved string | A / F |
| Case-insensitive FS | fingerprint is the resolved string; case folding not modeled | F NON_BLOCKING |
| Marker name | `.machi-owner.json` | A (product evidence name) |
| Hard links | marker writer + FileStore only | E / F |
| Network / FUSE / overlay | fail closed if link/write fails | F; must not overwrite |
| Read-only home | explicit / env root still works if writable | A (matrix I) |
| Root / sudo | not required | A |
| Docker / cloud | not required | A |

**Can a new path-policy provider be added without rewriting Install domain semantics?** YES — inject `default_root` (already).

---

## Block 2 — Discover

### 2.1.1 OS / architecture

```text
OSArchitectureObserver
  → NativeOSArchitectureObserver
  → platform.system() / platform.machine()
  → OSArchitectureObservation
```

**Finding.** Domain owns aliases and unknown/unrecognized. Adapter owns platform APIs. Presence is not support. `amd64` is a CPU alias, not AMD GPU. Do **not** split into Linux/macOS/Windows OS providers: `platform.*` is already a cross-platform native mechanism.  
**Status.** A / B

### 2.2.1 Memory

```text
MemoryObserver
  → NativeMemoryObserver
  → LinuxProcMemoryProvider | MacOSSysconfMemoryProvider
  → MemoryObservation
```

Consolidates the partial audit:

- Generic `physical_total_bytes`; never safe capacity.
- Linux `/proc/meminfo` MemTotal kB × 1024 in the Linux provider.
- macOS sysconf pages × page size in the macOS provider; Apple unified memory is not split into fake VRAM.
- Windows: `unsupported` + `Unresolved`, never `0`.
- Missing Linux table: `unobserved`, never `0`.
- Source/provenance is data (`linux_proc` / `sysconf`).
- No cgroup/available/swap in product.
- Composition wires `NativeMemoryObserver`, not the OS providers.

**Status.** A contract / B providers / E Windows memory

---

## Application composition

`machi.main` is the only production module that names:

- `FileStore`
- `JsonlJournal`
- `NativeOSArchitectureObserver`
- `NativeMemoryObserver`
- `StateRootBinder` / `SelfOwnershipMarker` / `RegistrySeed` / `InstallIdentity` / `InstallRunStore`

It does not name `LinuxProcMemoryProvider`, `MacOSSysconfMemoryProvider`, NVIDIA, Docker, or RunPod.

Domain modules do not construct those adapters. No DI framework.

---

## Packaging

| Item | State |
|---|---|
| `pyproject.machi.toml` runtime dependencies | empty |
| Optional provider extras | none (none required) |
| `import machi` | does not import adapters |
| `machi.main` | composition; may import adapters |
| Python | `>=3.11` |
| Wheel | `py3-none-any` |
| Unsupported-platform imports | Linux/macOS provider modules import stdlib only; Windows import of `NativeMemoryObserver` does not call `os.sysconf` |

Base import must not fail because an unused provider dependency is missing. Currently there are no such dependencies.

---

## Infrastructure assumption search

| Technology / assumption | Occurrences | Layer | Correct? | Action |
|---|---|---|---|---|
| Linux / darwin / windows / x86_64 / arm64 / amd64 / aarch64 | Discover contracts + normalize + providers | PRODUCT vocabulary / PROVIDER | Yes | Keep; unknown stays unrecognized |
| `platform.system` / `machine` | `native_os_arch.py` | PROVIDER | Yes | Keep in adapter |
| `/proc/meminfo` | Linux memory provider | PROVIDER | Yes | Domain/Kernel forbidden (tested) |
| `os.sysconf` | macOS memory provider | PROVIDER | Yes | Keep |
| `os.link` / `fsync` | FileStore, marker writer, JsonlJournal (`fsync` only) | PROVIDER / 1.3.1 writer | Yes if fail closed | Non-link backend deferred |
| `chmod` / mode `0o644` | FileStore + marker `os.open` | PROVIDER writer | Unix file mode | F; Windows may ignore |
| uid / gid / root / sudo | not in `src/machi` product policy | — | Yes | Keep out |
| `/tmp` | tests / tmp_path | TEST | Yes | Harness |
| `/workspace` | physical evidence docs (explicitly unused) | DOCUMENTATION / HARNESS | Yes | Keep out of product |
| RunPod / SSH / Ubuntu | physical evidence docs | HARNESS / DOCS | Yes | Not product |
| Docker / Podman / Kubernetes | not in production `src/machi` | — | Yes | Future Foundation adapters |
| NVIDIA / CUDA / NVML / ROCm / Metal / MPS | not implemented; docs name future 2.3.1 | DOCS | Yes | Do not start 2.3 here |
| Apple | macOS memory provider; not Metal | PROVIDER | Yes | Unified memory not faked |
| POSIX | FileStore + marker exclusive publish | PROVIDER | Fail closed | `PROVIDER_SELECTION_REQUIRED` for non-link |
| Internet | not required for M0–2.2.1 | PRODUCT | Yes | Air-gap representable |

---

## Server matrix (A–N)

| Env | Representable? | Implemented provider | Known blocker | Safe unsupported? | Physical evidence |
|---|---|---|---|---|---|
| A Ubuntu x86_64 bare metal | Yes | Linux OS/arch + Linux memory; FileStore if hard links | none architectural | n/a | 2.2.1 accepted on similar Linux (`66e8ee0` / `b341819` wheel) |
| B Ubuntu arm64 | Yes | same Linux providers; `aarch64`→`arm64` | none architectural | n/a | not specifically this audit |
| C Linux container, constrained memory | Yes as OS/arch + MemTotal | Linux memory reports **physical/system** total, not cgroup max | product does not expose cgroup | cgroup is deferred fact, not a lie if unused | harness noted cgroup ≪ MemTotal; **NON_BLOCKING debt** |
| D Linux VM without root | Yes | no root required | writable state root required | n/a | not specifically |
| E macOS Apple Silicon | Yes | native OS/arch + sysconf memory | FileStore/marker need hard links (APFS normally has them) | n/a | local tests; not the Linux physical pack |
| F Windows x86_64 | Partially | OS/arch via `platform`; memory `unsupported` | FileStore/marker `os.link`; Unix default path shape | memory: yes, `unsupported` | none |
| G POSIX hard-link FS | Yes | FileStore + marker writer | none | n/a | Linux physical used overlay that supported link |
| H no reliable hard links | Representable as fail closed | no alternate Store/marker publisher | exclusive publish fails | yes if error, **no** if overwrite | none |
| I read-only home, writable explicit root | Yes | binder precedence | none if explicit/env writable | n/a | not specifically |
| J network / FUSE / overlay | Representable | FileStore/journal/marker on that FS | link/fsync/locking semantics | fail closed required | `/workspace` FUSE existed and was **not** used |
| K air-gapped | Yes | no network in M0–2.2.1 | none | n/a | physical hosts were networked but product does not need net |
| L no accelerator | Yes | none implemented | none | n/a until 2.3 | n/a |
| M future NVIDIA | Representable later | **not implemented** | do not start here | n/a | none |
| N future AMD/Intel | Representable later | **not implemented** | do not start here | n/a | none |

---

## Provider coverage matrix

| Capability | Generic port | Generic contract | Provider | Implemented | Local tested | Physical accepted | Status |
|---|---|---|---|---|---|---|---|
| Journal | `Journal` | `EventRecord` / `JournalDefect` | JsonlJournal | Yes | Yes | M0 Linux | B |
| Store | `Store` | entity contracts | FileStore (`os.link`) | Yes | Yes | 0.4.1 Linux | B / E non-link |
| State-root default policy | binder `default_root` | `StateRootBinding` | Unix XDG-shaped function | Yes | Yes | 1.2.1 Linux | A / E Windows |
| Ownership marker publication | (component writer) | `LocalOwnershipMarker` | POSIX link writer | Yes | Yes | 1.3.1 Linux | E non-link |
| OS/arch observe | `OSArchitectureObserver` | `OSArchitectureObservation` | Native `platform.*` | Yes | Yes | 2.1.1 Linux | B |
| Memory observe | `MemoryObserver` | `MemoryObservation` | Linux `/proc` | Yes | Yes | 2.2.1 Linux | B |
| Memory observe | same | same | macOS sysconf | Yes | Yes (Darwin local) | not Linux pack | B |
| Memory observe | same | same | Windows | No | unsupported path tested | no | E |
| Accelerator | — | — | NVIDIA/AMD/Intel/Apple | **No** | — | — | not in scope |

---

## Shared filesystem publication

**Question:** one generic filesystem publication seam now?

**Outcome A** for this audit: FileStore and the marker writer stay independent. Both fail closed. Kernel must not own the primitive. Install must not import adapters.

**Outcome C** recorded: non-link Store adapter and alternative marker publisher are `PROVIDER_SELECTION_REQUIRED` when an environment without reliable hard links becomes a product target.

Not Outcome B: extracting a shared injected publisher now would change accepted 1.3.1 construction without removing a lie.

---

## Path policy

Existing `default_root` injection is sufficient. A Windows/macOS path provider can be added without rewriting bind precedence, ownership, or Store semantics.

---

## Provider Selection Gate

Documented in `ARCHITECTURE.md` §13, `MACHI_LEAD_DEVELOPER.md`, the Lead Developer agent, and `.cursor/rules/machi.mdc`.

Not invoked to invent providers during this audit.

---

## Physical revalidation (not run)

| Component | Changed in this full audit? | Observable behavior changed? | Prior physical still valid? | New physical needed? | Why |
|---|---|---|---|---|---|
| 0.1.1–0.3.1, 0.5.1 | docs/tests only | No | Yes | `NO_REVALIDATION` | no runtime change |
| 0.3.2 Journal | docstrings | No | Yes | `NO_REVALIDATION` | adapter unchanged |
| 0.4.1 Store | meaning text on proof event; FileStore unchanged | Event meaning text only | Yes | `NO_REVALIDATION` | FileStore publish path unchanged |
| 1.2.1–1.4.1 | docs / marker docstring / architecture tokens | No | Yes | `NO_REVALIDATION` | bind/own/seed/run unchanged |
| 2.1.1 | no | No | Yes | `NO_REVALIDATION` | native `platform.*` unchanged |
| 2.2.1 | no further change beyond `cd4b786` extraction | No vs accepted algorithm | Yes | `NO_REVALIDATION` | same MemTotal/sysconf math; layout-only move already on this branch |

`cd4b786` memory provider extraction remains behavior-preserving relative to accepted `b341819` / `66e8ee0`. Promoting this branch does not by itself require repeating Linux MemTotal proof.

---

## Technical debt register

### Required before next Block/component (`2.3`)

- Run the **Provider Selection Gate** for Accelerator Discovery (generic `AcceleratorObservation` / port **before** NVIDIA). Do not implement NVIDIA in this audit.
- Do not treat Linux+NVIDIA as the accelerator model.

### Required before commercial release

- Windows memory provider or an explicit supported-platform matrix that excludes Windows.
- Windows (and possibly macOS-standard) state-root path policy, or documented Unix-only install paths.
- Non-link Store and/or marker publisher if Windows/NTFS/NFS-without-link is in the supported matrix.
- Journal directory `fsync` / crash-consistency review if durability must exceed current JsonlJournal.
- Cgroup/execution memory limit as a **distinct** fact (not a replacement for physical total).
- Available memory and swap as distinct facts.

### Provider coverage gaps

| Gap | Owner | Reason | Severity | Revisit when |
|---|---|---|---|---|
| Windows memory | 2.2.1 | `unsupported` today | NON_BLOCKING | Windows is a product target |
| Non-link FileStore | 0.4.1 | POSIX link | NON_BLOCKING | FS without hard links must work |
| Non-link marker publisher | 1.3.1 | POSIX link | NON_BLOCKING | same |
| Windows path default | 1.2.1 | XDG-shaped default | NON_BLOCKING | Windows install UX |
| Accelerator vendors | 2.3 | not started | n/a | after this audit is reviewed |
| Alternate Journal | 0.3.2 | JSONL only | NON_BLOCKING | if JSONL is not acceptable |

### Physical acceptance gaps

- macOS FileStore/marker/memory not in the Linux physical pack.
- Windows none.
- arm64 Linux none specifically.
- Constrained-cgroup memory is harness-only.

### Safe future enhancements

- Injected exclusive-publish port for 1.3.1 when a second publisher is selected.
- `JournalDefect` locator rename in a new schema version if a non-line journal ships.
- Optional extras for heavy vendor SDKs (must not become base-wheel dependencies).

---

## Contract stability

No product schema kind/version bump. One fingerprint meaning restatement:

- `kernel.store.proved@1` field `created`: “published a new file” → “created a new record”.

`MemoryObservation` / `OSArchitectureObservation` / Install contracts unchanged.
