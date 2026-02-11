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
                self.assertTrue((node / ".local.env.example").exists())
                self.assertTrue((node / "config" / "callables.env").exists())
                self.assertTrue((node / "config" / "scheduled_prediction_configs.json").exists())
                self.assertTrue((node / "deployment" / "README.md").exists())
                self.assertTrue((node / "plugins" / "README.md").exists())
                self.assertTrue((node / "extensions" / "README.md").exists())

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

    def test_init_rejects_invalid_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "BTC Trader"])
                self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
