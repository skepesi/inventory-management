"""
Tests for file path resolution in the mock data loader.
"""
import json
import os
from pathlib import Path

import pytest

import mock_data

SERVER_DIR = Path(__file__).resolve().parent.parent.parent / "server"

DATA_FILES = [
    "inventory.json",
    "orders.json",
    "demand_forecasts.json",
    "backlog_items.json",
    "spending.json",
    "transactions.json",
    "purchase_orders.json",
]


class TestDataDirectoryPaths:
    """Test suite for the module-level data directory constants."""

    def test_base_dir_is_absolute(self):
        """Test that BASE_DIR does not depend on how the module was imported."""
        assert os.path.isabs(mock_data.BASE_DIR)

    def test_base_dir_is_server_directory(self):
        """Test that BASE_DIR points at the server directory."""
        assert Path(mock_data.BASE_DIR).resolve() == SERVER_DIR

    def test_data_dir_is_inside_base_dir(self):
        """Test that DATA_DIR is the data folder under BASE_DIR."""
        assert Path(mock_data.DATA_DIR).resolve() == SERVER_DIR / "data"

    def test_data_dir_exists(self):
        """Test that DATA_DIR is an existing directory."""
        assert os.path.isdir(mock_data.DATA_DIR)

    @pytest.mark.parametrize("filename", DATA_FILES)
    def test_data_file_exists(self, filename):
        """Test that each file the loader needs exists in DATA_DIR."""
        assert os.path.isfile(os.path.join(mock_data.DATA_DIR, filename))


class TestLoadJsonFilePaths:
    """Test suite for path handling in load_json_file."""

    @pytest.mark.parametrize("filename", DATA_FILES)
    def test_load_json_file_finds_data_file(self, filename):
        """Test that each data file loads by bare filename."""
        # Check the type, not truthiness: purchase_orders.json is a valid empty list.
        assert isinstance(mock_data.load_json_file(filename), (list, dict))

    def test_load_json_file_ignores_working_directory(self, tmp_path, monkeypatch):
        """Test that a file of the same name in the cwd is not loaded instead."""
        (tmp_path / "inventory.json").write_text(json.dumps({"decoy": True}))
        monkeypatch.chdir(tmp_path)

        data = mock_data.load_json_file("inventory.json")

        assert data != {"decoy": True}
        assert isinstance(data, list)

    def test_load_json_file_reads_from_data_dir(self, tmp_path, monkeypatch):
        """Test that the filename is resolved against DATA_DIR."""
        (tmp_path / "sample.json").write_text(json.dumps({"source": "tmp"}))
        monkeypatch.setattr(mock_data, "DATA_DIR", str(tmp_path))

        assert mock_data.load_json_file("sample.json") == {"source": "tmp"}

    def test_load_json_file_missing_file(self):
        """Test that a missing file raises and names the full resolved path."""
        with pytest.raises(FileNotFoundError) as exc_info:
            mock_data.load_json_file("does_not_exist.json")

        assert exc_info.value.filename == os.path.join(
            mock_data.DATA_DIR, "does_not_exist.json"
        )
