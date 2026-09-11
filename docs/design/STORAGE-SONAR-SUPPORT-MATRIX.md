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
| fallback | Empirical Storage Sonar runs on every expensive characterization to confirm or replace specialist bytes |

The 10% arbitration rule compares **available-to-available** on one domain:

`abs(native_available - probe_available) / max(native_available, probe_available)`

A heuristic 64 GiB disbelief ceiling may be recorded as a belief bound. It never
populates authorizing SAFE.

---

## Platforms

| Environment | Detection | Declared/native source | Technology-specific probe | Now? | Optional dependency? | Fallback Sonar | Confidence | Limitations / debt |
|---|---|---|---|---|---|---|---|---|
| Linux x86_64 | `host` OS/arch + mount family | `os.statvfs` (`posix-statvfs` native source); host `MountFacts.free_bytes` | linux-quota, fuse-identify, nfs-quota, moosefs-quota, zfs-dataset, cephfs-quota | yes | `quota`, `mfsgetquota`, `zfs` optional | yes, live host only | medium | Fixture parsers; physical K-105/K-102 remain OPEN |
| Linux ARM64 | same as x86_64 | same | same adapters; no arch-specific fork | yes | same | yes | medium | Physical ARM64 acceptance deferred |
| Windows / Windows Server | `os_name` windows/win32 | `GetDiskFreeSpaceExW` live on win32; else host mount facts | `windows-capacity` (native-class) | yes on win32 | none | yes (when live Windows exists) | medium | NTFS quota still **K-100** |
| macOS / Apple Silicon | `os_name` darwin | `os.statvfs` native source | `macos-capacity` | identify | none | yes if native is anomalous or untrusted | low | APFS/quota + `F_PREALLOCATE`: **K-28**, **K-101** |

---

## Filesystems and transports

| Environment | Detection | Declared/native source | Technology-specific probe | Now? | Optional dependency? | Fallback Sonar | Confidence | Limitations / debt |
|---|---|---|---|---|---|---|---|---|
| ext4 | mount `filesystem_type` | `statvfs` (credible local ≤500 GiB) | linux-quota | yes / optional | `quota` binary | yes on expensive path (confirms or replaces) | medium–high | Hidden project quota still **K-102** |
| XFS | family allow-list | `statvfs` | linux-quota | yes / optional | `quota` | yes on expensive path | medium | project quota parse deferred **K-102** |
| Btrfs | family allow-list | `statvfs` | linux-quota | yes / optional | `quota` | yes on expensive path | medium | qgroups **K-102** |
| ZFS | family allow-list | `statvfs` | zfs-dataset | yes / optional | `zfs` | if unresolved | medium | physical L2 **K-102** |
| APFS | darwin + family | `statvfs` | macos-capacity (not entitlement) | identify | none | if native >500 GiB | low | **K-101** |
| NTFS | windows + family | GetDiskFreeSpaceExW / host facts | windows-capacity (native-class) | yes on win32 | none | if native >500 GiB | medium | NTFS quota **K-100** |
| container overlay | overlay/overlayfs allow-list | `statvfs` (credible for this container) | none | yes as native | none | yes on expensive path | medium | Nested mount longest-prefix binding |
| NFS | nfs/nfs4 | mount free; not an entitlement | nfs-quota | optional | `quota` / `nfsstat` | yes if no numeric probe | low | rquota numeric parse **K-103** |
| SMB/CIFS | cifs/smb* family | mount free; not an entitlement | none | identify | none | yes | low | SMB quota adapter **K-104** |
| FUSE | fuse/fuseblk/fuse.* | `statvfs` **not** an entitlement | fuse-identify | identify | none | **yes** on expensive path | low | 64 GiB is belief only; never SAFE |
| MooseFS | fuse + mfs device/family | FUSE lie possible | moosefs-quota | optional | `mfsgetquota` (not bundled; GPL) | yes (confirms specialist or fills in) | low | Fixture parse; physical **K-105** |
| CephFS | ceph family | mount free; not an entitlement | cephfs-quota | yes / xattr | none | yes if no xattr | low | physical **K-106** |
| Kubernetes / container storage | overlay + CSI mounts as host facts | overlay credible; network volumes not | none specialized | partial | none | yes for non-credible | low | CSI/PVC quota **K-107** |
| Cloud / provider volumes | host mounts + future provider adapters | administrator bound; provider quota deferred | none | partial | none | yes | low | RunPod/cloud quota **K-108** |
| Unknown / proprietary | unrecognised family | reported free displayed, not authorizing | explicit `none` probe report | yes | none | **yes** | low | Fail closed |

---

## Probe registry behaviour

- `supports(environment)` then **always** `probe()` when compatible (cheap specialists; not gated on 500 GiB).
- No compatible probe → `ProbeReport(probe_name="none", compatible=False)`.
- `posix-statvfs` and `GetDiskFreeSpaceExW` are **native sources**, not specialist entitlements.
- Specialist remaining bytes always beat generic native until Sonar
  confirms or disagrees. 10% is diagnostic between native and the chosen
  figure, and is the confirmation ratio between specialist and Sonar.
- Native on a trusted-local family may authorize only at or below 500 GiB
  when no specialist produced domain bytes **and** Sonar could not
  characterize (cheap GET never Sonars).
- Empirical Sonar **always** runs on the expensive path when a live probe
  is injected. Cheap GET / `kultrun host` never writes 16–256 GiB.
- Hitting the top tier without failure means `lower ≥ 256 GiB`,
  `upper = UNKNOWN`. It does **not** mean `available = 256 GiB`.
- Production unit is 1 GiB; tests inject a tiny `unit_bytes`. The owned
  reserve is 1 GiB in production and is not SAFE.

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
