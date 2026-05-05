"""Tests for ferrox.utils.post_queue module."""

import asyncio
from datetime import datetime, timedelta

import pytest

from ferrox.utils.post_queue import PostQueue, QueuedPost


class TestPostQueueEnqueue:
    """Test enqueue functionality"""

    @pytest.fixture
    def queue(self):
        return PostQueue(max_posts_per_hour=2, max_posts_per_day=5)

    @pytest.mark.asyncio
    async def test_enqueue_new_post(self, queue):
        """New post is accepted"""
        post = QueuedPost(
            id="p1", platform="reddit", content={"title": "T"}, scheduled_at=datetime.now()
        )
        result = await queue.enqueue(post)
        assert result is True
        assert queue.pending_count == 1

    @pytest.mark.asyncio
    async def test_enqueue_duplicate_rejected(self, queue):
        """Duplicate post is rejected"""
        post = QueuedPost(
            id="p1", platform="reddit", content={"title": "T"}, scheduled_at=datetime.now()
        )
        await queue.enqueue(post)
        result = await queue.enqueue(post)
        assert result is False

    @pytest.mark.asyncio
    async def test_enqueue_duplicate_topic_hash(self, queue):
        """Post with duplicate topic_hash is rejected"""
        post1 = QueuedPost(
            id="p1", platform="reddit", content={"title": "T1"}, scheduled_at=datetime.now(), topic_hash="abc123"
        )
        post2 = QueuedPost(
            id="p2", platform="reddit", content={"title": "T2"}, scheduled_at=datetime.now(), topic_hash="abc123"
        )
        await queue.enqueue(post1)
        result = await queue.enqueue(post2)
        assert result is False


class TestPostQueueDequeue:
    """Test dequeue functionality"""

    @pytest.fixture
    def queue(self):
        return PostQueue(max_posts_per_hour=2, max_posts_per_day=5)

    @pytest.mark.asyncio
    async def test_dequeue_returns_post(self, queue):
        """Dequeue returns the next post"""
        post = QueuedPost(
            id="p1", platform="reddit", content={"title": "T"}, scheduled_at=datetime.now()
        )
        await queue.enqueue(post)
        result = await queue.dequeue()
        assert result is not None
        assert result.id == "p1"

    @pytest.mark.asyncio
    async def test_dequeue_empty_queue(self, queue):
        """Dequeue returns None when queue is empty"""
        result = await queue.dequeue()
        assert result is None

    @pytest.mark.asyncio
    async def test_dequeue_rate_limit_blocks(self, queue):
        """Dequeue returns None when rate limit reached"""
        q = PostQueue(max_posts_per_hour=1, max_posts_per_day=5)
        # Post twice within the hour
        post1 = QueuedPost(id="p1", platform="reddit", content={"title": "T1"}, scheduled_at=datetime.now())
        post2 = QueuedPost(id="p2", platform="reddit", content={"title": "T2"}, scheduled_at=datetime.now())
        await q.enqueue(post1)
        await q.enqueue(post2)
        first = await q.dequeue()
        assert first is not None
        await q.mark_posted(first)
        second = await q.dequeue()
        assert second is None  # Rate limited


class TestPostQueueMarkPosted:
    """Test mark_posted functionality"""

    @pytest.fixture
    def queue(self):
        return PostQueue(max_posts_per_hour=2, max_posts_per_day=5)

    @pytest.mark.asyncio
    async def test_mark_posted_updates_state(self, queue):
        """Mark posted updates post status and history"""
        post = QueuedPost(id="p1", platform="reddit", content={"title": "T"}, scheduled_at=datetime.now())
        await queue.enqueue(post)
        dequeued = await queue.dequeue()
        await queue.mark_posted(dequeued)

        assert dequeued.status == "posted"
        assert dequeued.posted_at is not None
        assert queue.posted_today() == 1

    @pytest.mark.asyncio
    async def test_posted_today_counts_only_recent(self, queue):
        """posted_today only counts posts in last 24h"""
        old_post = QueuedPost(
            id="old", platform="reddit", content={"title": "Old"}, scheduled_at=datetime.now()
        )
        await queue.mark_posted(old_post)
        # Manually set posted_at to 2 days ago
        old_post.posted_at = datetime.now() - timedelta(days=2)

        new_post = QueuedPost(
            id="new", platform="reddit", content={"title": "New"}, scheduled_at=datetime.now()
        )
        await queue.enqueue(new_post)
        dequeued = await queue.dequeue()
        await queue.mark_posted(dequeued)

        assert queue.posted_today() == 1


class TestPostQueueMarkFailed:
    """Test mark_failed functionality"""

    @pytest.fixture
    def queue(self):
        return PostQueue(max_posts_per_hour=2, max_posts_per_day=5)

    @pytest.mark.asyncio
    async def test_mark_failed_updates_state(self, queue):
        """Mark failed updates post status"""
        post = QueuedPost(id="p1", platform="reddit", content={"title": "T"}, scheduled_at=datetime.now())
        await queue.enqueue(post)
        dequeued = await queue.dequeue()
        await queue.mark_failed(dequeued)

        assert dequeued.status == "failed"
        assert dequeued.posted_at is not None
        assert queue.failed_today() == 1


class TestPostQueueConsecutiveFailures:
    """Test consecutive_failures tracking"""

    @pytest.fixture
    def queue(self):
        return PostQueue(max_posts_per_hour=2, max_posts_per_day=5)

    @pytest.mark.asyncio
    async def test_counts_consecutive_failures(self, queue):
        """Counts failures until a success breaks the chain"""
        for i in range(3):
            post = QueuedPost(id=f"f{i}", platform="reddit", content={"title": "T"}, scheduled_at=datetime.now())
            await queue.enqueue(post)
            dequeued = await queue.dequeue()
            await queue.mark_failed(dequeued)

        assert queue.consecutive_failures() == 3

    @pytest.mark.asyncio
    async def test_success_resets_count(self, queue):
        """Success resets consecutive failure count"""
        # One failure
        post1 = QueuedPost(id="f1", platform="reddit", content={"title": "T"}, scheduled_at=datetime.now())
        await queue.enqueue(post1)
        await queue.mark_failed(await queue.dequeue())

        # One success
        post2 = QueuedPost(id="s1", platform="reddit", content={"title": "T"}, scheduled_at=datetime.now())
        await queue.enqueue(post2)
        await queue.mark_posted(await queue.dequeue())

        # Two more failures
        for i in range(2):
            post = QueuedPost(id=f"f{i+2}", platform="reddit", content={"title": "T"}, scheduled_at=datetime.now())
            await queue.enqueue(post)
            await queue.mark_failed(await queue.dequeue())

        assert queue.consecutive_failures() == 2


class TestPostQueuePendingCount:
    """Test pending_count property"""

    def test_empty_queue(self):
        """Empty queue has 0 pending"""
        q = PostQueue()
        assert q.pending_count == 0

    @pytest.mark.asyncio
    async def test_after_enqueue(self):
        """Enqueue increases pending count"""
        q = PostQueue()
        post = QueuedPost(id="p1", platform="reddit", content={"title": "T"}, scheduled_at=datetime.now())
        await q.enqueue(post)
        assert q.pending_count == 1

    @pytest.mark.asyncio
    async def test_after_dequeue(self):
        """Dequeue decreases pending count"""
        q = PostQueue()
        post = QueuedPost(id="p1", platform="reddit", content={"title": "T"}, scheduled_at=datetime.now())
        await q.enqueue(post)
        await q.dequeue()
        assert q.pending_count == 0


class TestPostQueueMultiplePlatforms:
    """Test queue handles both reddit and x posts"""

    @pytest.fixture
    def queue(self):
        return PostQueue(max_posts_per_hour=10, max_posts_per_day=100)

    @pytest.mark.asyncio
    async def test_mixed_platforms(self, queue):
        """Queue handles posts from different platforms"""
        reddit_post = QueuedPost(id="r1", platform="reddit", content={"title": "T"}, scheduled_at=datetime.now())
        x_post = QueuedPost(id="x1", platform="x", content={"text": "Tweet"}, scheduled_at=datetime.now())

        await queue.enqueue(reddit_post)
        await queue.enqueue(x_post)

        assert queue.pending_count == 2
        first = await queue.dequeue()
        assert first.platform in ("reddit", "x")
        await queue.mark_posted(first)
        assert queue.posted_today() == 1
