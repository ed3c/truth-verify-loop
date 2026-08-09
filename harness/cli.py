"""Command-line interface for the live verification and memory harness."""

from __future__ import annotations

import argparse
from datetime import timedelta
import json
from pathlib import Path
import sys
from typing import Any, Iterable

from .closure import close_claim
from .documents import DocumentSnapshot, chunk_document
from .lake import EvidenceLake, LakeError
from .model import Claim, ContractError, Evidence, format_timestamp
from .orchestrator import HarnessError, run_live_verification
from .policy import SourcePolicy, decide_live_search
from .providers import AgyProvider, ProviderError
from .retriever import RetrievalError, extract_text, locate_quote


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_claim(path: Path) -> Claim:
    value = _load_json(path)
    if not isinstance(value, dict):
        raise ContractError("claim file must contain one JSON object")
    return Claim.from_dict(value)


def _load_evidence_jsonl(path: Path) -> list[Evidence]:
    items: list[Evidence] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ContractError(f"invalid evidence JSON at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise ContractError(f"evidence at {path}:{line_number} must be an object")
            items.append(Evidence.from_dict(value))
    if not items:
        raise ContractError("evidence fixture must contain at least one record")
    return items


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def command_decide(args: argparse.Namespace) -> int:
    claim = _load_claim(args.claim)
    decision = decide_live_search(
        claim,
        model_knowledge_cutoff=args.model_knowledge_cutoff,
    )
    _print(decision.to_dict())
    return 0


def command_run_fixture(args: argparse.Namespace) -> int:
    claim = _load_claim(args.claim)
    evidence_items = _load_evidence_jsonl(args.evidence)
    policy = SourcePolicy.load(args.policy)
    lake = EvidenceLake(args.lake)
    lake.initialize()

    source_bytes = args.source.read_bytes()
    receipt_bytes = args.receipt.read_bytes()
    source_media_type = args.source_media_type
    source_text = extract_text(source_bytes, source_media_type)
    source_record = lake.store_blob(
        source_bytes,
        source_uri=evidence_items[0].source_uri,
        media_type=source_media_type,
        capture_scope="full_source",
        retrieved_at=evidence_items[0].retrieved_at,
    )
    receipt_record = lake.store_blob(
        receipt_bytes,
        source_uri="urn:tvl:provider-receipt:sealed-fixture",
        media_type="application/json",
        capture_scope="provider_receipt",
        retrieved_at=evidence_items[0].retrieved_at,
    )

    lake.upsert_claim(claim)
    for item in evidence_items:
        if item.content_sha256 != source_record["content_sha256"]:
            raise ContractError(
                f"fixture evidence {item.evidence_id} does not point to the supplied source blob"
            )
        if item.provider_receipt_sha256 != receipt_record["content_sha256"]:
            raise ContractError(
                f"fixture evidence {item.evidence_id} does not point to the supplied receipt blob"
            )
        if locate_quote(item.quote, source_text) is None:
            raise ContractError(
                f"fixture quote for {item.evidence_id} was not found in the supplied source"
            )
        lake.upsert_evidence(item)

    first = evidence_items[0]
    snapshot = DocumentSnapshot.from_capture(
        source_uri=first.source_uri,
        source_type=first.source_class,
        authority_class=first.source_class,
        media_type=source_media_type,
        content_sha256=source_record["content_sha256"],
        retrieved_at=first.retrieved_at,
        capture_scope="full_source",
        title=first.title,
        scope=claim.scope,
        metadata={"fixture": True},
    )
    chunks = chunk_document(snapshot, source_text or "")
    lake.upsert_document(snapshot, chunks)

    as_of = max(item.retrieved_at for item in evidence_items) + timedelta(minutes=1)
    closure = close_claim(claim, evidence_items, policy=policy, now=as_of)
    closure["run"] = {
        "provider": "sealed-fixture",
        "provider_receipt_sha256": receipt_record["content_sha256"],
        "source_sha256": source_record["content_sha256"],
        "deterministic_as_of": format_timestamp(as_of),
    }
    lake.record_closure(closure)
    lake.append_ledger(
        "gold",
        "coverage-ledger",
        {
            "claim_id": claim.claim_id,
            "state": closure["state"],
            "gates": closure["gates"],
            "coverage": closure["coverage"],
            "fixture": True,
        },
    )
    manifest = lake.write_manifest()
    failures = lake.verify_integrity()
    result = {
        "closure": closure,
        "manifest": manifest.as_posix(),
        "integrity_failures": failures,
        "document_id": snapshot.document_id,
        "snapshot_id": snapshot.snapshot_id,
        "chunk_count": len(chunks),
    }
    _print(result)
    return 0 if closure["closed"] and not failures else 2


def command_run_agy(args: argparse.Namespace) -> int:
    claim = _load_claim(args.claim)
    policy = SourcePolicy.load(args.policy)
    lake = EvidenceLake(args.lake)
    provider = AgyProvider(
        binary=args.agy_binary,
        model=args.model,
        effort=args.effort,
        output_format=args.output_format,
        extra_args=tuple(args.agy_arg),
    )
    from .retriever import SafeHttpRetriever

    result = run_live_verification(
        claim,
        lake=lake,
        policy=policy,
        provider=provider,
        retriever=SafeHttpRetriever(
            timeout_seconds=args.fetch_timeout,
            max_bytes=args.max_bytes,
            https_only=policy.https_only,
        ),
        cwd=args.cwd,
        model_knowledge_cutoff=args.model_knowledge_cutoff,
        timeout_seconds=args.provider_timeout,
        instruction_files=tuple(args.instruction_file),
    )
    _print(result)
    return 0 if result["closure"]["closed"] else 2


def command_verify_lake(args: argparse.Namespace) -> int:
    lake = EvidenceLake(args.lake)
    lake.initialize()
    failures = lake.verify_integrity(require_manifest=not args.no_manifest)
    _print({"status": "PASS" if not failures else "FAIL", "failures": failures})
    return 0 if not failures else 2


def command_manifest(args: argparse.Namespace) -> int:
    lake = EvidenceLake(args.lake)
    path = lake.write_manifest()
    failures = lake.verify_manifest()
    _print(
        {
            "manifest": path.as_posix(),
            "status": "PASS" if not failures else "FAIL",
            "failures": failures,
        }
    )
    return 0 if not failures else 2


def command_search_hot(args: argparse.Namespace) -> int:
    lake = EvidenceLake(args.lake)
    lake.initialize()
    _print(lake.search_hot(args.query, limit=args.limit))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="truth-verify-loop",
        description="Live claim verification with immutable evidence receipts and tiered memory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    decide = subparsers.add_parser("decide", help="decide whether a claim requires live retrieval")
    decide.add_argument("--claim", type=Path, required=True)
    decide.add_argument("--model-knowledge-cutoff")
    decide.set_defaults(handler=command_decide)

    fixture = subparsers.add_parser("run-fixture", help="run the deterministic sealed fixture")
    fixture.add_argument("--claim", type=Path, required=True)
    fixture.add_argument("--evidence", type=Path, required=True)
    fixture.add_argument("--policy", type=Path, required=True)
    fixture.add_argument("--source", type=Path, required=True)
    fixture.add_argument("--receipt", type=Path, required=True)
    fixture.add_argument("--source-media-type", default="text/plain")
    fixture.add_argument("--lake", type=Path, required=True)
    fixture.set_defaults(handler=command_run_fixture)

    agy = subparsers.add_parser("run-agy", help="run live search through Antigravity CLI")
    agy.add_argument("--claim", type=Path, required=True)
    agy.add_argument("--policy", type=Path, required=True)
    agy.add_argument("--lake", type=Path, required=True)
    agy.add_argument("--model-knowledge-cutoff")
    agy.add_argument("--agy-binary", default="agy")
    agy.add_argument("--model")
    agy.add_argument("--effort")
    agy.add_argument("--output-format", choices=("json", "stream-json"), default="stream-json")
    agy.add_argument("--agy-arg", action="append", default=[])
    agy.add_argument("--cwd", type=Path, default=Path.cwd())
    agy.add_argument("--instruction-file", type=Path, action="append", default=[])
    agy.add_argument("--provider-timeout", type=float, default=90.0)
    agy.add_argument("--fetch-timeout", type=float, default=20.0)
    agy.add_argument("--max-bytes", type=int, default=2_000_000)
    agy.set_defaults(handler=command_run_agy)

    verify = subparsers.add_parser("verify-lake", help="verify blobs, hash chains, and manifest")
    verify.add_argument("--lake", type=Path, required=True)
    verify.add_argument("--no-manifest", action="store_true")
    verify.set_defaults(handler=command_verify_lake)

    manifest = subparsers.add_parser("manifest", help="write and verify MANIFEST.sha256")
    manifest.add_argument("--lake", type=Path, required=True)
    manifest.set_defaults(handler=command_manifest)

    search = subparsers.add_parser("search-hot", help="query current claim and document projections")
    search.add_argument("--lake", type=Path, required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=10)
    search.set_defaults(handler=command_search_hot)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return int(args.handler(args))
    except (
        ContractError,
        HarnessError,
        LakeError,
        ProviderError,
        RetrievalError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"truth-verify-loop: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
