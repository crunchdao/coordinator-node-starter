import unittest

from coordinator_core.cli.packs import get_pack, list_pack_names, list_pack_summaries


class TestCoordinatorCliPacks(unittest.TestCase):
    def test_lists_expected_builtin_packs(self):
        names = list_pack_names()
        self.assertIn("baseline", names)
        self.assertIn("realtime", names)
        self.assertIn("tournament", names)
        self.assertNotIn("in-sample", names)
        self.assertNotIn("out-of-sample", names)

    def test_get_pack_returns_required_sections(self):
        pack = get_pack("tournament")
        self.assertEqual(pack["id"], "tournament")
        self.assertIn("callables", pack)
        self.assertIn("scheduled_prediction_configs", pack)
        self.assertEqual(pack["template_set"], "default")
        self.assertEqual(len(pack["scheduled_prediction_configs"]), 2)

    def test_list_pack_summaries_contains_descriptions(self):
        summaries = dict(list_pack_summaries())
        self.assertIn("realtime", summaries)
        self.assertIn("tournament", summaries)
        self.assertTrue(summaries["realtime"])
        self.assertTrue(summaries["tournament"])


if __name__ == "__main__":
    unittest.main()
