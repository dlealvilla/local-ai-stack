"""Tier 2 — what third-party pieces Kultrun needs, and whether they are here.

This package states requirements and records what was found. It does not
provision: `install` acts on what this package reports, which is why a
component check can be run safely on a machine nobody wants modified.

Presence and compatibility are separate questions. Asking whether something
exists at an acceptable version needs no host facts; asking whether it is
*compatible* with this machine does. Keeping them apart is what stops tier 2
acquiring a cycle.
"""
