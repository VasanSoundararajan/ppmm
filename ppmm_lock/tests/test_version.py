"""Unit tests for ppmm_lock.version — SemanticVersion and helpers."""

import pytest

from ppmm_lock.version import SemanticVersion, parse_requirement, compare_versions


class TestSemanticVersionParsing:
    """Tests for ``SemanticVersion.parse``."""

    def test_three_part_version(self) -> None:
        v = SemanticVersion.parse("1.26.4")
        assert v.major == 1
        assert v.minor == 26
        assert v.patch == 4
        assert v.pre_release is None

    def test_two_part_version(self) -> None:
        v = SemanticVersion.parse("2.31")
        assert v.major == 2
        assert v.minor == 31
        assert v.patch == 0

    def test_pre_release_rc(self) -> None:
        v = SemanticVersion.parse("3.0.0rc1")
        assert v.major == 3
        assert v.minor == 0
        assert v.patch == 0
        assert v.pre_release == "rc1"

    def test_pre_release_alpha(self) -> None:
        v = SemanticVersion.parse("1.0.0a2")
        assert v.pre_release == "a2"

    def test_pre_release_beta(self) -> None:
        v = SemanticVersion.parse("2.1.0b1")
        assert v.pre_release == "b1"

    def test_invalid_version_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse version"):
            SemanticVersion.parse("not-a-version")

    def test_whitespace_stripped(self) -> None:
        v = SemanticVersion.parse("  1.2.3  ")
        assert v == SemanticVersion(1, 2, 3)


class TestSemanticVersionComparison:
    """Tests for ordering / equality."""

    def test_equal(self) -> None:
        a = SemanticVersion.parse("1.0.0")
        b = SemanticVersion.parse("1.0.0")
        assert a == b

    def test_less_than_major(self) -> None:
        assert SemanticVersion.parse("1.0.0") < SemanticVersion.parse("2.0.0")

    def test_less_than_minor(self) -> None:
        assert SemanticVersion.parse("1.0.0") < SemanticVersion.parse("1.1.0")

    def test_less_than_patch(self) -> None:
        assert SemanticVersion.parse("1.0.0") < SemanticVersion.parse("1.0.1")

    def test_pre_release_before_release(self) -> None:
        assert SemanticVersion.parse("1.0.0rc1") < SemanticVersion.parse("1.0.0")

    def test_sorting(self) -> None:
        versions = [
            SemanticVersion.parse("2.0.0"),
            SemanticVersion.parse("1.0.0"),
            SemanticVersion.parse("1.0.0rc1"),
            SemanticVersion.parse("1.1.0"),
        ]
        sorted_v = sorted(versions)
        assert sorted_v == [
            SemanticVersion.parse("1.0.0rc1"),
            SemanticVersion.parse("1.0.0"),
            SemanticVersion.parse("1.1.0"),
            SemanticVersion.parse("2.0.0"),
        ]

    def test_hash_works_in_sets(self) -> None:
        s = {SemanticVersion.parse("1.0.0"), SemanticVersion.parse("1.0.0")}
        assert len(s) == 1


class TestSemanticVersionStr:
    """Tests for ``__str__``."""

    def test_basic(self) -> None:
        assert str(SemanticVersion(1, 26, 4)) == "1.26.4"

    def test_with_pre_release(self) -> None:
        v = SemanticVersion(3, 0, 0, "rc1")
        assert str(v) == "3.0.0rc1"


class TestParseRequirement:
    """Tests for ``parse_requirement``."""

    def test_pinned(self) -> None:
        assert parse_requirement("requests==2.31.0") == ("requests", "==2.31.0")

    def test_minimum(self) -> None:
        assert parse_requirement("numpy>=1.24") == ("numpy", ">=1.24")

    def test_bare(self) -> None:
        assert parse_requirement("flask") == ("flask", "")

    def test_comment_line(self) -> None:
        assert parse_requirement("# this is a comment") == ("", "")

    def test_empty(self) -> None:
        assert parse_requirement("") == ("", "")

    def test_flag_line(self) -> None:
        assert parse_requirement("-i https://pypi.org") == ("", "")


class TestCompareVersions:
    """Tests for ``compare_versions``."""

    def test_format(self) -> None:
        result = compare_versions("1.0.0", "1.1.0")
        assert "1.0.0" in result
        assert "1.1.0" in result
        assert "available" in result
