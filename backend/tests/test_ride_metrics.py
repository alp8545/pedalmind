"""Tests for ride_metrics: decoupling and HR recovery computation."""

import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.services.ride_metrics import compute_decoupling, compute_hr_recovery


class TestComputeDecoupling:
    """Test Pw:Hr decoupling percentage computation."""

    def test_returns_none_for_too_few_records(self):
        # Less than MIN_VALID_RECORDS (20)
        records = [{"power": 200, "heartRate": 140}] * 10
        assert compute_decoupling(records) is None

    def test_returns_none_for_missing_data(self):
        records = [{"power": None, "heartRate": None}] * 50
        assert compute_decoupling(records) is None

    def test_zero_decoupling_for_steady_ride(self):
        # Same power and HR throughout — should be 0%
        records = [{"power": 200, "heartRate": 140}] * 50
        result = compute_decoupling(records)
        assert result is not None
        assert result == 0.0

    def test_negative_decoupling_for_hr_drift(self):
        # First half: 200W/130bpm, second half: 200W/150bpm
        # ratio drops because HR rose → negative decoupling
        h1 = [{"power": 200, "heartRate": 130}] * 30
        h2 = [{"power": 200, "heartRate": 150}] * 30
        result = compute_decoupling(h1 + h2)
        assert result is not None
        assert result < 0  # ratio decreased = HR drifted up

    def test_positive_decoupling_for_hr_improvement(self):
        # First half higher HR, second half lower HR at same power
        h1 = [{"power": 200, "heartRate": 150}] * 30
        h2 = [{"power": 200, "heartRate": 130}] * 30
        result = compute_decoupling(h1 + h2)
        assert result is not None
        assert result > 0

    def test_filters_zero_values(self):
        valid = [{"power": 200, "heartRate": 140}] * 30
        zeroes = [{"power": 0, "heartRate": 0}] * 20
        result = compute_decoupling(zeroes + valid)
        assert result is not None

    def test_realistic_garmin_data(self):
        """Simulate Garmin's ~30s sampling: 100 records for a ~50min ride."""
        h1 = [{"power": 195, "heartRate": 142}] * 50
        h2 = [{"power": 192, "heartRate": 148}] * 50
        result = compute_decoupling(h1 + h2)
        assert result is not None
        assert result < 0  # HR drifted up slightly


class TestComputeHrRecovery:
    """Test HR recovery computation."""

    def test_returns_none_for_too_few_records(self):
        records = [{"power": 200, "heartRate": 140}] * 5
        assert compute_hr_recovery(records) is None

    def test_basic_hr_recovery(self):
        # Easy section, then hard section, then recovery
        easy = [{"power": 100, "heartRate": 120}] * 20
        hard = [{"power": 300, "heartRate": 175}] * 15
        recovery = [
            {"power": 50, "heartRate": 160},  # ~30s after effort
            {"power": 50, "heartRate": 145},  # ~60s after effort
            {"power": 50, "heartRate": 135},
        ]
        records = easy + hard + recovery
        result = compute_hr_recovery(records)
        assert result is not None
        assert "hr_peak" in result
        assert result["hr_peak"] >= 170

    def test_returns_none_without_hr_data(self):
        records = [{"power": 200, "heartRate": 0}] * 30
        assert compute_hr_recovery(records) is None

    def test_returns_none_without_power_data(self):
        records = [{"power": 0, "heartRate": 140}] * 30
        assert compute_hr_recovery(records) is None
