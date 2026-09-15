# Provider-agnostic architecture audit

**Work token:** `MACHI-PROVIDER-AGNOSTIC-AUDIT`  
**Base:** accepted `2.2.1` `66e8ee0` (`checkpoint/machi-2.2.1-closed-66e8ee0`)  
**Branch:** `architecture/provider-agnostic-audit`  
**NVIDIA implemented:** NO

This is an audit and a bounded rewiring of seams that were already
leaking platform details into the wrong layer. It is not a provider
framework, not HostProfile, and not `2.3.1`.

Canonical rule: [ARCHITECTURE.md](ARCHITECTURE.md) §13.

## Verdict

Current Machi is **generic with bounded leaks**. Kernel, Install
ports, and Discover contracts were already capability-oriented.
Linux/macOS memory I/O lived in one adapter with Linux parsing in
domain; that is now split. Remaining gaps are unimplemented providers
and accepted POSIX publication primitives, not vendor-shaped domain
models.

## Findings

| Finding | Location | Layer | Classification | Severity | Why | Action |
|---|---|---|---|---|---|---|
| Kernel has no Discover/vendor imports | `src/machi/kernel/` | Kernel | A | NON_BLOCKING | Import law already holds | Keep architecture tests |
| Store port is exclusive create, not a filesystem | `kernel/store.py` | Kernel port | A | NON_BLOCKING | Port never named `os.link` | Documented; test forbids `os.link` on the port |
| FileStore uses `os.link` | `adapters/persistence/file_store.py` | Adapter | A / E | NON_BLOCKING | Correctly isolated; Server J (no hard links) will need another adapter or a truthful fail | Leave behavior; record debt |
| Marker exclusive create uses `os.link` | `install/marker.py` | Install domain | E | NON_BLOCKING | Same POSIX primitive inside accepted 1.3.1, not behind FileStore | Defer; fail-closed today |
| XDG `~/.local/state/machi` default | `install/defaults.py` | Install | E / C | NON_BLOCKING | Unix-shaped default; binder already injects `default_root` | Documented; Windows path policy deferred |
| `/var/lib/kultrun` refuse list | `install/binder.py` | Install | A | NON_BLOCKING | Collision guard, not a Machi path policy | Keep |
| OS/arch aliases in domain | `discover/normalize.py` | Discover domain | A | NON_BLOCKING | Pure map; unknown stays unrecognized; adapter owns `platform.*` | Keep |
| `OSFamily` / `CpuArchitecture` enums | `discover/contracts.py` | Contract | A | NON_BLOCKING | Capability vocabulary, not “this host is Linux so NVIDIA” | Keep |
| `MemorySource.linux_proc` / `sysconf` | `discover/contracts.py` | Contract | A | NON_BLOCKING | Provenance as data | Keep |
| Linux table parser in domain | was `discover/memory.py` | Domain leak | B | BLOCKING for next providers | Adding another OS reader would keep growing domain | **Fixed:** moved to `LinuxProcMemoryProvider` |
| sysconf conversion in domain | was `discover/memory.py` | Domain leak | B | BLOCKING for next providers | Same | **Fixed:** moved to `MacOSSysconfMemoryProvider` |
| OS branches inside one adapter | was `native_memory.py` | Adapter | E → A | NON_BLOCKING after fix | Replaceable, but not independently owned | **Fixed:** observer selects providers |
| Windows memory unimplemented | `NativeMemoryObserver` | Provider gap | C | NON_BLOCKING | Explicit `unsupported`, never `0` | Defer native Windows reader |
| Composition names adapters | `machi.main` | Composition | A | NON_BLOCKING | Intended wiring boundary | Test forbids naming Linux/macOS providers or NVIDIA in CLI |
| No NVIDIA/CUDA/NVML in production | `src/machi/` | — | A | NON_BLOCKING | 2.3.1 not started | Keep |
| No Docker/RunPod/sudo product requirement | production | — | A | NON_BLOCKING | Evidence docs mention hosts; product does not | Keep |
| `/workspace` in physical evidence only | `docs/machi/*PHYSICAL.md` | Harness/docs | D | NON_BLOCKING | Explicitly unused | Keep out of production |
| Roadmap named 2.3.1 as if it were the capability | ARCHITECTURE / ROADMAP | Docs | E | BLOCKING for 2.3.1 | NVIDIA would become the accelerator model | **Fixed:** 2.3 generic / 2.3.1 NVIDIA provider |
| No AcceleratorObservation code yet | — | Discover | C / E | NON_BLOCKING | Avoid locking a schema before the Component | Document seam; introduce contracts at 2.3 start, generic first |
| Available/swap/cgroup deferred | 2.2.1 | Discover | C | NON_BLOCKING | Distinct facts; do not collapse into physical total | Revisit at HostProfile/Capacity |
| Optional vendor deps | `pyproject.machi.toml` | Packaging | A | NON_BLOCKING | Runtime dependencies empty | Keep NVIDIA packages out of the base wheel |
| `amd64` CPU alias | `discover/normalize.py` | Domain | A | NON_BLOCKING | CPU name, not AMD GPU | Keep |
| Foundation/vLLM NVIDIA host in later roadmap | ROADMAP M5 | Future | E | NON_BLOCKING | Later physical target, not current domain | When M5 starts, keep native process first-class |
| JsonlJournal | `adapters/journal` | Adapter | A | NON_BLOCKING | Injected directory; no vendor | Keep |
| Tests use Darwin/Linux fixtures | `tests/machi` | Tests | A | NON_BLOCKING | Harness, not production assumption | Keep |

## Must fix before 2.3.1

Done in this branch:

- Linux/macOS memory I/O is provider-owned.
- Generic memory contract unchanged (`physical_total_bytes`).
- Docs name `2.3` as Accelerator Discovery.
- Architecture tests prevent domain/Kernel/CLI from owning `/proc/meminfo`, `os.link`, or NVIDIA.

Still required at the *start* of 2.3.1, not here: generic
`AcceleratorObservation` / `AcceleratorObserver` before any NVIDIA
module. Do not name the contract `NvidiaGpuObservation`.

## Safe deferred gaps

- Windows memory provider
- AMD/Intel/Apple accelerator providers
- Cgroup/execution memory limit as a distinct fact
- Available memory and swap
- Non-link Store adapter
- Marker writer behind a persistence adapter
- Windows/macOS Install path policy provider

## Infrastructure portability debt

- FileStore and SelfOwnershipMarker assume a POSIX link-capable
  filesystem for exclusive publish. Overlay Linux acceptance hosts
  support this. A filesystem without `os.link` must fail closed or
  use a different adapter — not a silent overwrite.
- Default state root is XDG-shaped. Composition can inject another
  default. Do not treat `~/.local/state/machi` as a Windows contract.
