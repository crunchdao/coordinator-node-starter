import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from coordinator_core.cli.main import main


@contextmanager
def _cwd(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class TestCoordinatorCliInit(unittest.TestCase):
    @staticmethod
    def _write_spec(path: Path, payload: dict) -> Path:
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_init_creates_expected_workspace_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                base = Path("crunch-implementations") / "btc-trader"
                node = base / "crunch-node-btc-trader"
                challenge = base / "crunch-btc-trader"
                package = challenge / "crunch_btc_trader"

                self.assertTrue((base / "README.md").exists())
                self.assertTrue((node / "README.md").exists())
                self.assertTrue((node / "pyproject.toml").exists())
                self.assertTrue((node / "Makefile").exists())
                self.assertTrue((node / ".local.env").exists())
                self.assertTrue((node / ".local.env.example").exists())
                self.assertTrue((node / "config" / "callables.env").exists())
                self.assertTrue((node / "config" / "scheduled_prediction_configs.json").exists())
                self.assertTrue((node / "deployment" / "README.md").exists())
                self.assertTrue((node / "deployment" / "docker-compose-local.override.yml").exists())
                self.assertTrue((node / "plugins" / "README.md").exists())
                self.assertTrue((node / "extensions" / "README.md").exists())

                makefile = (node / "Makefile").read_text(encoding="utf-8")
                self.assertIn("-f $(ROOT_DIR)/docker-compose.yml", makefile)
                self.assertIn("deployment/docker-compose-local.override.yml", makefile)

                self.assertTrue((challenge / "README.md").exists())
                self.assertTrue((challenge / "pyproject.toml").exists())
                self.assertTrue((package / "__init__.py").exists())
                self.assertTrue((package / "tracker.py").exists())
                self.assertTrue((package / "inference.py").exists())
                self.assertTrue((package / "validation.py").exists())
                self.assertTrue((package / "scoring.py").exists())
                self.assertTrue((package / "reporting.py").exists())
                self.assertTrue((package / "schemas" / "README.md").exists())
                self.assertTrue((package / "plugins" / "README.md").exists())
                self.assertTrue((package / "extensions" / "README.md").exists())

                self.assertFalse((node / "private_plugins").exists())
                self.assertFalse((package / "private_plugins").exists())

    def test_init_fails_when_target_exists_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                first = main(["init", "btc-trader"])
                second = main(["init", "btc-trader"])
                forced = main(["init", "btc-trader", "--force"])

                self.assertEqual(first, 0)
                self.assertEqual(second, 1)
                self.assertEqual(forced, 0)

    def test_init_supports_name_from_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                spec_path = self._write_spec(
                    Path("spec.json"),
                    {
                        "spec_version": "1",
                        "name": "eth-trader",
                        "crunch_id": "challenge-eth",
                        "model_base_classname": "crunch_eth_trader.tracker.CustomTrackerBase",
                    },
                )

                code = main(["init", "--spec", str(spec_path)])
                self.assertEqual(code, 0)

                node_env = Path(
                    "crunch-implementations/eth-trader/crunch-node-eth-trader/.local.env.example"
                ).read_text(encoding="utf-8")
                self.assertIn("CRUNCH_ID=challenge-eth", node_env)
                self.assertIn(
                    "MODEL_BASE_CLASSNAME=crunch_eth_trader.tracker.CustomTrackerBase",
                    node_env,
                )

    def test_init_spec_overrides_callables_and_schedule(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                spec_path = self._write_spec(
                    Path("btc-spec.json"),
                    {
                        "spec_version": "1",
                        "name": "btc-trader",
                        "callables": {
                            "SCORING_FUNCTION": "crunch_btc_trader.scoring:score_v2",
                            "REPORT_SCHEMA_PROVIDER": "crunch_btc_trader.reporting:report_schema_v2",
                        },
                        "scheduled_prediction_configs": [
                            {
                                "scope_key": "btc-5m",
                                "scope_template": {
                                    "asset": "BTC",
                                    "horizon_seconds": 300,
                                    "step_seconds": 60,
                                },
                                "schedule": {"every_seconds": 300},
                                "active": True,
                                "order": 0,
                            }
                        ],
                    },
                )

                code = main(["init", "btc-trader", "--spec", str(spec_path)])
                self.assertEqual(code, 0)

                callables_env = Path(
                    "crunch-implementations/btc-trader/crunch-node-btc-trader/config/callables.env"
                ).read_text(encoding="utf-8")
                runtime_env = Path(
                    "crunch-implementations/btc-trader/crunch-node-btc-trader/.local.env"
                ).read_text(encoding="utf-8")
                override_compose = Path(
                    "crunch-implementations/btc-trader/crunch-node-btc-trader/deployment/docker-compose-local.override.yml"
                ).read_text(encoding="utf-8")
                self.assertIn(
                    "SCORING_FUNCTION=crunch_btc_trader.scoring:score_v2",
                    callables_env,
                )
                self.assertIn(
                    "REPORT_SCHEMA_PROVIDER=crunch_btc_trader.reporting:report_schema_v2",
                    callables_env,
                )
                self.assertIn(
                    "SCORING_FUNCTION=crunch_btc_trader.scoring:score_v2",
                    runtime_env,
                )
                self.assertIn(
                    "REPORT_SCHEMA_PROVIDER=crunch_btc_trader.reporting:report_schema_v2",
                    runtime_env,
                )
                self.assertIn(
                    "./crunch-implementations/btc-trader/crunch-btc-trader:/app/challenge",
                    override_compose,
                )

                schedule_raw = Path(
                    "crunch-implementations/btc-trader/crunch-node-btc-trader/config/scheduled_prediction_configs.json"
                ).read_text(encoding="utf-8")
                schedule = json.loads(schedule_raw)
                self.assertEqual(schedule[0]["scope_key"], "btc-5m")
                self.assertEqual(schedule[0]["schedule"]["every_seconds"], 300)

    def test_init_fails_without_name_and_without_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init"])
                self.assertEqual(code, 1)

    def test_init_rejects_name_mismatch_between_cli_and_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                spec_path = self._write_spec(
                    Path("spec.json"), {"spec_version": "1", "name": "eth-trader"}
                )
                code = main(["init", "btc-trader", "--spec", str(spec_path)])
                self.assertEqual(code, 1)

    def test_init_rejects_spec_without_spec_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                spec_path = self._write_spec(Path("spec.json"), {"name": "btc-trader"})
                code = main(["init", "--spec", str(spec_path)])
                self.assertEqual(code, 1)

    def test_init_rejects_spec_with_unsupported_spec_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                spec_path = self._write_spec(
                    Path("spec.json"), {"spec_version": "2", "name": "btc-trader"}
                )
                code = main(["init", "--spec", str(spec_path)])
                self.assertEqual(code, 1)

    def test_init_rejects_invalid_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "BTC Trader"])
                self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
