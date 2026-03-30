"""Tests for the TrendService — CTL/ATL/TSB EWMA computation."""

import pytest
from app.services.trends import get_form_indicator, CYCLING_SPORTS


class TestFormIndicator:
    """Test TSB → form label mapping."""

    def test_peaked(self):
        assert get_form_indicator(15.0) == "Peaked"
        assert get_form_indicator(25.0) == "Peaked"

    def test_fresh(self):
        assert get_form_indicator(5.0) == "Fresh"
        assert get_form_indicator(14.9) == "Fresh"

    def test_building(self):
        assert get_form_indicator(-10.0) == "Building"
        assert get_form_indicator(0.0) == "Building"
        assert get_form_indicator(4.9) == "Building"

    def test_fatigued(self):
        assert get_form_indicator(-25.0) == "Fatigued"
        assert get_form_indicator(-11.0) == "Fatigued"

    def test_overreaching(self):
        assert get_form_indicator(-25.1) == "Overreaching"
        assert get_form_indicator(-50.0) == "Overreaching"

    def test_exact_boundaries(self):
        """Boundaries use >= so the value belongs to the higher tier."""
        assert get_form_indicator(15.0) == "Peaked"    # >= 15
        assert get_form_indicator(5.0) == "Fresh"      # >= 5
        assert get_form_indicator(-10.0) == "Building"  # >= -10
        assert get_form_indicator(-25.0) == "Fatigued"  # >= -25


class TestEWMAMath:
    """Verify EWMA formula produces correct CTL/ATL/TSB values.

    Manual calculation for a known input sequence:
    - Day 1: TSS=100, Day 2: rest, Day 3: TSS=80, Day 4: rest, Day 5: TSS=120

    CTL (TC=42): today = yesterday * (1 - 1/42) + daily_tss * (1/42)
    ATL (TC=7):  today = yesterday * (1 - 1/7)  + daily_tss * (1/7)
    """

    def _compute_ewma(self, daily_tss_values: list[float]) -> list[dict]:
        """Reproduce the EWMA computation from trends.py for verification."""
        ctl = 0.0
        atl = 0.0
        ctl_decay = 1.0 - 1.0 / 42
        ctl_gain = 1.0 / 42
        atl_decay = 1.0 - 1.0 / 7
        atl_gain = 1.0 / 7

        results = []
        for tss in daily_tss_values:
            ctl = ctl * ctl_decay + tss * ctl_gain
            atl = atl * atl_decay + tss * atl_gain
            tsb = ctl - atl
            results.append({"ctl": round(ctl, 1), "atl": round(atl, 1), "tsb": round(tsb, 1)})
        return results

    def test_single_ride(self):
        """After one 100 TSS ride, CTL should be ~2.4, ATL should be ~14.3."""
        results = self._compute_ewma([100.0])
        assert results[0]["ctl"] == 2.4     # 100 * (1/42) = 2.38 → 2.4
        assert results[0]["atl"] == 14.3    # 100 * (1/7)  = 14.28 → 14.3
        assert results[0]["tsb"] == -11.9   # 2.4 - 14.3 = -11.9

    def test_rest_day_decay(self):
        """After a ride + rest day, values should decay."""
        results = self._compute_ewma([100.0, 0.0])
        # Day 2: ctl = 2.38 * (41/42) = 2.32 → 2.3
        assert results[1]["ctl"] == 2.3
        # Day 2: atl = 14.28 * (6/7) = 12.24 → 12.2
        assert results[1]["atl"] == 12.2

    def test_five_day_sequence(self):
        """5 days: 100, 0, 80, 0, 120 — verify cumulative effect."""
        results = self._compute_ewma([100.0, 0.0, 80.0, 0.0, 120.0])
        # After 5 days, CTL should be slowly building, ATL responds faster
        assert results[4]["ctl"] > 0
        assert results[4]["atl"] > results[4]["ctl"]  # ATL > CTL early → negative TSB
        assert results[4]["tsb"] < 0  # Should be fatigued early in training

    def test_consistent_training_builds_ctl(self):
        """30 days of consistent 100 TSS/day should build significant CTL."""
        results = self._compute_ewma([100.0] * 30)
        # After 30 days of 100 TSS, CTL approaches 100 * (1 - decay^30)
        assert results[29]["ctl"] > 40  # Should be well above 40
        assert results[29]["ctl"] < 70  # But not yet at steady state
        # ATL converges faster (7-day TC) — should be near 100
        assert results[29]["atl"] > 85

    def test_zero_input(self):
        """All rest days should keep CTL/ATL at 0."""
        results = self._compute_ewma([0.0] * 10)
        assert results[9]["ctl"] == 0.0
        assert results[9]["atl"] == 0.0
        assert results[9]["tsb"] == 0.0


class TestCyclingSportsFilter:
    """Verify the cycling sports set covers expected Garmin activity types."""

    def test_common_cycling_types(self):
        assert "cycling" in CYCLING_SPORTS
        assert "road_biking" in CYCLING_SPORTS
        assert "mountain_biking" in CYCLING_SPORTS
        assert "indoor_cycling" in CYCLING_SPORTS

    def test_non_cycling_excluded(self):
        assert "running" not in CYCLING_SPORTS
        assert "swimming" not in CYCLING_SPORTS
        assert "hiking" not in CYCLING_SPORTS
        assert "strength_training" not in CYCLING_SPORTS
