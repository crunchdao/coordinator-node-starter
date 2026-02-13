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
    def test_init_creates_workspace_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                base = Path("btc-trader")
                node = base / "node"
                challenge = base / "challenge"
                package = challenge / "btc_trader"

                # Workspace
                self.assertTrue((base / "README.md").exists())
                self.assertTrue((base / "Makefile").exists())

                # Node
                self.assertTrue((node / "docker-compose.yml").exists())
                self.assertTrue((node / "Dockerfile").exists())
                self.assertTrue((node / "Makefile").exists())
                self.assertTrue((node / ".local.env").exists())
                self.assertTrue((node / "config" / "callables.env").exists())
                self.assertTrue((node / "scripts" / "verify_e2e.py").exists())
                self.assertTrue((node / "scripts" / "check_models.py").exists())
                self.assertTrue((node / "runtime_definitions" / "contracts.py").exists())
                self.assertTrue((node / "runtime" / "coordinator").exists())

                # Challenge
                self.assertTrue((challenge / "pyproject.toml").exists())
                self.assertTrue((package / "tracker.py").exists())
                self.assertTrue((package / "scoring.py").exists())
                self.assertTrue((package / "examples" / "mean_reversion_tracker.py").exists())

    def test_init_replaces_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                # Check slug replacement in content
                compose = Path("btc-trader/node/docker-compose.yml").read_text(encoding="utf-8")
                self.assertIn("btc-trader", compose)
                self.assertNotIn("starter-challenge", compose)

                # Check module replacement in content
                callables = Path("btc-trader/node/config/callables.env").read_text(encoding="utf-8")
                self.assertIn("btc_trader", callables)
                self.assertNotIn("starter_challenge", callables)

                # Check Python package dir was renamed
                self.assertTrue(Path("btc-trader/challenge/btc_trader").is_dir())
                self.assertFalse(Path("btc-trader/challenge/starter_challenge").exists())

    def test_init_generates_parseable_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                scripts = Path("btc-trader/node/scripts")
                py_compile.compile(str(scripts / "verify_e2e.py"), doraise=True)
                py_compile.compile(str(scripts / "capture_runtime_logs.py"), doraise=True)
                py_compile.compile(str(scripts / "check_models.py"), doraise=True)

    def test_init_fails_when_exists_without_force(self):
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
                code = main(["init", "btc-trader", "--output", "custom"])
                self.assertEqual(code, 0)
                self.assertTrue(Path("custom/btc-trader/node/docker-compose.yml").exists())

    def test_init_derives_name_from_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "my-project"
            output.mkdir()
            code = main(["init", "--output", str(output)])
            self.assertEqual(code, 0)
            self.assertTrue((output / "my-project" / "node").exists())

    def test_init_writes_process_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                raw = Path("btc-trader/process-log.jsonl").read_text(encoding="utf-8").strip()
                lines = [json.loads(line) for line in raw.splitlines()]
                self.assertGreaterEqual(len(lines), 1)
                self.assertEqual(lines[0]["phase"], "init")
                self.assertEqual(lines[0]["name"], "btc-trader")

    def test_init_container_names_use_challenge_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                compose = Path("btc-trader/node/docker-compose.yml").read_text(encoding="utf-8")
                self.assertIn("container_name: btc-trader-postgres", compose)
                self.assertIn("container_name: btc-trader-report-worker", compose)


if __name__ == "__main__":
    unittest.main()
