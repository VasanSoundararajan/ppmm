"""CLI entry-point for **ppmm-lock**.

Provides four subcommands:

* ``ppmm-lock lock``    — resolve and pin all dependencies
* ``ppmm-lock install`` — install from lock or requirements file
* ``ppmm-lock update``  — check for available upgrades
* ``ppmm-lock audit``   — scan for known vulnerabilities
"""

from __future__ import annotations

from pathlib import Path

import click

from ppmm_lock import __version__


# ======================================================================
# Helpers
# ======================================================================

def _styled(msg: str, *, fg: str = "green", bold: bool = False) -> None:
    click.echo(click.style(msg, fg=fg, bold=bold))


def _error(msg: str) -> None:
    click.echo(click.style(f"✖ {msg}", fg="red", bold=True), err=True)


def _info(msg: str) -> None:
    click.echo(click.style(f"  {msg}", fg="cyan"))


def _success(msg: str) -> None:
    click.echo(click.style(f"✔ {msg}", fg="green", bold=True))


def _warn(msg: str) -> None:
    click.echo(click.style(f"⚠ {msg}", fg="yellow"))


# ======================================================================
# CLI group
# ======================================================================

@click.group()
@click.version_option(version=__version__, prog_name="ppmm-lock")
def main() -> None:
    """PPMM Lock — Dependency lock & version management for Python projects."""


# ======================================================================
# ppmm-lock lock
# ======================================================================

@main.command()
@click.option(
    "-r",
    "--requirements",
    "req_path",
    default="requirements.txt",
    type=click.Path(exists=False),
    help="Path to requirements file (default: requirements.txt).",
)
@click.option(
    "--no-hashes",
    is_flag=True,
    default=False,
    help="Skip hash computation (faster).",
)
def lock(req_path: str, no_hashes: bool) -> None:
    """Resolve dependencies and generate a lockfile.

    Reads the requirements file, installs packages, captures the full
    resolved dependency tree (including transitive dependencies), and
    writes ``requirements.lock`` + ``requirements.lock.json``.
    """
    from ppmm_lock.resolver import resolve_dependencies, ResolvedDependency
    from ppmm_lock.lockfile import generate_lockfile

    path = Path(req_path)
    if not path.exists():
        _error(f"File not found: {path}")
        raise SystemExit(1)

    _styled("🔒 Resolving dependencies …", fg="cyan", bold=True)
    try:
        resolved = resolve_dependencies(path)
    except Exception as exc:
        _error(f"Resolution failed: {exc}")
        raise SystemExit(1)

    if no_hashes:
        # Strip hashes
        resolved = {
            k: ResolvedDependency(name=v.name, version=v.version)
            for k, v in resolved.items()
        }

    text_path, json_path = generate_lockfile(resolved, directory=path.parent)

    _success(f"Lockfile generated with {len(resolved)} packages")
    _info(f"Text → {text_path}")
    _info(f"JSON → {json_path}")

    click.echo()
    for dep in sorted(resolved.values(), key=lambda d: d.name):
        hash_suffix = f"  ({dep.hash[:30]}…)" if dep.hash else ""
        click.echo(f"  {dep.name}=={dep.version}{hash_suffix}")


# ======================================================================
# ppmm-lock install
# ======================================================================

@main.command()
@click.option(
    "-r",
    "--requirements",
    "req_path",
    default=None,
    type=click.Path(exists=False),
    help="Explicit requirements file to install from.",
)
def install(req_path: str | None) -> None:
    """Install packages from the lockfile (or requirements.txt fallback).

    If ``requirements.lock`` exists the locked versions are installed.
    Otherwise the tool falls back to ``requirements.txt``.
    """
    from ppmm_lock.lockfile import lockfile_exists, LOCK_TEXT
    from ppmm_lock.resolver import install_requirements

    cwd = Path.cwd()

    if req_path:
        target = Path(req_path)
    elif lockfile_exists(cwd):
        target = cwd / LOCK_TEXT
        _info("Installing from lockfile (requirements.lock)")
    elif (cwd / "requirements.txt").exists():
        target = cwd / "requirements.txt"
        _warn("No lockfile found — falling back to requirements.txt")
    else:
        _error("No requirements.lock or requirements.txt found.")
        raise SystemExit(1)

    _styled(f"📦 Installing from {target.name} …", fg="cyan", bold=True)
    try:
        install_requirements(target)
    except Exception as exc:
        _error(f"Installation failed: {exc}")
        raise SystemExit(1)

    _success("All packages installed successfully.")


# ======================================================================
# ppmm-lock update
# ======================================================================

@main.command()
@click.option(
    "--apply",
    is_flag=True,
    default=False,
    help="Apply updates and regenerate the lockfile.",
)
def update(apply: bool) -> None:
    """Check for available package upgrades.

    Compares installed versions with the latest releases on PyPI.
    Use ``--apply`` to actually upgrade and regenerate the lockfile.
    """
    from ppmm_lock.resolver import get_installed_packages, get_latest_version, _run_pip
    from ppmm_lock.version import SemanticVersion, compare_versions

    _styled("🔍 Checking for updates …", fg="cyan", bold=True)

    installed = get_installed_packages()
    if not installed:
        _warn("No packages installed.")
        return

    upgrades: list[tuple[str, str, str]] = []  # (name, current, latest)
    with click.progressbar(
        sorted(installed.items()),
        label="  Querying PyPI",
        show_pos=True,
    ) as bar:
        for name, current_ver in bar:
            latest = get_latest_version(name)
            if latest is None:
                continue
            try:
                cur = SemanticVersion.parse(current_ver)
                lat = SemanticVersion.parse(latest)
                if lat > cur:
                    upgrades.append((name, current_ver, latest))
            except ValueError:
                # Fall back to simple string comparison
                if latest != current_ver:
                    upgrades.append((name, current_ver, latest))

    click.echo()
    if not upgrades:
        _success("All packages are up to date!")
        return

    _styled(f"  {len(upgrades)} update(s) available:", fg="yellow", bold=True)
    click.echo()
    for name, current, latest in upgrades:
        click.echo(f"  {name} {compare_versions(current, latest)}")

    if not apply:
        click.echo()
        _info("Run with --apply to upgrade and regenerate the lockfile.")
        return

    # Apply upgrades
    click.echo()
    _styled("⬆ Applying upgrades …", fg="cyan", bold=True)
    for name, _, latest in upgrades:
        try:
            _run_pip("install", f"{name}=={latest}", capture=False)
            _success(f"  {name} → {latest}")
        except Exception as exc:
            _error(f"  Failed to upgrade {name}: {exc}")

    # Regenerate lockfile from current state
    click.echo()
    _styled("🔒 Regenerating lockfile …", fg="cyan", bold=True)
    req_path = Path.cwd() / "requirements.txt"
    if req_path.exists():
        from ppmm_lock.resolver import resolve_dependencies
        from ppmm_lock.lockfile import generate_lockfile

        resolved = resolve_dependencies(req_path)
        generate_lockfile(resolved)
        _success("Lockfile regenerated.")
    else:
        _warn("No requirements.txt found — lockfile not regenerated.")


# ======================================================================
# ppmm-lock audit
# ======================================================================

@main.command()
@click.option(
    "--json-output",
    "as_json",
    is_flag=True,
    default=False,
    help="Output results as JSON.",
)
def audit(as_json: bool) -> None:
    """Scan installed packages for known vulnerabilities.

    Integrates with ``pip-audit``, ``safety``, or falls back to PyPI
    advisory metadata.
    """
    import json as _json

    from ppmm_lock.scanner import audit_packages

    _styled("🛡️  Auditing dependencies …", fg="cyan", bold=True)

    try:
        vulns = audit_packages()
    except Exception as exc:
        _error(f"Audit failed: {exc}")
        raise SystemExit(1)

    if as_json:
        data = [
            {
                "package": v.package,
                "installed_version": v.installed_version,
                "vulnerability_id": v.vulnerability_id,
                "description": v.description,
                "fixed_version": v.fixed_version,
            }
            for v in vulns
        ]
        click.echo(_json.dumps(data, indent=2))
        return

    if not vulns:
        _success("No known vulnerabilities found!")
        return

    _styled(
        f"  Found {len(vulns)} vulnerability(ies):", fg="red", bold=True
    )
    click.echo()
    for v in vulns:
        _error(f"VULNERABLE: {v.package} {v.installed_version}")
        if v.vulnerability_id:
            _info(f"  ID: {v.vulnerability_id}")
        if v.description:
            desc = v.description[:120] + ("…" if len(v.description) > 120 else "")
            _info(f"  {desc}")
        if v.fixed_version:
            _success(f"  Fix: upgrade to {v.fixed_version}")
        click.echo()

    raise SystemExit(1)  # Non-zero exit if vulnerabilities found
