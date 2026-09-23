"""Ask an installed engine which architectures and predicates it knows."""

from __future__ import annotations

import json
from pathlib import Path

from machi.adapters.foundation.process import NativeProcessRunner
from machi.kernel.unresolved import NOT_PROVIDED
from machi.model.predicates import (
    PredicateRule,
    PredicateSupport,
    RuntimePredicate,
)

_QUERY = (
    "import json, sys\n"
    "from vllm.model_executor.models.registry import ModelRegistry\n"
    "try:\n"
    "    from vllm.model_executor.layers.quantization import QUANTIZATION_METHODS\n"
    "    quants = sorted(str(item) for item in QUANTIZATION_METHODS)\n"
    "except Exception:\n"
    "    quants = []\n"
    "archs = sorted(ModelRegistry.get_supported_archs())\n"
    "predicates = []\n"
    "try:\n"
    "    from vllm.v1.attention.backends.registry import AttentionBackendEnum\n"
    "    for item in AttentionBackendEnum:\n"
    "        try:\n"
    "            cls = item.get_class()\n"
    "        except Exception:\n"
    "            continue\n"
    "        fn = getattr(cls, 'supports_head_size', None)\n"
    "        if not callable(fn):\n"
    "            continue\n"
    "        accepted = [n for n in range(1, 257) if bool(fn(n))]\n"
    "        predicates.append({\n"
    "            'name': item.name,\n"
    "            'accepted': accepted,\n"
    "            'probed_max': 256,\n"
    "        })\n"
    "except Exception:\n"
    "    predicates = []\n"
    "Path = __import__('pathlib').Path\n"
    "Path(sys.argv[1]).write_text(\n"
    "    json.dumps({\n"
    "        'architectures': archs,\n"
    "        'quantizations': quants,\n"
    "        'head_probes': predicates,\n"
    "    }),\n"
    "    encoding='utf-8',\n"
    ")\n"
)


def query_runtime(
    python: Path,
    output: Path,
    *,
    timeout: int = 120,
) -> tuple[frozenset[str], frozenset[str], tuple[RuntimePredicate, ...]]:
    """Return architectures, quantization names, and head-size predicates.

    The engine writes a file. Process stdout is bounded and is not the record.
    """
    result = NativeProcessRunner().run(
        [str(python), "-c", _QUERY, str(output)],
        cwd=str(python.parent),
        timeout=timeout,
    )
    if result.timed_out or result.returncode != 0 or not output.is_file():
        return frozenset(), frozenset(), ()
    payload = json.loads(output.read_text(encoding="utf-8"))
    architectures = payload.get("architectures", [])
    quantizations = payload.get("quantizations", [])
    probes = payload.get("head_probes", [])
    if not isinstance(architectures, list) or not isinstance(quantizations, list):
        return frozenset(), frozenset(), ()
    if not isinstance(probes, list):
        probes = []
    return (
        frozenset(str(item) for item in architectures),
        frozenset(str(item) for item in quantizations),
        tuple(predicate_from_probe(item) for item in probes if isinstance(item, dict)),
    )


def predicate_from_probe(probe: dict[str, object]) -> RuntimePredicate:
    """Turn a finite probe into a rule. Universal acceptance is vacuous."""
    name = str(probe.get("name", "backend"))[:80]
    accepted_raw = probe.get("accepted", [])
    probed = probe.get("probed_max", 0)
    accepted = (
        {int(item) for item in accepted_raw}
        if isinstance(accepted_raw, list)
        else set()
    )
    width = int(probed) if isinstance(probed, int) else 0
    universe = set(range(1, width + 1))
    if not universe or accepted == universe:
        return _predicate(name, PredicateSupport.VACUOUS, PredicateRule.ANY, None, None)
    if not accepted:
        return _predicate(
            name, PredicateSupport.FINITE, PredicateRule.AT_LEAST, width + 1, None
        )
    minimum = min(accepted)
    if accepted == {item for item in universe if item >= minimum}:
        return _predicate(
            name, PredicateSupport.FINITE, PredicateRule.AT_LEAST, minimum, None
        )
    ceiling = max(accepted)
    for modulus in range(1, 129):
        expected = {
            item for item in universe if item % modulus == 0 and item <= ceiling
        }
        if accepted == expected:
            return _predicate(
                name,
                PredicateSupport.FINITE,
                PredicateRule.MULTIPLE_OF,
                modulus,
                ceiling,
            )
    return _predicate(
        name, PredicateSupport.UNRESOLVED, PredicateRule.ANY, None, None
    )


def _predicate(
    name: str,
    support: PredicateSupport,
    rule: PredicateRule,
    parameter: int | None,
    ceiling: int | None,
) -> RuntimePredicate:
    return RuntimePredicate(
        name=name,
        subject="head_size",
        support=support,
        rule=rule,
        parameter=parameter if parameter is not None else NOT_PROVIDED,
        ceiling=ceiling if ceiling is not None else NOT_PROVIDED,
        value="",
    )
