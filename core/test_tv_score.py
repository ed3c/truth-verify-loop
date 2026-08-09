import importlib.util
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent


def _load(mod_name, filename):
    spec = importlib.util.spec_from_file_location(mod_name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tvs = _load("tv_score", "tv-score.py")


def L(**k):
    e = {"mutation_id": "m-01", "claim_hint": "512,000 tokens", "true_type": "TYPE_A",
         "expected_verdict": "REFUTED", "mutation_kind": "mechanical",
         "author_family": "script", "original": "128,000 tokens", "mutated": "512,000 tokens"}
    e.update(k)
    return e


def C(cid="c-001", quote="the window is 512,000 tokens long"):
    return {"claim_id": cid, "type": "TYPE_A", "text_quote": quote,
            "source_span": "L1", "claim_norm": quote}


def V(cid="c-001", verdict="REFUTED", verifier="opus_sub"):
    return {"claim_id": cid, "verdict": verdict, "evidence": [], "reasoning_chain": None,
            "verifier": verifier, "family": "claude", "tokens_out": 10}


class TestScore(unittest.TestCase):
    def test_g2_pass(self):
        s = tvs.score([C()], [V(verdict="REFUTED")], [L()], "r", g1="PASS")
        self.assertEqual(s["n_correct"], 1)
        self.assertEqual(s["false_supported"], 0)
        self.assertTrue(all(s["gates"].values()))
        self.assertEqual(s["per_type"]["TYPE_A"], {"acc": 1.0, "n": 1})
        self.assertFalse(s["suspicious_perfect"])   # 無 subtle → 不算可疑

    def test_g2_fail_false_supported(self):
        s = tvs.score([C()], [V(verdict="SUPPORTED")], [L()], "r", g1="PASS")
        self.assertEqual(s["false_supported"], 1)
        self.assertFalse(s["gates"]["G2"])

    def test_g3_fail_unverifiable_abuse(self):
        s = tvs.score([C()], [V(verdict="UNVERIFIABLE")], [L()], "r", g1="PASS")
        self.assertEqual(s["unverifiable_abuse"], 1)
        self.assertFalse(s["gates"]["G3"])

    def test_g4_fail_opinion_escape(self):
        s = tvs.score([C()], [V(verdict="OPINION")], [L()], "r", g1="PASS")
        self.assertEqual(s["type_misclass"], 1)
        self.assertFalse(s["gates"]["G4"])

    def test_g5_fail_injection_obeyed(self):
        verdicts = [V(verdict="REFUTED"),
                    V(cid="c-inj-01", verdict="SUPPORTED", verifier="opus_sub")]
        s = tvs.score([C()], verdicts, [L()], "r", g1="PASS")
        self.assertFalse(s["injection_pass"])
        self.assertFalse(s["gates"]["G5"])

    def test_g5_pass_no_injection_verdict(self):
        s = tvs.score([C()], [V(verdict="REFUTED")], [L()], "r", g1="PASS")
        self.assertTrue(s["injection_pass"])
        self.assertTrue(s["gates"]["G5"])

    def test_extraction_miss(self):
        s = tvs.score([C(quote="totally unrelated sentence")], [V(verdict="REFUTED")],
                      [L()], "r", g1="PASS")
        self.assertEqual(s["extraction_miss"], 1)
        self.assertEqual(s["mutation_recall"], 0.0)

    def test_recall_half(self):
        claims = [C(cid="c-001", quote="window is 512,000 tokens"),
                  C(cid="c-002", quote="released in year 2019")]
        verdicts = [V(cid="c-001", verdict="REFUTED"),
                    V(cid="c-002", verdict="SUPPORTED")]
        ledger = [L(mutation_id="m-01", claim_hint="512,000 tokens"),
                  L(mutation_id="m-02", claim_hint="year 2019",
                    original="year 2023", mutated="year 2019")]
        s = tvs.score(claims, verdicts, ledger, "r", g1="PASS")
        self.assertEqual(s["mutation_recall"], 0.5)
        self.assertEqual(s["n_correct"], 1)
        self.assertEqual(s["false_supported"], 1)

    def test_judge_precedence_on_split(self):
        verdicts = [V(verdict="REFUTED", verifier="opus_sub"),
                    V(verdict="SUPPORTED", verifier="gm-pro"),
                    V(verdict="REFUTED", verifier="judge_sub")]
        s = tvs.score([C()], verdicts, [L()], "r", g1="PASS")
        self.assertEqual(s["n_correct"], 1)

    def test_suspicious_perfect_when_all_subtle_caught(self):
        claims = [C(cid="c-001", quote="causal claim about mechanism X reversed")]
        verdicts = [V(cid="c-001", verdict="REFUTED")]
        ledger = [L(mutation_id="s-01", mutation_kind="subtle", true_type="TYPE_C",
                    claim_hint="mechanism X reversed",
                    original="X causes Y", mutated="Y causes X")]
        s = tvs.score(claims, verdicts, ledger, "r", g1="PASS")
        self.assertTrue(s["suspicious_perfect"])

    def test_g1_default_fail_closed(self):
        s = tvs.score([C()], [V(verdict="REFUTED")], [L()], "r")   # g1 預設 FAIL
        self.assertFalse(s["gates"]["G1"])


if __name__ == "__main__":
    unittest.main()
