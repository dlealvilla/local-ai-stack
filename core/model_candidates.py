"""The curated candidate configurations this host may choose between.

AI_DEPLOYMENT_MODEL_CANDIDATES

A small declared set, not catalogue discovery. Choosing well among a
handful of vetted configurations is the product problem; ranking
thousands of community artifacts is not, and would make every selection
depend on a live remote catalogue.

The set is declared in configuration and normalized here into the same
candidate record shape `core.model_requirement` already accepts, so
nothing downstream learns a new format and no candidate identity is
compiled into the platform. Replacing the curated list with a
catalogue query later means changing where records come from, not what
consumes them.

Records carry `evaluation_id`, the name an evaluation provider knows a
candidate by, because provider catalogues and platform identities need
not agree and matching them is done by exact declaration rather than
by guessing at similar names.
"""

from __future__ import annotations

from core.config import load_config


MODEL_CANDIDATE_SCHEMA_VERSION = 1


REQUIRED_FIELDS = (
    "candidate_id",
    "provider",
    "source_model_id",
)


def _require(entry, index):
    for field in REQUIRED_FIELDS:
        value = entry.get(field)

        if not isinstance(value, str) or not value:
            raise ValueError(
                "curated candidate "
                + str(index)
                + " is missing "
                + field
            )


def _positive_int(value, *, field, index):
    if value is None:
        return None

    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        raise ValueError(
            "curated candidate "
            + str(index)
            + " has a non-numeric "
            + field
        )

    if value <= 0:
        raise ValueError(
            "curated candidate "
            + str(index)
            + " has a non-positive "
            + field
        )

    return int(value)


def normalize_candidate(entry, index=0):
    """One declared candidate as a normalized candidate record.

    Sizes are declared in gibibytes because that is how an operator
    reasons about them; everything downstream works in bytes.
    """

    _require(entry, index)

    gib = 1024 ** 3

    download_bytes = _positive_int(
        entry.get("download_gb"),
        field="download_gb",
        index=index,
    )

    if download_bytes is not None:
        download_bytes = int(
            entry["download_gb"] * gib
        )

    vram_bytes = _positive_int(
        entry.get("vram_gb"),
        field="vram_gb",
        index=index,
    )

    if vram_bytes is not None:
        vram_bytes = int(entry["vram_gb"] * gib)

    ram_bytes = _positive_int(
        entry.get("ram_gb"),
        field="ram_gb",
        index=index,
    )

    if ram_bytes is not None:
        ram_bytes = int(entry["ram_gb"] * gib)

    record = {
        "schema_version": (
            MODEL_CANDIDATE_SCHEMA_VERSION
        ),
        "catalog_id": (
            entry["provider"]
            + ":"
            + entry["source_model_id"]
        ),
        "candidate_id": entry["candidate_id"],
        "name": entry["candidate_id"],
        "target_name": entry.get(
            "target_name",
            entry["candidate_id"],
        ),
        #
        # Declared explicitly. An absent mapping simply means the
        # provider has no evidence for this candidate, which the
        # selector already handles.
        #
        "evaluation_id": entry.get(
            "evaluation_id"
        ),
        "family": entry.get("family"),
        "architecture": entry.get("architecture"),
        "quantization": entry.get("quantization"),
        "context_length": entry.get(
            "context_length"
        ),
        "parameters": {
            "count": entry.get("parameter_count"),
        },
        "source": {
            "provider": entry["provider"],
            "source_model_id": entry[
                "source_model_id"
            ],
            "revision": entry.get("revision"),
            "license": entry.get("license"),
            "location": entry.get("location"),
        },
        "size": {
            "download_bytes": download_bytes,
            #
            # A curated record describes a candidate, not an
            # installation. Whether it is installed is inventory's
            # answer, and claiming otherwise here would tell
            # feasibility no acquisition storage is needed.
            #
            "installed_bytes": None,
        },
        "format": {
            "weights": entry.get(
                "weights",
                "safetensors",
            ),
        },
        "runtime": {
            "supported": list(
                entry.get("runtimes", [])
            ),
        },
        "requirements": {
            "ram_bytes": ram_bytes,
            "vram_bytes": vram_bytes,
            "unified_memory_bytes": None,
        },
        "compatibility": {
            "status": entry.get(
                "compatibility",
                "compatible",
            ),
            "confidence": entry.get(
                "confidence",
                "declared",
            ),
            "reasons": [],
        },
    }

    return record


def load_curated_candidates(config=None):
    """The declared candidate set, normalized and in declared order.

    Order is preserved because it is the deterministic tie-break every
    selection ultimately falls back on.
    """

    if config is None:
        config = load_config()

    settings = (
        config.get("model_candidates") or {}
    )

    entries = settings.get("curated") or []

    if not isinstance(entries, list):
        raise ValueError(
            "model_candidates.curated must be a list"
        )

    return [
        normalize_candidate(entry, index)
        for index, entry in enumerate(entries)
    ]
