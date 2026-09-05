"""Tier 6 — the record of what was used.

Recording must never block an inference response, and the gateway must
never wait on an exporter.

A usage event keeps five identities apart — logical name, model, provider,
service and route reason — because the previous attempt left the explicit
instruction not to collapse them.
"""
