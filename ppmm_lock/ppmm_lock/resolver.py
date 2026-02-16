"""Dependency resolver layer.

Wraps ``pip`` and the PyPI JSON API to:

* install packages from a requirements file,
* capture the full resolved dependency tree (including transitive deps),
* query the latest available version for each package, and
* compute per-package hashes for integrity verification.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests


@dataclass
class ResolvedDependency:
    """A single resolved dependency with its pinned version and optional hash."""

    name: str
    version: str
    hash: Optional[str] = None


# ======================================================================
# pip helpers
# ======================================================================

def _run_pip(*args: str, capture: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a pip command using the current interpreter.

    Parameters
    ----------
    *args:
        Arguments forwarded to ``pip``.
    capture:
        Whether to capture stdout/stderr.

    Returns
    -------
    subprocess.CompletedProcess

    Raises
    ------
    subprocess.CalledProcessError
        If pip exits with a non-zero code.
    """
    cmd = [sys.executable, "-m", "pip", *args]
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=True,
    )


def get_installed_packages() -> dict[str, str]:
    """Return a mapping of installed package names to their versions.

    Uses ``pip list --format=json`` under the hood.

    Returns
    -------
    dict[str, str]
        Lowercase package name → installed version.
    """
    result = _run_pip("list", "--format=json")
    packages: list[dict[str, str]] = json.loads(result.stdout)
    return {pkg["name"].lower(): pkg["version"] for pkg in packages}


def install_requirements(requirements_path: Path) -> None:
    """Install packages from a requirements file.

    Parameters
    ----------
    requirements_path:
        Path to a ``requirements.txt`` (or ``.lock``) file.

    Raises
    ------
    FileNotFoundError
        If *requirements_path* does not exist.
    subprocess.CalledProcessError
        If pip fails.
    """
    if not requirements_path.exists():
        raise FileNotFoundError(f"Requirements file not found: {requirements_path}")
    _run_pip("install", "-r", str(requirements_path), capture=False)


# ======================================================================
# Resolution
# ======================================================================

def resolve_dependencies(requirements_path: Path) -> dict[str, ResolvedDependency]:
    """Resolve all dependencies (including transitive) from a requirements file.

    The strategy:

    1. Install everything listed in *requirements_path* into the current
       environment using ``pip install -r``.
    2. Run ``pip freeze`` to capture the exact resolved versions.
    3. Optionally compute download hashes via the PyPI JSON API.

    Parameters
    ----------
    requirements_path:
        Path to a ``requirements.txt`` file.

    Returns
    -------
    dict[str, ResolvedDependency]
        Mapping of lowercase package name → ``ResolvedDependency``.
    """
    if not requirements_path.exists():
        raise FileNotFoundError(f"Requirements file not found: {requirements_path}")

    # Step 1 — install
    _run_pip("install", "-r", str(requirements_path), capture=False)

    # Step 2 — freeze
    result = _run_pip("freeze")
    resolved: dict[str, ResolvedDependency] = {}
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        if "==" in line:
            name, version = line.split("==", 1)
            name = name.strip().lower()
            version = version.strip()

            # Step 3 — try to fetch hash from PyPI
            pkg_hash = _fetch_hash(name, version)
            resolved[name] = ResolvedDependency(
                name=name, version=version, hash=pkg_hash
            )
    return resolved


# ======================================================================
# PyPI queries
# ======================================================================

_PYPI_BASE = "https://pypi.org/pypi"


def _fetch_hash(package: str, version: str) -> Optional[str]:
    """Fetch the SHA-256 hash for a specific package release from PyPI.

    Returns ``None`` if the hash cannot be determined (network error, etc.).
    """
    try:
        url = f"{_PYPI_BASE}/{package}/{version}/json"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        # Use the first sdist or bdist_wheel digest
        for file_info in data.get("urls", []):
            digests = file_info.get("digests", {})
            sha256 = digests.get("sha256")
            if sha256:
                return f"sha256:{sha256}"
    except Exception:
        pass
    return None


def get_latest_version(package_name: str) -> Optional[str]:
    """Query PyPI for the latest stable version of *package_name*.

    Parameters
    ----------
    package_name:
        PyPI package name.

    Returns
    -------
    str | None
        Latest version string, or ``None`` on failure.
    """
    try:
        url = f"{_PYPI_BASE}/{package_name}/json"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data["info"]["version"]
    except Exception:
        return None


def get_package_hash(package_name: str, version: str) -> Optional[str]:
    """Public convenience wrapper around ``_fetch_hash``."""
    return _fetch_hash(package_name, version)
