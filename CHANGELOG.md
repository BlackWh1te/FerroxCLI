# Changelog

All notable changes to this project will be documented in this file.

## [1.2.5] - 2026-05-05

### Added
- **Phase 1: Daemon Intelligence** — Wired LLM content generation and rate-limited queuing into `reddit_daemon.py` and `social_daemon.py`.
  - `ferrox/utils/content_generator.py`: RSS fetching via `feedparser`, hash-based dedup, and mock LLM generation helpers (`generate_reddit_post`, `generate_reddit_comment`, `generate_x_tweet`, `generate_x_thread`). All outputs pass through `sanitize_content` and `moderation_check`.
  - `ferrox/utils/post_queue.py`: `PostQueue` class with `enqueue()` (dedup by content hash + topic hash), `dequeue()` (rate-limit gate), `mark_posted()`, `mark_failed()`, and rolling per-hour/per-day counters.
  - Reddit daemon: `_fetch_and_enqueue()` fetches news, generates post, enqueues; `_publish_from_queue()` dequeues and calls `post_submission_tool` (or logs in draft mode); `generate_and_post()` orchestrator fills queue then publishes.
  - X daemon: same pattern with `_fetch_and_enqueue()` for tweets and `_publish_from_queue()` calling `post_tweet_tool`.
- **Test coverage for `content_generator.py`** (29 tests): `NewsTopic` dataclass, `_hash_topic`, `fetch_news_topics` RSS parsing, empty sources, description fallback, injection skipping, parse failures, max_items, `generate_reddit_post` title/body parsing and truncation, moderation failure, `generate_reddit_comment`, `generate_x_tweet` length and prompt validation, `generate_x_thread` numbered parsing and truncation.
- **Test coverage for `post_queue.py`** (15 tests): enqueue/dequeue, duplicate rejection by content hash and topic hash, rate-limit blocking, `mark_posted`/`mark_failed` state updates, `posted_today`/`failed_today` 24h windows, `consecutive_failures` counting, mixed platforms.
- **Test coverage for `reddit_daemon.py` intelligence layer** (13 tests): `_fetch_and_enqueue`, `_publish_from_queue` draft/live/error paths, `generate_and_post` orchestrator with/without existing queue items, `_record_success`/`_record_failure`, daemon initialization with `PostQueue` and account-type rate limits.
- **Test coverage for `social_daemon.py` intelligence layer** (13 tests): `_fetch_and_enqueue`, `_publish_from_queue` draft/live/error paths, `generate_and_post` orchestrator, `_record_success`/`_record_failure`, daemon initialization with `PostQueue` and account-type rate limits.

### Fixed
- `fetch_news_topics` now returns early for empty source lists without importing `feedparser`.
- `PostQueue` now tracks `_queued_hashes` to reject duplicate posts that are already in-flight (not just already-posted).

## [1.2.4] - 2026-05-05

### Fixed
- `monitoring.py` now reads the release version dynamically from `ferrox.__version__` instead of a hardcoded `"1.0.0"`.

### Added
- **Test coverage for `monitoring.py`** (12 tests): Sentry initialization with/without DSN, environment fallback, version override, init failure handling, and all wrapper functions (`capture_exception`, `capture_message`, `add_breadcrumb`, `set_user_context`, `set_tag`).
- **Test coverage for `reddit_browser_login.py`** (13 tests): Path helpers, `_is_reddit_logged_in` URL state detection, `has_saved_reddit_session` with valid/empty/missing cookie files, `clear_reddit_session` file deletion, and `reddit_login_via_browser` BrowserLoginConfig creation.
- **Test coverage for `x_browser_login.py`** (12 tests): Path helpers, `_is_x_logged_in` URL state detection, `has_saved_x_session`, `clear_x_session`, and `x_login_via_browser` BrowserLoginConfig creation.
- **Test coverage for `utils/browser_login.py`** (10 tests): `save_cookies_playwright_format` JSON serialization and parent-dir creation, `convert_to_httpx_cookiejar` name/value extraction and empty-name skipping, `load_browser_cookies` dict/list format parsing and invalid JSON fallback.
- **Test coverage for `ui/tool_logger.py`** (9 tests): All tool execution logging paths (`read_file`, `search_text`, `edit_file` accepted/rejected, `run_command` success/failure, unknown tools with/without summary).
- **Test coverage for `ui/trace_viewer.py`** (11 tests): `show_help_panel` header and keyboard shortcuts, `show_trace_viewer` empty logs, thought/tool_call/tool_result rendering, summary stats, long content handling, timestamp string fallback, and input waiting.

## [1.2.3] - 2026-05-05

### Fixed
- Eliminated `RuntimeWarning: coroutine was never awaited` in `orchestrator.py` by replacing `asyncio.create_task(event_bus.publish(...))` calls with a new synchronous `event_bus.publish_sync()` wrapper.
- Removed unused `asyncio` import from `orchestrator.py`.

### Added
- Added `AgentEventBus.publish_sync()` method for safe fire-and-forget event publishing from synchronous code without leaking unawaited coroutines.
- Auto-creates agent registry entries for first-seen agents (any event type), ensuring `get_active_agents()` always returns current participants.
- Comprehensive test suite for `event_bus.py` covering sync/async publish, subscribe/unsubscribe, event processing, subscriber exception handling, registry queries, history export, and max-history truncation (26 new tests).

## [1.2.2] - 2026-05-05

### Fixed
- Resolved 554 ruff lint issues, 86 bandit warnings, and 4 runtime bugs across the codebase.
- Added `usedforsecurity=False` to Reddit tool MD5 hash to satisfy security linters.
- Fixed tracer context manager bug and improved social tool prompt mapping.
- Fixed user-friendly X API error messages for twikit compatibility issues.
- Fixed twikit cookie format and session validation robustness.
- Fixed Windows console UTF-8 encoding for emojis.
- Fixed agent response formatting and X bot guidance.
- Resolved all bare except clauses and hardcoded model reference.
- Resolved security audit issues and broken tests across codebase.

### Added
- Integrated Reddit Bot into FerroxCLI with comprehensive anti-ban protections.
- Added unit tests for untested modules and cleaned test-suite lint.
- Added SOCIAL mode, account validation, THINK spam removal, and model label fix.
- Added full anti-bot stealth for `/x-login` browser authentication.
- Added `/x-login` browser-based X authentication (password-free).

### Changed
- Extracted shared browser-login utilities into `ferrox/utils/browser_login.py`.
- Replaced Playwright browser login with real-browser local server.
- Switched autocomplete to MULTI_COLUMN dropdown style.

### Documentation
- Documented Ferrox X skillset advantages over Bika.ai / SaaS platforms.
