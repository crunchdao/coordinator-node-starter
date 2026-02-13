import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

import py_compile

from coordinator_cli.commands.main import main


@contextmanager
def _cwd(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class TestCoordinatorCliInit(unittest.TestCase):
    def test_init_creates_expected_workspace_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                base = Path("btc-trader")
                node = base / "crunch-node-btc-trader"
                challenge = base / "crunch-btc-trader"
                package = challenge / "crunch_btc_trader"

                self.assertTrue((base / "README.md").exists())
                self.assertTrue((base / "SKILL.md").exists())
                self.assertTrue((node / "README.md").exists())
                self.assertTrue((node / "SKILL.md").exists())
                self.assertTrue((node / "pyproject.toml").exists())
                self.assertTrue((node / "Makefile").exists())
                self.assertTrue((node / "Dockerfile").exists())
                self.assertTrue((node / "docker-compose.yml").exists())
                self.assertTrue((node / "scripts" / "verify_e2e.py").exists())
                self.assertTrue((node / "scripts" / "capture_runtime_logs.py").exists())
                self.assertTrue((node / "runtime" / "coordinator").exists())
                self.assertTrue((node / ".local.env").exists())
                self.assertTrue((node / ".local.env.example").exists())
                self.assertTrue((node / "config" / "callables.env").exists())
                self.assertTrue((node / "config" / "scheduled_prediction_configs.json").exists())
                self.assertTrue((node / "deployment" / "README.md").exists())
                self.assertTrue((node / "plugins" / "README.md").exists())
                self.assertTrue((node / "extensions" / "README.md").exists())

                makefile = (node / "Makefile").read_text(encoding="utf-8")
                self.assertIn("-f docker-compose.yml", makefile)
                self.assertIn("logs-capture", makefile)

                self.assertTrue((challenge / "README.md").exists())
                self.assertTrue((challenge / "SKILL.md").exists())
                self.assertTrue((challenge / "pyproject.toml").exists())
                self.assertTrue((package / "__init__.py").exists())
                self.assertTrue((package / "tracker.py").exists())
                self.assertTrue((package / "scoring.py").exists())
                self.assertFalse((package / "inference.py").exists())
                self.assertFalse((package / "validation.py").exists())
                self.assertFalse((package / "reporting.py").exists())
                self.assertTrue((package / "examples" / "mean_reversion_tracker.py").exists())

                self.assertTrue((node / "runtime_definitions" / "__init__.py").exists())
                self.assertTrue((node / "runtime_definitions" / "contracts.py").exists())
                self.assertFalse((node / "runtime_definitions" / "inference.py").exists())
                self.assertFalse((node / "runtime_definitions" / "validation.py").exists())

                self.assertTrue((node / "RUNBOOK.md").exists())
                self.assertTrue((base / "process-log.jsonl").exists())

    def test_init_generates_skill_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                workspace_skill = Path("btc-trader/SKILL.md").read_text(encoding="utf-8")
                node_skill = Path("btc-trader/crunch-node-btc-trader/SKILL.md").read_text(encoding="utf-8")
                challenge_skill = Path("btc-trader/crunch-btc-trader/SKILL.md").read_text(encoding="utf-8")

                self.assertIn("make deploy", workspace_skill)
                self.assertIn("make verify-e2e", workspace_skill)
                self.assertIn("make logs", node_skill)
                self.assertIn("tracker.py", challenge_skill)
                self.assertIn("scoring.py", challenge_skill)

    def test_init_generates_process_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                raw = Path("btc-trader/process-log.jsonl").read_text(encoding="utf-8").strip()
                lines = [json.loads(line) for line in raw.splitlines()]
                self.assertGreaterEqual(len(lines), 2)
                self.assertEqual(lines[0]["phase"], "init")

    def test_init_defaults_model_base_classname(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                env = Path("btc-trader/crunch-node-btc-trader/.local.env").read_text(encoding="utf-8")
                self.assertIn("MODEL_BASE_CLASSNAME=tracker.TrackerBase", env)

    def test_init_writes_uv_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                pyproject = Path("btc-trader/crunch-node-btc-trader/pyproject.toml").read_text(encoding="utf-8")
                self.assertIn("[tool.uv.sources]", pyproject)
                self.assertIn('crunch-btc-trader = { path = "../crunch-btc-trader", editable = true }', pyproject)

    def test_init_generates_parseable_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                scripts = Path("btc-trader/crunch-node-btc-trader/scripts")
                py_compile.compile(str(scripts / "verify_e2e.py"), doraise=True)
                py_compile.compile(str(scripts / "capture_runtime_logs.py"), doraise=True)
                py_compile.compile(str(scripts / "check_models.py"), doraise=True)

    def test_init_fails_when_target_exists_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                self.assertEqual(main(["init", "btc-trader"]), 0)
                self.assertEqual(main(["init", "btc-trader"]), 1)
                self.assertEqual(main(["init", "btc-trader", "--force"]), 0)

    def test_init_rejects_invalid_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                self.assertEqual(main(["init", "BTC Trader"]), 1)

    def test_init_respects_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader", "--output", "custom-output"])
                self.assertEqual(code, 0)
                self.assertTrue(Path("custom-output/btc-trader").exists())

    def test_init_uses_only_scoring_callable(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                callables = Path("btc-trader/crunch-node-btc-trader/config/callables.env").read_text(encoding="utf-8")
                self.assertIn("SCORING_FUNCTION=crunch_btc_trader.scoring:score_prediction", callables)
                self.assertNotIn("RAW_INPUT_PROVIDER", callables)
                self.assertNotIn("GROUND_TRUTH_RESOLVER", callables)

    def test_init_uses_realtime_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                env = Path("btc-trader/crunch-node-btc-trader/.local.env").read_text(encoding="utf-8")
                self.assertIn("CHECKPOINT_INTERVAL_SECONDS=15", env)

                schedule = json.loads(
                    Path("btc-trader/crunch-node-btc-trader/config/scheduled_prediction_configs.json").read_text(encoding="utf-8")
                )
                self.assertEqual(schedule[0]["scope_key"], "realtime-btc")

    def test_init_derives_name_from_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "my-project"
            output.mkdir()
            code = main(["init", "--output", str(output)])
            self.assertEqual(code, 0)
            self.assertTrue((output / "my-project").exists())

    def test_init_uses_new_feed_env_vars(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                env = Path("btc-trader/crunch-node-btc-trader/.local.env").read_text(encoding="utf-8")
                self.assertIn("FEED_SOURCE=pyth", env)
                self.assertIn("FEED_SUBJECTS=BTC", env)
                self.assertNotIn("FEED_PROVIDER=", env)
                self.assertNotIn("FEED_ASSETS=", env)


if __name__ == "__main__":
    unittest.main()
