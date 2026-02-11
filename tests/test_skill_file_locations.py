import unittest
from pathlib import Path


class TestSkillFileLocations(unittest.TestCase):
    def test_node_template_skill_files_exist(self):
        expected = [
            Path("node_template/entities/SKILL.md"),
            Path("node_template/services/SKILL.md"),
            Path("node_template/workers/SKILL.md"),
            Path("node_template/infrastructure/http/SKILL.md"),
        ]

        for file_path in expected:
            with self.subTest(path=str(file_path)):
                self.assertTrue(file_path.exists())

    def test_legacy_skill_files_if_present_are_compatibility_stubs(self):
        legacy_map = {
            Path("legacy_backend/entities/SKILL.md"): "node_template/entities/SKILL.md",
            Path("legacy_backend/services/SKILL.md"): "node_template/services/SKILL.md",
            Path("legacy_backend/workers/SKILL.md"): "node_template/workers/SKILL.md",
            Path("legacy_backend/infrastructure/http/SKILL.md"): "node_template/infrastructure/http/SKILL.md",
        }

        for old_path, new_path in legacy_map.items():
            with self.subTest(path=str(old_path)):
                if not old_path.exists():
                    continue
                text = old_path.read_text()
                self.assertIn("Compatibility Stub", text)
                self.assertIn(new_path, text)


if __name__ == "__main__":
    unittest.main()
