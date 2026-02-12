import json
import os
import socket
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

                self.assertFalse(Path("crunch-implementations").exists())
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
                self.assertNotIn("ROOT_DIR", makefile)
                self.assertNotIn("../../..", makefile)
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
                self.assertTrue((package / "schemas" / "README.md").exists())
                self.assertTrue((package / "examples" / "__init__.py").exists())
                self.assertTrue((package / "examples" / "README.md").exists())
                self.assertTrue((package / "examples" / "mean_reversion_tracker.py").exists())
                self.assertTrue((package / "examples" / "trend_following_tracker.py").exists())
                self.assertTrue((package / "examples" / "volatility_regime_tracker.py").exists())

                self.assertTrue((node / "runtime_definitions" / "__init__.py").exists())
                self.assertTrue((node / "runtime_definitions" / "contracts.py").exists())
                self.assertTrue((node / "runtime_definitions" / "contracts.py").exists())
                # Removed templates — should NOT exist
                self.assertFalse((node / "runtime_definitions" / "inference.py").exists())
                self.assertFalse((node / "runtime_definitions" / "validation.py").exists())
                self.assertFalse((node / "runtime_definitions" / "reporting.py").exists())

                self.assertTrue((node / "RUNBOOK.md").exists())
                self.assertTrue((base / "process-log.jsonl").exists())

    def test_init_generates_workspace_skill_guidance(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                workspace_skill = Path("btc-trader/SKILL.md").read_text(encoding="utf-8")
                node_skill = Path("btc-trader/crunch-node-btc-trader/SKILL.md").read_text(encoding="utf-8")
                challenge_skill = Path("btc-trader/crunch-btc-trader/SKILL.md").read_text(encoding="utf-8")

                self.assertIn("make deploy", workspace_skill)
                self.assertIn("make verify-e2e", workspace_skill)
                self.assertIn("process-log.jsonl", workspace_skill)

                self.assertIn("make logs", node_skill)
                self.assertIn("make logs-capture", node_skill)
                self.assertIn("runtime-services.jsonl", node_skill)

                self.assertIn("tracker.py", challenge_skill)
                self.assertIn("scoring.py", challenge_skill)

    def test_init_generates_runbook_with_troubleshooting(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                runbook = Path("btc-trader/crunch-node-btc-trader/RUNBOOK.md").read_text(encoding="utf-8")
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

    def test_init_defaults_model_base_classname_to_tracker_trackerbase(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                node_env = Path("btc-trader/crunch-node-btc-trader/.local.env").read_text(encoding="utf-8")
                self.assertIn("MODEL_BASE_CLASSNAME=tracker.TrackerBase", node_env)

    def test_init_writes_local_uv_sources_for_challenge_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                node_pyproject = Path("btc-trader/crunch-node-btc-trader/pyproject.toml").read_text(encoding="utf-8")
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

    def test_init_generates_parseable_capture_runtime_logs_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                script = Path("btc-trader/crunch-node-btc-trader/scripts/capture_runtime_logs.py")
                py_compile.compile(str(script), doraise=True)

    def test_init_fails_when_target_exists_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                first = main(["init", "btc-trader"])
                second = main(["init", "btc-trader"])
                forced = main(["init", "btc-trader", "--force"])

                self.assertEqual(first, 0)
                self.assertEqual(second, 1)
                self.assertEqual(forced, 0)

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

    def test_init_uses_only_tier1_callables(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                callables_env = Path(
                    "btc-trader/crunch-node-btc-trader/config/callables.env"
                ).read_text(encoding="utf-8")

                # Only scoring callable present
                self.assertIn("SCORING_FUNCTION=crunch_btc_trader.scoring:score_prediction", callables_env)

                # No other callables
                self.assertNotIn("RAW_INPUT_PROVIDER", callables_env)
                self.assertNotIn("GROUND_TRUTH_RESOLVER", callables_env)
                self.assertNotIn("INFERENCE_INPUT_BUILDER", callables_env)
                self.assertNotIn("INFERENCE_OUTPUT_VALIDATOR", callables_env)

    def test_init_uses_realtime_pack_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                node_env = Path("btc-trader/crunch-node-btc-trader/.local.env").read_text(encoding="utf-8")
                self.assertIn("CHECKPOINT_INTERVAL_SECONDS=15", node_env)

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

    def test_preflight_halts_when_port_busy(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            port = sock.getsockname()[1]
            code = main(["preflight", "--ports", str(port)])
            self.assertEqual(code, 1)

    def test_preflight_passes_when_port_free(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        code = main(["preflight", "--ports", str(port)])
        self.assertEqual(code, 0)

    def test_demo_creates_btc_up_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["demo"])
                self.assertEqual(code, 0)

                workspace = Path("btc-up")
                node_dir = workspace / "crunch-node-btc-up"
                compose = (node_dir / "docker-compose.yml").read_text(encoding="utf-8")

                self.assertTrue(workspace.exists())
                self.assertTrue(node_dir.exists())
                self.assertIn(
                    "${REPORT_UI_BUILD_CONTEXT:-https://github.com/crunchdao/coordinator-webapp.git}",
                    compose,
                )

    def test_scaffold_generates_check_models_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                script = Path("btc-trader/crunch-node-btc-trader/scripts/check_models.py")
                self.assertTrue(script.exists())
                py_compile.compile(str(script), doraise=True)

    def test_scaffold_makefile_has_check_models_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                makefile = Path("btc-trader/crunch-node-btc-trader/Makefile").read_text(encoding="utf-8")
                self.assertIn("check-models", makefile)

    def test_demo_can_pin_local_webapp_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                local_webapp = Path("../coordinator-webapp").resolve()
                local_webapp.mkdir(parents=True, exist_ok=True)

                code = main(["demo", "--webapp-path", str(local_webapp)])
                self.assertEqual(code, 0)

                node_env = Path("btc-up/crunch-node-btc-up/.local.env").read_text(encoding="utf-8")
                self.assertIn(f"REPORT_UI_BUILD_CONTEXT={local_webapp}", node_env)

    def test_scaffold_supports_platform_ui_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                node_dir = Path("btc-trader/crunch-node-btc-trader")
                compose = (node_dir / "docker-compose.yml").read_text(encoding="utf-8")
                env = (node_dir / ".local.env").read_text(encoding="utf-8")

                self.assertIn("${REPORT_UI_APP:-starter}", compose)
                self.assertIn("${NEXT_PUBLIC_API_URL:-http://report-worker:8000}", compose)
                self.assertIn("REPORT_UI_APP=starter", env)
                self.assertIn("REPORT_UI_APP=platform", env)


if __name__ == "__main__":
    unittest.main()
