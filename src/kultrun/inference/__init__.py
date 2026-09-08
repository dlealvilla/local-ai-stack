"""Tier 6 — one deployed model-serving workload.

Status and health are different questions. Status asks whether the port is
reachable; health asks whether the API functions. A reachable port that
returns errors is not healthy. Prompts and generated text are transient.
"""
