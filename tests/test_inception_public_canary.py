from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from harness.inception_public_canary import (
    PUBLIC_COMMIT,
    PUBLIC_PATH,
    PUBLIC_REPOSITORY,
    PUBLIC_TREE,
    reconcile_fixture_reviewers,
    run_public_blob_canary,
)


class InceptionPublicCanaryTests(unittest.TestCase):
    def test_public_canary_logic_is_hermetic_in_generic_suite(self) -> None:
        source = b"def run_live_verification():\n    return True\n"
        with patch(
            "harness.inception_public_canary._git",
            side_effect=[(PUBLIC_TREE + "\n").encode("utf-8"), source],
        ):
            result = run_public_blob_canary(Path("."))

        self.assertEqual(
            result["subject"],
            {
                "repository": PUBLIC_REPOSITORY,
                "commit": PUBLIC_COMMIT,
                "tree": PUBLIC_TREE,
                "path": PUBLIC_PATH,
                "blob_digest": result["subject"]["blob_digest"],
            },
        )
        self.assertEqual(result["code"]["physical_state"], "PASS")
        self.assertEqual(result["code"]["parser"], "python-ast")
        self.assertEqual(result["citation"]["lexical_state"], "PASS")
        self.assertEqual(result["citation"]["semantic_state"], "SUPPORTED")
        self.assertRegex(result["citation"]["semantic_receipt"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            result["reviewers"],
            ["regex-symbol-reviewer/v1", "python-ast-symbol-reviewer/v1"],
        )
        self.assertEqual(result["evidence_ceiling"], "PUBLIC_DETERMINISTIC_FIXTURE_ONLY")
        self.assertTrue(result["claims_not_proven"])

    def test_reviewer_disagreement_does_not_promote_support(self) -> None:
        self.assertEqual(reconcile_fixture_reviewers(True, False), "CONFLICTED")
        self.assertEqual(reconcile_fixture_reviewers(False, True), "CONFLICTED")
        self.assertEqual(reconcile_fixture_reviewers(False, False), "ABSTAIN")


if __name__ == "__main__":
    unittest.main()
