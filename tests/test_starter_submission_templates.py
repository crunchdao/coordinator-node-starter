import unittest

from coordinator_core.cli.init_cmd import _starter_submission_tracker


class TestStarterSubmissionTemplates(unittest.TestCase):
    def test_tracker_template_guards_non_iterable_tick_points(self):
        template = _starter_submission_tracker()
        self.assertIn("if not isinstance(points, (list, tuple))", template)
        self.assertIn("self.history.setdefault(asset, []).extend(points)", template)


if __name__ == "__main__":
    unittest.main()
