from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest

from harness.cli import build_parser, main


class CliTests(unittest.TestCase):
    def test_run_agy_exposes_provider_and_outer_timeouts(self):
        args = build_parser().parse_args(
            [
                "run-agy",
                "--claim",
                "claim.json",
                "--policy",
                "policy.json",
                "--lake",
                ".tvlake",
            ]
        )

        self.assertEqual(args.provider_print_timeout, 300.0)
        self.assertEqual(args.outer_timeout, 330.0)
        self.assertIsNone(args.semantic_config)

    def test_run_agy_accepts_a_versioned_semantic_config(self):
        args = build_parser().parse_args(
            [
                "run-agy",
                "--claim",
                "claim.json",
                "--policy",
                "policy.json",
                "--lake",
                ".tvlake",
                "--semantic-config",
                "semantic.json",
            ]
        )

        self.assertEqual(args.semantic_config, Path("semantic.json"))

    def test_run_agy_validates_semantic_config_before_live_execution(self):
        root = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            config = work / "semantic.json"
            config.write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")
            lake = work / "lake"
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        "run-agy",
                        "--claim",
                        str(root / "examples/live-search/claim.json"),
                        "--policy",
                        str(root / "config/source-policy.example.json"),
                        "--lake",
                        str(lake),
                        "--semantic-config",
                        str(config),
                    ]
                )

            self.assertFalse(lake.exists())

        self.assertEqual(exit_code, 2)
        self.assertIn("semantic verifier config fields", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
