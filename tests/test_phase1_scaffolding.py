import importlib.util
import unittest


class TestPhase1Scaffolding(unittest.TestCase):
    def test_new_package_roots_exist(self):
        self.assertIsNotNone(importlib.util.find_spec("coordinator_core"))
        self.assertIsNotNone(importlib.util.find_spec("node_template"))

    def test_core_subpackages_exist(self):
        required_modules = [
            "coordinator_core.entities",
            "coordinator_core.infrastructure.db",
            "coordinator_core.services.interfaces",
        ]

        for module_name in required_modules:
            with self.subTest(module=module_name):
                self.assertIsNotNone(importlib.util.find_spec(module_name))

    def test_template_subpackages_exist(self):
        required_modules = [
            "node_template.config",
            "node_template.entities",
            "node_template.infrastructure",
            "node_template.services",
            "node_template.workers",
            "node_template.extensions",
        ]

        for module_name in required_modules:
            with self.subTest(module=module_name):
                self.assertIsNotNone(importlib.util.find_spec(module_name))


if __name__ == "__main__":
    unittest.main()
