"""Tests for the Garmin API rate limiter in garth_client.py.

The refresh state machine lives in token_store.attempt_refresh — those tests
require an async DB and are exercised in integration. Here we cover only the
pure-sync pieces: _needs_refresh and _sync_api_call (rate limiting + retries).
"""

import os
import time
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

from app.core.garth_client import (
    _sync_api_call,
    _needs_refresh,
    GarminRateLimitError,
    GarminInBackoffError,
    MIN_CALL_INTERVAL,
)


class TestNeedsRefresh:
    """Token expiry detection."""

    def test_returns_true_when_no_token(self):
        import garth
        original = getattr(garth.client, 'oauth2_token', None)
        garth.client.oauth2_token = None
        assert _needs_refresh() is True
        garth.client.oauth2_token = original

    def test_returns_true_when_expires_at_is_none(self):
        import garth
        original = getattr(garth.client, 'oauth2_token', None)
        mock_token = MagicMock()
        mock_token.expires_at = None
        garth.client.oauth2_token = mock_token
        assert _needs_refresh() is True
        garth.client.oauth2_token = original

    def test_returns_false_when_token_fresh(self):
        import garth
        original = getattr(garth.client, 'oauth2_token', None)
        mock_token = MagicMock()
        # Fresh for the next hour (well past the 10-min refresh buffer)
        mock_token.expires_at = time.time() + 3600
        garth.client.oauth2_token = mock_token
        assert _needs_refresh() is False
        garth.client.oauth2_token = original


class TestInBackoffError:
    """The exception that signals callers to surface a 503 Retry-After."""

    def test_retry_after_seconds_is_set(self):
        e = GarminInBackoffError(retry_after_seconds=600)
        assert e.retry_after_seconds == 600

    def test_clamps_to_min_one(self):
        e = GarminInBackoffError(retry_after_seconds=0)
        assert e.retry_after_seconds >= 1


class TestSyncApiCall:
    """Rate-limited API call logic. Auth is assumed to already be ready."""

    def setup_method(self):
        import app.core.garth_client as gc
        gc._last_call_time = 0.0
        gc._client_ready = True

    @patch("app.core.garth_client.garth")
    def test_happy_path(self, mock_garth):
        mock_garth.connectapi.return_value = [{"activityId": 123}]
        result = _sync_api_call("/test-endpoint", params={"limit": 1})
        assert result == [{"activityId": 123}]
        mock_garth.connectapi.assert_called_once_with("/test-endpoint", params={"limit": 1})

    @patch("app.core.garth_client.garth")
    def test_rate_limit_enforces_interval(self, mock_garth):
        import app.core.garth_client as gc
        gc._last_call_time = time.time()
        mock_garth.connectapi.return_value = "ok"

        start = time.time()
        _sync_api_call("/test")
        elapsed = time.time() - start
        assert elapsed >= MIN_CALL_INTERVAL * 0.9

    @patch("app.core.garth_client.garth")
    @patch("app.core.garth_client.time.sleep")
    def test_429_retries(self, mock_sleep, mock_garth):
        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise Exception("429 Too Many Requests")
            return "success"
        mock_garth.connectapi.side_effect = side_effect
        result = _sync_api_call("/test")
        assert result == "success"
        assert call_count == 2

    @patch("app.core.garth_client.garth")
    @patch("app.core.garth_client.time.sleep")
    def test_three_429s_raises(self, mock_sleep, mock_garth):
        mock_garth.connectapi.side_effect = Exception("429 Too Many Requests")
        with pytest.raises(GarminRateLimitError, match="after 3 attempts"):
            _sync_api_call("/test")

    @patch("app.core.garth_client.garth")
    @patch("app.core.garth_client.time.sleep")
    def test_connection_error_retries(self, mock_sleep, mock_garth):
        import requests.exceptions
        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise requests.exceptions.ConnectionError("DNS failure")
            return "recovered"
        mock_garth.connectapi.side_effect = side_effect
        result = _sync_api_call("/test")
        assert result == "recovered"

    @patch("app.core.garth_client.garth")
    def test_non_retryable_error_raises_immediately(self, mock_garth):
        mock_garth.connectapi.side_effect = ValueError("unexpected")
        with pytest.raises(ValueError, match="unexpected"):
            _sync_api_call("/test")
