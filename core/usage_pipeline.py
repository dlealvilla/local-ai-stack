import threading
import time

from core.retention import (
    apply_usage_retention,
)


class UsagePipeline:
    """
    Coordinate persistence, retention and future export.

    Gateway responsibility:
        emit UsageEvent

    Pipeline responsibility:
        store / retain / optionally export

    This prevents the Gateway from depending on analytics
    storage duration or destination.
    """

    def __init__(
        self,
        *,
        config,
        usage_store,
        usage_exporter,
    ):
        self.config = config
        self.usage_store = (
            usage_store
        )
        self.usage_exporter = (
            usage_exporter
        )

        self._retention_lock = (
            threading.Lock()
        )

        self._last_retention = 0.0


    def record(
        self,
        event,
    ):
        self.usage_store.append_event(
            event,
            self.config,
        )

        self.apply_retention_if_due()

        analytics = self.config[
            "analytics"
        ]

        if analytics.get(
            "export_enabled",
            False,
        ):
            # FUTURE:
            # Replace with asynchronous durable export queue.
            self.usage_exporter.export_event(
                event,
                self.config,
            )


    def apply_retention_if_due(
        self,
        *,
        force=False,
    ):
        """
        Check retention at most hourly unless explicitly forced.

        PROVISIONAL:
        Later this may move to a scheduler or database TTL.
        """

        now = time.monotonic()

        if (
            not force
            and now
            - self._last_retention
            < 3600
        ):
            return None

        with self._retention_lock:

            now = time.monotonic()

            if (
                not force
                and now
                - self._last_retention
                < 3600
            ):
                return None

            result = (
                apply_usage_retention(
                    config=self.config,
                    usage_store=(
                        self.usage_store
                    ),
                )
            )

            self._last_retention = now

            return result
