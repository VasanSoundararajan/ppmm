"""Semantic version parsing, comparison, and requirement-line utilities.

Provides a ``SemanticVersion`` dataclass that supports full ordering and a
handful of helpers for parsing ``requirements.txt``-style lines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering
from typing import Optional


@total_ordering
@dataclass(frozen=True)
class SemanticVersion:
    """An immutable representation of a semantic version (major.minor.patch).

    Supports comparison, sorting, and string round-tripping.

    Examples
    --------
    >>> v = SemanticVersion.parse("1.26.4")
    >>> v.major, v.minor, v.patch
    (1, 26, 4)
    >>> SemanticVersion.parse("2.0.0") > v
    True
    """

    major: int
    minor: int
    patch: int
    pre_release: Optional[str] = None

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def parse(cls, version_string: str) -> "SemanticVersion":
        """Parse a version string like ``'1.26.4'`` or ``'2.0.0rc1'``.

        Parameters
        ----------
        version_string:
            A dot-separated version, optionally followed by a pre-release
            suffix (e.g. ``a1``, ``b2``, ``rc1``).

        Returns
        -------
        SemanticVersion

        Raises
        ------
        ValueError
            If *version_string* cannot be parsed.
        """
        version_string = version_string.strip()
        match = re.match(
            r"^(\d+)\.(\d+)\.(\d+)(?:[.\-]?((?:a|b|rc|alpha|beta|dev|post)\d*))?$",
            version_string,
        )
        if not match:
            # Try two-part versions like "2.31"
            match2 = re.match(r"^(\d+)\.(\d+)$", version_string)
            if match2:
                return cls(
                    major=int(match2.group(1)),
                    minor=int(match2.group(2)),
                    patch=0,
                )
            raise ValueError(f"Cannot parse version: {version_string!r}")
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
            pre_release=match.group(4),
        )

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    def _as_tuple(self) -> tuple[int, int, int, int, str]:
        """Return a tuple suitable for ordering.

        Pre-release versions sort *before* the corresponding release:
        ``1.0.0a1 < 1.0.0``.
        """
        return (
            self.major,
            self.minor,
            self.patch,
            0 if self.pre_release else 1,  # pre-release sorts first
            self.pre_release or "",
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return self._as_tuple() == other._as_tuple()

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return self._as_tuple() < other._as_tuple()

    def __hash__(self) -> int:
        return hash(self._as_tuple())

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre_release:
            base += self.pre_release
        return base


# ======================================================================
# Utility functions
# ======================================================================

def parse_requirement(line: str) -> tuple[str, str]:
    """Parse a requirement line into ``(package_name, version_spec)``.

    Supports a variety of common formats::

        requests==2.31.0   -> ("requests", "==2.31.0")
        numpy>=1.24        -> ("numpy", ">=1.24")
        flask              -> ("flask", "")

    Parameters
    ----------
    line:
        A single non-empty line from a ``requirements.txt`` file.

    Returns
    -------
    tuple[str, str]
        Package name (normalised to lowercase) and version specifier
        (including the operator, or empty string if unpinned).
    """
    line = line.strip()
    if not line or line.startswith("#") or line.startswith("-"):
        return ("", "")

    # Split on the first version operator
    match = re.match(r"^([A-Za-z0-9_\-\.]+)\s*(.*)", line)
    if not match:
        return ("", "")
    name = match.group(1).strip().lower()
    spec = match.group(2).strip()
    return (name, spec)


def compare_versions(current: str, latest: str) -> str:
    """Return a human-readable upgrade arrow string.

    Parameters
    ----------
    current:
        Currently installed version string.
    latest:
        Latest available version string.

    Returns
    -------
    str
        e.g. ``"1.26.4 → 1.27.0 available"``
    """
    return f"{current} → {latest} available"
