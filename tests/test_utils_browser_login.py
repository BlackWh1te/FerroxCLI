"""Tests for ferrox.utils.browser_login cookie helpers"""

import json
from pathlib import Path

import pytest

from ferrox.utils.browser_login import (
    convert_to_httpx_cookiejar,
    load_browser_cookies,
    save_cookies_playwright_format,
)


class TestSaveCookiesPlaywrightFormat:
    """Test save_cookies_playwright_format"""

    def test_saves_valid_json(self, tmp_path):
        """Saves cookies in Playwright JSON format"""
        path = tmp_path / "cookies.json"
        cookies = [
            {"name": "session", "value": "abc123", "domain": ".reddit.com"},
        ]
        save_cookies_playwright_format(cookies, path)

        assert path.exists()
        data = json.loads(path.read_text())
        assert data["format"] == "playwright"
        assert "saved_at" in data
        assert data["cookies"] == cookies

    def test_creates_parent_dirs(self, tmp_path):
        """Creates parent directories if needed"""
        path = tmp_path / "deep" / "nested" / "cookies.json"
        save_cookies_playwright_format([], path)
        assert path.exists()

    def test_empty_cookies(self, tmp_path):
        """Handles empty cookie list"""
        path = tmp_path / "empty.json"
        save_cookies_playwright_format([], path)
        data = json.loads(path.read_text())
        assert data["cookies"] == []


class TestConvertToHttpxCookiejar:
    """Test convert_to_httpx_cookiejar"""

    def test_converts_cookies(self):
        """Converts Playwright cookies to name->value dict"""
        cookies = [
            {"name": "a", "value": "1"},
            {"name": "b", "value": "2"},
        ]
        jar = convert_to_httpx_cookiejar(cookies)
        assert jar == {"a": "1", "b": "2"}

    def test_skips_empty_names(self):
        """Skips cookies with empty names"""
        cookies = [
            {"name": "", "value": "skip"},
            {"name": "valid", "value": "keep"},
        ]
        jar = convert_to_httpx_cookiejar(cookies)
        assert jar == {"valid": "keep"}

    def test_empty_list(self):
        """Handles empty cookie list"""
        jar = convert_to_httpx_cookiejar([])
        assert jar == {}

    def test_missing_name_key(self):
        """Handles cookies without 'name' key"""
        cookies = [
            {"value": "no-name"},
            {"name": "has-name", "value": "yes"},
        ]
        jar = convert_to_httpx_cookiejar(cookies)
        assert jar == {"has-name": "yes"}


class TestLoadBrowserCookies:
    """Test load_browser_cookies"""

    def test_file_not_exists(self, tmp_path):
        """Returns None when file doesn't exist"""
        path = tmp_path / "nonexistent.json"
        assert load_browser_cookies(path) is None

    def test_dict_format_with_cookies_key(self, tmp_path):
        """Loads cookies from dict with 'cookies' key"""
        path = tmp_path / "cookies.json"
        path.write_text(
            json.dumps(
                {
                    "format": "playwright",
                    "cookies": [{"name": "s", "value": "v"}],
                }
            )
        )
        result = load_browser_cookies(path)
        assert result == [{"name": "s", "value": "v"}]

    def test_list_format(self, tmp_path):
        """Loads cookies from raw list"""
        path = tmp_path / "cookies.json"
        path.write_text(json.dumps([{"name": "s", "value": "v"}]))
        result = load_browser_cookies(path)
        assert result == [{"name": "s", "value": "v"}]

    def test_invalid_json_returns_none(self, tmp_path):
        """Returns None for invalid JSON"""
        path = tmp_path / "bad.json"
        path.write_text("not json")
        assert load_browser_cookies(path) is None

    def test_dict_without_cookies_key_returns_none(self, tmp_path):
        """Returns None for dict without 'cookies' key"""
        path = tmp_path / "other.json"
        path.write_text(json.dumps({"foo": "bar"}))
        assert load_browser_cookies(path) is None
