from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from harness.inception_evidence import (
    InceptionEvidenceError,
    sha256_text,
    validate_citation_claim,
    validate_code_evidence,
)


class InceptionEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "sample.py"
        self.source.write_text(
            "def target(value: int) -> int:\n"
            "    return value + 1\n"
            "\n"
            "class Other:\n"
            "    pass\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def code_record(self) -> dict:
        lines = self.source.read_text(encoding="utf-8").splitlines(keepends=True)
        snippet = "".join(lines[0:2])
        return {
            "schema_version": "truth-verify-loop/inception-code-evidence/v1",
            "repository": "ed3c/public-fixture",
            "commit": "0123456789abcdef0123456789abcdef01234567",
            "tree": "89abcdef0123456789abcdef0123456789abcdef",
            "path": "sample.py",
            "start_line": 1,
            "end_line": 2,
            "snippet_digest": sha256_text(snippet),
            "symbol": "target",
            "parser": "python-ast",
            "parser_coverage": "FULL",
            "physical_state": "CANDIDATE",
            "claims_not_proven": [
                "Physical code readback does not establish business-claim truth.",
                "No independent semantic reviewer has executed.",
            ],
        }

    def citation_record(self) -> dict:
        quote = "Example API is available."
        return {
            "schema_version": "truth-verify-loop/inception-citation-claim/v1",
            "claim_id": "claim-fixture-1",
            "source_digest": "sha256:" + "a" * 64,
            "locator": "fixture.txt:L1",
            "quote": quote,
            "quote_digest": sha256_text(quote),
            "lexical_state": "PASS",
            "semantic_state": "NOT_EXERCISED",
            "semantic_receipt": None,
            "claims_not_proven": [
                "Lexical match is not semantic entailment.",
                "No business claim is closed by this fixture.",
            ],
        }

    def assert_refused(self, operation, expected: str) -> None:
        with self.assertRaisesRegex(InceptionEvidenceError, expected):
            operation()

    def test_exact_code_readback_passes(self) -> None:
        result = validate_code_evidence(self.root, self.code_record())
        self.assertEqual(result["physical_state"], "PASS")
        self.assertEqual(result["symbol"], "target")

    def test_path_escape_fails_closed(self) -> None:
        record = self.code_record()
        record["path"] = "../escape.py"
        self.assert_refused(lambda: validate_code_evidence(self.root, record), "traversal")

    def test_symlink_escape_fails_closed(self) -> None:
        outside = self.root.parent / f"outside-{self.root.name}.py"
        outside.write_text("def target():\n    pass\n", encoding="utf-8")
        link = self.root / "escape.py"
        try:
            link.symlink_to(outside)
            record = self.code_record()
            record["path"] = "escape.py"
            record["start_line"] = 1
            record["end_line"] = 2
            record["snippet_digest"] = sha256_text(outside.read_text(encoding="utf-8"))
            self.assert_refused(lambda: validate_code_evidence(self.root, record), "escapes")
        finally:
            outside.unlink(missing_ok=True)

    def test_line_and_snippet_mismatch_fail_closed(self) -> None:
        record = self.code_record()
        record["end_line"] = 99
        self.assert_refused(lambda: validate_code_evidence(self.root, record), "exceeds")

        record = self.code_record()
        record["snippet_digest"] = "sha256:" + "0" * 64
        self.assert_refused(lambda: validate_code_evidence(self.root, record), "snippet digest mismatch")

    def test_missing_symbol_and_false_parser_coverage_fail_closed(self) -> None:
        record = self.code_record()
        record["symbol"] = "missing"
        self.assert_refused(lambda: validate_code_evidence(self.root, record), "symbol absent")

        record = self.code_record()
        record["parser"] = "unavailable"
        record["parser_coverage"] = "FULL"
        record["symbol"] = None
        self.assert_refused(lambda: validate_code_evidence(self.root, record), "cannot claim coverage")

    def test_lexical_pass_does_not_self_promote_semantics(self) -> None:
        result = validate_citation_claim(self.citation_record())
        self.assertEqual(result["lexical_state"], "PASS")
        self.assertEqual(result["semantic_state"], "NOT_EXERCISED")
        self.assertIsNone(result["semantic_receipt"])

    def test_semantic_state_requires_independent_receipt_shape(self) -> None:
        record = self.citation_record()
        record["semantic_state"] = "SUPPORTED"
        self.assert_refused(lambda: validate_citation_claim(record), "semantic receipt required")

        record["semantic_receipt"] = "sha256:" + "b" * 64
        result = validate_citation_claim(record)
        self.assertEqual(result["semantic_state"], "SUPPORTED")

    def test_quote_digest_mutation_fails_closed(self) -> None:
        record = self.citation_record()
        record["quote"] = "Changed quote."
        self.assert_refused(lambda: validate_citation_claim(record), "quote digest mismatch")

    def test_mutable_subject_is_not_accepted_as_commit(self) -> None:
        record = self.code_record()
        record["commit"] = "main"
        self.assert_refused(lambda: validate_code_evidence(self.root, record), "exact 40-hex")


if __name__ == "__main__":
    unittest.main()
