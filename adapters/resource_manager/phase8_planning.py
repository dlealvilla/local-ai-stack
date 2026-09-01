"""Phase 8 planning provider for Resource Manager v1.

AI_DEPLOYMENT_PHASE9_RESOURCE_MANAGER_V1
"""

from __future__ import annotations

from typing import Any

from core.resource_reservation_bridge import (
    build_live_reservation_view,
)


class Phase8ReservationPlanningProvider:
    def build_view(
        self,
    ) -> dict[str, Any]:
        return build_live_reservation_view()
