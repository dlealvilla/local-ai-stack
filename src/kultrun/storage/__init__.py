"""Tier 2 — storage as a set of pools.

A mutation is admitted against the specific pool it will mutate. Pools are
plural from v1 even though the reference host has one: the previous attempt
designed multi-pool storage and never exercised it.

This package may never import `model`. Platform-managed usage arrives
through a port that speaks bytes per pool and carries no entity identity.
"""
