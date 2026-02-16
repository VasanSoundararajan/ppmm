"""Security scanner — audits installed packages for known vulnerabilities.

Uses the following strategy (in order of priority):

1. ``pip-audit`` (preferred) — runs ``pip-audit --format=json``.
2. ``safety`` — runs ``safety check --json``.
3. **PyPI advisory fallback** — queries the PyPI JSON API for
   ``vulnerabilities`` metadata (available since PEP 685 / Warehouse).

The public entry point is :func:`audit_packages`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class Vulnerability:
    """A single known vulnerability for an installed package."""

    package: str
    installed_version: str
    vulnerability_id: str
    description: str
    fixed_version: Optional[str] = None


# ======================================================================
# Public API
# ======================================================================

def audit_packages() -> list[Vulnerability]:
    """Scan installed packages for known vulnerabilities.

    Tries ``pip-audit`` first, then ``safety``, and finally falls back to
    the PyPI advisory metadata.

    Returns
    -------
    list[Vulnerability]
        Potentially empty list of discovered vulnerabilities.
    """
    # 1. pip-audit
    vulns = _try_pip_audit()
    if vulns is not None:
        return vulns

    # 2. safety
    vulns = _try_safety()
    if vulns is not None:
        return vulns

    # 3. PyPI advisory fallback
    return _try_pypi_advisory()


# ======================================================================
# pip-audit
# ======================================================================

def _try_pip_audit() -> Optional[list[Vulnerability]]:
    """Attempt to run ``pip-audit --format=json``."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--format=json", "--output=-"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        # pip-audit exits 1 when vulns are found — that's fine
        output = result.stdout.strip()
        if not output:
            return []
        data = json.loads(output)
        vulns: list[Vulnerability] = []
        if isinstance(data, dict):
            # pip-audit >= 2.x format: {"dependencies": [...]}
            entries = data.get("dependencies", [])
        else:
            entries = data  # older flat-list format

        for entry in entries:
            pkg = entry.get("name", "")
            ver = entry.get("version", "")
            for v in entry.get("vulns", []):
                vulns.append(
                    Vulnerability(
                        package=pkg,
                        installed_version=ver,
                        vulnerability_id=v.get("id", "UNKNOWN"),
                        description=v.get("description", ""),
                        fixed_version=_first_fixed(v.get("fix_versions", [])),
                    )
                )
        return vulns
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    except Exception:
        return None


# ======================================================================
# safety
# ======================================================================

def _try_safety() -> Optional[list[Vulnerability]]:
    """Attempt to run ``safety check --json``."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "safety", "check", "--json"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout.strip()
        if not output:
            return []
        data = json.loads(output)
        vulns: list[Vulnerability] = []
        # safety JSON output is a list of 5-element lists
        if isinstance(data, list):
            for item in data:
                if isinstance(item, list) and len(item) >= 5:
                    vulns.append(
                        Vulnerability(
                            package=item[0],
                            installed_version=item[2],
                            vulnerability_id=item[4],
                            description=item[3],
                            fixed_version=item[1] if item[1] else None,
                        )
                    )
        return vulns
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    except Exception:
        return None


# ======================================================================
# PyPI advisory fallback
# ======================================================================

def _try_pypi_advisory() -> list[Vulnerability]:
    """Query the PyPI JSON API for vulnerability metadata.

    PyPI includes a ``vulnerabilities`` key in the per-version JSON
    endpoint (e.g. ``/pypi/<pkg>/<ver>/json``).
    """
    from ppmm_lock.resolver import get_installed_packages

    installed = get_installed_packages()
    vulns: list[Vulnerability] = []

    for pkg, ver in installed.items():
        try:
            url = f"https://pypi.org/pypi/{pkg}/{ver}/json"
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            for v in data.get("vulnerabilities", []):
                fixed = None
                fixed_in = v.get("fixed_in", [])
                if fixed_in:
                    fixed = fixed_in[-1]  # latest fix version
                vulns.append(
                    Vulnerability(
                        package=pkg,
                        installed_version=ver,
                        vulnerability_id=v.get("id", v.get("aliases", ["UNKNOWN"])[0]),
                        description=v.get("summary", v.get("details", "")),
                        fixed_version=fixed,
                    )
                )
        except Exception:
            continue

    return vulns


# ======================================================================
# Helpers
# ======================================================================

def _first_fixed(versions: list[str]) -> Optional[str]:
    """Return the first (lowest) fix version, or None."""
    return versions[0] if versions else None
