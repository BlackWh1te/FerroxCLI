"""Tests for SocialBotDaemon intelligence layer (Phase 1)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ferrox.social_config import SocialConfig
from ferrox.utils.post_queue import PostQueue, QueuedPost


@pytest.fixture
def mock_social_config():
    """Return a SocialConfig with safe test settings."""
    return SocialConfig(
        enabled=True,
        strategy="Post tech news",
        content={"tone": "witty", "draft_mode": False},
        news_sources=["https://example.com/feed"],
        safety={"auto_pause_on_failures": 3, "warmup_enabled": False},
    )


@pytest.fixture
def mock_daemon(mock_social_config):
    """Return a SocialBotDaemon with mocked state/lock."""
    with patch("ferrox.social_daemon.load_social_state") as mock_load:
        mock_state = MagicMock()
        mock_state.posts_today = 0
        mock_state.comments_today = 0
        mock_state.consecutive_failures = 0
        mock_state.session_valid = True
        mock_state.daemon_running = False
        mock_state.daemon_started_at = None
        mock_state.daemon_pid = None
        mock_load.return_value = mock_state

        with patch("ferrox.social_daemon.LockFileDaemon") as mock_lock:
            mock_lock_instance = MagicMock()
            mock_lock_instance.read_command.return_value = ""
            mock_lock.return_value = mock_lock_instance

            with patch("ferrox.social_daemon.save_social_state"):
                from ferrox.social_daemon import SocialBotDaemon

                daemon = SocialBotDaemon(config=mock_social_config)
                daemon.queue = PostQueue(max_posts_per_hour=10, max_posts_per_day=100)
                return daemon


class TestFetchAndEnqueue:
    """Test _fetch_and_enqueue"""

    @pytest.mark.asyncio
    async def test_fetches_and_enqueues(self, mock_daemon):
        """Fetches topics and enqueues generated tweet"""
        from ferrox.utils.content_generator import NewsTopic

        topic = NewsTopic(title="AI news", summary="New model", link="L", source="S")

        with patch("ferrox.social_daemon.fetch_news_topics", return_value=[topic]):
            with patch("ferrox.social_daemon.generate_x_tweet", return_value="Tweet text here"):
                result = await mock_daemon._fetch_and_enqueue()

        assert result is True
        assert mock_daemon.queue.pending_count == 1

    @pytest.mark.asyncio
    async def test_no_topics_returns_false(self, mock_daemon):
        """No topics found means nothing enqueued"""
        with patch("ferrox.social_daemon.fetch_news_topics", return_value=[]):
            result = await mock_daemon._fetch_and_enqueue()
        assert result is False
        assert mock_daemon.queue.pending_count == 0

    @pytest.mark.asyncio
    async def test_generation_error_returns_false(self, mock_daemon):
        """Content generation error means nothing enqueued"""
        from ferrox.utils.content_generator import ContentGenerationError

        topic = MagicMock()
        with patch("ferrox.social_daemon.fetch_news_topics", return_value=[topic]):
            with patch(
                "ferrox.social_daemon.generate_x_tweet",
                side_effect=ContentGenerationError("bad"),
            ):
                result = await mock_daemon._fetch_and_enqueue()
        assert result is False


class TestPublishFromQueue:
    """Test _publish_from_queue"""

    @pytest.mark.asyncio
    async def test_no_pending_returns_false(self, mock_daemon):
        """Empty queue returns False"""
        result = await mock_daemon._publish_from_queue()
        assert result is False

    @pytest.mark.asyncio
    async def test_draft_mode_publishes_without_browser(self, mock_daemon):
        """Draft mode marks posted without browser call"""
        mock_daemon.config.content.draft_mode = True
        post = QueuedPost(
            id="x1",
            platform="x",
            content={"text": "Hello world"},
            scheduled_at=datetime.now(),
        )
        await mock_daemon.queue.enqueue(post)

        with patch("ferrox.social_daemon.save_social_state"):
            result = await mock_daemon._publish_from_queue()

        assert result is True
        assert mock_daemon.queue.posted_today() == 1

    @pytest.mark.asyncio
    async def test_live_post_via_tool(self, mock_daemon):
        """Live mode calls post_tweet_tool"""
        mock_daemon.config.content.draft_mode = False
        post = QueuedPost(
            id="x1",
            platform="x",
            content={"text": "Live tweet"},
            scheduled_at=datetime.now(),
        )
        await mock_daemon.queue.enqueue(post)

        with patch("ferrox.agent.tools_social.post_tweet_tool", new_callable=AsyncMock) as mock_post:
            with patch("pydantic_ai.RunContext"):
                with patch("ferrox.social_daemon.save_social_state"):
                    result = await mock_daemon._publish_from_queue()

        assert result is True
        mock_post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_browser_error_marks_failed(self, mock_daemon):
        """Browser error marks post as failed"""
        mock_daemon.config.content.draft_mode = False
        post = QueuedPost(
            id="x1",
            platform="x",
            content={"text": "Live tweet"},
            scheduled_at=datetime.now(),
        )
        await mock_daemon.queue.enqueue(post)

        with patch("ferrox.agent.tools_social.post_tweet_tool", side_effect=Exception("network")):
            with patch("pydantic_ai.RunContext"):
                with patch("ferrox.social_daemon.save_social_state"):
                    result = await mock_daemon._publish_from_queue()

        assert result is False
        assert mock_daemon.queue.failed_today() == 1


class TestGenerateAndPost:
    """Test generate_and_post orchestrator"""

    @pytest.mark.asyncio
    async def test_calls_fetch_and_publish(self, mock_daemon):
        """Orchestrator calls fetch then publish"""
        mock_daemon._fetch_and_enqueue = AsyncMock(return_value=True)
        mock_daemon._publish_from_queue = AsyncMock(return_value=True)

        result = await mock_daemon.generate_and_post()

        assert result is True
        mock_daemon._fetch_and_enqueue.assert_awaited_once()
        mock_daemon._publish_from_queue.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_fetch_if_queue_not_empty(self, mock_daemon):
        """Does not fetch if queue already has items"""
        post = QueuedPost(
            id="x1", platform="x", content={"text": "T"}, scheduled_at=datetime.now()
        )
        await mock_daemon.queue.enqueue(post)
        mock_daemon._fetch_and_enqueue = AsyncMock(return_value=True)
        mock_daemon._publish_from_queue = AsyncMock(return_value=True)

        result = await mock_daemon.generate_and_post()

        assert result is True
        mock_daemon._fetch_and_enqueue.assert_not_awaited()
        mock_daemon._publish_from_queue.assert_awaited_once()


class TestRecordSuccessAndFailure:
    """Test state tracking methods"""

    def test_record_success(self, mock_daemon):
        """record_success updates counters"""
        with patch("ferrox.social_daemon.save_social_state"):
            mock_daemon._record_success()
        assert mock_daemon.state.posts_today == 1
        assert mock_daemon.state.consecutive_failures == 0

    def test_record_failure(self, mock_daemon):
        """record_failure increments fail counter"""
        with patch("ferrox.social_daemon.save_social_state"):
            mock_daemon._record_failure()
        assert mock_daemon.state.consecutive_failures == 1


class TestDaemonInitialization:
    """Test constructor and queue setup"""

    def test_creates_queue(self, mock_social_config):
        """Daemon initializes with PostQueue"""
        with patch("ferrox.social_daemon.load_social_state") as mock_load:
            mock_state = MagicMock()
            mock_state.daemon_running = False
            mock_state.daemon_started_at = None
            mock_state.daemon_pid = None
            mock_load.return_value = mock_state

            with patch("ferrox.social_daemon.LockFileDaemon") as mock_lock:
                mock_lock.return_value = MagicMock()
                with patch("ferrox.social_daemon.save_social_state"):
                    from ferrox.social_daemon import SocialBotDaemon

                    d = SocialBotDaemon(config=mock_social_config)
                    assert isinstance(d.queue, PostQueue)

    def test_queue_limits_for_new_account(self, mock_social_config):
        """New account gets stricter limits"""
        from ferrox.social_daemon import get_rate_limits_for_account_type

        with patch("ferrox.social_daemon.load_social_state") as mock_load:
            mock_state = MagicMock()
            mock_state.daemon_running = False
            mock_state.daemon_started_at = None
            mock_state.daemon_pid = None
            mock_load.return_value = mock_state

            with patch("ferrox.social_daemon.LockFileDaemon") as mock_lock:
                mock_lock.return_value = MagicMock()
                with patch("ferrox.social_daemon.save_social_state"):
                    from ferrox.social_daemon import SocialBotDaemon

                    d = SocialBotDaemon(config=mock_social_config)
                    d.current_account_type = "new"
                    limits = get_rate_limits_for_account_type("new")
                    assert d.queue.max_posts_per_hour == limits.max_posts_per_hour
                    assert d.queue.max_posts_per_day == limits.max_posts_per_day
