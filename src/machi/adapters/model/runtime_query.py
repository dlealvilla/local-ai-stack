"""Ask an installed engine which architectures it knows. No weights."""

from __future__ import annotations

import json
from pathlib import Path

from machi.adapters.foundation.process import NativeProcessRunner

_QUERY = (
    "import json, sys\n"
    "from vllm.model_executor.models.registry import ModelRegistry\n"
    "try:\n"
    "    from vllm.model_executor.layers.quantization import QUANTIZATION_METHODS\n"
    "    quants = sorted(str(item) for item in QUANTIZATION_METHODS)\n"
    "except Exception:\n"
    "    quants = []\n"
    "archs = sorted(ModelRegistry.get_supported_archs())\n"
    "Path = __import__('pathlib').Path\n"
    "Path(sys.argv[1]).write_text(\n"
    "    json.dumps({'architectures': archs, 'quantizations': quants}),\n"
    "    encoding='utf-8',\n"
    ")\n"
)


def query_runtime(
    python: Path,
    output: Path,
    *,
    timeout: int = 120,
) -> tuple[frozenset[str], frozenset[str]]:
    """Return recognized architectures and quantization names.

    The engine writes a file. Process stdout is bounded and is not the record.
    """
    result = NativeProcessRunner().run(
        [str(python), "-c", _QUERY, str(output)],
        cwd=str(python.parent),
        timeout=timeout,
    )
    if result.timed_out or result.returncode != 0 or not output.is_file():
        return frozenset(), frozenset()
    payload = json.loads(output.read_text(encoding="utf-8"))
    architectures = payload.get("architectures", [])
    quantizations = payload.get("quantizations", [])
    if not isinstance(architectures, list) or not isinstance(quantizations, list):
        return frozenset(), frozenset()
    return (
        frozenset(str(item) for item in architectures),
        frozenset(str(item) for item in quantizations),
    )
