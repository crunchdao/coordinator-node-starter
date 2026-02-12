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


class TestCoordinatorCliDoctor(unittest.TestCase):
    def test_doctor_accepts_valid_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                Path("spec.json").write_text(
                    json.dumps(
                        {
                            "spec_version": "1",
                            "name": "btc-trader",
                            "crunch_id": "starter-btc",
                            "callables": {
                                "SCORING_FUNCTION": "crunch_btc_trader.scoring:score_prediction"
                            },
                        }
                    ),
                    encoding="utf-8",
                )

                code = main(["doctor", "--spec", "spec.json"])
                self.assertEqual(code, 0)

    def test_doctor_rejects_missing_spec_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["doctor", "--spec", "does-not-exist.json"])
                self.assertEqual(code, 1)

    def test_doctor_ignores_unknown_callable_keys_in_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                Path("spec.json").write_text(
                    json.dumps(
                        {
                            "spec_version": "1",
                            "name": "btc-trader",
                            "callables": {
                                "UNKNOWN_KEY": "crunch_btc_trader.scoring:score_prediction"
                            },
                        }
                    ),
                    encoding="utf-8",
                )

                code = main(["doctor", "--spec", "spec.json"])
                self.assertEqual(code, 0)

    def test_doctor_rejects_missing_spec_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                Path("spec.json").write_text(
                    json.dumps({"name": "btc-trader"}),
                    encoding="utf-8",
                )

                code = main(["doctor", "--spec", "spec.json"])
                self.assertEqual(code, 1)

    def test_doctor_rejects_unsupported_spec_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                Path("spec.json").write_text(
                    json.dumps({"spec_version": "2", "name": "btc-trader"}),
                    encoding="utf-8",
                )

                code = main(["doctor", "--spec", "spec.json"])
                self.assertEqual(code, 1)

    def test_doctor_rejects_unknown_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                Path("spec.json").write_text(
                    json.dumps({"spec_version": "1", "name": "btc-trader", "pack": "unknown"}),
                    encoding="utf-8",
                )

                code = main(["doctor", "--spec", "spec.json"])
                self.assertEqual(code, 1)

    def test_doctor_rejects_template_callable_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                Path("spec.json").write_text(
                    json.dumps(
                        {
                            "spec_version": "1",
                            "name": "btc-trader",
                            "callables": {
                                "SCORING_FUNCTION": "node_template.extensions.default_callables:default_score_prediction"
                            },
                        }
                    ),
                    encoding="utf-8",
                )

                code = main(["doctor", "--spec", "spec.json"])
                self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
