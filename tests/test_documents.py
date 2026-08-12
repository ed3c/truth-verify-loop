from datetime import datetime, timezone
import unittest

from harness.documents import DocumentSnapshot, canonicalize_uri, chunk_document, chunk_for_span
from harness.model import sha256_text


class DocumentTests(unittest.TestCase):
    def snapshot(self, digest="a" * 64):
        return DocumentSnapshot.from_capture(
            source_uri="https://Docs.Example.Invalid:443/guide#install",
            source_type="official_doc",
            authority_class="official_doc",
            media_type="text/plain",
            content_sha256=digest,
            retrieved_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
            capture_scope="full_source",
            scope={"product": "SDK", "version": "4.2"},
        )

    def test_uri_identity_drops_fragment_and_default_port(self):
        self.assertEqual(canonicalize_uri("https://Docs.Example.Invalid:443/a#b"), "https://docs.example.invalid/a")

    def test_document_id_is_stable_while_snapshot_tracks_content(self):
        first = self.snapshot("a" * 64)
        second = self.snapshot("b" * 64)
        self.assertEqual(first.document_id, second.document_id)
        self.assertNotEqual(first.snapshot_id, second.snapshot_id)

    def test_chunks_preserve_heading_path_and_symbols(self):
        chunks = chunk_document(self.snapshot(), "# Install\n\nUse SDK.Client and --dry-run with MAX_RETRIES.")
        self.assertEqual(chunks[0].structural_path, ("Install",))
        self.assertIn("SDK.Client", chunks[0].symbols)
        self.assertIn("--dry-run", chunks[0].symbols)
        self.assertEqual(chunks[0].text_sha256, sha256_text(chunks[0].text))

    def test_chunk_for_span_returns_the_overlapping_chunk(self):
        chunks = chunk_document(self.snapshot(), "# A\n\nalpha\n\n# B\n\nbeta")
        target = chunk_for_span(chunks, chunks[-1].char_start, chunks[-1].char_end)
        self.assertEqual(target.chunk_id if target else None, chunks[-1].chunk_id)


if __name__ == "__main__":
    unittest.main()
