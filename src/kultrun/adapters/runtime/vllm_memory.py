"""vLLM log interpretation for bounded runtime-memory probes.

Adapter-owned. Does not launch a process and does not admit resources.
"""

from __future__ import annotations

import math
import re

from kultrun.kernel.ids import Name
from kultrun.runtime.memory import measured_non_kv_bytes, runtime_extra_bytes
from kultrun.runtime.ports import InterpretedRuntimeMemory

IDENTITY = Name("vllm-memory")
GiB = 1024**3
MiB = 1024**2

_KV = re.compile(
    r"Available KV cache memory:\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*(GiB|GB|MiB|MB)\b",
    re.IGNORECASE,
)
_LOAD = re.compile(
    r"Model loading took\s+([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*(GiB|GB|MiB|MB)\s+memory\b",
    re.IGNORECASE,
)


class VllmMemoryInterpreter:
    """Parse native vLLM memory lines. Not a benchmark harness."""

    @property
    def identity(self) -> Name:
        return IDENTITY

    def interpret(
        self,
        *,
        stdout: str,
        stderr: str,
        probe_budget_bytes: int,
    ) -> InterpretedRuntimeMemory:
        text = f"{stdout}\n{stderr}"
        kv = _last_bytes(_KV, text)
        load = _last_bytes(_LOAD, text)
        if kv is None:
            return InterpretedRuntimeMemory(
                model_load_bytes=load,
                available_kv_bytes=None,
                usable=False,
                reason="available_kv_not_captured",
            )
        extra = None
        if load is not None:
            extra = runtime_extra_bytes(
                measured_non_kv_bytes(probe_budget_bytes, kv),
                load,
            )
        return InterpretedRuntimeMemory(
            model_load_bytes=load,
            available_kv_bytes=kv,
            usable=True,
            extra=extra,
        )


def format_fixture_logs(
    *,
    model_load_bytes: int | None,
    available_kv_bytes: int,
) -> str:
    """Deterministic vLLM-shaped logs for T0/T1/T2 fixtures."""
    lines: list[str] = []
    if model_load_bytes is not None:
        lines.append(
            f"INFO Model loading took {_gib(model_load_bytes)} GiB memory"
        )
    lines.append(
        f"INFO Available KV cache memory: {_gib(available_kv_bytes)} GiB"
    )
    return "\n".join(lines) + "\n"


def _last_bytes(pattern: re.Pattern[str], text: str) -> int | None:
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    amount = float(matches[-1].group(1))
    unit = matches[-1].group(2).lower()
    if not math.isfinite(amount):
        return None
    scale = GiB if unit in {"gib", "gb"} else MiB
    return round(amount * scale)


def _gib(value: int) -> str:
    text = format(value / GiB, ".2f").rstrip("0").rstrip(".")
    return text if text else "0"
