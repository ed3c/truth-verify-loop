from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

from harness.model import Claim, ContractError, Evidence, sha256_text
from harness.semantic import SemanticReviewRequest
from harness.semantic_adapters import load_semantic_dispatcher


NOW = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)
FAKE_VERIFIER = Path(__file__).parent / "fixtures" / "fake_semantic_verifier.py"


def request() -> SemanticReviewRequest:
    claim = Claim.from_dict(
        {
            "claim_id": "claim-cli",
            "statement": "Example SDK 4.2 is generally available.",
            "risk": "medium",
            "temporality": "versioned",
            "freshness_sla_seconds": 86400,
            "scope": {"version": "4.2"},
        }
    )
    quote = "Example SDK 4.2 is generally available."
    evidence = Evidence.from_dict(
        {
            "evidence_id": "evidence-cli",
            "claim_id": "claim-cli",
            "source_uri": "https://docs.example.invalid/releases/4.2",
            "source_class": "official_release",
            "relationship": "supports",
            "quote": quote,
            "retrieved_at": NOW.isoformat(),
            "content_sha256": "a" * 64,
            "quote_sha256": sha256_text(quote),
            "capture_scope": "full_source",
            "provider_receipt_sha256": "b" * 64,
            "citation": {"quote_verified": True, "snapshot_id": "snapshot-cli"},
        }
    )
    return SemanticReviewRequest.from_evidence(claim, evidence)


class SemanticAdapterTests(unittest.TestCase):
    def config_entry(
        self,
        *,
        family: str = "fixture-family-a",
        provider: str = "fixture-command",
        model: str = "fixture-model-a",
        command: list[str] | None = None,
        max_attempts: int = 1,
        timeout_seconds: float = 1,
    ) -> dict[str, object]:
        return {
            "family": family,
            "provider": provider,
            "provider_version": "1.0",
            "model": model,
            "command": command or [sys.executable, FAKE_VERIFIER.as_posix()],
            "timeout_seconds": timeout_seconds,
            "max_attempts": max_attempts,
            "instruction_files": [],
        }

    def test_versioned_json_schemas_publish_the_command_adapter_contract(self) -> None:
        schema_dir = Path(__file__).parents[1] / "schemas"
        schemas = {
            name: json.loads((schema_dir / name).read_text(encoding="utf-8"))
            for name in (
                "semantic-verifier-config.v1.schema.json",
                "semantic-review-command.v1.schema.json",
                "semantic-review-batch.v1.schema.json",
            )
        }

        self.assertEqual(
            schemas["semantic-verifier-config.v1.schema.json"]["properties"]
            ["schema"]["const"],
            "tvl.semantic-verifier-config.v1",
        )
        self.assertEqual(
            schemas["semantic-review-command.v1.schema.json"]["properties"]
            ["role"]["enum"],
            ["verifier", "judge"],
        )
        result_review = schemas["semantic-review-batch.v1.schema.json"][
            "properties"
        ]["reviews"]["items"]
        self.assertFalse(result_review["additionalProperties"])
        self.assertNotIn("family", result_review["properties"])
        self.assertNotIn("verifier_receipt_sha256", result_review["properties"])

    def test_bundled_local_cli_example_loads_without_running_providers(self) -> None:
        root = Path(__file__).parents[1]
        dispatcher = load_semantic_dispatcher(
            root / "config/semantic-verifiers.local-cli.example.json",
            cwd=root,
        )

        self.assertEqual(
            [verifier.family for verifier in dispatcher.verifiers],
            ["openai-codex", "anthropic-claude"],
        )
        self.assertTrue(Path(dispatcher.verifiers[0].command[0]).is_absolute())
        self.assertEqual(dispatcher.judge.family, "fresh-anthropic-judge")

    def test_published_example_config_loads_without_running_placeholders(self) -> None:
        root = Path(__file__).parents[1]
        dispatcher = load_semantic_dispatcher(
            root / "config/semantic-verifiers.example.json",
            cwd=root,
        )

        self.assertEqual(len(dispatcher.verifiers), 2)
        self.assertIsNotNone(dispatcher.judge)
        self.assertEqual(dispatcher.max_judge_requests, 8)

    def test_versioned_config_builds_a_receipted_command_verifier(self) -> None:
        config = {
            "schema": "tvl.semantic-verifier-config.v1",
            "verifiers": [
                self.config_entry()
            ],
            "judge": None,
            "max_judge_requests": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            dispatcher = load_semantic_dispatcher(config_path, cwd=Path.cwd())
            result = dispatcher.dispatch([request()], minimum_families=1)

        aggregate = result.aggregates["evidence-cli"]
        self.assertEqual(aggregate.verdict, "ENTAILS")
        self.assertEqual(aggregate.accepted_families, ("fixture-family-a",))
        self.assertTrue(aggregate.policy_satisfied)
        receipt = result.runs[0].receipt
        self.assertEqual(receipt.provider, "fixture-command")
        self.assertEqual(receipt.provider_version, "1.0")
        self.assertEqual(receipt.model, "fixture-model-a")
        self.assertEqual(receipt.usage["cost_usd"], 0.02)
        self.assertEqual(len(receipt.prompt_sha256), 64)
        self.assertEqual(len(receipt.output_sha256), 64)

    def test_failed_primary_and_successful_recovery_both_remain_receipted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "attempt-state"
            config = {
                "schema": "tvl.semantic-verifier-config.v1",
                "verifiers": [
                    self.config_entry(
                        family="recovery-family",
                        command=[
                            sys.executable,
                            FAKE_VERIFIER.as_posix(),
                            "recover",
                            state.as_posix(),
                        ],
                        max_attempts=2,
                    )
                ],
                "judge": None,
                "max_judge_requests": 2,
            }
            config_path = root / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            dispatcher = load_semantic_dispatcher(config_path, cwd=Path.cwd())
            result = dispatcher.dispatch([request()], minimum_families=1)

        attempts = result.runs[0].attempt_receipts
        self.assertEqual(
            [(item.status, item.attempt_kind) for item in attempts],
            [("failed", "primary"), ("succeeded", "recovery")],
        )
        self.assertEqual(result.totals["attempts"], 2)
        self.assertEqual(result.totals["failed_attempts"], 1)
        self.assertEqual(result.totals["recovery_attempts"], 1)
        self.assertTrue(result.aggregates["evidence-cli"].policy_satisfied)

    def test_invalid_output_fails_closed_with_actionable_receipt_hashes(self) -> None:
        config = {
            "schema": "tvl.semantic-verifier-config.v1",
            "verifiers": [
                self.config_entry(
                    command=[
                        sys.executable,
                        FAKE_VERIFIER.as_posix(),
                        "invalid",
                    ]
                )
            ],
            "judge": None,
            "max_judge_requests": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            result = load_semantic_dispatcher(
                config_path, cwd=Path.cwd()
            ).dispatch([request()], minimum_families=1)

        receipt = result.runs[0].receipt
        self.assertEqual(receipt.status, "failed")
        self.assertEqual(receipt.failure_reason, "invalid_json")
        self.assertEqual(len(receipt.command_sha256 or ""), 64)
        self.assertEqual(len(receipt.stderr_sha256 or ""), 64)
        stream = result.runs[0].attempt_streams[0]
        self.assertEqual(stream.receipt_sha256, receipt.digest)
        self.assertEqual(stream.stdout, b"not-json\n")
        self.assertEqual(sha256_text(stream.stdout.decode()), receipt.output_sha256)
        self.assertFalse(result.aggregates["evidence-cli"].policy_satisfied)

    def test_timeout_is_a_receipted_fail_closed_terminal_attempt(self) -> None:
        config = {
            "schema": "tvl.semantic-verifier-config.v1",
            "verifiers": [
                self.config_entry(
                    command=[
                        sys.executable,
                        FAKE_VERIFIER.as_posix(),
                        "timeout",
                    ],
                    timeout_seconds=0.05,
                )
            ],
            "judge": None,
            "max_judge_requests": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            result = load_semantic_dispatcher(
                config_path, cwd=Path.cwd()
            ).dispatch([request()], minimum_families=1)

        receipt = result.runs[0].receipt
        self.assertEqual(receipt.status, "timeout")
        self.assertEqual(receipt.failure_reason, "timeout_after_0.05s")
        self.assertEqual(result.totals["timeout_attempts"], 1)
        self.assertFalse(result.aggregates["evidence-cli"].policy_satisfied)

    def test_invalid_usage_is_preserved_as_a_failed_attempt(self) -> None:
        config = {
            "schema": "tvl.semantic-verifier-config.v1",
            "verifiers": [
                self.config_entry(
                    command=[
                        sys.executable,
                        FAKE_VERIFIER.as_posix(),
                        "invalid-usage",
                    ]
                )
            ],
            "judge": None,
            "max_judge_requests": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            result = load_semantic_dispatcher(
                config_path, cwd=Path.cwd()
            ).dispatch([request()], minimum_families=1)

        receipt = result.runs[0].receipt
        self.assertEqual(receipt.status, "failed")
        self.assertEqual(receipt.failure_reason, "invalid_usage_contract")
        self.assertEqual(receipt.usage, {})
        self.assertFalse(result.aggregates["evidence-cli"].policy_satisfied)

    def test_incomplete_review_batch_is_preserved_as_a_failed_attempt(self) -> None:
        config = {
            "schema": "tvl.semantic-verifier-config.v1",
            "verifiers": [
                self.config_entry(
                    command=[
                        sys.executable,
                        FAKE_VERIFIER.as_posix(),
                        "missing-review",
                    ]
                )
            ],
            "judge": None,
            "max_judge_requests": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            result = load_semantic_dispatcher(
                config_path, cwd=Path.cwd()
            ).dispatch([request()], minimum_families=1)

        receipt = result.runs[0].receipt
        self.assertEqual(receipt.status, "failed")
        self.assertEqual(receipt.failure_reason, "invalid_review_batch")
        self.assertFalse(result.aggregates["evidence-cli"].policy_satisfied)

    def test_nonzero_exit_salvages_valid_usage_without_accepting_reviews(self) -> None:
        config = {
            "schema": "tvl.semantic-verifier-config.v1",
            "verifiers": [
                self.config_entry(
                    command=[
                        sys.executable,
                        FAKE_VERIFIER.as_posix(),
                        "fail-with-usage",
                    ]
                )
            ],
            "judge": None,
            "max_judge_requests": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            result = load_semantic_dispatcher(
                config_path, cwd=Path.cwd()
            ).dispatch([request()], minimum_families=1)

        receipt = result.runs[0].receipt
        self.assertEqual(receipt.status, "failed")
        self.assertEqual(receipt.failure_reason, "exit_code_17")
        self.assertEqual(receipt.usage["cost_usd"], 0.02)
        self.assertEqual(result.reviews, ())

    def test_adapter_rejects_output_beyond_the_fixed_capture_limit(self) -> None:
        config = {
            "schema": "tvl.semantic-verifier-config.v1",
            "verifiers": [
                self.config_entry(
                    command=[sys.executable, FAKE_VERIFIER.as_posix(), "oversized"]
                )
            ],
            "judge": None,
            "max_judge_requests": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            result = load_semantic_dispatcher(
                config_path, cwd=Path.cwd()
            ).dispatch([request()], minimum_families=1)

        receipt = result.runs[0].receipt
        self.assertEqual(receipt.status, "failed")
        self.assertEqual(receipt.failure_reason, "output_limit_exceeded")
        stream = result.runs[0].attempt_streams[0]
        self.assertTrue(stream.stdout_truncated)
        self.assertEqual(len(stream.stdout), 1_048_576)
        self.assertTrue(receipt.stdout_truncated)
        self.assertFalse(receipt.stderr_truncated)
        self.assertEqual(receipt.stdout_captured_bytes, 1_048_576)
        self.assertEqual(receipt.stream_limit_bytes, 1_048_576)

    def test_timeout_terminates_children_that_inherit_output_pipes(self) -> None:
        config = {
            "schema": "tvl.semantic-verifier-config.v1",
            "verifiers": [
                self.config_entry(
                    command=[
                        sys.executable,
                        FAKE_VERIFIER.as_posix(),
                        "child-holds-pipe",
                    ],
                    timeout_seconds=0.05,
                )
            ],
            "judge": None,
            "max_judge_requests": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            started = time.monotonic()

            result = load_semantic_dispatcher(
                config_path, cwd=Path.cwd()
            ).dispatch([request()], minimum_families=1)

        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(result.runs[0].receipt.status, "timeout")

    def test_normal_parent_exit_still_terminates_children_holding_pipes(self) -> None:
        config = {
            "schema": "tvl.semantic-verifier-config.v1",
            "verifiers": [
                self.config_entry(
                    command=[
                        sys.executable,
                        FAKE_VERIFIER.as_posix(),
                        "parent-exits-child-holds-pipe",
                    ],
                )
            ],
            "judge": None,
            "max_judge_requests": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            started = time.monotonic()

            result = load_semantic_dispatcher(
                config_path, cwd=Path.cwd()
            ).dispatch([request()], minimum_families=1)

        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(result.runs[0].receipt.status, "failed")
        self.assertEqual(result.runs[0].receipt.failure_reason, "invalid_json")

    def test_escaped_child_pipe_is_a_bounded_receipted_failure(self) -> None:
        config = {
            "schema": "tvl.semantic-verifier-config.v1",
            "verifiers": [
                self.config_entry(
                    command=[
                        sys.executable,
                        FAKE_VERIFIER.as_posix(),
                        "escaped-child-holds-pipe",
                    ],
                )
            ],
            "judge": None,
            "max_judge_requests": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            started = time.monotonic()

            result = load_semantic_dispatcher(
                config_path, cwd=Path.cwd()
            ).dispatch([request()], minimum_families=1)

        elapsed = time.monotonic() - started
        receipt = result.runs[0].receipt
        self.assertLess(elapsed, 1)
        self.assertEqual(receipt.status, "failed")
        self.assertEqual(receipt.failure_reason, "stream_drain_timeout")
        self.assertTrue(receipt.stdout_truncated)
        self.assertTrue(receipt.stderr_truncated)
        self.assertEqual(len(result.runs[0].attempt_streams), 1)

    def test_instruction_hash_matches_the_exact_bytes_sent_to_the_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            instruction = root / "instruction.md"
            instruction.write_bytes(b"first\r\nsecond\r\n")
            config = {
                "schema": "tvl.semantic-verifier-config.v1",
                "verifiers": [
                    {
                        **self.config_entry(
                            command=[
                                sys.executable,
                                FAKE_VERIFIER.as_posix(),
                                "verify-instruction-digest",
                            ]
                        ),
                        "instruction_files": [instruction.name],
                    }
                ],
                "judge": None,
                "max_judge_requests": 2,
            }
            config_path = root / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            result = load_semantic_dispatcher(
                config_path, cwd=Path.cwd()
            ).dispatch([request()], minimum_families=1)

        self.assertEqual(result.runs[0].receipt.status, "succeeded")

    def test_command_runs_in_an_empty_cwd_with_a_minimal_environment(self) -> None:
        config = {
            "schema": "tvl.semantic-verifier-config.v1",
            "verifiers": [
                self.config_entry(
                    command=[
                        sys.executable,
                        FAKE_VERIFIER.as_posix(),
                        "assert-isolated-runtime",
                    ]
                )
            ],
            "judge": None,
            "max_judge_requests": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            result = load_semantic_dispatcher(
                config_path, cwd=Path.cwd()
            ).dispatch([request()], minimum_families=1)

        self.assertEqual(result.runs[0].receipt.status, "succeeded")

    def test_explicit_cli_credential_home_survives_without_replacing_process_home(self) -> None:
        config = {
            "schema": "tvl.semantic-verifier-config.v1",
            "verifiers": [
                self.config_entry(
                    command=[
                        sys.executable,
                        FAKE_VERIFIER.as_posix(),
                        "assert-explicit-cli-home",
                    ]
                )
            ],
            "judge": None,
            "max_judge_requests": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            credential_home = root / "service-account"
            credential_home.mkdir()
            config_path = root / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            with mock.patch.dict(
                os.environ,
                {"TVL_CLI_HOME": credential_home.as_posix()},
            ):
                result = load_semantic_dispatcher(
                    config_path, cwd=Path.cwd()
                ).dispatch([request()], minimum_families=1)

        self.assertEqual(result.runs[0].receipt.status, "succeeded")

    def test_config_rejects_family_aliases_backed_by_one_identity(self) -> None:
        config = {
            "schema": "tvl.semantic-verifier-config.v1",
            "verifiers": [
                self.config_entry(family="alias-a"),
                self.config_entry(family="alias-b"),
            ],
            "judge": None,
            "max_judge_requests": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            with self.assertRaisesRegex(ContractError, "identities must be unique"):
                load_semantic_dispatcher(config_path, cwd=Path.cwd())

    def test_config_rejects_judge_backed_by_a_verifier_identity(self) -> None:
        config = {
            "schema": "tvl.semantic-verifier-config.v1",
            "verifiers": [self.config_entry()],
            "judge": self.config_entry(
                family="fixture-judge",
                provider="fixture-command",
                model="fixture-model-a",
            ),
            "max_judge_requests": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            with self.assertRaisesRegex(ContractError, "judge identity must be fresh"):
                load_semantic_dispatcher(config_path, cwd=Path.cwd())

    def test_config_rejects_shell_commands(self) -> None:
        config = {
            "schema": "tvl.semantic-verifier-config.v1",
            "verifiers": [self.config_entry(command=["/bin/sh", "-c", "true"])],
            "judge": None,
            "max_judge_requests": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            with self.assertRaisesRegex(ContractError, "shell executables are forbidden"):
                load_semantic_dispatcher(config_path, cwd=Path.cwd())

    def test_config_rejects_instruction_paths_outside_its_directory(self) -> None:
        config = {
            "schema": "tvl.semantic-verifier-config.v1",
            "verifiers": [
                {
                    **self.config_entry(),
                    "instruction_files": ["../outside.md"],
                }
            ],
            "judge": None,
            "max_judge_requests": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config" / "semantic.json"
            config_path.parent.mkdir()
            config_path.write_text(json.dumps(config), encoding="utf-8")

            with self.assertRaisesRegex(ContractError, "remain inside the config directory"):
                load_semantic_dispatcher(config_path, cwd=Path.cwd())

    def test_two_independent_families_can_escalate_to_a_fresh_judge(self) -> None:
        config = {
            "schema": "tvl.semantic-verifier-config.v1",
            "verifiers": [
                self.config_entry(),
                self.config_entry(
                    family="fixture-family-b",
                    provider="fixture-command-b",
                    model="fixture-model-b",
                    command=[
                        sys.executable,
                        FAKE_VERIFIER.as_posix(),
                        "does-not-entail",
                    ],
                ),
            ],
            "judge": self.config_entry(
                family="fixture-judge",
                provider="fixture-judge-command",
                model="fixture-judge-model",
                command=[
                    sys.executable,
                    FAKE_VERIFIER.as_posix(),
                    "require-judge",
                ],
            ),
            "max_judge_requests": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "semantic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            result = load_semantic_dispatcher(
                config_path, cwd=Path.cwd()
            ).dispatch([request()], minimum_families=2)

        aggregate = result.aggregates["evidence-cli"]
        self.assertEqual(aggregate.verdict, "ENTAILS")
        self.assertEqual(aggregate.judge_family, "fixture-judge")
        self.assertEqual(
            aggregate.accepted_families,
            ("fixture-family-a", "fixture-family-b"),
        )
        self.assertTrue(aggregate.policy_satisfied)
        self.assertEqual(result.totals["judge_attempts"], 1)
        self.assertEqual(len(result.runs), 3)


if __name__ == "__main__":
    unittest.main()
