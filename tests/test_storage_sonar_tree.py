"""HOST-mode Sonar V2 logical tree. No I/O."""

from __future__ import annotations

from kultrun.kernel.unresolved import is_resolved
from kultrun.storage.sonar_tree import SonarAttempt, classify_sonar_tree


def _run(fail: set[int]):
    def test(target: int) -> SonarAttempt:
        return SonarAttempt.CAPACITY if target in fail else SonarAttempt.SUCCESS

    return classify_sonar_tree(test)


def test_tree_256() -> None:
    result = _run(set())
    assert result.lower_units == 256
    assert not is_resolved(result.upper_units)
    assert result.attempted == (64, 128, 256)


def test_tree_192() -> None:
    result = _run({256})
    assert result.lower_units == 192
    assert result.upper_units == 256


def test_tree_128() -> None:
    result = _run({256, 192})
    assert result.lower_units == 128
    assert result.upper_units == 192


def test_tree_96() -> None:
    result = _run({128})
    assert result.lower_units == 96
    assert result.upper_units == 128


def test_tree_64() -> None:
    result = _run({128, 96})
    assert result.lower_units == 64
    assert result.upper_units == 96


def test_tree_48() -> None:
    result = _run({64})
    assert result.lower_units == 48
    assert result.upper_units == 64


def test_tree_32() -> None:
    result = _run({64, 48})
    assert result.lower_units == 32
    assert result.upper_units == 48


def test_tree_24() -> None:
    result = _run({64, 32})
    assert result.lower_units == 24
    assert result.upper_units == 32


def test_tree_16() -> None:
    result = _run({64, 32, 24})
    assert result.lower_units == 16
    assert result.upper_units == 24


def test_tree_unresolved() -> None:
    result = _run({64, 32, 16})
    assert not is_resolved(result.lower_units)
    assert result.upper_units == 16
    assert 24 not in result.attempted


def test_tree_other_is_not_an_upper_bound() -> None:
    def test(target: int) -> SonarAttempt:
        if target == 64:
            return SonarAttempt.SUCCESS
        if target == 128:
            return SonarAttempt.OTHER
        raise AssertionError(target)

    result = classify_sonar_tree(test)
    assert result.lower_units == 64
    assert not is_resolved(result.upper_units)
