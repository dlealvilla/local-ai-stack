"""Tier 2 — what the machine can safely do.

Recommends; never authorizes. The Resource Manager is authoritative for
admission.

This package may never import `model`: capacity precedes catalogue, and a
candidate model must not be able to influence characterization.
"""
