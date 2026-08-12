from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.gates.check_delivery_receipt import check


class DeliveryReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        registry_path = (
            self.root / ".skill-bindings/forgejo-delivery-loop/registry.json"
        )
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(
            json.dumps(
                {
                    "required_receipt_fields": [
                        "line",
                        "repo",
                        "issues",
                        "pr",
                        "milestone_url",
                        "synced_at_commit",
                    ],
                    "lines": [
                        {
                            "line": "demo",
                            "forgejo_repo": "neon/demo",
                            "materialized_path": ".",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_receipt(self, **overrides: object) -> None:
        receipt = {
            "line": "demo",
            "repo": "neon/demo",
            "issues": ["http://localhost:3000/neon/demo/issues/1"],
            "pr": "http://localhost:3000/neon/demo/pulls/1",
            "milestone_url": "http://localhost:3000/neon/demo/milestone/1",
            "synced_at_commit": "0123456",
        }
        receipt.update(overrides)
        (self.root / "delivery.json").write_text(
            json.dumps(receipt), encoding="utf-8"
        )

    def test_complete_local_receipt_passes(self) -> None:
        self.write_receipt()
        check(self.root)

    def test_missing_receipt_fails_loudly(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing file"):
            check(self.root)

    def test_non_local_forge_url_is_rejected(self) -> None:
        self.write_receipt(pr="https://github.com/neon/demo/pull/1")
        with self.assertRaisesRegex(ValueError, "localhost:3000"):
            check(self.root)


if __name__ == "__main__":
    unittest.main()
