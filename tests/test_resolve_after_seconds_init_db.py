"""Tests that init_db validates resolve_after_seconds at config load time.

Issue #5 (continued): The validation must also run during DB migration
when scheduled_prediction_configs are loaded, not just at predict worker
startup.
"""

from __future__ import annotations

import pytest


class TestInitDbConfigValidation:
    """load_scheduled_prediction_configs should validate timing constraints."""

    def test_validate_scheduled_configs_rejects_zero_resolve(self, monkeypatch):
        """A config with resolve_after_seconds=0 must be rejected at load time."""
        from coordinator_node.db import init_db

        bad_configs = [
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
            init_db.validate_scheduled_configs(bad_configs)

    def test_validate_scheduled_configs_accepts_valid(self):
        """A config with positive resolve_after_seconds should pass."""
        from coordinator_node.db import init_db

        good_configs = [
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
        init_db.validate_scheduled_configs(good_configs)
