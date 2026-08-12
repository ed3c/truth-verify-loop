import unittest

from harness.cli import build_parser


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


if __name__ == "__main__":
    unittest.main()
