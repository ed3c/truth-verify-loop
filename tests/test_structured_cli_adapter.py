import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts.semantic.structured_cli_adapter import (
    AdapterError,
    _run_command,
    build_claude_command,
    build_codex_command,
    build_prompt,
    child_environment,
    parse_claude_output,
    parse_codex_output,
)


class StructuredCliAdapterTests(unittest.TestCase):
    def test_prompt_treats_batch_as_data_and_forbids_final_truth(self):
        prompt = build_prompt({"schema": "tvl.semantic-review-command.v1"})

        self.assertIn("untrusted data", prompt)
        self.assertIn("Do not decide final truth", prompt)
        self.assertIn('"schema":"tvl.semantic-review-command.v1"', prompt)

    def test_codex_command_is_ephemeral_read_only_and_schema_pinned(self):
        command = build_codex_command(
            model="gpt-test",
            schema_path=Path("/tmp/schema.json"),
            output_path=Path("/tmp/result.json"),
        )

        self.assertEqual(command[:3], ["codex", "-a", "never"])
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertEqual(command[command.index("--model") + 1], "gpt-test")
        self.assertNotIn("--search", command)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)

    def test_claude_command_disables_tools_and_session_persistence(self):
        command = build_claude_command(model="sonnet-test")

        self.assertEqual(command[:2], ["claude", "--print"])
        self.assertEqual(command[command.index("--tools") + 1], "")
        self.assertIn("--no-session-persistence", command)
        self.assertEqual(command[command.index("--model") + 1], "sonnet-test")
        self.assertNotIn("--dangerously-skip-permissions", command)

    def test_credential_home_is_explicit_and_only_expected_environment_survives(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            environment = child_environment(
                {
                    "PATH": "/bin",
                    "LANG": "C.UTF-8",
                    "SSH_AUTH_SOCK": "/private/socket",
                    "ANTHROPIC_API_KEY": "secret",
                },
                credential_home=home,
            )

        self.assertEqual(environment["HOME"], home.as_posix())
        self.assertEqual(environment["CODEX_HOME"], (home / ".codex").as_posix())
        self.assertEqual(
            environment["CLAUDE_CONFIG_DIR"], (home / ".claude").as_posix()
        )
        self.assertNotIn("SSH_AUTH_SOCK", environment)
        self.assertNotIn("ANTHROPIC_API_KEY", environment)

    def test_codex_output_uses_only_last_message_and_records_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            output.write_text(
                json.dumps({"reviews": [{"request_id": "r1"}]}), encoding="utf-8"
            )
            stream = "\n".join(
                [
                    json.dumps({"type": "item.completed", "item": {"text": "ignore"}}),
                    json.dumps(
                        {
                            "type": "turn.completed",
                            "usage": {"input_tokens": 7, "output_tokens": 3},
                        }
                    ),
                ]
            )

            result, usage = parse_codex_output(output, stream)

        self.assertEqual(result["reviews"][0]["request_id"], "r1")
        self.assertEqual(usage, {"input_tokens": 7, "output_tokens": 3})

    def test_claude_output_requires_structured_output_and_keeps_cost(self):
        result, usage = parse_claude_output(
            json.dumps(
                {
                    "structured_output": {"reviews": [{"request_id": "r1"}]},
                    "usage": {"input_tokens": 5, "output_tokens": 2},
                    "total_cost_usd": 0.01,
                }
            )
        )

        self.assertEqual(result["reviews"][0]["request_id"], "r1")
        self.assertEqual(usage["cost_usd"], 0.01)

        with self.assertRaisesRegex(AdapterError, "structured_output"):
            parse_claude_output(json.dumps({"result": "plain text"}))

    def test_child_failure_preserves_both_output_channels(self):
        completed = subprocess.CompletedProcess(
            args=["model-cli"],
            returncode=2,
            stdout="structured error on stdout",
            stderr="diagnostic on stderr",
        )

        with mock.patch("subprocess.run", return_value=completed):
            with self.assertRaises(AdapterError) as raised:
                _run_command(
                    ["model-cli"],
                    prompt="request",
                    environment={"PATH": "/bin"},
                    timeout_seconds=1,
                )

        message = str(raised.exception)
        self.assertIn("structured error on stdout", message)
        self.assertIn("diagnostic on stderr", message)


if __name__ == "__main__":
    unittest.main()
