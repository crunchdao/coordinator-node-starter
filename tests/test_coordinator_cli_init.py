import io
import json
import os
import socket
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

import py_compile

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

                base = Path("btc-trader")
                node = base / "crunch-node-btc-trader"
                challenge = base / "crunch-btc-trader"
                package = challenge / "crunch_btc_trader"

                self.assertFalse(Path("crunch-implementations").exists())
                self.assertTrue((base / "README.md").exists())
                self.assertTrue((node / "README.md").exists())
                self.assertTrue((node / "pyproject.toml").exists())
                self.assertTrue((node / "Makefile").exists())
                self.assertTrue((node / "Dockerfile").exists())
                self.assertTrue((node / "docker-compose.yml").exists())
                self.assertTrue((node / "scripts" / "verify_e2e.py").exists())
                self.assertTrue((node / "runtime" / "coordinator_core").exists())
                self.assertTrue((node / "runtime" / "coordinator_runtime").exists())
                self.assertTrue((node / "runtime" / "node_template").exists())
                self.assertTrue((node / ".local.env").exists())
                self.assertTrue((node / ".local.env.example").exists())
                self.assertTrue((node / "config" / "callables.env").exists())
                self.assertTrue((node / "config" / "scheduled_prediction_configs.json").exists())
                self.assertTrue((node / "deployment" / "README.md").exists())
                self.assertTrue((node / "plugins" / "README.md").exists())
                self.assertTrue((node / "extensions" / "README.md").exists())

                makefile = (node / "Makefile").read_text(encoding="utf-8")
                self.assertIn("-f docker-compose.yml", makefile)
                self.assertNotIn("ROOT_DIR", makefile)
                self.assertNotIn("../../..", makefile)

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
                self.assertTrue((node / "RUNBOOK.md").exists())
                self.assertTrue((base / "process-log.jsonl").exists())

    def test_init_generates_runbook_with_troubleshooting(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                runbook = Path("btc-trader/crunch-node-btc-trader/RUNBOOK.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("Ports already in use", runbook)
                self.assertIn("MODEL_BASE_CLASSNAME=tracker.TrackerBase", runbook)

    def test_init_generates_process_log_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                raw = Path("btc-trader/process-log.jsonl").read_text(encoding="utf-8").strip()
                lines = [json.loads(line) for line in raw.splitlines()]
                self.assertGreaterEqual(len(lines), 2)
                self.assertEqual(lines[0]["phase"], "init")
                self.assertIn("timestamp", lines[0])

    def test_init_accepts_answers_file_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                answers = {
                    "name": "from-answers",
                    "crunch_id": "answers-crunch",
                    "checkpoint_interval_seconds": 33,
                }
                Path("answers.json").write_text(json.dumps(answers), encoding="utf-8")

                code = main(["init", "--answers", "answers.json"])
                self.assertEqual(code, 0)

                env = Path("from-answers/crunch-node-from-answers/.local.env").read_text(
                    encoding="utf-8"
                )
                self.assertIn("CRUNCH_ID=answers-crunch", env)
                self.assertIn("CHECKPOINT_INTERVAL_SECONDS=33", env)

    def test_preflight_halts_when_port_busy(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            port = sock.getsockname()[1]
            code = main(["preflight", "--ports", str(port)])
            self.assertEqual(code, 1)

    def test_init_defaults_model_base_classname_to_tracker_trackerbase(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                node_env = Path("btc-trader/crunch-node-btc-trader/.local.env").read_text(
                    encoding="utf-8"
                )
                self.assertIn("MODEL_BASE_CLASSNAME=tracker.TrackerBase", node_env)

    def test_init_writes_local_uv_sources_for_challenge_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                node_pyproject = Path("btc-trader/crunch-node-btc-trader/pyproject.toml").read_text(
                    encoding="utf-8"
                )
                self.assertIn("[tool.uv.sources]", node_pyproject)
                self.assertIn(
                    'crunch-btc-trader = { path = "../crunch-btc-trader", editable = true }',
                    node_pyproject,
                )

    def test_init_generates_parseable_verify_e2e_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                script = Path("btc-trader/crunch-node-btc-trader/scripts/verify_e2e.py")
                py_compile.compile(str(script), doraise=True)

                content = script.read_text(encoding="utf-8")
                self.assertIn('return (result.stdout or "") + "\\n" + (result.stderr or "")', content)

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
                    "eth-trader/crunch-node-eth-trader/.local.env.example"
                ).read_text(encoding="utf-8")
                self.assertIn("CRUNCH_ID=challenge-eth", node_env)
                self.assertIn(
                    "MODEL_BASE_CLASSNAME=crunch_eth_trader.tracker.CustomTrackerBase",
                    node_env,
                )

    def test_init_normalizes_package_scoped_model_base_classname(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                spec_path = self._write_spec(
                    Path("spec.json"),
                    {
                        "spec_version": "1",
                        "name": "eth-trader",
                        "model_base_classname": "crunch_eth_trader.tracker.TrackerBase",
                    },
                )

                code = main(["init", "--spec", str(spec_path)])
                self.assertEqual(code, 0)

                node_env = Path(
                    "eth-trader/crunch-node-eth-trader/.local.env.example"
                ).read_text(encoding="utf-8")
                self.assertIn("MODEL_BASE_CLASSNAME=tracker.TrackerBase", node_env)

                rendered_spec = json.loads(Path("eth-trader/spec.json").read_text(encoding="utf-8"))
                self.assertEqual(rendered_spec["model_base_classname"], "tracker.TrackerBase")

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
                    "btc-trader/crunch-node-btc-trader/config/callables.env"
                ).read_text(encoding="utf-8")
                runtime_env = Path(
                    "btc-trader/crunch-node-btc-trader/.local.env"
                ).read_text(encoding="utf-8")
                compose = Path(
                    "btc-trader/crunch-node-btc-trader/docker-compose.yml"
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
                    "../crunch-btc-trader:/app/challenge",
                    compose,
                )

                schedule_raw = Path(
                    "btc-trader/crunch-node-btc-trader/config/scheduled_prediction_configs.json"
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

    def test_init_respects_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                output = Path("custom-output")
                code = main(["init", "btc-trader", "--output", str(output)])
                self.assertEqual(code, 0)
                self.assertTrue((output / "btc-trader").exists())
                self.assertFalse((output / "crunch-implementations").exists())

    def test_init_supports_preset_flag_overriding_spec_preset(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                spec_path = self._write_spec(
                    Path("spec.json"),
                    {
                        "spec_version": "1",
                        "name": "btc-trader",
                        "preset": "in-sample",
                    },
                )

                code = main(["init", "--spec", str(spec_path), "--preset", "realtime"])
                self.assertEqual(code, 0)

                node_dir = Path("btc-trader/crunch-node-btc-trader")
                runtime_env = (node_dir / ".local.env").read_text(encoding="utf-8")
                schedule = json.loads(
                    (node_dir / "config" / "scheduled_prediction_configs.json").read_text(
                        encoding="utf-8"
                    )
                )

                self.assertIn("CHECKPOINT_INTERVAL_SECONDS=15", runtime_env)
                self.assertEqual(schedule[0]["scope_key"], "realtime-btc")
                self.assertEqual(schedule[0]["schedule"]["every_seconds"], 15)

    def test_preflight_passes_when_port_free(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        code = main(["preflight", "--ports", str(port)])
        self.assertEqual(code, 0)

    def test_init_rejects_unknown_preset(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader", "--preset", "unknown"])
                self.assertEqual(code, 1)

    def test_init_lists_available_presets(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                output = io.StringIO()
                with redirect_stdout(output):
                    code = main(["init", "--list-presets"])

                self.assertEqual(code, 0)
                value = output.getvalue()
                self.assertIn("baseline", value)
                self.assertIn("realtime", value)
                self.assertIn("in-sample", value)
                self.assertIn("out-of-sample", value)

    def test_init_uses_public_runtime_callables_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                callables_env = Path(
                    "btc-trader/crunch-node-btc-trader/config/callables.env"
                ).read_text(encoding="utf-8")

                self.assertNotIn("node_template.", callables_env)
                self.assertIn(
                    "MODEL_SCORE_AGGREGATOR=coordinator_runtime.defaults:aggregate_model_scores",
                    callables_env,
                )
                self.assertIn(
                    "LEADERBOARD_RANKER=coordinator_runtime.defaults:rank_leaderboard",
                    callables_env,
                )

    def test_init_rejects_legacy_tokens_in_rendered_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                spec_path = self._write_spec(
                    Path("spec.json"),
                    {
                        "spec_version": "1",
                        "name": "btc-trader",
                        "callables": {
                            "MODEL_SCORE_AGGREGATOR": "node_template.extensions.default_callables:default_aggregate_model_scores"
                        },
                    },
                )

                code = main(["init", "--spec", str(spec_path)])
                self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
