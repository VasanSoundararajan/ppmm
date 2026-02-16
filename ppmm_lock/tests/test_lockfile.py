"""Unit tests for ppmm_lock.lockfile — lockfile generation and reading."""

import json
from pathlib import Path

import pytest

from ppmm_lock.lockfile import (
    LOCK_JSON,
    LOCK_TEXT,
    generate_lockfile,
    lockfile_exists,
    read_lockfile,
)
from ppmm_lock.resolver import ResolvedDependency


@pytest.fixture()
def tmp_dir(tmp_path: Path) -> Path:
    """Return a clean temporary directory."""
    return tmp_path


@pytest.fixture()
def sample_resolved() -> dict[str, ResolvedDependency]:
    """Return a small set of resolved deps for testing."""
    return {
        "requests": ResolvedDependency(
            name="requests", version="2.31.0", hash="sha256:abc123"
        ),
        "numpy": ResolvedDependency(
            name="numpy", version="1.26.4", hash=None
        ),
        "urllib3": ResolvedDependency(
            name="urllib3", version="2.0.7", hash="sha256:def456"
        ),
    }


class TestGenerateLockfile:
    """Tests for ``generate_lockfile``."""

    def test_creates_both_files(
        self, tmp_dir: Path, sample_resolved: dict[str, ResolvedDependency]
    ) -> None:
        text_path, json_path = generate_lockfile(sample_resolved, tmp_dir)
        assert text_path.exists()
        assert json_path.exists()

    def test_text_lockfile_content(
        self, tmp_dir: Path, sample_resolved: dict[str, ResolvedDependency]
    ) -> None:
        text_path, _ = generate_lockfile(sample_resolved, tmp_dir)
        content = text_path.read_text(encoding="utf-8")
        assert "numpy==1.26.4" in content
        assert "requests==2.31.0" in content
        assert "urllib3==2.0.7" in content
        # Sorted alphabetically
        lines = [l for l in content.splitlines() if l and not l.startswith("#")]
        names = [l.split("==")[0] for l in lines]
        assert names == sorted(names)

    def test_json_lockfile_structure(
        self, tmp_dir: Path, sample_resolved: dict[str, ResolvedDependency]
    ) -> None:
        _, json_path = generate_lockfile(sample_resolved, tmp_dir)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["lockfile_version"] == "1"
        assert "created_at" in data
        deps = data["dependencies"]
        assert deps["requests"]["version"] == "2.31.0"
        assert deps["requests"]["hash"] == "sha256:abc123"
        assert "hash" not in deps["numpy"]  # None → omitted

    def test_overwrites_existing(
        self, tmp_dir: Path, sample_resolved: dict[str, ResolvedDependency]
    ) -> None:
        generate_lockfile(sample_resolved, tmp_dir)
        # Write again — should not raise
        generate_lockfile(sample_resolved, tmp_dir)


class TestReadLockfile:
    """Tests for ``read_lockfile``."""

    def test_read_json(
        self, tmp_dir: Path, sample_resolved: dict[str, ResolvedDependency]
    ) -> None:
        generate_lockfile(sample_resolved, tmp_dir)
        result = read_lockfile(tmp_dir)
        assert "requests" in result
        assert result["requests"].version == "2.31.0"
        assert result["urllib3"].hash == "sha256:def456"

    def test_read_text_fallback(
        self, tmp_dir: Path, sample_resolved: dict[str, ResolvedDependency]
    ) -> None:
        generate_lockfile(sample_resolved, tmp_dir)
        # Remove JSON file → forces text fallback
        (tmp_dir / LOCK_JSON).unlink()
        result = read_lockfile(tmp_dir)
        assert "numpy" in result
        assert result["numpy"].version == "1.26.4"

    def test_missing_raises(self, tmp_dir: Path) -> None:
        with pytest.raises(FileNotFoundError, match="No lockfile found"):
            read_lockfile(tmp_dir)


class TestLockfileExists:
    """Tests for ``lockfile_exists``."""

    def test_false_when_missing(self, tmp_dir: Path) -> None:
        assert lockfile_exists(tmp_dir) is False

    def test_true_when_present(
        self, tmp_dir: Path, sample_resolved: dict[str, ResolvedDependency]
    ) -> None:
        generate_lockfile(sample_resolved, tmp_dir)
        assert lockfile_exists(tmp_dir) is True
