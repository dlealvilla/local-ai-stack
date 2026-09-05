"""Where a deployed instance keeps its records.

`docs/DEBT.md` K-20: the installed artifact resolved `state_root` against
the working directory, so two invocations from different directories built
two unrelated state stores, and an environment variable set on the command
line silently did nothing.

Stage 1.2 is about to write durable capacity evidence, and after it
reservations and model inventory. State whose location depends on the
operator's shell is state that will eventually be lost, so this is a
prerequisite rather than a tidy-up.

The test worth naming is `test_a_configured_root_does_not_follow_the_working_directory`.
That is the actual failure mode: not that configuration was impossible, but
that it moved without anyone being told.
"""

from __future__ import annotations

import os
from pathlib import Path

from kultrun.kernel.config import Configuration
from kultrun.main import (
    STATE_ROOT_VARIABLE,
    build,
    config_schema,
    resolve_configuration,
)
from kultrun.platform.contracts import PlatformSettings


class TestResolvingTheStateRoot:
    def test_an_environment_override_is_applied(self) -> None:
        configuration = resolve_configuration({STATE_ROOT_VARIABLE: "/srv/kultrun"})
        assert configuration.section(PlatformSettings).state_root == "/srv/kultrun"

    def test_no_override_leaves_the_declared_default(self) -> None:
        configuration = resolve_configuration({})
        assert (
            configuration.section(PlatformSettings).state_root
            == PlatformSettings().state_root
        )

    def test_an_empty_or_blank_override_is_not_a_configuration(self) -> None:
        """An unset variable and a variable set to whitespace mean the same.

        Otherwise `KULTRUN_STATE_ROOT=""` would resolve durable state to the
        filesystem root, which is the kind of accident that only shows up
        once something has already been written there.
        """
        for blank in ("", "   ", "\t"):
            configuration = resolve_configuration({STATE_ROOT_VARIABLE: blank})
            assert (
                configuration.section(PlatformSettings).state_root
                == PlatformSettings().state_root
            )

    def test_the_real_environment_is_read_when_none_is_given(
        self, tmp_path: Path
    ) -> None:
        previous = os.environ.get(STATE_ROOT_VARIABLE)
        os.environ[STATE_ROOT_VARIABLE] = str(tmp_path / "records")
        try:
            resolved = resolve_configuration().section(PlatformSettings)
            assert resolved.state_root == str(tmp_path / "records")
        finally:
            if previous is None:
                os.environ.pop(STATE_ROOT_VARIABLE, None)
            else:
                os.environ[STATE_ROOT_VARIABLE] = previous


class TestTheResolvedRootIsHandedDown:
    def configured(self, root: Path) -> Configuration:
        return config_schema().load({"platform": {"state_root": str(root)}})

    def test_records_are_written_under_the_configured_root(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "records"
        platform = build(self.configured(root))
        assert platform.state_root == root.resolve()
        assert root.is_dir()
        assert list(root.rglob("*.json")), "startup wrote no records"

    def test_a_configured_root_does_not_follow_the_working_directory(
        self, tmp_path: Path
    ) -> None:
        """The actual K-20 failure: state that moved without anyone knowing.

        Same configuration, two different working directories, one location.
        The second run reporting `first_run = False` is the proof that it
        found the first run's records rather than quietly starting a new
        installation beside the new working directory.
        """
        root = tmp_path / "records"
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()

        original = Path.cwd()
        try:
            first = build(self.configured(root))
            os.chdir(elsewhere)
            second = build(self.configured(root))
        finally:
            os.chdir(original)

        assert first.state_root == second.state_root == root.resolve()
        assert first.startup_report.first_run is True
        assert second.startup_report.first_run is False
        assert not (elsewhere / ".state").exists()

    def test_the_root_is_absolute_even_when_configured_relatively(
        self, tmp_path: Path
    ) -> None:
        """A relative root is resolved once, at startup, and then fixed."""
        original = Path.cwd()
        try:
            os.chdir(tmp_path)
            platform = build(self.configured(Path("./relative-records")))
        finally:
            os.chdir(original)
        assert platform.state_root.is_absolute()
        assert platform.state_root == (tmp_path / "relative-records").resolve()

    def test_the_effective_configuration_reports_the_root(
        self, tmp_path: Path
    ) -> None:
        """An administrator can see where state actually went."""
        root = tmp_path / "records"
        platform = build(self.configured(root))
        effective = platform.plane.configuration.effective()
        assert effective["platform"]["state_root"] == str(root)

    def test_a_default_root_is_marked_as_not_configured(
        self, tmp_path: Path
    ) -> None:
        """Which is what lets an installed artifact warn instead of stay quiet."""
        original = Path.cwd()
        try:
            os.chdir(tmp_path)
            defaulted = build()
            chosen = build(self.configured(tmp_path / "records"))
        finally:
            os.chdir(original)
        assert defaulted.state_root_configured is False
        assert chosen.state_root_configured is True
