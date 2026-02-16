"""Integration tests for ppmm_lock.cli — exercises CLI via CliRunner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from ppmm_lock.cli import main
from ppmm_lock.resolver import ResolvedDependency


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """Create a temp directory with a sample requirements.txt."""
    req = tmp_path / "requirements.txt"
    req.write_text("requests>=2.28\nnumpy>=1.24\n", encoding="utf-8")
    return tmp_path


class TestVersionFlag:
    def test_version_output(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "ppmm-lock" in result.output


class TestLockCommand:
    @patch("ppmm_lock.resolver.resolve_dependencies")
    def test_lock_creates_files(
        self,
        mock_resolve: MagicMock,
        runner: CliRunner,
        tmp_project: Path,
    ) -> None:
        mock_resolve.return_value = {
            "requests": ResolvedDependency("requests", "2.31.0", "sha256:abc"),
            "numpy": ResolvedDependency("numpy", "1.26.4"),
        }
        req_file = str(tmp_project / "requirements.txt")
        result = runner.invoke(main, ["lock", "-r", req_file])
        assert result.exit_code == 0
        assert "2 packages" in result.output

    def test_lock_missing_requirements(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(
            main, ["lock", "-r", str(tmp_path / "nope.txt")]
        )
        assert result.exit_code != 0


class TestInstallCommand:
    @patch("ppmm_lock.resolver.install_requirements")
    def test_install_from_lockfile(
        self,
        mock_install: MagicMock,
        runner: CliRunner,
        tmp_project: Path,
    ) -> None:
        # Create a lockfile
        lock = tmp_project / "requirements.lock"
        lock.write_text("requests==2.31.0\nnumpy==1.26.4\n", encoding="utf-8")

        with runner.isolated_filesystem(temp_dir=tmp_project):
            # Copy files into the isolated dir
            Path("requirements.lock").write_text(lock.read_text())
            Path("requirements.txt").write_text("requests>=2.28\n")
            result = runner.invoke(main, ["install"])

        assert result.exit_code == 0

    def test_install_no_files(self, runner: CliRunner, tmp_path: Path) -> None:
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["install"])
        assert result.exit_code != 0


class TestUpdateCommand:
    @patch("ppmm_lock.resolver.get_latest_version")
    @patch("ppmm_lock.resolver.get_installed_packages")
    def test_shows_upgrades(
        self,
        mock_installed: MagicMock,
        mock_latest: MagicMock,
        runner: CliRunner,
    ) -> None:
        mock_installed.return_value = {"requests": "2.30.0", "numpy": "1.26.4"}
        mock_latest.side_effect = lambda pkg: {
            "requests": "2.31.0",
            "numpy": "1.27.0",
        }.get(pkg)

        result = runner.invoke(main, ["update"])
        assert result.exit_code == 0
        assert "available" in result.output

    @patch("ppmm_lock.resolver.get_latest_version")
    @patch("ppmm_lock.resolver.get_installed_packages")
    def test_no_upgrades(
        self,
        mock_installed: MagicMock,
        mock_latest: MagicMock,
        runner: CliRunner,
    ) -> None:
        mock_installed.return_value = {"requests": "2.31.0"}
        mock_latest.return_value = "2.31.0"

        result = runner.invoke(main, ["update"])
        assert result.exit_code == 0
        assert "up to date" in result.output


class TestAuditCommand:
    @patch("ppmm_lock.scanner.audit_packages")
    def test_no_vulns(
        self,
        mock_audit: MagicMock,
        runner: CliRunner,
    ) -> None:
        mock_audit.return_value = []
        result = runner.invoke(main, ["audit"])
        assert result.exit_code == 0
        assert "No known vulnerabilities" in result.output

    @patch("ppmm_lock.scanner.audit_packages")
    def test_vulns_found(
        self,
        mock_audit: MagicMock,
        runner: CliRunner,
    ) -> None:
        from ppmm_lock.scanner import Vulnerability

        mock_audit.return_value = [
            Vulnerability(
                package="urllib3",
                installed_version="1.25.0",
                vulnerability_id="CVE-2021-12345",
                description="A critical vulnerability",
                fixed_version="1.26.18",
            )
        ]
        result = runner.invoke(main, ["audit"])
        assert result.exit_code != 0  # Non-zero on vulns
        assert "VULNERABLE" in result.output
        assert "urllib3" in result.output
        assert "1.26.18" in result.output

    @patch("ppmm_lock.scanner.audit_packages")
    def test_json_output(
        self,
        mock_audit: MagicMock,
        runner: CliRunner,
    ) -> None:
        mock_audit.return_value = []
        result = runner.invoke(main, ["audit", "--json-output"])
        assert result.exit_code == 0
        assert "[]" in result.output
