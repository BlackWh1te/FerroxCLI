"""Tests for ferrox.reddit_browser_login module"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ferrox.reddit_browser_login import (
    _is_reddit_logged_in,
    clear_reddit_session,
    get_cookie_path,
    get_user_data_dir,
    has_saved_reddit_session,
    reddit_login_via_browser,
)


class TestPaths:
    """Test path helper functions"""

    def test_get_cookie_path(self):
        """Returns correct Reddit cookie path"""
        path = get_cookie_path()
        assert path == Path.home() / ".ferrox" / "reddit_cookies.json"

    def test_get_user_data_dir(self):
        """Returns correct Reddit browser profile path"""
        path = get_user_data_dir()
        assert path == Path.home() / ".ferrox" / "reddit_browser_profile"


class TestIsRedditLoggedIn:
    """Test _is_reddit_logged_in URL checker"""

    def test_login_page_returns_false(self):
        """reddit.com/login is not a logged-in state"""
        assert _is_reddit_logged_in("https://www.reddit.com/login") is False
        assert _is_reddit_logged_in("https://reddit.com/login/") is False

    def test_account_page_returns_false(self):
        """reddit.com/account is not a logged-in state"""
        assert _is_reddit_logged_in("https://www.reddit.com/account") is False

    def test_register_page_returns_false(self):
        """reddit.com/register is not a logged-in state"""
        assert _is_reddit_logged_in("https://www.reddit.com/register") is False

    def test_home_page_returns_true(self):
        """reddit.com/ is a logged-in state"""
        assert _is_reddit_logged_in("https://www.reddit.com/") is True

    def test_feed_page_returns_true(self):
        """reddit.com/r/all is a logged-in state"""
        assert _is_reddit_logged_in("https://www.reddit.com/r/all") is True

    def test_case_insensitive(self):
        """URL check is case-insensitive"""
        assert _is_reddit_logged_in("https://www.REDDIT.COM/LOGIN") is False
        assert _is_reddit_logged_in("https://REDDIT.COM/") is True


class TestHasSavedRedditSession:
    """Test has_saved_reddit_session"""

    def test_no_file_returns_false(self, tmp_path, monkeypatch):
        """When cookie file doesn't exist, return False"""
        fake_path = tmp_path / "reddit_cookies.json"
        monkeypatch.setattr(
            "ferrox.reddit_browser_login.get_cookie_path", lambda: fake_path
        )
        assert has_saved_reddit_session() is False

    def test_empty_file_returns_false(self, tmp_path, monkeypatch):
        """When cookie file is empty, return False"""
        fake_path = tmp_path / "reddit_cookies.json"
        fake_path.write_text("")
        monkeypatch.setattr(
            "ferrox.reddit_browser_login.get_cookie_path", lambda: fake_path
        )
        assert has_saved_reddit_session() is False

    def test_valid_cookies_returns_true(self, tmp_path, monkeypatch):
        """When cookie file has valid cookies, return True"""
        fake_path = tmp_path / "reddit_cookies.json"
        fake_path.write_text(
            json.dumps(
                {
                    "format": "playwright",
                    "saved_at": "2025-01-01T00:00:00",
                    "cookies": [{"name": "reddit_session", "value": "abc"}],
                }
            )
        )
        monkeypatch.setattr(
            "ferrox.reddit_browser_login.get_cookie_path", lambda: fake_path
        )
        assert has_saved_reddit_session() is True

    def test_list_format_returns_true(self, tmp_path, monkeypatch):
        """When cookie file is a raw list, return True"""
        fake_path = tmp_path / "reddit_cookies.json"
        fake_path.write_text(json.dumps([{"name": "session", "value": "x"}]))
        monkeypatch.setattr(
            "ferrox.reddit_browser_login.get_cookie_path", lambda: fake_path
        )
        assert has_saved_reddit_session() is True


class TestClearRedditSession:
    """Test clear_reddit_session"""

    def test_deletes_cookie_file(self, tmp_path, monkeypatch):
        """Deletes cookie file if it exists"""
        fake_path = tmp_path / "reddit_cookies.json"
        fake_path.write_text("cookies")
        monkeypatch.setattr(
            "ferrox.reddit_browser_login.get_cookie_path", lambda: fake_path
        )
        clear_reddit_session()
        assert not fake_path.exists()

    def test_deletes_jar_file(self, tmp_path, monkeypatch):
        """Deletes jar file if it exists"""
        fake_path = tmp_path / "reddit_cookies.json"
        jar_path = tmp_path / "reddit_cookies.jar.json"
        fake_path.write_text("cookies")
        jar_path.write_text("jar")
        monkeypatch.setattr(
            "ferrox.reddit_browser_login.get_cookie_path", lambda: fake_path
        )
        clear_reddit_session()
        assert not fake_path.exists()
        assert not jar_path.exists()

    def test_no_files_no_error(self, tmp_path, monkeypatch):
        """No error when files don't exist"""
        fake_path = tmp_path / "reddit_cookies.json"
        monkeypatch.setattr(
            "ferrox.reddit_browser_login.get_cookie_path", lambda: fake_path
        )
        clear_reddit_session()  # should not raise


class TestRedditLoginViaBrowser:
    """Test reddit_login_via_browser async flow"""

    @pytest.mark.asyncio
    async def test_calls_run_browser_login(self, monkeypatch):
        """Creates correct BrowserLoginConfig and delegates to run_browser_login"""
        captured_config = None

        async def mock_run(config):
            nonlocal captured_config
            captured_config = config
            return "Session saved (42 cookies). Run '/reddit start' to begin."

        monkeypatch.setattr(
            "ferrox.reddit_browser_login.run_browser_login", mock_run
        )

        result = await reddit_login_via_browser(timeout_seconds=300)

        assert result == "Session saved (42 cookies). Run '/reddit start' to begin."
        assert captured_config is not None
        assert captured_config.cookie_path == get_cookie_path()
        assert captured_config.profile_dir == get_user_data_dir()
        assert captured_config.login_url == "https://www.reddit.com/login/"
        assert captured_config.title == "Reddit Browser Login (Stealth Mode)"
        assert captured_config.fallback_cmd == "/reddit login"
        assert captured_config.start_cmd == "/reddit start"
        assert captured_config.key_cookie_names == {
            "reddit_session",
            "token_v2",
            "session_tracker",
            "loid",
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
            "ferrox.reddit_browser_login.run_browser_login", mock_run
        )

        await reddit_login_via_browser()
        assert captured_config.timeout_seconds == 180
