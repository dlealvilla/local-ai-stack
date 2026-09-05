"""Host discovery providers.

Every module here implements `kultrun.host.ports.HostDiscoveryProvider` and
nothing else. Under Law 5 each inherits `host`'s import budget, so none can
reach `model`, `planning`, `resource`, `runtime` or `inference` — a provider
structurally cannot decide anything.

The set is deliberately small and each member earns its place from a gap
measured on the reference host rather than from architectural symmetry.
"""
