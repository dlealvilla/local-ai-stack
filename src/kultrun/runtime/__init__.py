"""Tier 5 — what executable configuration should be launched.

Owns runtime translation into a structured launch spec, declared support,
and runtime path resolution. Does not own process lifecycle, capacity
policy, model selection or admission. May never import `execution` or
`capacity`.
"""
