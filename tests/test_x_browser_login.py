"""Tests for ferrox.x_browser_login module"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ferrox.x_browser_login import (
    _is_x_logged_in,
    clear_x_session,
    get_cookie_path,
    get_user_data_dir,
    has_saved_x_session,
    x_login_via_browser,
)


class TestPaths:
    """Test path helper functions"""

    def test_get_cookie_path(self):
        """Returns correct X cookie path"""
        path = get_cookie_path()
        assert path == Path.home() / ".ferrox" / "twikit_cookies.json"

    def test_get_user_data_dir(self):
        """Returns correct X browser profile path"""
        path = get_user_data_dir()
        assert path == Path.home() / ".ferrox" / "browser_profile"


class TestIsXLoggedIn:
    """Test _is_x_logged_in URL checker"""

    def test_x_home_returns_true(self):
        """x.com/home indicates logged in"""
        assert _is_x_logged_in("https://x.com/home") is True

    def test_twitter_home_returns_true(self):
        """twitter.com/home indicates logged in"""
        assert _is_x_logged_in("https://twitter.com/home") is True

    def test_x_other_page_returns_true(self):
        """Any x.com page not /i/flow/login indicates logged in"""
        assert _is_x_logged_in("https://x.com/explore") is True
        assert _is_x_logged_in("https://x.com/settings") is True

    def test_login_flow_returns_false(self):
        """x.com/i/flow/login is not logged in"""
        assert _is_x_logged_in("https://x.com/i/flow/login") is False

    def test_case_insensitive(self):
        """URL check is case-insensitive"""
        assert _is_x_logged_in("https://X.COM/HOME") is True
        assert _is_x_logged_in("https://X.COM/I/FLOW/LOGIN") is False


class TestHasSavedXSession:
    """Test has_saved_x_session"""

    def test_no_file_returns_false(self, tmp_path, monkeypatch):
        """When cookie file doesn't exist, return False"""
        fake_path = tmp_path / "twikit_cookies.json"
        monkeypatch.setattr(
            "ferrox.x_browser_login.get_cookie_path", lambda: fake_path
        )
        assert has_saved_x_session() is False

    def test_empty_file_returns_false(self, tmp_path, monkeypatch):
        """When cookie file is empty, return False"""
        fake_path = tmp_path / "twikit_cookies.json"
        fake_path.write_text("")
        monkeypatch.setattr(
            "ferrox.x_browser_login.get_cookie_path", lambda: fake_path
        )
        assert has_saved_x_session() is False

    def test_valid_cookies_returns_true(self, tmp_path, monkeypatch):
        """When cookie file has valid cookies, return True"""
        fake_path = tmp_path / "twikit_cookies.json"
        fake_path.write_text(
            json.dumps(
                {
                    "format": "playwright",
                    "saved_at": "2025-01-01T00:00:00",
                    "cookies": [{"name": "auth_token", "value": "abc"}],
                }
            )
        )
        monkeypatch.setattr(
            "ferrox.x_browser_login.get_cookie_path", lambda: fake_path
        )
        assert has_saved_x_session() is True


class TestClearXSession:
    """Test clear_x_session"""

    def test_deletes_cookie_file(self, tmp_path, monkeypatch):
        """Deletes cookie file if it exists"""
        fake_path = tmp_path / "twikit_cookies.json"
        fake_path.write_text("cookies")
        monkeypatch.setattr(
            "ferrox.x_browser_login.get_cookie_path", lambda: fake_path
        )
        clear_x_session()
        assert not fake_path.exists()

    def test_deletes_jar_file(self, tmp_path, monkeypatch):
        """Deletes jar file if it exists"""
        fake_path = tmp_path / "twikit_cookies.json"
        jar_path = tmp_path / "twikit_cookies.jar.json"
        fake_path.write_text("cookies")
        jar_path.write_text("jar")
        monkeypatch.setattr(
            "ferrox.x_browser_login.get_cookie_path", lambda: fake_path
        )
        clear_x_session()
        assert not fake_path.exists()
        assert not jar_path.exists()

    def test_no_files_no_error(self, tmp_path, monkeypatch):
        """No error when files don't exist"""
        fake_path = tmp_path / "twikit_cookies.json"
        monkeypatch.setattr(
            "ferrox.x_browser_login.get_cookie_path", lambda: fake_path
        )
        clear_x_session()  # should not raise


class TestXLoginViaBrowser:
    """Test x_login_via_browser async flow"""

    @pytest.mark.asyncio
    async def test_calls_run_browser_login(self, monkeypatch):
        """Creates correct BrowserLoginConfig and delegates to run_browser_login"""
        captured_config = None

        async def mock_run(config):
            nonlocal captured_config
            captured_config = config
            return "Session saved (42 cookies). Run '/social start' to begin."

        monkeypatch.setattr(
            "ferrox.x_browser_login.run_browser_login", mock_run
        )

        result = await x_login_via_browser(timeout_seconds=300)

        assert result == "Session saved (42 cookies). Run '/social start' to begin."
        assert captured_config is not None
        assert captured_config.cookie_path == get_cookie_path()
        assert captured_config.profile_dir == get_user_data_dir()
        assert captured_config.login_url == "https://x.com/i/flow/login"
        assert captured_config.title == "X Browser Login (Stealth Mode)"
        assert captured_config.fallback_cmd == "/social login"
        assert captured_config.start_cmd == "/social start"
        assert captured_config.key_cookie_names == {
            "auth_token",
            "ct0",
            "twid",
            "guest_id",
        }
        assert captured_config.timeout_seconds == 300

    @pytest.mark.asyncio
    async def test_default_timeout(self, monkeypatch):
        """Default timeout is 180 seconds"""
        captured_config = None

        async def mock_run(config):
            nonlocal captured_config
            captured_config = config
            return "ok"

        monkeypatch.setattr(
            "ferrox.x_browser_login.run_browser_login", mock_run
        )

        await x_login_via_browser()
        assert captured_config.timeout_seconds == 180
