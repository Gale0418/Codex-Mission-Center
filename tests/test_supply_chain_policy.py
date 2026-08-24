import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class SupplyChainPolicyTests(unittest.TestCase):
    def test_actions_and_release_dependency_are_content_pinned(self):
        policy = (ROOT / "docs" / "supply-chain-policy.md").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        requirements = (ROOT / "requirements-runtime.txt").read_text(encoding="utf-8")
        lock = (ROOT / "requirements-runtime.lock").read_text(encoding="utf-8")
        self.assertIn("websockets>=16.1,<17", policy)
        self.assertIn("websockets>=16.1,<17", requirements)
        self.assertIn("websockets-16.1-py3-none-any.whl", lock)
        self.assertRegex(lock, r"--hash=sha256:[0-9a-f]{64}")
        self.assertIn("--require-hashes -r requirements-runtime.lock", workflow)
        refs = re.findall(r"uses:\s+[^@\s]+@([^\s]+)", workflow)
        self.assertTrue(refs)
        for ref in refs:
            self.assertRegex(ref, r"^[0-9a-f]{40}$")
        self.assertIn("Never guess", policy)


if __name__ == "__main__":
    unittest.main()
