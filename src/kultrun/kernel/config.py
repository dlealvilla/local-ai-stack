"""Configuration ownership.

Each subsystem registers one section, and a section **is a contract** — so
it carries a ``schema_version``, states what each field means, and appears
in the committed schema fingerprint. That unification is deliberate: the
rule "no existing config field may be reinterpreted" is then enforced by
exactly the same mechanism as "field meaning must never change silently",
rather than by a second convention that could drift from the first.

Everything unrecognised fails closed. An unknown section, an unknown key or
a misspelled key is an error, because a configuration value that is silently
ignored looks identical to one that was applied — and the previous attempt's
own guidance was that settings must be explicit, documented, and never
hidden behind a magic constant.

Provenance — which source supplied which value — is deliberately not tracked
yet. It is recorded in `docs/DEBT.md` against Stage 6.1, where the Admin
surface first has to show automatic settings apart from manual overrides.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeVar

from kultrun.kernel.errors import ConfigError, DuplicateRegistrationError
from kultrun.kernel.ids import Name
from kultrun.kernel.schema import Contract, decode_as, to_dict

SectionT = TypeVar("SectionT", bound=Contract)


class ConfigSchema:
    """The set of configuration sections the platform recognises."""

    def __init__(self) -> None:
        self._sections: dict[str, type[Contract]] = {}

    def register(self, name: str, section: type[Contract]) -> None:
        """Claim a section name for one subsystem's settings contract."""
        validated = Name(name).value
        existing = self._sections.get(validated)
        if existing is not None:
            raise DuplicateRegistrationError(
                "a configuration section is already registered under this name",
                section=validated,
                existing=existing.__qualname__,
                attempted=section.__qualname__,
            )
        self._sections[validated] = section

    def names(self) -> tuple[str, ...]:
        """Every registered section name."""
        return tuple(sorted(self._sections))

    def load(self, data: Mapping[str, Any]) -> Configuration:
        """Validate a raw mapping into typed sections, failing closed.

        A section absent from the input is built from its declared defaults,
        which is how a first run with no configuration file works. A section
        with no defaults and no input is an error naming the missing keys.
        """
        unknown = sorted(set(data) - set(self._sections))
        if unknown:
            raise ConfigError(
                "configuration contains sections the platform does not recognise",
                unknown_sections=unknown,
                known_sections=sorted(self._sections),
            )
        loaded: dict[str, Contract] = {}
        for name, section in self._sections.items():
            raw = data.get(name, {})
            if not isinstance(raw, Mapping):
                raise ConfigError(
                    "configuration section must be a table",
                    section=name,
                    got=type(raw).__name__,
                )
            try:
                loaded[name] = decode_as(section, raw)
            except Exception as error:  # re-raised as ConfigError
                raise ConfigError(
                    "configuration section is invalid",
                    section=name,
                    contract=section.kind,
                    reason=str(error),
                ) from error
        return Configuration(loaded)

    def load_file(self, path: Path) -> Configuration:
        """Load TOML from disk. A missing file means "all defaults"."""
        if not path.exists():
            return self.load({})
        try:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
        except tomllib.TOMLDecodeError as error:
            raise ConfigError(
                "configuration file is not valid TOML",
                path=str(path),
                reason=str(error),
            ) from error
        return self.load(data)


class Configuration:
    """Validated configuration, addressable by the contract that declares it."""

    def __init__(self, sections: Mapping[str, Contract]) -> None:
        self._sections = dict(sections)
        self._by_type = {type(value): value for value in sections.values()}

    def section(self, section: type[SectionT]) -> SectionT:
        """The settings for one subsystem."""
        found = self._by_type.get(section)
        if found is None:
            raise ConfigError(
                "no configuration was loaded for this section",
                contract=section.kind,
                loaded=sorted(self._sections),
            )
        if not isinstance(found, section):
            raise ConfigError(
                "configuration section has an unexpected type",
                contract=section.kind,
            )
        return found

    def effective(self) -> dict[str, Any]:
        """Every section as it was actually applied.

        This is what the Platform API reports from Stage 0.3, so that an
        administrator can see the values in force rather than inferring them
        from a file that may not be the only input.
        """
        return {name: to_dict(value) for name, value in sorted(self._sections.items())}
