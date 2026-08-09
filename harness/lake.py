"""Local conformance profile for an Agentic Data Lake.

Canonical evidence lives in immutable content-addressed blobs and append-only ledgers.
SQLite is only a rebuildable hot projection; it is never the source of truth.
"""

from .lake_base import LakeBase, LakeError, ZONE_STREAMS
from .lake_documents import DocumentLakeMixin
from .lake_records import RecordLakeMixin


class EvidenceLake(DocumentLakeMixin, RecordLakeMixin, LakeBase):
    """Cold, warm, and hot memory facade for the verification harness."""


__all__ = ["EvidenceLake", "LakeError", "ZONE_STREAMS"]
