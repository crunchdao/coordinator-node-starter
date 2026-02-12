import unittest


class TestInitServiceCompatibility(unittest.TestCase):
    def test_init_cmd_reexports_run_init_from_init_service(self):
        from coordinator_core.cli import init_cmd, init_service

        self.assertIs(init_cmd.run_init, init_service.run_init)


if __name__ == "__main__":
    unittest.main()
