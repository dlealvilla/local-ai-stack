"""Ampere and Ada selection. Pool labels are not GPU identity."""

from __future__ import annotations

from tools.acceptance_lab.nvidia_matrix import AcceleratorOffer, select_nvidia

CAP = 1.50


def _offer(
    model: str,
    *,
    capability: str,
    memory: int,
    stock: str = "available",
    price: float = 0.50,
    pool: str = "ignored",
    sku: str | None = None,
) -> AcceleratorOffer:
    return AcceleratorOffer(
        provider="fixture",
        region="fixture-region",
        sku=sku or model,
        normalized_model=model,
        memory_gib=memory,
        compute_capability=capability,
        hourly_usd=price,
        stock=stock,
        pool_name=pool,
        driver="fixture",
    )


def test_a40_is_selected_when_available() -> None:
    chosen = select_nvidia(
        "N1",
        (
            _offer("RTX A6000", capability="8.6", memory=48),
            _offer("A40", capability="8.6", memory=48),
        ),
        hourly_cap=CAP,
    )
    assert chosen.blocked is False
    assert chosen.offer is not None
    assert chosen.offer.normalized_model == "A40"
    assert chosen.memory_envelope_gib == 48


def test_a6000_is_selected_when_a40_is_absent() -> None:
    chosen = select_nvidia(
        "N1",
        (
            _offer("A40", capability="8.6", memory=48, stock="none"),
            _offer("RTX A6000", capability="8.6", memory=48),
        ),
        hourly_cap=CAP,
    )
    assert chosen.offer is not None
    assert chosen.offer.normalized_model == "RTX A6000"


def test_n1_is_blocked_when_both_ampere_offers_are_absent() -> None:
    chosen = select_nvidia(
        "N1",
        (
            _offer("A40", capability="8.6", memory=48, stock="none"),
            _offer("RTX A6000", capability="8.6", memory=48, stock="none"),
        ),
        hourly_cap=CAP,
    )
    assert chosen.blocked is True
    assert chosen.offer is None


def test_l40s_is_selected_for_ada() -> None:
    chosen = select_nvidia(
        "N2",
        (
            _offer("L4", capability="8.9", memory=24),
            _offer("L40S", capability="8.9", memory=48),
        ),
        hourly_cap=CAP,
    )
    assert chosen.offer is not None
    assert chosen.offer.normalized_model == "L40S"
    assert chosen.memory_envelope_gib == 48


def test_l4_records_the_smaller_envelope() -> None:
    chosen = select_nvidia(
        "N2",
        (
            _offer("L40S", capability="8.9", memory=48, stock="none"),
            _offer("L4", capability="8.9", memory=24),
            _offer("RTX 4090", capability="8.9", memory=24),
        ),
        hourly_cap=CAP,
    )
    assert chosen.offer is not None
    assert chosen.offer.normalized_model == "L4"
    assert chosen.memory_envelope_gib == 24


def test_pool_name_does_not_override_gpu_identity() -> None:
    mislabeled = _offer(
        "L4",
        capability="8.9",
        memory=24,
        pool="AMPERE_24",
        sku="pool-says-ampere",
    )
    n1 = select_nvidia("N1", (mislabeled,), hourly_cap=CAP)
    n2 = select_nvidia("N2", (mislabeled,), hourly_cap=CAP)
    assert n1.blocked is True
    assert n2.offer is not None
    assert n2.offer.normalized_model == "L4"
    assert n2.memory_envelope_gib == 24


def test_blackwell_stays_deferred() -> None:
    chosen = select_nvidia(
        "N3",
        (_offer("RTX PRO 4500", capability="10.0", memory=32, price=0.72),),
        hourly_cap=CAP,
    )
    assert chosen.blocked is True
    assert chosen.offer is None
