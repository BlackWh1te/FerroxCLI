"""Content generation for social media automation.

Fetches news from RSS feeds, extracts topics, and uses the configured LLM
(via Ferrox's ``send_message`` API) to generate Reddit posts / comments and
X/Twitter tweets.  All fetched content is sanitised through
:func:`~ferrox.utils.content_safety.sanitize_content` and all generated
content is run through :func:`~ferrox.utils.content_safety.moderation_check`
before it is returned.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from ferrox.utils.content_safety import moderation_check, sanitize_content


# Lazily imported to avoid dragging heavy deps at import time
_feedparser: Optional[type] = None


def _get_feedparser():
    global _feedparser
    if _feedparser is None:
        import feedparser

        _feedparser = feedparser
    return _feedparser


@dataclass(frozen=True)
class NewsTopic:
    """A single news item extracted from an RSS feed."""

    title: str
    summary: str
    link: str
    source: str

    def to_prompt_context(self, max_chars: int = 800) -> str:
        """Return a concise string suitable for LLM prompts."""
        text = f"Title: {self.title}\nSummary: {self.summary}"
        return text[:max_chars]


def fetch_news_topics(sources: list[str], max_items: int = 5) -> list[NewsTopic]:
    """Fetch news from RSS feeds and return sanitised topics.

    Args:
        sources: List of RSS/Atom feed URLs.
        max_items: Maximum items to pull *per* source.

    Returns:
        List of :class:`NewsTopic` objects.  Empty list if all feeds fail.
    """
    if not sources:
        return []

    fp = _get_feedparser()
    topics: list[NewsTopic] = []

    for url in sources:
        try:
            feed = fp.parse(url)
            for entry in getattr(feed, "entries", [])[:max_items]:
                title = entry.get("title", "")
                summary = entry.get("summary", "") or entry.get("description", "")
                link = entry.get("link", "")

                # Defensive sanitisation
                s_title, t_warn = sanitize_content(title)
                s_summary, s_warn = sanitize_content(summary)
                if t_warn or s_warn:
                    # Prompt-injection or other high-risk content – skip
                    continue

                topics.append(
                    NewsTopic(
                        title=s_title.strip(),
                        summary=s_summary.strip(),
                        link=link.strip(),
                        source=url,
                    )
                )
        except Exception:
            # Feed unparseable / unreachable – silently skip
            continue

    return topics


class ContentGenerationError(Exception):
    """Raised when content generation or moderation fails."""

    pass


def _hash_topic(topic: NewsTopic) -> str:
    """Short MD5 hash for deduplication."""
    payload = f"{topic.title}:{topic.link}"
    return hashlib.md5(payload.encode(), usedforsecurity=False).hexdigest()[:16]


def _call_llm(prompt: str) -> str:
    """Send *prompt* to the active LLM and return the full response text.

    This is a thin wrapper around :func:`ferrox.api.send_message`.
    """
    # Lazy imports avoid circular deps and heavy startup cost
    from ferrox.api import send_message
    from ferrox.config import get_default_config, load_config

    config = load_config()
    if config is None:
        config = get_default_config()

    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful social-media content creator. "
                "Create natural, engaging posts that sound human. "
                "Follow the user's output-format instructions exactly."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    try:
        chunks = list(send_message(config, messages, stream=False))
    except Exception as exc:
        raise ContentGenerationError(f"LLM request failed: {exc}") from exc

    return "".join(chunks).strip()


def _moderate(text: str, label: str) -> None:
    """Run moderation check and raise on violations."""
    is_safe, violations = moderation_check(text)
    if not is_safe:
        raise ContentGenerationError(f"{label} failed moderation: {violations}")


# ---------------------------------------------------------------------------
# Reddit
# ---------------------------------------------------------------------------


def generate_reddit_post(
    strategy: str,
    topic: NewsTopic,
    tone: str = "casual",
    subreddit: str = "",
) -> dict[str, str]:
    """Generate a Reddit post title and body from a news topic.

    Args:
        strategy: Natural-language bot strategy.
        topic: News topic to base the post on.
        tone: Writing tone (professional, casual, witty, neutral).
        subreddit: Target subreddit name (contextual hint).

    Returns:
        Dict with ``title``, ``body``, and ``topic_hash`` keys.

    Raises:
        ContentGenerationError: On LLM failure or moderation violation.
    """
    prompt = f"""Create a Reddit post based on this news topic:

{topic.to_prompt_context()}

Bot strategy: {strategy}
Target subreddit: {subreddit or "general"}
Tone: {tone}

Requirements:
- Title must be under 300 characters
- Body should be 1-3 paragraphs
- Do NOT include the raw source URL in the post text
- Write naturally, as a human Redditor would
- If the topic is technical, explain it in accessible terms

Output format:
TITLE: <post title>
BODY: <post body>"""

    response = _call_llm(prompt)

    # Parse TITLE / BODY sections
    title = ""
    body = ""
    lower = response.lower()
    if "title:" in lower and "body:" in lower:
        # Find case-insensitive split point
        idx = lower.index("body:")
        title_part = response[:idx].strip()
        body_part = response[idx + 5 :].strip()
        # Strip "TITLE:" prefix if present
        if title_part.lower().startswith("title:"):
            title_part = title_part[6:].strip()
        title = title_part
        body = body_part
    else:
        lines = response.split("\n", 1)
        title = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""

    # Enforce limits
    title = title[:300]
    body = body[:4000]

    _moderate(title + " " + body, "Reddit post")

    return {
        "title": title,
        "body": body,
        "topic_hash": _hash_topic(topic),
    }


def generate_reddit_comment(
    strategy: str,
    post_title: str,
    post_body: str,
    tone: str = "casual",
) -> str:
    """Generate a Reddit comment from post context.

    Args:
        strategy: Natural-language bot strategy.
        post_title: Title of the post being commented on.
        post_body: Body of the post (truncated internally).
        tone: Writing tone.

    Returns:
        Generated comment text.

    Raises:
        ContentGenerationError: On LLM failure or moderation violation.
    """
    prompt = f"""Create a Reddit comment for this post:

Post title: {post_title}
Post body: {post_body[:500]}

Bot strategy: {strategy}
Tone: {tone}

Requirements:
- 1-3 sentences
- Be helpful, constructive, or add value
- Write naturally, as a human Redditor would
- Do NOT be promotional
- Do NOT include URLs"""

    comment = _call_llm(prompt)
    comment = comment[:2000]

    _moderate(comment, "Reddit comment")
    return comment


# ---------------------------------------------------------------------------
# X / Twitter
# ---------------------------------------------------------------------------


def generate_x_tweet(
    strategy: str,
    topic: NewsTopic,
    tone: str = "casual",
) -> str:
    """Generate an X/Twitter tweet from a news topic.

    Args:
        strategy: Natural-language bot strategy.
        topic: News topic to base the tweet on.
        tone: Writing tone.

    Returns:
        Tweet text (guaranteed ≤ 280 characters).

    Raises:
        ContentGenerationError: On LLM failure or moderation violation.
    """
    prompt = f"""Create a tweet based on this news topic:

{topic.to_prompt_context(max_chars=600)}

Bot strategy: {strategy}
Tone: {tone}

Requirements:
- Must be under 280 characters
- Do NOT include the raw source URL
- Write naturally, as a human would tweet
- Can include 1-2 relevant hashtags if natural
- Be engaging and conversational"""

    tweet = _call_llm(prompt)
    tweet = tweet[:280].strip()

    _moderate(tweet, "X tweet")
    return tweet


def generate_x_thread(
    strategy: str,
    topic: NewsTopic,
    tone: str = "casual",
    max_tweets: int = 3,
) -> list[str]:
    """Generate an X/Twitter thread (list of tweets) from a news topic.

    Args:
        strategy: Natural-language bot strategy.
        topic: News topic to base the thread on.
        tone: Writing tone.
        max_tweets: Maximum number of tweets in the thread.

    Returns:
        List of tweet texts, each ≤ 280 characters.

    Raises:
        ContentGenerationError: On LLM failure or moderation violation.
    """
    prompt = f"""Create an X/Twitter thread based on this news topic:

{topic.to_prompt_context(max_chars=600)}

Bot strategy: {strategy}
Tone: {tone}

Requirements:
- Thread should have 2-{max_tweets} tweets
- Each tweet must be under 280 characters
- Do NOT include the raw source URL
- Write naturally, as a human would tweet
- First tweet should be a hook / attention grabber
- Number each tweet: 1. 2. 3. etc.

Output format:
1. <first tweet>
2. <second tweet>
..."""

    response = _call_llm(prompt)
    tweets: list[str] = []

    for line in response.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip leading numbering like "1. " or "Tweet 1:"
        cleaned = line
        if ". " in cleaned[:5]:
            cleaned = cleaned.split(". ", 1)[1]
        elif cleaned.lower().startswith("tweet "):
            cleaned = cleaned.split(":", 1)[1] if ":" in cleaned else cleaned[6:]
        cleaned = cleaned.strip()
        if cleaned:
            cleaned = cleaned[:280]
            _moderate(cleaned, f"X thread tweet {len(tweets) + 1}")
            tweets.append(cleaned)

    if not tweets:
        raise ContentGenerationError("LLM returned no valid tweets for thread")

    return tweets[:max_tweets]
