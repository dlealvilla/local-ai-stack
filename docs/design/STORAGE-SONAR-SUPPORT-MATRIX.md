# Storage Sonar support matrix

Stage 1.6L. Detection and native sources are architectural now. Technology-specific
probes are replaceable adapters. A missing probe is explicit; it is never silent
verification. The proprietary fallback (`EmpiricalStorageProbe`) characterizes
writable capacity **before** runtime or model selection when required.

**GET `/host` and `CapacityService.compute` never probe.** They consume stored
evidence only.

Legend:

| Implemented now | Meaning |
|---|---|
| yes | Adapter/contract exists and can run in this increment |
| fixture | Contract and tests exist; physical implementation deferred |
| identify | Detection only; no available-bytes figure |
| optional | Uses a system binary if present; never a mandatory Kultrun dependency |
| fallback | Empirical Storage Sonar may run when other evidence cannot authorize |

The 10% arbitration rule compares **available-to-available** on one domain:

`abs(native_available - probe_available) / max(native_available, probe_available)`

A heuristic 64 GiB disbelief ceiling may be recorded as a belief bound. It never
populates authorizing SAFE.

---

## Platforms

| Environment | Detection | Declared/native source | Technology-specific probe | Now? | Optional dependency? | Fallback Sonar | Confidence | Limitations / debt |
|---|---|---|---|---|---|---|---|---|
| Linux x86_64 | `host` OS/arch + mount family | `os.statvfs` (`posix-statvfs` native source); host `MountFacts.free_bytes` | linux-quota, fuse-identify, nfs-quota, moosefs-quota | yes | `quota`, `mfsgetquota`, NFS helpers optional | yes, live host only | medium | Numeric quota parse is best-effort |
| Linux ARM64 | same as x86_64 | same | same adapters; no arch-specific fork | yes | same | yes | medium | Physical ARM64 acceptance deferred |
| Windows / Windows Server | `os_name` windows/win32 | host mount facts; Win32 capacity deferred | `windows-capacity` | fixture | none | yes (when live Windows exists) | low | `GetDiskFreeSpaceEx` / NTFS quota: **K-100** |
| macOS / Apple Silicon | `os_name` darwin | `os.statvfs` native source | `macos-capacity` | fixture | none | yes | low | APFS/quota + `F_PREALLOCATE`: **K-28**, **K-101** |

---

## Filesystems and transports

| Environment | Detection | Declared/native source | Technology-specific probe | Now? | Optional dependency? | Fallback Sonar | Confidence | Limitations / debt |
|---|---|---|---|---|---|---|---|---|
| ext4 | mount `filesystem_type` | `statvfs` (credible local) | linux-quota | yes / optional | `quota` binary | no if native trusted | medium–high | Quota tool output not fully parsed |
| XFS | family allow-list | `statvfs` | linux-quota | yes / optional | `quota` | no if native trusted | medium | project quota parse deferred **K-102** |
| Btrfs | family allow-list | `statvfs` | linux-quota | yes / optional | `quota` | no if native trusted | medium | same |
| ZFS | family allow-list | `statvfs` | none specialized | identify via family | none | if unresolved | medium | dataset quota adapter **K-102** |
| APFS | darwin + family | `statvfs` | macos-capacity (fixture) | fixture | none | if needed | low | **K-101** |
| NTFS | windows + family | host facts | windows-capacity (fixture) | fixture | none | if needed | low | **K-100** |
| container overlay | overlay/overlayfs allow-list | `statvfs` (credible for this container) | none | yes as native | none | no if native trusted | medium | Nested mount longest-prefix binding |
| NFS | nfs/nfs4 | mount free; not an entitlement | nfs-quota | optional | `quota` / `nfsstat` | yes if no numeric probe | low | rquota numeric parse **K-103** |
| SMB/CIFS | cifs/smb* family | mount free; not an entitlement | none | identify | none | yes | low | SMB quota adapter **K-104** |
| FUSE | fuse/fuseblk/fuse.* | `statvfs` **not** an entitlement | fuse-identify | identify | none | **yes** unless a capacity probe settled bytes | low | 64 GiB is belief only; never SAFE |
| MooseFS | fuse + mfs device/family | FUSE lie possible | moosefs-quota | optional | `mfsgetquota` (not bundled; GPL) | yes if tool absent or unparsed | low | Numeric parse **K-105** |
| CephFS | ceph family | mount free; not an entitlement | none | identify | none | yes | low | Provider/ceph quota **K-106** |
| Kubernetes / container storage | overlay + CSI mounts as host facts | overlay credible; network volumes not | none specialized | partial | none | yes for non-credible | low | CSI/PVC quota **K-107** |
| Cloud / provider volumes | host mounts + future provider adapters | administrator bound; provider quota deferred | none | partial | none | yes | low | RunPod/cloud quota **K-108** |
| Unknown / proprietary | unrecognised family | reported free displayed, not authorizing | explicit `none` probe report | yes | none | **yes** | low | Fail closed |

---

## Probe registry behaviour

- `supports(environment)` then **always** `probe()` when compatible.
- No compatible probe → `ProbeReport(probe_name="none", compatible=False)`.
- `posix-statvfs` is a **native source**, not a corroborating technology probe (it would corroborate FUSE’s own lie).
- Empirical fallback does **not** run on local credible families merely because `quota` is absent.
- Empirical fallback **does** run for FUSE/NFS/unknown when no probe produced available bytes, and only on a live host (fixture replay never writes 25 GiB).
- Default empirical exploration ceiling is **25 GiB** (policy). Hitting it without failure means `lower ≥ 25 GiB`, `upper = UNKNOWN`. It does **not** mean `available = 25 GiB`.

---

## Dependencies reviewed (no new hard Python dependencies)

| Candidate | License | Maintenance | Portability | Bundling | Status |
|---|---|---|---|---|---|
| psutil | BSD-3 | active | good | would be a hard dep | **not added**; OS APIs used |
| quota-tools | GPL | distro | Linux | must not embed | optional system binary |
| FsQuota | various | niche | limited | not added | deferred |
| MooseFS `mfsgetquota` | GPL (MooseFS) | upstream | Linux | never bundled | optional |
| rquota / NFS tooling | various / GPL | distro | Linux | never bundled | optional |

Kultrun adds **no** new mandatory third-party package for Storage Sonar.
