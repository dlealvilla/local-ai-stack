"""Tier 5 — how an already-defined workload is started, observed and stopped.

Owns process lifecycle. Does not own runtime translation, capacity policy,
model selection or admission. May never import `runtime` or `capacity`.
"""
