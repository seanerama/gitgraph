"""Unit tests for the fiddly bits of the extractor: parsing --numstat and
--raw diff lines (binary files, renames, normal add/delete lines)."""

import pytest

from gitgraph.extractor import (
    build_file_changes,
    parse_numstat_line,
    parse_raw_line,
)


class TestParseNumstatLine:
    def test_normal_add_delete_line(self):
        result = parse_numstat_line("12\t3\tsrc/main.py")
        assert result == {
            "additions": 12,
            "deletions": 3,
            "is_binary": False,
            "path": "src/main.py",
            "old_path": None,
        }

    def test_binary_line(self):
        result = parse_numstat_line("-\t-\tassets/logo.png")
        assert result["is_binary"] is True
        assert result["additions"] is None
        assert result["deletions"] is None
        assert result["path"] == "assets/logo.png"
        assert result["old_path"] is None

    def test_rename_line_simple_arrow(self):
        result = parse_numstat_line("1\t0\told_name.txt => new_name.txt")
        assert result["old_path"] == "old_name.txt"
        assert result["path"] == "new_name.txt"
        assert result["is_binary"] is False

    def test_rename_line_brace_factored(self):
        result = parse_numstat_line("2\t1\tsrc/{old => new}/module.py")
        assert result["old_path"] == "src/old/module.py"
        assert result["path"] == "src/new/module.py"

    def test_zero_line(self):
        result = parse_numstat_line("0\t0\tempty.txt")
        assert result["additions"] == 0
        assert result["deletions"] == 0
        assert result["is_binary"] is False

    def test_unparseable_line_raises(self):
        with pytest.raises(Exception):
            parse_numstat_line("not a numstat line")


class TestParseRawLine:
    def test_add(self):
        result = parse_raw_line(":000000 100644 0000000 abc1234 A\tnew_file.txt")
        assert result == {"change_type": "add", "old_path": None, "path": "new_file.txt"}

    def test_modify(self):
        result = parse_raw_line(":100644 100644 aaa1111 bbb2222 M\tsrc/main.py")
        assert result["change_type"] == "modify"
        assert result["path"] == "src/main.py"
        assert result["old_path"] is None

    def test_delete(self):
        result = parse_raw_line(":100644 000000 aaa1111 0000000 D\told.txt")
        assert result["change_type"] == "delete"
        assert result["path"] == "old.txt"

    def test_rename(self):
        result = parse_raw_line(":100644 100644 2227cdd e83a496 R064\ta.txt\tb.txt")
        assert result["change_type"] == "rename"
        assert result["old_path"] == "a.txt"
        assert result["path"] == "b.txt"

    def test_copy(self):
        result = parse_raw_line(":100644 100644 e83a496 e83a496 C100\tb.txt\te.txt")
        assert result["change_type"] == "copy"
        assert result["old_path"] == "b.txt"
        assert result["path"] == "e.txt"

    def test_unrecognized_status_raises(self):
        with pytest.raises(Exception):
            parse_raw_line(":100644 100644 aaa1111 bbb2222 U\tconflicted.txt")


class TestBuildFileChanges:
    def test_zips_raw_and_numstat_positionally(self):
        raw_lines = [
            ":100644 000000 aaa 000 D\tbin.dat",
            ":000000 100644 000 bbb A\tf1.txt",
        ]
        numstat_lines = [
            "-\t-\tbin.dat",
            "1\t0\tf1.txt",
        ]
        changes = build_file_changes(raw_lines, numstat_lines)
        assert len(changes) == 2
        assert changes[0] == {
            "file_path": "bin.dat",
            "additions": None,
            "deletions": None,
            "is_binary": 1,
            "change_type": "delete",
            "old_path": None,
        }
        assert changes[1] == {
            "file_path": "f1.txt",
            "additions": 1,
            "deletions": 0,
            "is_binary": 0,
            "change_type": "add",
            "old_path": None,
        }

    def test_rename_carries_old_path(self):
        raw_lines = [":100644 100644 2227cdd e83a496 R064\ta.txt\tb.txt"]
        numstat_lines = ["1\t0\ta.txt => b.txt"]
        changes = build_file_changes(raw_lines, numstat_lines)
        assert changes == [
            {
                "file_path": "b.txt",
                "additions": 1,
                "deletions": 0,
                "is_binary": 0,
                "change_type": "rename",
                "old_path": "a.txt",
            }
        ]

    def test_mismatched_line_counts_raises(self):
        with pytest.raises(Exception):
            build_file_changes([":000000 100644 000 bbb A\tf1.txt"], [])
