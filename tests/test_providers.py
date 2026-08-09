import json
import unittest

from harness.model import Claim, ContractError
from harness.providers import (
    AgyProvider,
    build_search_prompt,
    collect_usage,
    extract_search_envelope,
    parse_provider_output,
)


class ProviderTests(unittest.TestCase):
    def test_stream_parser_and_usage_include_cache_reads(self):
        raw = b'{"type":"usage","input_tokens":7,"cache_read_tokens":11}\n'
        events = tuple(parse_provider_output(raw, "stream-json"))
        self.assertEqual(collect_usage(events)["cache_read_tokens"], 11)

    def test_final_nested_search_envelope_is_extracted(self):
        envelope = {
            "schema": "tvl.search-result.v1",
            "query": "q",
            "candidates": [{
                "source_uri": "https://docs.example.invalid/a",
                "relationship": "supports",
                "quote": "exact",
            }],
        }
        events = ({"message": "```json\n" + json.dumps(envelope) + "\n```"},)
        parsed = extract_search_envelope(events)
        self.assertEqual(parsed.candidates[0].quote, "exact")

    def test_unsafe_permission_flags_are_rejected(self):
        for flag in (
            "--dangerously-skip-permissions",
            "--dangerously-skip-permissions=true",
            "--yolo=true",
        ):
            with self.subTest(flag=flag), self.assertRaises(ContractError):
                AgyProvider(extra_args=(flag,))

    def test_command_is_an_argument_vector_with_redactable_prompt(self):
        provider = AgyProvider(model="fast", effort="low")
        command = provider._command("claim text")
        self.assertIsInstance(command, list)
        self.assertEqual(command[:3], ["agy", "--print", "claim text"])
        self.assertNotIn("sh", command)

    def test_search_prompt_is_one_machine_contract(self):
        claim = Claim.from_dict({
            "claim_id": "c-provider",
            "statement": "A current claim.",
            "risk": "medium",
            "temporality": "dynamic",
            "freshness_sla_seconds": 3600,
        })
        value = json.loads(build_search_prompt(claim))
        self.assertEqual(value["required_output"]["schema"], "tvl.search-result.v1")
        self.assertIn("untrusted", " ".join(value["rules"]))


if __name__ == "__main__":
    unittest.main()
