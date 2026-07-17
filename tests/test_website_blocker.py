"""Unit tests for focuslock.blocking.website_blocker.

Covers: _strip, normalize_domain, is_valid_domain, _atomic_write, and
block_sites/unblock_sites behavior (with HOSTS monkeypatched to a temp file).
"""

import os
import tempfile
from pathlib import Path

import pytest

from focuslock.blocking.website_blocker import (
    _strip,
    normalize_domain,
    is_valid_domain,
    _atomic_write,
    block_sites,
    unblock_sites,
    FL_START,
    FL_END,
)


# ═══════════════════════════════════════════════════════════════════════════
# _strip
# ═══════════════════════════════════════════════════════════════════════════

class TestStrip:
    """Remove everything between FocusLock markers."""

    def test_strips_block(self):
        content = f"line1\n{FL_START}\n127.0.0.1 a.com\n{FL_END}\nline2"
        assert _strip(content) == "line1\nline2"

    def test_strips_multiple_blocks(self):
        content = (
            f"a\n{FL_START}\n127.0.0.1 x.com\n{FL_END}\n"
            f"b\n{FL_START}\n127.0.0.1 y.com\n{FL_END}\nc"
        )
        result = _strip(content)
        assert "x.com" not in result
        assert "y.com" not in result
        assert result == "a\nb\nc"

    def test_no_markers_unchanged(self):
        content = "just some text\n127.0.0.1 example.com"
        assert _strip(content) == content

    def test_empty_content(self):
        assert _strip("") == ""

    def test_markers_only(self):
        content = f"{FL_START}\n{FL_END}"
        assert _strip(content) == ""

    def test_open_block_without_end(self):
        """Block without closing marker should strip to end of content."""
        content = f"before\n{FL_START}\n127.0.0.1 a.com\nafter"
        result = _strip(content)
        assert "127.0.0.1" not in result
        assert "before" in result

    def test_preserves_text_outside_markers(self):
        content = (
            "127.0.0.1 real.com\n"
            f"{FL_START}\n"
            "127.0.0.1 fake.com\n"
            f"{FL_END}\n"
            "127.0.0.1 also-real.com"
        )
        result = _strip(content)
        assert "real.com" in result
        assert "also-real.com" in result
        assert "fake.com" not in result


# ═══════════════════════════════════════════════════════════════════════════
# normalize_domain
# ═══════════════════════════════════════════════════════════════════════════

class TestNormalizeDomain:
    """Strip schemes, www., paths, queries, fragments, and lowercase."""

    @pytest.mark.parametrize("raw,expected", [
        ("https://example.com", "example.com"),
        ("http://example.com", "example.com"),
        ("www.example.com", "example.com"),
        ("https://www.example.com", "example.com"),
        ("Example.COM", "example.com"),
        ("  Example.com  ", "example.com"),
        ("example.com/path", "example.com"),
        ("example.com?q=1", "example.com"),
        ("example.com#section", "example.com"),
        ("example.com/path?q=1#section", "example.com"),
        ("HTTP://WWW.EXAMPLE.COM/path", "example.com"),
        ("example.com.", "example.com"),
        (".example.com.", "example.com"),
    ])
    def test_normalizations(self, raw, expected):
        assert normalize_domain(raw) == expected

    def test_none_returns_empty(self):
        assert normalize_domain(None) == ""

    def test_empty_string(self):
        assert normalize_domain("") == ""

    def test_whitespace_only(self):
        assert normalize_domain("   ") == ""


# ═══════════════════════════════════════════════════════════════════════════
# is_valid_domain
# ═══════════════════════════════════════════════════════════════════════════

class TestIsValidDomain:
    """RFC-ish domain validation."""

    @pytest.mark.parametrize("domain", [
        "example.com",
        "sub.domain.example.com",
        "my-site.co.uk",
        "a.b",
        "test123.org",
        "xn--nxasmq6b.com",  # IDN punycode
    ])
    def test_valid_domains(self, domain):
        assert is_valid_domain(domain) is True

    @pytest.mark.parametrize("domain,reason", [
        ("", "empty"),
        ("com", "single label"),
        ("example", "no TLD"),
        ("exam ple.com", "space"),
        ("-example.com", "leading dash"),
        ("example-.com", "trailing dash"),
        ("exam" * 20 + ".com", "part > 63 chars"),
        ("a" * 254 + ".com", "total > 253 chars"),
        (".example.com", "leading dot"),
        ("example..com", "double dot"),
    ])
    def test_invalid_domains(self, domain, reason):
        assert is_valid_domain(domain) is False

    def test_none_returns_false(self):
        assert is_valid_domain(None) is False


# ═══════════════════════════════════════════════════════════════════════════
# _atomic_write
# ═══════════════════════════════════════════════════════════════════════════

class TestAtomicWrite:
    """Atomic write via temp file + os.replace()."""

    def test_creates_file(self, tmp_path):
        target = tmp_path / "hosts"
        _atomic_write(target, "hello world")
        assert target.read_text(encoding="utf-8") == "hello world"

    def test_overwrites_existing(self, tmp_path):
        target = tmp_path / "hosts"
        target.write_text("old content", encoding="utf-8")
        _atomic_write(target, "new content")
        assert target.read_text(encoding="utf-8") == "new content"

    def test_no_temp_file_left_on_success(self, tmp_path):
        target = tmp_path / "hosts"
        _atomic_write(target, "data")
        temps = list(tmp_path.glob("*.tmp"))
        assert len(temps) == 0

    def test_cleans_up_on_error(self, tmp_path):
        target = tmp_path / "hosts"
        # Force an error by writing to a path where replace will fail
        with pytest.raises(Exception):
            _atomic_write(Path("/nonexistent/dir/file"), "data")
        # No .tmp files should remain
        temps = list(tmp_path.glob("*.tmp"))
        assert len(temps) == 0

    def test_content_is_utf8(self, tmp_path):
        target = tmp_path / "hosts"
        _atomic_write(target, "日本語テスト")
        assert target.read_text(encoding="utf-8") == "日本語テスト"


# ═══════════════════════════════════════════════════════════════════════════
# block_sites / unblock_sites (HOSTS monkeypatched)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def hosts_file(tmp_path, monkeypatch):
    """Create a fake hosts file and monkeypatch HOSTS to point to it."""
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    monkeypatch.setattr("focuslock.blocking.website_blocker.HOSTS", hosts)
    return hosts


class TestBlockSites:
    """block_sites injects entries between FocusLock markers."""

    def test_adds_entries(self, hosts_file):
        block_sites(["example.com"])
        content = hosts_file.read_text(encoding="utf-8")
        assert "127.0.0.1 example.com" in content
        assert "127.0.0.1 www.example.com" in content
        assert FL_START in content
        assert FL_END in content

    def test_preserves_existing_hosts(self, hosts_file):
        block_sites(["example.com"])
        content = hosts_file.read_text(encoding="utf-8")
        assert "127.0.0.1 localhost" in content

    def test_idempotent(self, hosts_file):
        block_sites(["example.com"])
        block_sites(["example.com"])
        content = hosts_file.read_text(encoding="utf-8")
        assert content.count("127.0.0.1 example.com") == 1

    def test_multiple_domains(self, hosts_file):
        block_sites(["a.com", "b.com"])
        content = hosts_file.read_text(encoding="utf-8")
        assert "127.0.0.1 a.com" in content
        assert "127.0.0.1 b.com" in content

    def test_empty_list_unblocks(self, hosts_file):
        block_sites(["example.com"])
        block_sites([])
        content = hosts_file.read_text(encoding="utf-8")
        assert "example.com" not in content

    def test_normalizes_domains(self, hosts_file):
        block_sites(["HTTPS://WWW.Example.COM/path"])
        content = hosts_file.read_text(encoding="utf-8")
        assert "127.0.0.1 example.com" in content

    def test_deduplicates(self, hosts_file):
        block_sites(["example.com", "example.com", "Example.com"])
        content = hosts_file.read_text(encoding="utf-8")
        assert content.count("127.0.0.1 example.com") == 1

    def test_www_not_doubled_if_already_present(self, hosts_file):
        block_sites(["www.example.com"])
        content = hosts_file.read_text(encoding="utf-8")
        assert "127.0.0.1 www.example.com" in content
        # Should NOT add a second www.www.example.com
        assert "www.www." not in content

    def test_returns_true_on_success(self, hosts_file):
        assert block_sites(["example.com"]) is True

    def test_returns_false_on_permission_error(self, monkeypatch):
        import focuslock.blocking.website_blocker as wb
        original = wb.HOSTS

        def _raise_permission(*a, **kw):
            raise PermissionError("denied")

        monkeypatch.setattr(wb, "HOSTS", Path("/nonexistent/hosts"))
        # PermissionError is caught and returns False
        result = block_sites(["example.com"])
        assert result is False


class TestUnblockSites:
    """unblock_sites removes all FocusLock entries."""

    def test_removes_block_entries(self, hosts_file):
        block_sites(["example.com"])
        unblock_sites()
        content = hosts_file.read_text(encoding="utf-8")
        assert "example.com" not in content
        assert FL_START not in content

    def test_preserves_original_hosts(self, hosts_file):
        block_sites(["example.com"])
        unblock_sites()
        content = hosts_file.read_text(encoding="utf-8")
        assert "127.0.0.1 localhost" in content

    def test_no_markers_is_noop(self, hosts_file):
        unblock_sites()
        content = hosts_file.read_text(encoding="utf-8")
        assert "127.0.0.1 localhost" in content

    def test_returns_true_on_success(self, hosts_file):
        assert unblock_sites() is True

    def test_returns_false_on_permission_error(self, monkeypatch):
        import focuslock.blocking.website_blocker as wb
        monkeypatch.setattr(wb, "HOSTS", Path("/nonexistent/hosts"))
        result = unblock_sites()
        assert result is False


class TestBlockUnblockCycle:
    """Full block → unblock cycle."""

    def test_round_trip(self, hosts_file):
        original = hosts_file.read_text(encoding="utf-8")
        block_sites(["test.com", "other.com"])
        unblock_sites()
        final = hosts_file.read_text(encoding="utf-8")
        # _strip uses splitlines() which drops trailing newline, so normalize
        assert final.strip() == original.strip()

    def test_block_change_unblock(self, hosts_file):
        block_sites(["a.com"])
        block_sites(["b.com"])
        unblock_sites()
        content = hosts_file.read_text(encoding="utf-8")
        assert "a.com" not in content
        assert "b.com" not in content
