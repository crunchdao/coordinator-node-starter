"""Tests that multi-asset support is documented with an example config.

Issue #7: No multi-asset example despite multi-asset being natively supported.
"""

from __future__ import annotations

import json
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "base" / "node" / "config"


class TestMultiAssetExample:
    """Scaffold should include or document a multi-asset configuration example."""

    def test_multi_asset_example_config_exists(self):
        """There should be an example multi-asset config file."""
        example_path = (
            EXAMPLES_DIR / "scheduled_prediction_configs.multi_asset.example.json"
        )
        assert example_path.exists(), (
            f"Missing {example_path} — add a multi-asset example config "
            f"so users know this is natively supported"
        )

    def test_multi_asset_example_has_multiple_subjects(self):
        """The multi-asset example should have configs for different subjects."""
        example_path = (
            EXAMPLES_DIR / "scheduled_prediction_configs.multi_asset.example.json"
        )
        if not example_path.exists():
            import pytest

            pytest.skip("Example file not created yet")

        configs = json.loads(example_path.read_text())
        assert isinstance(configs, list)
        assert len(configs) >= 2, "Multi-asset example should have at least 2 subjects"

        subjects = {c.get("scope_template", {}).get("subject") for c in configs}
        subjects.discard(None)
        assert len(subjects) >= 2, (
            f"Multi-asset example should have different subjects, got: {subjects}"
        )

    def test_multi_asset_example_validates(self):
        """Each entry in the multi-asset example should be a valid config."""
        example_path = (
            EXAMPLES_DIR / "scheduled_prediction_configs.multi_asset.example.json"
        )
        if not example_path.exists():
            import pytest

            pytest.skip("Example file not created yet")

        from coordinator_node.schemas import ScheduledPredictionConfigEnvelope

        configs = json.loads(example_path.read_text())
        for i, entry in enumerate(configs):
            try:
                ScheduledPredictionConfigEnvelope.model_validate(entry)
            except Exception as exc:
                import pytest

                pytest.fail(f"Multi-asset example entry [{i}] failed validation: {exc}")
