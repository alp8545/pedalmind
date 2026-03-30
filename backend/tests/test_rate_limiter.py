"""Tests for the Garmin API rate limiter in garth_client.py."""

import os
import time
import pytest
from unittest.mock import patch, MagicMock

# Set required env vars before importing garth_client (it loads Settings on import)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.core.garth_client import (
    _call_with_retry,
    GarminRateLimitError,
    MIN_CALL_INTERVAL,
)


def _make_429_error():
    """Create an exception that _is_rate_limit() recognizes as a 429."""
    # _is_rate_limit checks: isinstance(exc, GarthHTTPError) + exc.error.response.status_code == 429
    # Also falls back to '429' in str(exc). Use the string fallback for simpler mocking.
    return Exception("429 Too Many Requests")


class TestCallWithRetry:
    """Test the rate-limited retry logic."""

    def setup_method(self):
        """Reset the global last call time before each test."""
        import app.core.garth_client as gc
        gc._last_call_time = 0.0

    def test_happy_path_succeeds(self):
        """First attempt succeeds, no retry needed."""
        mock_fn = MagicMock(return_value={"data": "ok"})
        result = _call_with_retry(mock_fn, "arg1")
        assert result == {"data": "ok"}
        assert mock_fn.call_count == 1

    def test_rate_limit_enforces_interval(self):
        """Calls should be spaced at least MIN_CALL_INTERVAL apart."""
        import app.core.garth_client as gc
        gc._last_call_time = time.time()  # Pretend we just called

        mock_fn = MagicMock(return_value="ok")
        start = time.time()
        _call_with_retry(mock_fn)
        elapsed = time.time() - start
        assert elapsed >= MIN_CALL_INTERVAL * 0.9  # Allow 10% tolerance

    def test_429_retries_with_backoff(self):
        """On 429, retries up to 3 times with increasing wait."""
        call_count = 0
        def failing_then_ok(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise _make_429_error()
            return "success"

        with patch("app.core.garth_client.time.sleep"):
            result = _call_with_retry(failing_then_ok)
        assert result == "success"
        assert call_count == 2

    def test_three_429s_raises(self):
        """After 3 consecutive 429s, raises GarminRateLimitError."""
        def always_429(*args, **kwargs):
            raise _make_429_error()

        with patch("app.core.garth_client.time.sleep"):
            with pytest.raises(GarminRateLimitError, match="after 3 attempts"):
                _call_with_retry(always_429)

    def test_timeout_retries(self):
        """On timeout, retries with backoff."""
        import requests.exceptions

        call_count = 0
        def timeout_then_ok(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise requests.exceptions.Timeout("timed out")
            return "recovered"

        with patch("app.core.garth_client.time.sleep"):
            result = _call_with_retry(timeout_then_ok)
        assert result == "recovered"
        assert call_count == 2

    def test_non_429_error_raises_immediately(self):
        """Non-rate-limit errors should not be retried."""
        def server_error(*args, **kwargs):
            raise ValueError("unexpected")

        with pytest.raises(ValueError, match="unexpected"):
            _call_with_retry(server_error)
