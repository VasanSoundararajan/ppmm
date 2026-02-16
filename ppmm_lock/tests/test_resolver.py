"""Unit tests for ppmm_lock.resolver — dependency resolution helpers."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from ppmm_lock.resolver import (
    ResolvedDependency,
    get_installed_packages,
    get_latest_version,
    get_package_hash,
)


class TestResolvedDependency:
    """Tests for the ``ResolvedDependency`` dataclass."""

    def test_basic_creation(self) -> None:
        dep = ResolvedDependency(name="numpy", version="1.26.4")
        assert dep.name == "numpy"
        assert dep.version == "1.26.4"
        assert dep.hash is None

    def test_with_hash(self) -> None:
        dep = ResolvedDependency(
            name="requests", version="2.31.0", hash="sha256:abc"
        )
        assert dep.hash == "sha256:abc"


class TestGetInstalledPackages:
    """Tests for ``get_installed_packages`` (mocked pip)."""

    @patch("ppmm_lock.resolver._run_pip")
    def test_parses_json(self, mock_pip: MagicMock) -> None:
        mock_pip.return_value = MagicMock(
            stdout='[{"name": "numpy", "version": "1.26.4"}, '
                   '{"name": "Requests", "version": "2.31.0"}]'
        )
        result = get_installed_packages()
        assert result == {"numpy": "1.26.4", "requests": "2.31.0"}

    @patch("ppmm_lock.resolver._run_pip")
    def test_empty_list(self, mock_pip: MagicMock) -> None:
        mock_pip.return_value = MagicMock(stdout="[]")
        result = get_installed_packages()
        assert result == {}


class TestGetLatestVersion:
    """Tests for ``get_latest_version`` (mocked HTTP)."""

    @patch("ppmm_lock.resolver.requests.get")
    def test_returns_version(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"info": {"version": "2.32.0"}}
        mock_get.return_value = mock_resp

        assert get_latest_version("requests") == "2.32.0"

    @patch("ppmm_lock.resolver.requests.get")
    def test_returns_none_on_404(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        assert get_latest_version("nonexistent-pkg") is None

    @patch("ppmm_lock.resolver.requests.get")
    def test_returns_none_on_exception(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = Exception("network error")
        assert get_latest_version("requests") is None


class TestGetPackageHash:
    """Tests for ``get_package_hash`` (mocked HTTP)."""

    @patch("ppmm_lock.resolver.requests.get")
    def test_returns_hash(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "urls": [
                {
                    "digests": {"sha256": "abcdef1234567890"},
                    "packagetype": "sdist",
                }
            ]
        }
        mock_get.return_value = mock_resp

        result = get_package_hash("numpy", "1.26.4")
        assert result == "sha256:abcdef1234567890"

    @patch("ppmm_lock.resolver.requests.get")
    def test_returns_none_on_failure(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = Exception("boom")
        assert get_package_hash("numpy", "1.26.4") is None
