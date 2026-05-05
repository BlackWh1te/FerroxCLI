"""Tests for ferrox.utils.content_generator module."""

from unittest.mock import MagicMock, patch

import pytest

from ferrox.utils.content_generator import (
    ContentGenerationError,
    NewsTopic,
    _hash_topic,
    fetch_news_topics,
    generate_reddit_comment,
    generate_reddit_post,
    generate_x_thread,
    generate_x_tweet,
)


class TestNewsTopic:
    """Test NewsTopic dataclass"""

    def test_creation(self):
        """NewsTopic stores title, summary, link, source"""
        t = NewsTopic(title="T", summary="S", link="L", source="SRC")
        assert t.title == "T"
        assert t.summary == "S"
        assert t.link == "L"
        assert t.source == "SRC"

    def test_to_prompt_context(self):
        """to_prompt_context returns concise prompt text"""
        t = NewsTopic(title="AI Breakthrough", summary="New model released.", link="", source="")
        ctx = t.to_prompt_context()
        assert "AI Breakthrough" in ctx
        assert "New model released." in ctx
        assert "Title:" in ctx

    def test_to_prompt_context_truncation(self):
        """Respects max_chars limit"""
        t = NewsTopic(title="A" * 100, summary="B" * 1000, link="", source="")
        ctx = t.to_prompt_context(max_chars=50)
        assert len(ctx) <= 50


class TestHashTopic:
    """Test _hash_topic"""

    def test_deterministic(self):
        """Same topic produces same hash"""
        t = NewsTopic(title="T", summary="S", link="L", source="SRC")
        h1 = _hash_topic(t)
        h2 = _hash_topic(t)
        assert h1 == h2
        assert len(h1) == 16

    def test_different_topics_different_hashes(self):
        """Different topics produce different hashes"""
        t1 = NewsTopic(title="A", summary="S", link="L", source="SRC")
        t2 = NewsTopic(title="B", summary="S", link="L", source="SRC")
        assert _hash_topic(t1) != _hash_topic(t2)


class TestFetchNewsTopics:
    """Test fetch_news_topics RSS parsing"""

    def test_empty_sources(self):
        """Empty source list returns empty topics"""
        result = fetch_news_topics([])
        assert result == []

    @patch("ferrox.utils.content_generator._get_feedparser")
    def test_successful_parse(self, mock_get_fp):
        """Parses feed entries into NewsTopic objects"""
        mock_fp = MagicMock()
        mock_entry = MagicMock()
        mock_entry.get.side_effect = lambda k, default="": {
            "title": "Test Title",
            "summary": "Test Summary",
            "description": "",
            "link": "https://example.com",
        }.get(k, default)
        mock_fp.parse.return_value = MagicMock(entries=[mock_entry])
        mock_get_fp.return_value = mock_fp

        with patch("ferrox.utils.content_generator.sanitize_content", return_value=("Clean", [])):
            topics = fetch_news_topics(["https://feed.example"])

        assert len(topics) == 1
        assert topics[0].title == "Clean"
        assert topics[0].link == "https://example.com"

    @patch("ferrox.utils.content_generator._get_feedparser")
    def test_description_fallback(self, mock_get_fp):
        """Uses description when summary is missing"""
        mock_fp = MagicMock()
        mock_entry = MagicMock()
        mock_entry.get.side_effect = lambda k, default="": {
            "title": "T",
            "summary": "",
            "description": "Desc",
            "link": "L",
        }.get(k, default)
        mock_fp.parse.return_value = MagicMock(entries=[mock_entry])
        mock_get_fp.return_value = mock_fp

        with patch("ferrox.utils.content_generator.sanitize_content", return_value=("Clean", [])):
            topics = fetch_news_topics(["https://feed.example"])

        assert topics[0].summary == "Clean"

    @patch("ferrox.utils.content_generator._get_feedparser")
    def test_skips_injected_content(self, mock_get_fp):
        """Skips entries that trigger sanitize_content warnings"""
        mock_fp = MagicMock()
        mock_entry = MagicMock()
        mock_entry.get.side_effect = lambda k, default="": {
            "title": "Bad",
            "summary": "",
            "description": "",
            "link": "L",
        }.get(k, default)
        mock_fp.parse.return_value = MagicMock(entries=[mock_entry])
        mock_get_fp.return_value = mock_fp

        with patch(
            "ferrox.utils.content_generator.sanitize_content",
            return_value=("Blocked", ["PROMPT INJECTION DETECTED"]),
        ):
            topics = fetch_news_topics(["https://feed.example"])

        assert topics == []

    @patch("ferrox.utils.content_generator._get_feedparser")
    def test_graceful_parse_failure(self, mock_get_fp):
        """Unparseable feed is silently skipped"""
        mock_fp = MagicMock()
        mock_fp.parse.side_effect = Exception("parse error")
        mock_get_fp.return_value = mock_fp

        topics = fetch_news_topics(["https://bad.feed"])
        assert topics == []

    @patch("ferrox.utils.content_generator._get_feedparser")
    def test_respects_max_items(self, mock_get_fp):
        """Only pulls max_items per source"""
        mock_fp = MagicMock()
        entries = []
        for i in range(10):
            e = MagicMock()
            e.get.side_effect = lambda k, default="", idx=i: {
                "title": f"T{idx}",
                "summary": f"S{idx}",
                "link": f"L{idx}",
            }.get(k, default)
            entries.append(e)
        mock_fp.parse.return_value = MagicMock(entries=entries)
        mock_get_fp.return_value = mock_fp

        with patch("ferrox.utils.content_generator.sanitize_content", return_value=("Clean", [])):
            topics = fetch_news_topics(["https://feed.example"], max_items=3)

        assert len(topics) == 3


class TestGenerateRedditPost:
    """Test generate_reddit_post LLM integration"""

    @patch("ferrox.utils.content_generator._call_llm")
    @patch("ferrox.utils.content_generator.moderation_check", return_value=(True, []))
    def test_parses_title_body(self, mock_mod, mock_llm):
        """Parses TITLE / BODY format from LLM response"""
        mock_llm.return_value = "TITLE: My Post\nBODY: This is the body text."
        topic = NewsTopic(title="News", summary="Summary", link="L", source="S")

        result = generate_reddit_post(
            strategy="Post tech news", topic=topic, tone="casual", subreddit="technology"
        )

        assert result["title"] == "My Post"
        assert result["body"] == "This is the body text."
        assert result["topic_hash"] == _hash_topic(topic)
        mock_llm.assert_called_once()
        mock_mod.assert_called_once()

    @patch("ferrox.utils.content_generator._call_llm")
    @patch("ferrox.utils.content_generator.moderation_check", return_value=(True, []))
    def test_fallback_first_line_title(self, mock_mod, mock_llm):
        """When TITLE: / BODY: missing, first line is title, rest is body"""
        mock_llm.return_value = "First line title\nSecond line body\nThird line"
        topic = NewsTopic(title="News", summary="Summary", link="L", source="S")

        result = generate_reddit_post(
            strategy="Post tech news", topic=topic, tone="casual", subreddit="technology"
        )

        assert result["title"] == "First line title"
        assert "Second line body" in result["body"]

    @patch("ferrox.utils.content_generator._call_llm")
    @patch("ferrox.utils.content_generator.moderation_check", return_value=(True, []))
    def test_title_truncated_to_300(self, mock_mod, mock_llm):
        """Title is truncated to 300 characters"""
        mock_llm.return_value = f"TITLE: {'A' * 400}\nBODY: body"
        topic = NewsTopic(title="News", summary="Summary", link="L", source="S")

        result = generate_reddit_post(strategy="S", topic=topic)
        assert len(result["title"]) == 300

    @patch("ferrox.utils.content_generator._call_llm")
    @patch("ferrox.utils.content_generator.moderation_check", return_value=(False, ["SPAM detected"]))
    def test_moderation_failure_raises(self, mock_mod, mock_llm):
        """Moderation violation raises ContentGenerationError"""
        mock_llm.return_value = "TITLE: Bad\nBODY: Spam content"
        topic = NewsTopic(title="News", summary="Summary", link="L", source="S")

        with pytest.raises(ContentGenerationError) as exc_info:
            generate_reddit_post(strategy="S", topic=topic)

        assert "failed moderation" in str(exc_info.value)

    @patch("ferrox.utils.content_generator._call_llm")
    @patch("ferrox.utils.content_generator.moderation_check", return_value=(True, []))
    def test_empty_subreddit(self, mock_mod, mock_llm):
        """Works with empty subreddit string"""
        mock_llm.return_value = "TITLE: T\nBODY: B"
        topic = NewsTopic(title="News", summary="Summary", link="L", source="S")

        result = generate_reddit_post(strategy="S", topic=topic, subreddit="")
        assert result["title"] == "T"


class TestGenerateRedditComment:
    """Test generate_reddit_comment"""

    @patch("ferrox.utils.content_generator._call_llm")
    @patch("ferrox.utils.content_generator.moderation_check", return_value=(True, []))
    def test_returns_comment_text(self, mock_mod, mock_llm):
        """Returns generated comment text"""
        mock_llm.return_value = "Great post! I learned a lot."
        result = generate_reddit_comment(
            strategy="Be helpful", post_title="Python Tips", post_body="Here are some tips..."
        )
        assert result == "Great post! I learned a lot."
        mock_llm.assert_called_once()

    @patch("ferrox.utils.content_generator._call_llm")
    @patch("ferrox.utils.content_generator.moderation_check", return_value=(True, []))
    def test_truncates_long_body(self, mock_mod, mock_llm):
        """Post body is truncated to 500 chars in prompt"""
        long_body = "A" * 1000
        generate_reddit_comment(
            strategy="S", post_title="T", post_body=long_body
        )
        prompt = mock_llm.call_args[0][0]
        assert "A" * 500 in prompt
        assert "A" * 600 not in prompt

    @patch("ferrox.utils.content_generator._call_llm")
    @patch("ferrox.utils.content_generator.moderation_check", return_value=(False, ["VIOLENCE"]))
    def test_moderation_failure(self, mock_mod, mock_llm):
        """Raises on moderation failure"""
        with pytest.raises(ContentGenerationError):
            generate_reddit_comment(strategy="S", post_title="T", post_body="B")


class TestGenerateXTweet:
    """Test generate_x_tweet"""

    @patch("ferrox.utils.content_generator._call_llm")
    @patch("ferrox.utils.content_generator.moderation_check", return_value=(True, []))
    def test_returns_tweet_under_280(self, mock_mod, mock_llm):
        """Returns tweet truncated to 280 chars"""
        mock_llm.return_value = "A" * 500
        topic = NewsTopic(title="News", summary="Summary", link="L", source="S")

        result = generate_x_tweet(strategy="S", topic=topic, tone="witty")
        assert len(result) <= 280
        assert result == "A" * 280

    @patch("ferrox.utils.content_generator._call_llm")
    @patch("ferrox.utils.content_generator.moderation_check", return_value=(True, []))
    def test_prompt_includes_topic(self, mock_mod, mock_llm):
        """Prompt includes topic context"""
        mock_llm.return_value = "Tweet text"
        topic = NewsTopic(title="Breaking News", summary="Something happened", link="L", source="S")

        generate_x_tweet(strategy="Post news", topic=topic)
        prompt = mock_llm.call_args[0][0]
        assert "Breaking News" in prompt
        assert "Something happened" in prompt
        assert "Post news" in prompt

    @patch("ferrox.utils.content_generator._call_llm")
    @patch("ferrox.utils.content_generator.moderation_check", return_value=(False, ["SPAM"]))
    def test_moderation_failure(self, mock_mod, mock_llm):
        """Raises on moderation failure"""
        topic = NewsTopic(title="News", summary="Summary", link="L", source="S")
        with pytest.raises(ContentGenerationError):
            generate_x_tweet(strategy="S", topic=topic)


class TestGenerateXThread:
    """Test generate_x_thread"""

    @patch("ferrox.utils.content_generator._call_llm")
    @patch("ferrox.utils.content_generator.moderation_check", return_value=(True, []))
    def test_returns_list_of_tweets(self, mock_mod, mock_llm):
        """Parses numbered tweets from LLM response"""
        mock_llm.return_value = "1. First tweet here\n2. Second tweet here\n3. Third one"
        topic = NewsTopic(title="News", summary="Summary", link="L", source="S")

        tweets = generate_x_thread(strategy="S", topic=topic, max_tweets=3)

        assert len(tweets) == 3
        assert tweets[0] == "First tweet here"
        assert tweets[1] == "Second tweet here"
        assert tweets[2] == "Third one"

    @patch("ferrox.utils.content_generator._call_llm")
    @patch("ferrox.utils.content_generator.moderation_check", return_value=(True, []))
    def test_respects_max_tweets(self, mock_mod, mock_llm):
        """Truncates to max_tweets"""
        mock_llm.return_value = "1. One\n2. Two\n3. Three\n4. Four"
        topic = NewsTopic(title="News", summary="Summary", link="L", source="S")

        tweets = generate_x_thread(strategy="S", topic=topic, max_tweets=2)
        assert len(tweets) == 2

    @patch("ferrox.utils.content_generator._call_llm")
    @patch("ferrox.utils.content_generator.moderation_check", return_value=(True, []))
    def test_empty_response_raises(self, mock_mod, mock_llm):
        """Empty parsed tweets raises ContentGenerationError"""
        mock_llm.return_value = ""
        topic = NewsTopic(title="News", summary="Summary", link="L", source="S")

        with pytest.raises(ContentGenerationError):
            generate_x_thread(strategy="S", topic=topic)

    @patch("ferrox.utils.content_generator._call_llm")
    @patch("ferrox.utils.content_generator.moderation_check", return_value=(True, []))
    def test_tweet_prefix_stripping(self, mock_mod, mock_llm):
        """Handles 'Tweet 1:' prefix style"""
        mock_llm.return_value = "Tweet 1: Hello\nTweet 2: World"
        topic = NewsTopic(title="News", summary="Summary", link="L", source="S")

        tweets = generate_x_thread(strategy="S", topic=topic)
        assert tweets[0] == "Hello"
        assert tweets[1] == "World"

    @patch("ferrox.utils.content_generator._call_llm")
    @patch("ferrox.utils.content_generator.moderation_check", return_value=(True, []))
    def test_each_tweet_under_280(self, mock_mod, mock_llm):
        """Each tweet is truncated to 280 chars"""
        mock_llm.return_value = "1. " + "A" * 500 + "\n2. Short"
        topic = NewsTopic(title="News", summary="Summary", link="L", source="S")

        tweets = generate_x_thread(strategy="S", topic=topic)
        assert len(tweets[0]) <= 280


class TestContentGenerationError:
    """Test exception type"""

    def test_is_exception(self):
        """ContentGenerationError is an Exception subclass"""
        assert issubclass(ContentGenerationError, Exception)

    def test_message(self):
        """Stores message"""
        exc = ContentGenerationError("something broke")
        assert str(exc) == "something broke"
