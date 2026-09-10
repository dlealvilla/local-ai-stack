"""Storage as a set of pools.

A pool is the platform's interpretation of a mount as allocatable,
quota-bounded, fingerprinted capacity. That is a different concept from the
mount facts `host` reports, which is why they have different owners: one is
inspection, the other is the domain against which a mutation is admitted.

Ownership, topology, Storage Sonar evidence and empirical fallback live
here. Capacity consumes the resulting contracts and never probes.
"""
