# Changelog

All notable changes to this project will be documented in this file.

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
