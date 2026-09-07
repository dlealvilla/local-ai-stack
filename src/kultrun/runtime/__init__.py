"""Tier 5 — what executable configuration should be launched.

Owns runtime translation into a structured launch spec, plus
host-driven runtime candidates, installations and capability profiles.
Does not own process lifecycle, capacity policy, model selection or
admission. May import `host.contracts`. May never import `execution`,
`capacity`, `model` or `planning`.
"""
