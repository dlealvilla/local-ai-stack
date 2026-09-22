"""Block 3 Steward — ownership, occupancy, and reclaimability.

Tier 2 classifies known roots. It does not delete, does not crawl
arbitrary mounts, and does not compute SAFE storage.
"""

from machi.steward.contracts import OccupancyMap
from machi.steward.events import (
    occupancy_observed,
    ownership_conflict,
    reclaimability_assessed,
    resource_classified,
)

__all__ = [
    "OccupancyMap",
    "occupancy_observed",
    "ownership_conflict",
    "reclaimability_assessed",
    "resource_classified",
]
