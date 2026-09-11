"""Deterministic Sonar payload. Not a CSPRNG."""

from __future__ import annotations

from kultrun.storage.payload import PAYLOAD_VERSION, fill_payload


def test_payload_is_versioned_deterministic_and_nonzero() -> None:
    first = bytearray(64)
    again = bytearray(64)
    fill_payload(first, 0)
    fill_payload(again, 0)
    assert PAYLOAD_VERSION == "shake128-v1"
    assert first == again
    assert any(byte != 0 for byte in first)
    other = bytearray(64)
    fill_payload(other, 4096)
    assert other != first


def test_payload_fill_is_bounded_to_the_buffer() -> None:
    buffer = bytearray(32)
    fill_payload(buffer, 1)
    assert len(buffer) == 32
