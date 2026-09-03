"""Tests for the llmfit model-evaluation adapter.

The subprocess is injected, so these tests cover the two things that
actually matter and would be expensive to prove against the real binary:
that the capacity handed to llmfit is the platform's *safe* figure
rather than anything it could detect itself, and that every way the tool
can fail degrades to "unavailable" instead of raising.

The JSON fixture is trimmed from real `llmfit recommend --json` output
captured on the reference host.
"""

from __future__ import annotations

import json
import subprocess
import unittest
from unittest import mock

import adapters.model_evaluation.llmfit as llmfit

from core.capacity_contracts import (
    build_capacity_envelope,
)
from core.resource_capacity import build_resource_capacity
from core.resource_reservation_bridge import (
    reservation_capacities_from_resource_safety,
)
from core.resource_reservations import (
    ResourceReservationLedger,
)
from core.resource_safety import build_resource_safety

GIB = 1024 ** 3
MIB = 1024 * 1024

HOST_RAM_TOTAL = 811_121_754_112
HOST_RAM_AVAILABLE = 664_193_302_528
HOST_VRAM_TOTAL = 34_207_694_848
HOST_VRAM_FREE = 33_688_649_728

SAFE_VRAM = 30_267_880_244
SAFE_RAM = 583_081_127_117


class Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def snapshot(*, accelerators=None):
    if accelerators is None:
        accelerators = [
            {
                "index": 0,
                "vendor": "nvidia",
                "name": "NVIDIA GeForce RTX 5090",
                "memory": {
                    "total_bytes": HOST_VRAM_TOTAL,
                    "used_bytes": (
                        HOST_VRAM_TOTAL
                        - HOST_VRAM_FREE
                    ),
                    "free_bytes": HOST_VRAM_FREE,
                },
            },
        ]

    return {
        "schema_version": 1,
        "generated_at": "2026-09-03T12:00:00+00:00",
        "host": {
            "operating_system": "Linux",
            "architecture": "x86_64",
            "cpu_model": "AMD EPYC 9354 32-Core Processor",
            "cpu_cores": 128,
        },
        "memory": {
            "total_bytes": HOST_RAM_TOTAL,
            "used_bytes": (
                HOST_RAM_TOTAL - HOST_RAM_AVAILABLE
            ),
            "available_bytes": HOST_RAM_AVAILABLE,
            "availability_source": (
                "/proc/meminfo:MemAvailable"
            ),
        },
        "accelerators": accelerators,
        "storage": {
            "path": "/workspace",
            "total_bytes": 1_000_000_000_000,
            "used_bytes": 0,
            "free_bytes": 1_000_000_000_000,
            "scope": "mounted_filesystem_observation",
            "quota_known": False,
        },
        "workload": {
            "selected_model_ids": [],
            "running_model_ids": [],
            "loaded_model_ids": [],
            "reservations": None,
        },
    }


def envelope(
    *,
    accelerators=None,
    reserved_vram_bytes=0,
    with_reservations=True,
):
    snap = snapshot(accelerators=accelerators)
    safety = build_resource_safety(
        build_resource_capacity(snap)
    )

    reservation_snapshot = None

    if with_reservations:
        ledger = ResourceReservationLedger(
            reservation_capacities_from_resource_safety(
                safety
            )
        )

        if reserved_vram_bytes:
            ledger.reserve(
                "existing",
                {
                    "accelerator:0:memory": (
                        reserved_vram_bytes
                    ),
                },
            )

        reservation_snapshot = (
            ledger.snapshot().to_dict()
        )

    return build_capacity_envelope(
        capacity_snapshot=snap,
        resource_safety=safety,
        reservation_snapshot=reservation_snapshot,
    )


class Candidate:
    """Minimal stand-in for core.model_selection.SelectionCandidate."""

    def __init__(self, candidate_id, evaluation_id=None):
        self.candidate_id = candidate_id
        self.evaluation_id = evaluation_id

    @property
    def provider_identity(self):
        return (
            self.evaluation_id or self.candidate_id
        )


SYSTEM = {
    "backend": "CUDA",
    "cpu_cores": 128,
    "cpu_name": "AMD EPYC 9354 32-Core Processor",
    "gpu_count": 1,
}


#
# Trimmed from real `llmfit --json info "<model>"` output captured on
# the reference host, which wraps one model in the same envelope the
# other subcommands use.
#
REAL_MODELS = {
    "Ar4ikov/Qwen3.8-27B-AWQ-W4A16-ASYM": {
        "name": (
            "Ar4ikov/Qwen3.8-27B-AWQ-W4A16-ASYM"
        ),
        "provider": "Ar4ikov",
        "parameter_count": "24.4B",
        "fit_level": "Perfect",
        "run_mode": "GPU",
        "runtime": "vLLM",
        "score": 100.0,
        "score_components": {
            "context": 100.0,
            "fit": 100.0,
            "quality": 100.0,
            "speed": 100.0,
        },
        "best_quant": "AWQ-4bit",
        "memory_required_gb": 15.49,
        "memory_available_gb": 28.19,
        "utilization_pct": 51.1,
        "notes": ["GPU: model loaded into VRAM"],
    },
    "Qwen/Qwen3-8B-AWQ": {
        "name": "Qwen/Qwen3-8B-AWQ",
        "provider": "Qwen",
        "parameter_count": "8.2B",
        "fit_level": "Perfect",
        "runtime": "vLLM",
        "score": 91.0,
        "score_components": {
            "context": 90.0,
            "fit": 100.0,
            "quality": 85.0,
            "speed": 95.0,
        },
        "best_quant": "AWQ-4bit",
        "memory_required_gb": 6.7,
        "memory_available_gb": 28.19,
        "utilization_pct": 23.8,
        "notes": [],
    },
}


def requested_identity(command):
    """The model an `info` invocation asked about."""

    return command[command.index("info") + 1]


def real_runner(models=None):
    """Answer each `info` call with that model, as llmfit does."""

    known = REAL_MODELS if models is None else models

    def runner(command, timeout):
        identity = requested_identity(command)

        if identity not in known:
            # llmfit exits non-zero for an unknown model.
            return Completed(
                returncode=1,
                stderr=f"model not found: {identity}",
            )

        return Completed(
            stdout=json.dumps(
                {
                    "system": SYSTEM,
                    "models": [known[identity]],
                }
            )
        )

    return runner


def ready_runtime(fn):
    """Pretend llmfit is provisioned."""

    return mock.patch.object(
        llmfit,
        "runtime_is_ready",
        lambda name: True,
    )(
        mock.patch.object(
            llmfit,
            "runtime_executable",
            lambda name: (
                "/opt/ai-stack/runtime/llmfit/.venv/bin/llmfit"
            ),
        )(fn)
    )


class CapacityAuthorityTests(unittest.TestCase):
    """The platform decides what memory llmfit is told about."""

    def test_overrides_use_safe_not_physical_capacity(self):
        flags, used = llmfit.build_overrides(
            envelope()
        )

        expected_mib = SAFE_VRAM // MIB

        self.assertIn(
            f"--memory={expected_mib}M",
            flags,
        )
        self.assertEqual(
            used["primary_memory_bytes"],
            SAFE_VRAM,
        )

        # Not physical, not free, and not rounded upward.
        for wrong in (
            HOST_VRAM_TOTAL,
            HOST_VRAM_FREE,
        ):
            self.assertNotIn(
                f"--memory={wrong // MIB}M",
                flags,
            )

        self.assertLess(
            expected_mib * MIB,
            HOST_VRAM_FREE,
        )

    def test_headroom_is_not_subtracted_twice(self):
        # The figure passed is exactly the envelope's safe-available
        # value, not that value minus headroom again.
        env = envelope()

        pool = env.memory_pool(
            "accelerator:0:memory"
        )

        flags, used = llmfit.build_overrides(env)

        self.assertEqual(
            used["primary_memory_bytes"],
            pool.safe_available_for_additional_workload_bytes,
        )

        double = (
            pool.safe_available_for_additional_workload_bytes
            - pool.protected_reserve_bytes
        )

        self.assertNotIn(
            f"--memory={double // MIB}M",
            flags,
        )

    def test_existing_reservation_is_reflected(self):
        reserved = 8 * GIB

        flags, used = llmfit.build_overrides(
            envelope(
                reserved_vram_bytes=reserved
            )
        )

        self.assertEqual(
            used["primary_memory_bytes"],
            SAFE_VRAM - reserved,
        )
        self.assertIn(
            f"--memory={(SAFE_VRAM - reserved) // MIB}M",
            flags,
        )

    def test_safe_ram_is_supplied(self):
        flags, used = llmfit.build_overrides(
            envelope()
        )

        self.assertIn(
            f"--ram={SAFE_RAM // MIB}M",
            flags,
        )
        self.assertEqual(
            used["system_ram_bytes"],
            SAFE_RAM,
        )

    def test_unknown_reservation_state_supplies_no_override(self):
        # Without a ledger the envelope reports availability as
        # unknown, and an unknown figure must not be invented.
        flags, used = llmfit.build_overrides(
            envelope(with_reservations=False)
        )

        self.assertEqual(flags, [])
        self.assertEqual(used, {})

    def test_no_accelerator_pool_supplies_no_memory_override(self):
        flags, used = llmfit.build_overrides(
            envelope(accelerators=[])
        )

        self.assertNotIn(
            "primary_memory_bytes",
            used,
        )
        self.assertTrue(
            any(
                flag.startswith("--ram=")
                for flag in flags
            )
        )


class InvocationTests(unittest.TestCase):
    @ready_runtime
    def test_command_shape_is_safe_and_correct(self):
        captured = []

        def runner(command, timeout):
            captured.append((command, timeout))
            return real_runner()(command, timeout)

        llmfit.evaluate(
            candidates=[
                Candidate("Qwen/Qwen3-8B-AWQ")
            ],
            envelope=envelope(),
            config={
                "model_evaluation": {
                    "timeout_seconds": 33,
                }
            },
            runner=runner,
        )

        command, timeout = captured[0]

        # Argument array, no shell, identities never interpolated.
        self.assertIsInstance(command, list)
        self.assertTrue(
            command[0].endswith("/llmfit")
        )
        self.assertEqual(timeout, 33)

        # Global overrides must precede the subcommand.
        subcommand = command.index("info")

        self.assertTrue(
            all(
                argument.startswith("--memory=")
                or argument.startswith("--ram=")
                or argument == "--json"
                for argument in command[1:subcommand]
            )
        )

        # The identity is its own argument, never concatenated.
        self.assertEqual(
            command[subcommand + 1],
            "Qwen/Qwen3-8B-AWQ",
        )

    @ready_runtime
    def test_each_candidate_is_asked_about_individually(self):
        asked = []

        def runner(command, timeout):
            asked.append(
                requested_identity(command)
            )
            return real_runner()(command, timeout)

        llmfit.evaluate(
            candidates=[
                Candidate("Qwen/Qwen3-8B-AWQ"),
                Candidate(
                    "Ar4ikov/Qwen3.8-27B-AWQ-W4A16-ASYM"
                ),
            ],
            envelope=envelope(),
            runner=runner,
        )

        self.assertEqual(
            asked,
            [
                "Qwen/Qwen3-8B-AWQ",
                "Ar4ikov/Qwen3.8-27B-AWQ-W4A16-ASYM",
            ],
        )

    @ready_runtime
    def test_real_payload_becomes_normalized_evidence(self):
        result = llmfit.evaluate(
            candidates=[
                Candidate("Qwen/Qwen3-8B-AWQ"),
                Candidate(
                    "Ar4ikov/Qwen3.8-27B-AWQ-W4A16-ASYM"
                ),
            ],
            envelope=envelope(),
            runner=real_runner(),
        )

        self.assertTrue(result.available)
        self.assertEqual(result.provider, "llmfit")

        top = result.for_candidate(
            "Ar4ikov/Qwen3.8-27B-AWQ-W4A16-ASYM"
        )
        second = result.for_candidate(
            "Qwen/Qwen3-8B-AWQ"
        )

        # Rank follows llmfit's own ordering, not our input order.
        self.assertTrue(top.usable)
        self.assertEqual(top.rank, 0)
        self.assertEqual(top.overall_score, 100.0)
        self.assertEqual(top.fit_score, 100.0)
        self.assertEqual(top.quality_score, 100.0)
        self.assertEqual(top.speed_score, 100.0)
        self.assertEqual(top.context_score, 100.0)
        self.assertEqual(top.fit_level, "Perfect")
        self.assertEqual(
            top.recommended_quantization,
            "AWQ-4bit",
        )
        self.assertEqual(
            top.notes,
            ("GPU: model loaded into VRAM",),
        )

        self.assertEqual(second.rank, 1)
        self.assertEqual(second.overall_score, 91.0)

    @ready_runtime
    def test_rank_comes_from_score_not_output_position(self):
        # llmfit's output position is not a stable ranking: on the
        # reference host the whole top of its catalogue ties at 100.0
        # and positions move between invocations. Equal scores must
        # therefore get equal rank.
        models = {
            "tied-b": {
                "name": "tied-b",
                "score": 100.0,
            },
            "better": {
                "name": "better",
                "score": 100.0,
            },
            "worse": {
                "name": "worse",
                "score": 80.0,
            },
            "unscored": {"name": "unscored"},
        }

        result = llmfit.evaluate(
            candidates=[
                Candidate("better"),
                Candidate("tied-b"),
                Candidate("worse"),
                Candidate("unscored"),
            ],
            envelope=envelope(),
            runner=real_runner(models),
        )

        ranks = {
            entry.candidate_id: entry.rank
            for entry in result.evidence
        }

        # Both 100.0 entries tie regardless of output position.
        self.assertEqual(ranks["better"], 0)
        self.assertEqual(ranks["tied-b"], 0)

        # Lower score ranks worse; a missing score ranks last.
        self.assertEqual(ranks["worse"], 1)
        self.assertEqual(ranks["unscored"], 2)

    @ready_runtime
    def test_tied_scores_leave_the_choice_to_input_order(self):
        from core.model_selection import (
            SelectionCandidate,
        )

        models = {
            "second": {
                "name": "second",
                "score": 100.0,
            },
            "first": {
                "name": "first",
                "score": 100.0,
            },
        }

        result = llmfit.evaluate(
            candidates=[
                Candidate("first"),
                Candidate("second"),
            ],
            envelope=envelope(),
            runner=real_runner(models),
        )

        self.assertEqual(
            {
                entry.candidate_id: entry.rank
                for entry in result.evidence
            },
            {"first": 0, "second": 0},
        )

        del SelectionCandidate

    @ready_runtime
    def test_identity_mapping_is_exact_with_an_explicit_seam(self):
        result = llmfit.evaluate(
            candidates=[
                # Our id differs from llmfit's name.
                Candidate(
                    "qwen3-8b-awq",
                    evaluation_id="Qwen/Qwen3-8B-AWQ",
                ),
                # No mapping and no exact match.
                Candidate("some-private-model"),
            ],
            envelope=envelope(),
            runner=real_runner(),
        )

        mapped = result.for_candidate(
            "qwen3-8b-awq"
        )
        unmapped = result.for_candidate(
            "some-private-model"
        )

        self.assertTrue(mapped.usable)
        self.assertEqual(mapped.rank, 0)

        # Unmatched is reported as unusable, never guessed.
        self.assertFalse(unmapped.usable)
        self.assertIsNone(unmapped.rank)
        self.assertIn(
            "some-private-model",
            unmapped.notes[0],
        )


class FailureModeTests(unittest.TestCase):
    def candidates(self):
        return [Candidate("Qwen/Qwen3-8B-AWQ")]

    def test_missing_executable_is_unavailable(self):
        with mock.patch.object(
            llmfit,
            "runtime_is_ready",
            lambda name: False,
        ):
            result = llmfit.evaluate(
                candidates=self.candidates(),
                envelope=envelope(),
                runner=lambda command, timeout: (
                    Completed()
                ),
            )

        self.assertFalse(result.available)
        self.assertIn(
            "not provisioned",
            result.reason,
        )

    @ready_runtime
    def test_non_zero_exit_is_unavailable(self):
        result = llmfit.evaluate(
            candidates=self.candidates(),
            envelope=envelope(),
            runner=lambda command, timeout: Completed(
                returncode=1,
                stderr="hardware detection failed",
            ),
        )

        self.assertFalse(result.available)
        self.assertIn("exited 1", result.reason)
        self.assertIn(
            "hardware detection failed",
            result.reason,
        )

    @ready_runtime
    def test_malformed_json_is_unavailable(self):
        result = llmfit.evaluate(
            candidates=self.candidates(),
            envelope=envelope(),
            runner=lambda command, timeout: Completed(
                stdout="not json at all"
            ),
        )

        self.assertFalse(result.available)
        self.assertIn(
            "not valid JSON",
            result.reason,
        )

    @ready_runtime
    def test_unexpected_shape_is_unavailable(self):
        result = llmfit.evaluate(
            candidates=self.candidates(),
            envelope=envelope(),
            runner=lambda command, timeout: Completed(
                stdout=json.dumps(
                    {"unexpected": True}
                )
            ),
        )

        self.assertFalse(result.available)
        self.assertIn(
            "no models array",
            result.reason,
        )

    @ready_runtime
    def test_recognized_envelope_without_the_model_is_usable_provider(self):
        # The tool worked and simply has nothing for this candidate:
        # that is unusable evidence, not a provider failure.
        result = llmfit.evaluate(
            candidates=self.candidates(),
            envelope=envelope(),
            runner=lambda command, timeout: Completed(
                stdout=json.dumps(
                    {
                        "system": SYSTEM,
                        "models": [
                            {"name": "something-else"}
                        ],
                    }
                )
            ),
        )

        self.assertTrue(result.available)

        evidence = result.for_candidate(
            "Qwen/Qwen3-8B-AWQ"
        )

        self.assertFalse(evidence.usable)
        self.assertIn(
            "no matching model",
            evidence.notes[0],
        )

    @ready_runtime
    def test_a_different_name_is_never_accepted(self):
        # Guards against evaluating the wrong model.
        result = llmfit.evaluate(
            candidates=self.candidates(),
            envelope=envelope(),
            runner=lambda command, timeout: Completed(
                stdout=json.dumps(
                    {
                        "models": [
                            {
                                "name": "Qwen/Qwen3-32B",
                                "score": 100.0,
                            }
                        ],
                    }
                )
            ),
        )

        evidence = result.for_candidate(
            "Qwen/Qwen3-8B-AWQ"
        )

        self.assertFalse(evidence.usable)
        self.assertIsNone(evidence.overall_score)

    @ready_runtime
    def test_one_unknown_candidate_does_not_sink_the_others(self):
        result = llmfit.evaluate(
            candidates=[
                Candidate("Qwen/Qwen3-8B-AWQ"),
                Candidate("not-in-catalogue"),
            ],
            envelope=envelope(),
            runner=real_runner(),
        )

        self.assertTrue(result.available)
        self.assertTrue(
            result.for_candidate(
                "Qwen/Qwen3-8B-AWQ"
            ).usable
        )
        self.assertFalse(
            result.for_candidate(
                "not-in-catalogue"
            ).usable
        )

    @ready_runtime
    def test_timeout_is_unavailable(self):
        def runner(command, timeout):
            raise subprocess.TimeoutExpired(
                cmd=command,
                timeout=timeout,
            )

        result = llmfit.evaluate(
            candidates=self.candidates(),
            envelope=envelope(),
            runner=runner,
        )

        self.assertFalse(result.available)
        self.assertIn("timed out", result.reason)

    @ready_runtime
    def test_os_error_is_unavailable(self):
        def runner(command, timeout):
            raise OSError("permission denied")

        result = llmfit.evaluate(
            candidates=self.candidates(),
            envelope=envelope(),
            runner=runner,
        )

        self.assertFalse(result.available)
        self.assertIn(
            "could not be executed",
            result.reason,
        )

    def test_no_candidates_is_unavailable(self):
        result = llmfit.evaluate(
            candidates=[],
            envelope=envelope(),
        )

        self.assertFalse(result.available)
        self.assertIn(
            "no candidates",
            result.reason,
        )

    @ready_runtime
    def test_failures_never_raise(self):
        # Whatever the tool does, selection must be able to continue.
        for runner in (
            lambda c, t: Completed(returncode=127),
            lambda c, t: Completed(stdout=""),
            lambda c, t: Completed(
                stdout=json.dumps([1, 2, 3])
            ),
        ):
            result = llmfit.evaluate(
                candidates=self.candidates(),
                envelope=envelope(),
                runner=runner,
            )

            self.assertFalse(result.available)
            self.assertIsInstance(
                result.reason,
                str,
            )


class BoundaryTests(unittest.TestCase):
    def test_adapter_uses_no_server_or_http_mode(self):
        # Asserted on the constructed command and the module's real
        # imports rather than on prose, which mentions the modes the
        # adapter deliberately avoids.
        captured = {}

        with mock.patch.object(
            llmfit,
            "runtime_is_ready",
            lambda name: True,
        ), mock.patch.object(
            llmfit,
            "runtime_executable",
            lambda name: "/x/llmfit",
        ):
            def runner(command, timeout):
                captured["command"] = command
                return real_runner()(command, timeout)

            llmfit.evaluate(
                candidates=[
                    Candidate("Qwen/Qwen3-8B-AWQ")
                ],
                envelope=envelope(),
                runner=runner,
            )

        command = captured["command"]

        for forbidden in (
            "serve",
            "bench",
            "download",
            "run",
            "update",
        ):
            self.assertNotIn(
                forbidden,
                command,
                msg=forbidden,
            )

        self.assertIn("info", command)

        imported = {
            getattr(
                getattr(llmfit, name),
                "__name__",
                "",
            )
            for name in dir(llmfit)
            if not name.startswith("__")
        }

        for forbidden in (
            "requests",
            "urllib",
            "socket",
            "http",
            "httpx",
        ):
            self.assertNotIn(forbidden, imported)

    def test_subprocess_never_uses_a_shell(self):
        import inspect

        source = inspect.getsource(llmfit._run)

        self.assertIn("shell=False", source)
        self.assertNotIn("shell=True", source)

    def test_adapter_registry_resolves_the_provider(self):
        from adapters.model_evaluation import (
            get_model_evaluation_adapter,
        )

        self.assertIs(
            get_model_evaluation_adapter("llmfit"),
            llmfit,
        )

        with self.assertRaises(ValueError):
            get_model_evaluation_adapter(
                "not-a-provider"
            )

    @ready_runtime
    def test_provider_object_satisfies_the_core_contract(self):
        adapter = llmfit.LlmfitEvaluationAdapter(
            runner=real_runner()
        )

        result = adapter.evaluate(
            candidates=[
                Candidate("Qwen/Qwen3-8B-AWQ")
            ],
            envelope=envelope(),
            config=None,
        )

        self.assertTrue(result.available)
        self.assertEqual(
            adapter.provider,
            "llmfit",
        )


if __name__ == "__main__":
    unittest.main()
