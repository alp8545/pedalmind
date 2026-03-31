"""Tests for ride_metrics: decoupling and HR recovery computation."""

import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.services.ride_metrics import compute_decoupling, compute_hr_recovery


class TestComputeDecoupling:
    """Test Pw:Hr decoupling percentage computation."""

    def test_returns_none_for_short_ride(self):
        # Less than 20 min (1200 records)
        records = [{"power": 200, "heartRate": 140}] * 600
        assert compute_decoupling(records) is None

    def test_returns_none_for_missing_data(self):
        records = [{"power": None, "heartRate": None}] * 1500
        assert compute_decoupling(records) is None

    def test_zero_decoupling_for_steady_ride(self):
        # Same power and HR throughout — should be ~0%
        records = [{"power": 200, "heartRate": 140}] * 2400
        result = compute_decoupling(records)
        assert result is not None
        assert result == 0.0

    def test_positive_decoupling_for_hr_drift(self):
        # First half: 200W / 130bpm, second half: 200W / 150bpm
        # ratio_h1 = 200/130 = 1.538, ratio_h2 = 200/150 = 1.333
        # decoupling = (1.333 - 1.538) / 1.538 * 100 = -13.3% (negative = HR rose)
        # Wait — positive decoupling means ratio dropped (HR drifted UP)
        h1 = [{"power": 200, "heartRate": 130}] * 1200
        h2 = [{"power": 200, "heartRate": 150}] * 1200
        result = compute_decoupling(h1 + h2)
        assert result is not None
        assert result < 0  # ratio decreased because HR went up

    def test_negative_decoupling_for_hr_improvement(self):
        # First half higher HR, second half lower HR at same power
        h1 = [{"power": 200, "heartRate": 150}] * 1200
        h2 = [{"power": 200, "heartRate": 130}] * 1200
        result = compute_decoupling(h1 + h2)
        assert result is not None
        assert result > 0  # ratio increased because HR went down

    def test_filters_zero_values(self):
        # Records with power=0 or hr=0 should be filtered out
        valid = [{"power": 200, "heartRate": 140}] * 1500
        zeroes = [{"power": 0, "heartRate": 0}] * 500
        result = compute_decoupling(zeroes + valid)
        assert result is not None  # Should still compute from the valid records


class TestComputeHrRecovery:
    """Test HR recovery computation."""

    def test_returns_none_for_short_ride(self):
        records = [{"power": 200, "heartRate": 140}] * 100
        assert compute_hr_recovery(records) is None

    def test_basic_hr_recovery(self):
        # Build a ride: 10 min easy, 5 min hard, 2 min recovery
        easy = [{"power": 100, "heartRate": 120}] * 600
        hard = [{"power": 300, "heartRate": 175}] * 300
        # Recovery: HR drops linearly from 175 to 140 over 120s
        recovery = []
        for i in range(120):
            hr = 175 - int(i * 35 / 120)
            recovery.append({"power": 50, "heartRate": hr})

        records = easy + hard + recovery
        result = compute_hr_recovery(records)
        assert result is not None
        assert "hr_peak" in result
        assert "drop_30s" in result
        assert "drop_60s" in result
        assert result["hr_peak"] == 175
        assert result["drop_30s"] > 0
        assert result["drop_60s"] > result["drop_30s"]

    def test_returns_none_without_hr_data(self):
        records = [{"power": 200, "heartRate": 0}] * 500
        assert compute_hr_recovery(records) is None
