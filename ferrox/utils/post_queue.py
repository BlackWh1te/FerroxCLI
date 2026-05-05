"""Async post queue with rate limiting and deduplication for social daemons.

Provides :class:`PostQueue` — an asyncio-friendly queue that enforces
per-hour and per-day posting limits, deduplicates content by hash, and
tracks posting history for visibility and reset logic.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class QueuedPost:
    """A single item waiting to be published."""

    id: str
    platform: str  # "reddit" or "x"
    content: dict
    scheduled_at: datetime
    priority: int = 0
    posted_at: Optional[datetime] = None
    status: str = "pending"  # pending, posted, failed, skipped
    topic_hash: str = ""


class PostQueue:
    """Async queue for social-media posts with built-in rate limiting.

    Usage::

        queue = PostQueue(max_posts_per_hour=2, max_posts_per_day=5)
        await queue.enqueue(QueuedPost(...))
        post = await queue.dequeue()
        if post:
            # ... publish ...
            await queue.mark_posted(post)
    """

    def __init__(
        self,
        max_posts_per_hour: int = 1,
        max_posts_per_day: int = 5,
        dedup_window_hours: int = 72,
    ):
        self._queue: asyncio.Queue[QueuedPost] = asyncio.Queue()
        self._history: list[QueuedPost] = []
        self.max_posts_per_hour = max_posts_per_hour
        self.max_posts_per_day = max_posts_per_day
        self.dedup_window_hours = dedup_window_hours
        self._posted_hashes: set[str] = set()
        self._queued_hashes: set[str] = set()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def enqueue(self, post: QueuedPost) -> bool:
        """Add *post* to the queue.

        Returns ``False`` if the post (or its topic hash) is a duplicate
        inside the deduplication window.
        """
        content_hash = self._hash_post(post)
        if content_hash in self._posted_hashes or content_hash in self._queued_hashes:
            return False
        if post.topic_hash and (post.topic_hash in self._posted_hashes or post.topic_hash in self._queued_hashes):
            return False

        self._queued_hashes.add(content_hash)
        if post.topic_hash:
            self._queued_hashes.add(post.topic_hash)
        await self._queue.put(post)
        return True

    async def dequeue(self) -> Optional[QueuedPost]:
        """Return the next post if rate limits allow, otherwise ``None``."""
        async with self._lock:
            if not await self._can_post():
                return None
            if self._queue.empty():
                return None
            return self._queue.get_nowait()

    async def mark_posted(self, post: QueuedPost) -> None:
        """Record *post* as successfully published."""
        post.status = "posted"
        post.posted_at = datetime.now()
        self._history.append(post)
        h = self._hash_post(post)
        self._queued_hashes.discard(h)
        self._posted_hashes.add(h)
        if post.topic_hash:
            self._queued_hashes.discard(post.topic_hash)
            self._posted_hashes.add(post.topic_hash)
        self._cleanup_old_hashes()

    async def mark_failed(self, post: QueuedPost) -> None:
        """Record *post* as failed."""
        post.status = "failed"
        post.posted_at = datetime.now()
        self._history.append(post)
        self._queued_hashes.discard(self._hash_post(post))
        if post.topic_hash:
            self._queued_hashes.discard(post.topic_hash)

    async def mark_skipped(self, post: QueuedPost) -> None:
        """Record *post* as skipped (e.g. night-mode)."""
        post.status = "skipped"
        self._history.append(post)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    def posted_today(self) -> int:
        """Count successfully posted items in the last 24 h."""
        day_ago = datetime.now() - timedelta(days=1)
        return sum(
            1
            for p in self._history
            if p.status == "posted" and p.posted_at is not None and p.posted_at > day_ago
        )

    def failed_today(self) -> int:
        """Count failed items in the last 24 h."""
        day_ago = datetime.now() - timedelta(days=1)
        return sum(
            1
            for p in self._history
            if p.status == "failed" and p.posted_at is not None and p.posted_at > day_ago
        )

    def consecutive_failures(self) -> int:
        """Count consecutive failures at the tail of history."""
        count = 0
        for p in reversed(self._history):
            if p.status == "failed":
                count += 1
            elif p.status == "posted":
                break
            else:
                continue
        return count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _can_post(self) -> bool:
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)

        posted_this_hour = sum(
            1
            for p in self._history
            if p.status == "posted"
            and p.posted_at is not None
            and p.posted_at > hour_ago
        )
        posted_today = sum(
            1
            for p in self._history
            if p.status == "posted"
            and p.posted_at is not None
            and p.posted_at > day_ago
        )

        return (
            posted_this_hour < self.max_posts_per_hour
            and posted_today < self.max_posts_per_day
        )

    @staticmethod
    def _hash_post(post: QueuedPost) -> str:
        payload = f"{post.platform}:{post.id}:{str(post.content)}"
        return hashlib.md5(payload.encode(), usedforsecurity=False).hexdigest()[:16]

    def _cleanup_old_hashes(self) -> None:
        """Trim the dedup set so it doesn't grow unbounded."""
        if len(self._posted_hashes) > 200:
            # Keep the most recent 100 (set is unordered, so just drop half)
            self._posted_hashes = set(list(self._posted_hashes)[100:])
