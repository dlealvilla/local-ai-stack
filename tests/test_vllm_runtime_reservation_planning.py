import copy
import unittest

from adapters.resource_manager.vllm_runtime_planning import (
    VllmRuntimeAwareReservationPlanningProvider,
    VllmRuntimePlanningError,
    vllm_runtime_requirement_bytes,
)


GIB = 1024 ** 3
MIB = 1024 ** 2


class FakeBaseProvider:
    def __init__(
        self,
        view,
    ):
        self.view = view

    def build_view(
        self,
    ):
        return copy.deepcopy(
            self.view
        )


def base_view(
    requirement=7 * GIB,
):
    return {
        "capacities": {
            "accelerator:0:memory":
                30 * GIB,

            "memory:system_ram":
                128 * GIB,
        },

        "requirements_by_model": {
            "model-a": {
                "accelerator:0:memory":
                    requirement,
            },
        },

        "requirement_resolutions_by_model": {
            "model-a": {
                "model_id":
                    "model-a",

                "resolved":
                    True,

                "basis":
                    "provisional_estimate",

                "requirements": {
                    "accelerator:0:memory":
                        requirement,
                },
            },
        },

        "phase8": {
            "planner_stage":
                "test",
        },
    }


class VllmRuntimeRequirementTests(
    unittest.TestCase
):
    def test_runtime_formula(
        self,
    ):
        result = (
            vllm_runtime_requirement_bytes(
                total_vram_bytes=
                    32 * GIB,

                gpu_memory_utilization=
                    0.85,
            )
        )

        expected_target = (
            29205777613
        )

        self.assertEqual(
            result[
                "target_bytes"
            ],
            expected_target,
        )

        self.assertEqual(
            result[
                "overhead_bytes"
            ],
            687194768,
        )

        self.assertEqual(
            result[
                "requirement_bytes"
            ],
            expected_target
            + 687194768,
        )

    def test_invalid_utilization_fails(
        self,
    ):
        for value in (
            0,
            -0.1,
            1.1,
        ):
            with self.subTest(
                value=value
            ):
                with self.assertRaises(
                    ValueError
                ):
                    vllm_runtime_requirement_bytes(
                        total_vram_bytes=
                            32 * GIB,

                        gpu_memory_utilization=
                            value,
                    )

    def test_runtime_requirement_overrides_lower_base(
        self,
    ):
        source = base_view(
            requirement=7 * GIB
        )

        provider = (
            VllmRuntimeAwareReservationPlanningProvider(
                config={
                    "inference": {
                        "provider":
                            "vllm",
                    },
                },

                performance={
                    "gpu_memory_utilization":
                        0.85,
                },

                base_provider=
                    FakeBaseProvider(
                        source
                    ),

                total_vram_bytes_provider=
                    lambda:
                        32 * GIB,
            )
        )

        result = provider.build_view()

        selected = result[
            "requirements_by_model"
        ][
            "model-a"
        ][
            "accelerator:0:memory"
        ]

        self.assertGreater(
            selected,
            7 * GIB,
        )

        resolution = result[
            "requirement_resolutions_by_model"
        ][
            "model-a"
        ]

        self.assertEqual(
            resolution[
                "basis"
            ],
            "runtime_aware_vllm_config",
        )

        self.assertEqual(
            resolution[
                "requirements"
            ][
                "accelerator:0:memory"
            ],
            selected,
        )

    def test_higher_base_requirement_is_preserved(
        self,
    ):
        source = base_view(
            requirement=31 * GIB
        )

        provider = (
            VllmRuntimeAwareReservationPlanningProvider(
                config={
                    "inference": {
                        "provider":
                            "vllm",
                    },
                },

                performance={
                    "gpu_memory_utilization":
                        0.50,
                },

                base_provider=
                    FakeBaseProvider(
                        source
                    ),

                total_vram_bytes_provider=
                    lambda:
                        32 * GIB,
            )
        )

        result = provider.build_view()

        self.assertEqual(
            result[
                "requirements_by_model"
            ][
                "model-a"
            ][
                "accelerator:0:memory"
            ],
            31 * GIB,
        )

    def test_base_view_is_not_mutated(
        self,
    ):
        source = base_view()

        original = copy.deepcopy(
            source
        )

        provider = (
            VllmRuntimeAwareReservationPlanningProvider(
                config={
                    "inference": {
                        "provider":
                            "vllm",
                    },
                },

                performance={
                    "gpu_memory_utilization":
                        0.85,
                },

                base_provider=
                    FakeBaseProvider(
                        source
                    ),

                total_vram_bytes_provider=
                    lambda:
                        32 * GIB,
            )
        )

        provider.build_view()

        self.assertEqual(
            source,
            original,
        )

    def test_non_vllm_config_fails(
        self,
    ):
        with self.assertRaises(
            ValueError
        ):
            VllmRuntimeAwareReservationPlanningProvider(
                config={
                    "inference": {
                        "provider":
                            "other",
                    },
                },

                performance={
                    "gpu_memory_utilization":
                        0.85,
                },
            )

    def test_ambiguous_accelerators_fail_closed(
        self,
    ):
        source = base_view()

        source[
            "capacities"
        ][
            "accelerator:1:memory"
        ] = 30 * GIB

        provider = (
            VllmRuntimeAwareReservationPlanningProvider(
                config={
                    "inference": {
                        "provider":
                            "vllm",
                    },
                },

                performance={
                    "gpu_memory_utilization":
                        0.85,
                },

                base_provider=
                    FakeBaseProvider(
                        source
                    ),

                total_vram_bytes_provider=
                    lambda:
                        32 * GIB,
            )
        )

        with self.assertRaises(
            VllmRuntimePlanningError
        ):
            provider.build_view()


if __name__ == "__main__":
    unittest.main()
