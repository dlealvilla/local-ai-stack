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

#: Default maximum bytes the fallback empirical probe may physically write.
#: Hitting this without failure means lower bound >= this figure, upper unknown.
DEFAULT_MAX_EMPIRICAL_PROBE_BYTES: Final = 25 * _GIB

#: Display/belief ceiling for families whose reported size is not an entitlement.
#: Never authorizing SAFE.
DEFAULT_BELIEF_BOUND_BYTES: Final = 64 * _GIB

#: After Step 0 and truthful characterization, do not start a multi-gigabyte
#: stack below this authorizing SAFE figure. Ask the administrator first.
LOW_SPACE_THRESHOLD_BYTES: Final = 5 * _GIB

#: Leave this much unexplored so a probe cannot be "fill until it breaks".
DEFAULT_EMERGENCY_RESERVE_BYTES: Final = 1 * _GIB

#: Real-write chunk size. Small enough to avoid giant in-memory buffers.
DEFAULT_PROBE_CHUNK_BYTES: Final = 8 * _MIB

#: Wall clock for one empirical search. Tests inject a smaller budget.
DEFAULT_PROBE_TIMEOUT_SECONDS: Final = 600.0

#: First real-write rung of the fallback search.
DEFAULT_FIRST_PROBE_BYTES: Final = 1 * _MIB

#: Smallest refinement step once a failure bracket exists.
DEFAULT_SEARCH_GRANULARITY_BYTES: Final = 64 * _MIB

#: Original plus three smaller reselections. Never a fourth.
MAX_STORAGE_REDUCTIONS: Final = 3

#: Peak-budget caps for reduction 0..3. Reselection must pick a real candidate.
REDUCTION_PEAK_CAPS: Final = (1.00, 0.70, 0.49, 0.343)

POLICY_VERSION: Final = "1.6L.0-storage-sonar"
CREATED_BY: Final = "kultrun"
