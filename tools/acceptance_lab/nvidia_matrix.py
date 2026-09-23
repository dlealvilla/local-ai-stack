"""NVIDIA acceptance selection. Product Core does not know these SKUs."""

from __future__ import annotations

from dataclasses import dataclass

AMPERE_CAPABILITY = "8.6"
ADA_CAPABILITY = "8.9"
N1_PREFERENCE = ("A40", "RTX A6000")
N2_PREFERENCE = ("L40S", "L4", "RTX 4090")
N1_MEMORY_FLOOR_GIB = 48


@dataclass(frozen=True, slots=True)
class AcceleratorOffer:
    """One discovered accelerator. Pool names are not identity."""

    provider: str
    region: str
    sku: str
    normalized_model: str
    memory_gib: int
    compute_capability: str
    hourly_usd: float
    stock: str
    pool_name: str
    driver: str
    foundation_compatible: bool = True


@dataclass(frozen=True, slots=True)
class MatrixSelection:
    """The exact offer for one campaign, or a blocked campaign."""

    campaign: str
    offer: AcceleratorOffer | None
    memory_envelope_gib: int | None
    blocked: bool
    reason: str


def select_nvidia(
    campaign: str,
    offers: tuple[AcceleratorOffer, ...],
    *,
    hourly_cap: float,
) -> MatrixSelection:
    """Pick one SKU. A class pass is not inferred from the winner."""
    if campaign == "N3":
        return MatrixSelection(
            "N3",
            None,
            None,
            True,
            "blackwell qualification is deferred",
        )
    if campaign == "N1":
        return _pick(
            "N1",
            offers,
            capability=AMPERE_CAPABILITY,
            preference=N1_PREFERENCE,
            memory_floor=N1_MEMORY_FLOOR_GIB,
            hourly_cap=hourly_cap,
        )
    if campaign == "N2":
        return _pick(
            "N2",
            offers,
            capability=ADA_CAPABILITY,
            preference=N2_PREFERENCE,
            memory_floor=None,
            hourly_cap=hourly_cap,
        )
    return MatrixSelection(campaign, None, None, True, "unknown campaign")


def _pick(
    campaign: str,
    offers: tuple[AcceleratorOffer, ...],
    *,
    capability: str,
    preference: tuple[str, ...],
    memory_floor: int | None,
    hourly_cap: float,
) -> MatrixSelection:
    eligible: list[AcceleratorOffer] = []
    for offer in offers:
        if offer.compute_capability != capability:
            continue
        if offer.stock.strip().lower() in {"", "none", "unavailable"}:
            continue
        if offer.hourly_usd > hourly_cap:
            continue
        if not offer.foundation_compatible:
            continue
        if memory_floor is not None and offer.memory_gib < memory_floor:
            continue
        eligible.append(offer)
    for name in preference:
        for offer in eligible:
            if offer.normalized_model == name:
                return MatrixSelection(
                    campaign,
                    offer,
                    offer.memory_gib,
                    False,
                    f"selected {name}",
                )
    return MatrixSelection(
        campaign,
        None,
        None,
        True,
        "no eligible accelerator for this campaign",
    )
