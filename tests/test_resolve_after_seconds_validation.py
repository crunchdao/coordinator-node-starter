"""Tests for startup validation of resolve_after_seconds constraint.

Issue #5: If resolve_after_seconds < feed poll interval, predictions will
never accumulate enough data to resolve ground truth. The system should
fail fast at startup instead of silently scoring 0.
"""

from __future__ import annotations

import pytest


class TestResolveAfterSecondsValidation:
    """resolve_after_seconds must be >= feed poll interval at startup."""

    def test_rejects_resolve_after_seconds_below_feed_interval(self):
        """If resolve_after_seconds < feed_poll_seconds, startup must raise."""
        from coordinator_node.services.realtime_predict import RealtimePredictService

        configs = [
            {
                "scope_key": "test",
                "scope_template": {"subject": "BTC"},
                "schedule": {
                    "prediction_interval_seconds": 15,
                    "resolve_after_seconds": 5,
                },
                "active": True,
            }
        ]

        with pytest.raises(ValueError, match="resolve_after_seconds"):
            RealtimePredictService.validate_prediction_configs(
                configs, feed_poll_seconds=10.0
            )

    def test_accepts_resolve_after_seconds_equal_to_feed_interval(self):
        """Exact match is OK."""
        from coordinator_node.services.realtime_predict import RealtimePredictService

        configs = [
            {
                "scope_key": "test",
                "scope_template": {"subject": "BTC"},
                "schedule": {
                    "prediction_interval_seconds": 15,
                    "resolve_after_seconds": 10,
                },
                "active": True,
            }
        ]

        # Should not raise
        RealtimePredictService.validate_prediction_configs(
            configs, feed_poll_seconds=10.0
        )

    def test_accepts_resolve_after_seconds_above_feed_interval(self):
        """Larger resolve window is fine."""
        from coordinator_node.services.realtime_predict import RealtimePredictService

        configs = [
            {
                "scope_key": "test",
                "scope_template": {"subject": "BTC"},
                "schedule": {
                    "prediction_interval_seconds": 15,
                    "resolve_after_seconds": 60,
                },
                "active": True,
            }
        ]

        # Should not raise
        RealtimePredictService.validate_prediction_configs(
            configs, feed_poll_seconds=10.0
        )

    def test_rejects_zero_resolve_after_seconds(self):
        """resolve_after_seconds=0 means no ground truth data window -> must reject."""
        from coordinator_node.services.realtime_predict import RealtimePredictService

        configs = [
            {
                "scope_key": "test",
                "scope_template": {"subject": "BTC"},
                "schedule": {
                    "prediction_interval_seconds": 15,
                    "resolve_after_seconds": 0,
                },
                "active": True,
            }
        ]

        with pytest.raises(ValueError, match="resolve_after_seconds"):
            RealtimePredictService.validate_prediction_configs(
                configs, feed_poll_seconds=5.0
            )

    def test_skips_inactive_configs(self):
        """Inactive configs should not be validated."""
        from coordinator_node.services.realtime_predict import RealtimePredictService

        configs = [
            {
                "scope_key": "test",
                "scope_template": {"subject": "BTC"},
                "schedule": {
                    "prediction_interval_seconds": 15,
                    "resolve_after_seconds": 1,  # too low, but inactive
                },
                "active": False,
            }
        ]

        # Should not raise because config is inactive
        RealtimePredictService.validate_prediction_configs(
            configs, feed_poll_seconds=10.0
        )
