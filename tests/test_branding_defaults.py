import unittest
from pathlib import Path


class TestBrandingDefaults(unittest.TestCase):
    def test_repository_is_free_of_legacy_brand_references(self):
        roots = [
            Path("README.md"),
            Path("Makefile"),
            Path(".local.env"),
            Path(".dev.env"),
            Path(".production.env"),
            Path("docker-compose.yml"),
            Path("docker-compose-local.yml"),
            Path("docker-compose-prod.yml"),
            Path("coordinator_core"),
            Path("node_template"),
            Path("deployment/model-orchestrator-local/config"),
            Path("deployment/model-orchestrator-local/data/submissions"),
            Path("docs"),
            Path("tests"),
        ]

        blocked_terms = ("condor" + "game", "condor" + "game_backend")

        offenders: list[str] = []
        for root in roots:
            paths = [root] if root.is_file() else list(root.rglob("*"))
            for path in paths:
                if not path.is_file():
                    continue
                if "__pycache__" in path.parts:
                    continue
                if path.suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".db", ".pyc", ".ipynb"}:
                    continue
                text = path.read_text(errors="ignore")
                lower = text.lower()
                if any(term in lower for term in blocked_terms):
                    offenders.append(str(path))

        self.assertEqual([], offenders, f"Found legacy branding references in: {offenders}")


if __name__ == "__main__":
    unittest.main()
