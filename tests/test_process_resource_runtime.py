from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest

from adapters.resource_manager.process_runtime import (
    ProcessExecutorRuntime,
    ProcessIdentityError,
    ProcessRuntimeError,
)


class StaticSpecProvider:
    def build(
        self,
        *,
        model_id,
        metadata,
    ):
        return {
            "model_id": model_id,
            "metadata": dict(metadata),
        }


class SyntheticPopenExecutor:
    """Test-only executor that behaves like existing ProcessExecutor.start."""

    def start(
        self,
        service_spec,
    ):
        return subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(60)",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


class BrokenExecutor:
    def start(
        self,
        service_spec,
    ):
        return None


class ProcessExecutorRuntimeTests(unittest.TestCase):
    def make_runtime(
        self,
        executor=None,
    ):
        return ProcessExecutorRuntime(
            executor=(
                executor
                or SyntheticPopenExecutor()
            ),
            service_spec_provider=
                StaticSpecProvider(),
            stop_timeout_seconds=5,
            poll_interval_seconds=0.05,
        )

    def test_start_captures_durable_process_identity(self):
        runtime = self.make_runtime()

        state = runtime.start(
            workload_id="workload-a",
            model_id="model-a",
            metadata={},
        )

        try:
            self.assertEqual(
                state["runtime_kind"],
                "process_executor",
            )

            self.assertGreater(
                state["pid"],
                1,
            )

            self.assertIsInstance(
                state["proc_start_ticks"],
                int,
            )

            self.assertTrue(
                state["command_sha256"]
            )

        finally:
            runtime.stop(
                workload_id="workload-a",
                model_id="model-a",
                runtime_state=state,
            )

    def test_stop_terminates_exact_started_process(self):
        runtime = self.make_runtime()

        state = runtime.start(
            workload_id="workload-a",
            model_id="model-a",
            metadata={},
        )

        pid = state["pid"]

        runtime.stop(
            workload_id="workload-a",
            model_id="model-a",
            runtime_state=state,
        )

        time.sleep(0.05)

        with self.assertRaises(
            ProcessLookupError
        ):
            os.kill(
                pid,
                0,
            )

    def test_stop_is_idempotent_if_process_already_exited(self):
        runtime = self.make_runtime()

        state = runtime.start(
            workload_id="workload-a",
            model_id="model-a",
            metadata={},
        )

        runtime.stop(
            workload_id="workload-a",
            model_id="model-a",
            runtime_state=state,
        )

        runtime.stop(
            workload_id="workload-a",
            model_id="model-a",
            runtime_state=state,
        )

    def test_pid_identity_mismatch_fails_closed(self):
        runtime = self.make_runtime()

        state = runtime.start(
            workload_id="workload-a",
            model_id="model-a",
            metadata={},
        )

        bad_state = dict(state)
        bad_state["proc_start_ticks"] += 1

        try:
            with self.assertRaises(
                ProcessIdentityError
            ):
                runtime.stop(
                    workload_id="workload-a",
                    model_id="model-a",
                    runtime_state=bad_state,
                )

        finally:
            runtime.stop(
                workload_id="workload-a",
                model_id="model-a",
                runtime_state=state,
            )

    def test_bad_executor_return_is_rejected(self):
        runtime = self.make_runtime(
            executor=BrokenExecutor()
        )

        with self.assertRaises(
            ProcessRuntimeError
        ):
            runtime.start(
                workload_id="workload-a",
                model_id="model-a",
                metadata={},
            )


if __name__ == "__main__":
    unittest.main()
