from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from harness.closure import close_claim
from harness.documents import DocumentSnapshot, chunk_document
from harness.lake import EvidenceLake, LakeError
from harness.model import Claim, ContractError, Evidence, sha256_text
from harness.policy import SourcePolicy

NOW = datetime(2026, 8, 9, 10, 0, tzinfo=timezone.utc)


def make_claim():
    return Claim.from_dict({
        "claim_id": "c-lake",
        "statement": "The SDK uses MAX_RETRIES.",
        "risk": "low",
        "temporality": "static",
        "freshness_sla_seconds": 86400,
    })


class LakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "lake"
        self.lake = EvidenceLake(self.root)
        self.root = self.lake.root
        self.lake.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def _evidence(self, source_hash: str, receipt_hash: str) -> Evidence:
        quote = "The SDK uses MAX_RETRIES."
        return Evidence.from_dict({
            "evidence_id": "ev-lake",
            "claim_id": "c-lake",
            "source_uri": "https://docs.example.invalid/sdk",
            "source_class": "official_doc",
            "relationship": "supports",
            "quote": quote,
            "retrieved_at": NOW.isoformat(),
            "content_sha256": source_hash,
            "quote_sha256": sha256_text(quote),
            "capture_scope": "full_source",
            "provider_receipt_sha256": receipt_hash,
            "citation": {"quote_verified": True, "semantic_verifier_families": ["fixture"]},
        })

    def _populate_full_lake(self):
        raw = b"# Limits\n\nThe SDK uses MAX_RETRIES."
        source = self.lake.store_blob(
            raw,
            source_uri="https://docs.example.invalid/sdk",
            media_type="text/plain",
            capture_scope="full_source",
            retrieved_at=NOW,
        )
        receipt = self.lake.store_blob(
            b'{"provider":"fixture"}',
            source_uri="urn:tvl:receipt:fixture",
            media_type="application/json",
            capture_scope="provider_receipt",
            retrieved_at=NOW,
        )
        claim = make_claim()
        item = self._evidence(source["content_sha256"], receipt["content_sha256"])
        self.lake.upsert_claim(claim)
        self.lake.upsert_evidence(item)
        closure = close_claim(claim, [item], policy=SourcePolicy(), now=NOW)
        self.lake.record_closure(closure)
        snapshot = DocumentSnapshot.from_capture(
            source_uri="https://docs.example.invalid/sdk",
            source_type="official_doc",
            authority_class="official_doc",
            media_type="text/plain",
            content_sha256=source["content_sha256"],
            retrieved_at=NOW,
            capture_scope="full_source",
            scope={"product": "SDK", "version": "4.2"},
        )
        chunks = chunk_document(snapshot, raw.decode())
        self.lake.upsert_document(snapshot, chunks)
        return claim, item, closure, snapshot, chunks

    def test_canonical_records_manifest_and_hot_search(self):
        self._populate_full_lake()
        self.lake.write_manifest()
        self.assertEqual(self.lake.verify_integrity(), [])
        self.assertEqual(
            self.lake.search_records("MAX_RETRIES")[0]["closure"]["state"],
            "SUPPORTED",
        )

    def test_evidence_cannot_be_indexed_without_both_blobs(self):
        with self.assertRaises(ContractError):
            self.lake.upsert_evidence(self._evidence("a" * 64, "b" * 64))

    def test_tampered_ledger_is_detected_and_cannot_be_extended(self):
        self.lake.upsert_claim(make_claim())
        path = self.lake.ledger_path("silver", "claims")
        text = path.read_text(encoding="utf-8").replace("MAX_RETRIES", "MIN_RETRIES")
        path.write_text(text, encoding="utf-8")
        self.assertTrue(self.lake.verify_ledger("silver", "claims"))
        with self.assertRaises(LakeError):
            self.lake.upsert_claim(make_claim())

    def test_document_revision_replaces_current_chunks_and_records_relation(self):
        raw = b"# Limits\n\nThe SDK uses MAX_RETRIES."
        first_blob = self.lake.store_blob(
            raw,
            source_uri="https://docs.example.invalid/sdk",
            media_type="text/plain",
            capture_scope="full_source",
            retrieved_at=NOW,
        )
        first = DocumentSnapshot.from_capture(
            source_uri="https://docs.example.invalid/sdk",
            source_type="official_doc",
            authority_class="official_doc",
            media_type="text/plain",
            content_sha256=first_blob["content_sha256"],
            retrieved_at=NOW,
            capture_scope="full_source",
            scope={"product": "SDK", "version": "4.2"},
        )
        self.lake.upsert_document(first, chunk_document(first, raw.decode()))

        revised_raw = b"# Limits\n\nThe SDK now uses MAX_ATTEMPTS."
        revised_blob = self.lake.store_blob(
            revised_raw,
            source_uri="https://docs.example.invalid/sdk",
            media_type="text/plain",
            capture_scope="full_source",
            retrieved_at=NOW + timedelta(minutes=1),
        )
        revised = DocumentSnapshot.from_capture(
            source_uri="https://docs.example.invalid/sdk",
            source_type="official_doc",
            authority_class="official_doc",
            media_type="text/plain",
            content_sha256=revised_blob["content_sha256"],
            retrieved_at=NOW + timedelta(minutes=1),
            capture_scope="full_source",
            scope={"product": "SDK", "version": "4.2"},
        )
        result = self.lake.upsert_document(
            revised, chunk_document(revised, revised_raw.decode())
        )

        current = self.lake.current_document_for_uri("https://docs.example.invalid/sdk")
        self.assertEqual(current["snapshot_id"], revised.snapshot_id)
        self.assertEqual(current["supersedes_snapshot_id"], first.snapshot_id)
        self.assertIsNotNone(result["revision_event_hash"])
        revision = self.lake.read_ledger("silver", "revisions")[-1]["payload"]
        self.assertEqual(revision["relation"], "REVISES_OR_SUPERSEDES")
        self.assertEqual(revision["previous_snapshot_id"], first.snapshot_id)
        self.assertEqual(self.lake.search_documents("MAX_RETRIES"), [])
        self.assertEqual(
            self.lake.search_documents("MAX_ATTEMPTS")[0]["document"]["snapshot_id"],
            revised.snapshot_id,
        )

    def test_hot_projection_rebuild_replays_without_mutating_ledgers(self):
        _claim, _item, _closure, snapshot, chunks = self._populate_full_lake()
        self.lake.write_manifest()
        canonical_before = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.lake.iter_canonical_files()
        }

        result = self.lake.rebuild_hot()

        canonical_after = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.lake.iter_canonical_files()
        }
        self.assertEqual(canonical_after, canonical_before)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["claims"], 1)
        self.assertEqual(result["evidence"], 1)
        self.assertEqual(result["closures"], 1)
        self.assertEqual(result["documents"], 1)
        self.assertEqual(result["chunks"], len(chunks))
        self.assertEqual(
            self.lake.search_records("MAX_RETRIES")[0]["closure"]["state"],
            "SUPPORTED",
        )
        self.assertEqual(
            self.lake.search_documents("MAX_RETRIES")[0]["document"]["snapshot_id"],
            snapshot.snapshot_id,
        )


if __name__ == "__main__":
    unittest.main()
