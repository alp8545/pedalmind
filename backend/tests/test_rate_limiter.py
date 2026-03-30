"""Tests for the Garmin API rate limiter in garth_client.py."""

import os
import time
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.core.garth_client import (
    _sync_api_call,
    _ensure_auth,
    _needs_refresh,
    GarminRateLimitError,
    MIN_CALL_INTERVAL,
)


class TestNeedsRefresh:
    """Test token expiry detection."""

    def test_returns_true_when_no_token(self):
        import garth
        original = getattr(garth.client, 'oauth2_token', None)
        garth.client.oauth2_token = None
        assert _needs_refresh() is True
        garth.client.oauth2_token = original

    def test_returns_true_when_expires_at_is_none(self):
        """BUG-3 fix: handles None expires_at without crashing."""
        import garth
        original = getattr(garth.client, 'oauth2_token', None)
        mock_token = MagicMock()
        mock_token.expires_at = None
        garth.client.oauth2_token = mock_token
        assert _needs_refresh() is True  # Should not raise TypeError
        garth.client.oauth2_token = original


class TestSyncApiCall:
    """Test the rate-limited API call logic."""

    def setup_method(self):
        import app.core.garth_client as gc
        gc._last_call_time = 0.0
        gc._client_ready = True  # skip auth for unit tests

    @patch("app.core.garth_client._ensure_auth")
    @patch("app.core.garth_client.garth")
    def test_happy_path(self, mock_garth, mock_auth):
        mock_garth.connectapi.return_value = [{"activityId": 123}]
        result = _sync_api_call("/test-endpoint", params={"limit": 1})
        assert result == [{"activityId": 123}]
        mock_garth.connectapi.assert_called_once_with("/test-endpoint", params={"limit": 1})

    @patch("app.core.garth_client._ensure_auth")
    @patch("app.core.garth_client.garth")
    def test_rate_limit_enforces_interval(self, mock_garth, mock_auth):
        import app.core.garth_client as gc
        gc._last_call_time = time.time()  # pretend we just called
        mock_garth.connectapi.return_value = "ok"

        start = time.time()
        _sync_api_call("/test")
        elapsed = time.time() - start
        assert elapsed >= MIN_CALL_INTERVAL * 0.9

    @patch("app.core.garth_client._ensure_auth")
    @patch("app.core.garth_client.garth")
    @patch("app.core.garth_client.time.sleep")
    def test_429_retries(self, mock_sleep, mock_garth, mock_auth):
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

    @patch("app.core.garth_client._ensure_auth")
    @patch("app.core.garth_client.garth")
    @patch("app.core.garth_client.time.sleep")
    def test_three_429s_raises(self, mock_sleep, mock_garth, mock_auth):
        mock_garth.connectapi.side_effect = Exception("429 Too Many Requests")
        with pytest.raises(GarminRateLimitError, match="after 3 attempts"):
            _sync_api_call("/test")

    @patch("app.core.garth_client._ensure_auth")
    @patch("app.core.garth_client.garth")
    @patch("app.core.garth_client.time.sleep")
    def test_connection_error_retries(self, mock_sleep, mock_garth, mock_auth):
        """BUG-6 fix: ConnectionError should retry, not crash."""
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

    @patch("app.core.garth_client._ensure_auth")
    @patch("app.core.garth_client.garth")
    def test_non_retryable_error_raises_immediately(self, mock_garth, mock_auth):
        mock_garth.connectapi.side_effect = ValueError("unexpected")
        with pytest.raises(ValueError, match="unexpected"):
            _sync_api_call("/test")
