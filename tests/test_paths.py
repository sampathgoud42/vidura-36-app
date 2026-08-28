from __future__ import annotations

import pytest

from app.core import paths


def test_windows_style_detection():
    assert paths.is_windows_style("D:\\data\\customers\\sampath")
    assert paths.is_windows_style("D:/data/customers/sampath")
    assert paths.is_windows_style("\\\\server\\share\\folder")
    assert not paths.is_windows_style("/home/sampath/customers")
    assert not paths.is_windows_style("relative/path")


def test_canonical_str_forward_slashes():
    assert paths.canonical_str("D:\\a\\b") == "D:/a/b"
    assert paths.canonical_str("/home/x/y") == "/home/x/y"


def test_resolve_user_file_inside_root(tmp_path):
    (tmp_path / "wellness-profile.json").write_text("{}")
    resolved = paths.resolve_user_file(str(tmp_path), "wellness-profile.json")
    assert resolved.is_file()


def test_resolve_user_file_blocks_traversal(tmp_path):
    with pytest.raises(paths.PathSecurityError):
        paths.resolve_user_file(str(tmp_path), "..", "other-user", ".env")


def test_empty_root_rejected():
    with pytest.raises(ValueError):
        paths.normalize_root("   ")
