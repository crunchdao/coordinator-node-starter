import unittest

from coordinator_cli.commands.packs import get_pack, list_pack_names, list_pack_summaries


class TestCoordinatorCliPacks(unittest.TestCase):
    def test_lists_realtime_pack(self):
        names = list_pack_names()
        self.assertIn("realtime", names)
        self.assertEqual(len(names), 1)

    def test_get_pack_returns_required_sections(self):
        pack = get_pack("realtime")
        self.assertEqual(pack["id"], "realtime")
        self.assertIn("callables", pack)
        self.assertIn("scheduled_prediction_configs", pack)
        self.assertEqual(pack["template_set"], "default")

    def test_list_pack_summaries_contains_descriptions(self):
        summaries = dict(list_pack_summaries())
        self.assertIn("realtime", summaries)
        self.assertTrue(summaries["realtime"])


if __name__ == "__main__":
    unittest.main()
