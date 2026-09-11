"""Storage-capacity policy numbers owned by storage, not by a caller.

These are conservative starting points. They never become "available
capacity". The empirical probe ceiling is how far a search may physically
explore, not a claim that that many bytes exist.
"""

from __future__ import annotations

from typing import Final

_GIB: Final = 1024**3
_MIB: Final = 1024**2

#: Symmetric disagreement: abs(a-b)/max(a,b). Compare available-to-available.
DISAGREEMENT_RATIO: Final = 0.10

#: On an otherwise-trusted family, a native figure this large is not an
#: entitlement unless a specialist produced domain bytes. Not a product cap.
#: Compatible specialists still run below this (hidden quotas, FUSE, NFS).
NATIVE_ANOMALY_TRIGGER_BYTES: Final = 500 * _GIB

#: Probe names that echo OS-native statistics. Their bytes never beat
#: native and do not suppress the anomaly trigger.
NATIVE_CLASS_PROBE_NAMES: Final = frozenset(
    {
        "fuse-identify",
        "macos-capacity",
        "nfs-quota",
        "none",
        "posix-statvfs",
        "windows-capacity",
    }
)

#: One Sonar V2 unit in production. Tests inject a tiny unit_bytes.
SONAR_UNIT_BYTES: Final = _GIB

#: HOST-mode tree identity. Not a schema_version.
SONAR_ALGORITHM_VERSION: Final = "sonar-v2-tree"

#: Default maximum bytes the fallback empirical probe may physically write.
#: Hitting this without failure means lower bound >= this figure, upper unknown.
DEFAULT_MAX_EMPIRICAL_PROBE_BYTES: Final = 256 * _GIB

#: Display/belief ceiling for families whose reported size is not an entitlement.
#: Never authorizing SAFE.
DEFAULT_BELIEF_BOUND_BYTES: Final = 64 * _GIB

#: After Step 0 and truthful characterization, do not start a multi-gigabyte
#: stack below this authorizing SAFE figure. Ask the administrator first.
LOW_SPACE_THRESHOLD_BYTES: Final = 5 * _GIB

#: Kept back from authorizing capacity so a managed write cannot fill the
#: filesystem. Capacity envelope and foundation fit must use the same pair.
#: A fraction alone protects nothing on a small pool; a floor alone
#: protects nothing on a large one.
STORAGE_RESERVE_FRACTION: Final = 0.10
STORAGE_RESERVE_FLOOR_BYTES: Final = 5 * _GIB

#: Leave this much unexplored so a probe cannot be "fill until it breaks".
DEFAULT_EMERGENCY_RESERVE_BYTES: Final = 1 * _GIB

#: Real-write chunk size. Small enough to avoid giant in-memory buffers.
DEFAULT_PROBE_CHUNK_BYTES: Final = 8 * _MIB

#: Wall clock for one empirical search. Tests inject a smaller budget.
#: 256 GiB on slow FUSE may still exceed this; last checkpoint is kept.
DEFAULT_PROBE_TIMEOUT_SECONDS: Final = 3600.0

#: First real-write rung of the fallback search.
DEFAULT_FIRST_PROBE_BYTES: Final = 1 * _MIB

#: Smallest refinement step once a failure bracket exists.
DEFAULT_SEARCH_GRANULARITY_BYTES: Final = 64 * _MIB

#: Original plus five smaller reselections. Never a sixth.
MAX_STORAGE_REDUCTIONS: Final = 5

#: Multiplicative footprint ceiling: next = previous * 0.80.
#: Integer bytes use floor(original * 4^n / 5^n) so a candidate cannot
#: sneak above the intended ceiling.
REDUCTION_FACTOR_NUMERATOR: Final = 4
REDUCTION_FACTOR_DENOMINATOR: Final = 5

POLICY_VERSION: Final = "1.6L5.0-manual-grepl"
CREATED_BY: Final = "kultrun"
