"""Focused tests for the probe-size ceiling seam.

Host characterization is bounded by iteration budgets rather than by
probe size, so it must be able to request probes larger than the
configured `probe_max_gb`. Existing callers must keep the configured
ceiling exactly as before.

Deterministic by construction: the ceiling is configured down to a few
mebibytes so the "above the ceiling" and "unbounded" paths are both
exercised with real `posix_fallocate` calls costing a few megabytes,
rather than by writing tens of gibibytes.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.storage_probe import (
    USE_CONFIGURED_PROBE_CEILING,
    probe_required_capacity,
)

MIB = 1024 * 1024

# The probe reserves space with posix_fallocate, which macOS does not
# provide. Ceiling arithmetic is platform independent and always
# tested; the paths that actually reserve bytes run on Linux.
requires_fallocate = unittest.skipUnless(
    hasattr(os, "posix_fallocate"),
    "posix_fallocate is unavailable on this platform",
)


class ProbeCeilingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.config = {
            "platform": {
                "data_root": self.tmp.name,
            },
            "storage_capacity": {
                "probe_enabled": True,
                # A 4 MiB ceiling keeps every path cheap.
                "probe_max_gb": 4 / 1024,
                "probe_directory": "data/capacity-probes",
            },
        }

    def probe_dir(self):
        return (
            Path(self.tmp.name)
            / "data"
            / "capacity-probes"
        )

    def assert_no_artifacts(self):
        directory = self.probe_dir()

        if not directory.exists():
            return

        self.assertEqual(
            sorted(
                entry.name
                for entry in directory.iterdir()
            ),
            [],
        )

    def test_configured_ceiling_applies_when_omitted(self):
        # Existing callers pass no ceiling argument and must keep
        # today's behaviour exactly.
        result = probe_required_capacity(
            8 * MIB,
            config=self.config,
        )

        self.assertFalse(result["success"])
        self.assertEqual(
            result["reason"],
            "probe_limit_exceeded",
        )
        self.assertEqual(
            result["max_probe_bytes"],
            4 * MIB,
        )
        self.assert_no_artifacts()

    def test_sentinel_is_identical_to_omitting_the_argument(self):
        omitted = probe_required_capacity(
            8 * MIB,
            config=self.config,
        )

        explicit = probe_required_capacity(
            8 * MIB,
            config=self.config,
            max_probe_bytes=(
                USE_CONFIGURED_PROBE_CEILING
            ),
        )

        self.assertEqual(
            omitted["reason"],
            explicit["reason"],
        )
        self.assertEqual(
            omitted["max_probe_bytes"],
            explicit["max_probe_bytes"],
        )

    @requires_fallocate
    def test_none_removes_the_ceiling_entirely(self):
        # The same request that was refused above now runs for real.
        result = probe_required_capacity(
            8 * MIB,
            config=self.config,
            max_probe_bytes=None,
        )

        self.assertTrue(result["supported"])
        self.assertTrue(result["success"])
        self.assertTrue(
            result["reservation_accepted"]
        )
        self.assertEqual(
            result["requested_bytes"],
            8 * MIB,
        )
        self.assertIsNone(result["reason"])

        # The temporary reservation is still removed.
        self.assert_no_artifacts()

    @requires_fallocate
    def test_explicit_integer_ceiling_is_honoured(self):
        # Above the supplied ceiling: refused.
        refused = probe_required_capacity(
            8 * MIB,
            config=self.config,
            max_probe_bytes=6 * MIB,
        )

        self.assertEqual(
            refused["reason"],
            "probe_limit_exceeded",
        )
        self.assertEqual(
            refused["max_probe_bytes"],
            6 * MIB,
        )

        # Within it: allowed, even though it exceeds the configured
        # 4 MiB value.
        allowed = probe_required_capacity(
            5 * MIB,
            config=self.config,
            max_probe_bytes=6 * MIB,
        )

        self.assertTrue(allowed["success"])
        self.assert_no_artifacts()

    @requires_fallocate
    def test_within_the_configured_ceiling_still_probes(self):
        result = probe_required_capacity(
            1 * MIB,
            config=self.config,
        )

        self.assertTrue(result["success"])
        self.assertEqual(
            result["method"],
            "posix_fallocate",
        )
        self.assert_no_artifacts()

    def test_invalid_ceiling_is_rejected(self):
        for value in (0, -1):
            with self.assertRaises(ValueError):
                probe_required_capacity(
                    1 * MIB,
                    config=self.config,
                    max_probe_bytes=value,
                )

    def test_disabled_probe_still_short_circuits(self):
        config = dict(self.config)
        config["storage_capacity"] = dict(
            self.config["storage_capacity"]
        )
        config["storage_capacity"][
            "probe_enabled"
        ] = False

        result = probe_required_capacity(
            1 * MIB,
            config=config,
            max_probe_bytes=None,
        )

        self.assertFalse(result["success"])
        self.assertEqual(
            result["reason"],
            "probe_disabled",
        )

    def test_invalid_request_sizes_are_still_rejected(self):
        for value in (0, -1):
            with self.assertRaises(ValueError):
                probe_required_capacity(
                    value,
                    config=self.config,
                    max_probe_bytes=None,
                )


class CalibrationCallerCompatibilityTests(unittest.TestCase):
    def test_calibration_does_not_pass_a_ceiling(self):
        # The existing calibration coordinator calls the probe without
        # a ceiling argument, so it keeps the configured limit.
        import inspect

        import core.storage_capacity_calibration as module

        source = inspect.getsource(module)

        self.assertIn(
            "probe_required_capacity(",
            source,
        )
        self.assertNotIn("max_probe_bytes=", source)


if __name__ == "__main__":
    unittest.main()
