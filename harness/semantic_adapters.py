"""Versioned configuration and subprocess adapters for semantic review."""

from __future__ import annotations

import json
import math
import os
import selectors
import signal
from dataclasses import dataclass, replace
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any, Sequence

from .model import ContractError, canonical_json, sha256_bytes, sha256_text, utc_now
from .semantic import (
    SemanticDispatcher,
    SemanticJudgeRequest,
    SemanticReview,
    SemanticReviewRequest,
    VerifierAttemptStream,
    VerifierIdentity,
    VerifierReceipt,
    VerifierRun,
    validate_verifier_usage,
)


CONFIG_SCHEMA = "tvl.semantic-verifier-config.v1"
COMMAND_SCHEMA = "tvl.semantic-review-command.v1"
RESULT_SCHEMA = "tvl.semantic-review-batch.v1"
MAX_STREAM_BYTES = 1_048_576
SEMANTIC_ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "TERM")
ENTRY_FIELDS = {
    "family",
    "provider",
    "provider_version",
    "model",
    "command",
    "timeout_seconds",
    "max_attempts",
    "instruction_files",
}
FORBIDDEN_SHELL_EXECUTABLES = {
    "bash",
    "dash",
    "fish",
    "ksh",
    "powershell",
    "pwsh",
    "sh",
    "zsh",
}


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object")
    return value


def _text(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ContractError(f"{label} must be a non-empty canonical string")
    return value


def _usage_is_valid(usage: dict[str, Any]) -> bool:
    try:
        validate_verifier_usage(usage)
    except ContractError:
        return False
    return True


@dataclass(frozen=True)
class _ProcessCapture:
    exit_code: int
    stdout: bytes
    stderr: bytes
    timed_out: bool
    stdout_truncated: bool
    stderr_truncated: bool
    stream_drain_timed_out: bool


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        try:
            process.kill()
        except ProcessLookupError:
            pass


def _run_bounded_command(
    command: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str],
    payload: bytes,
    timeout_seconds: float,
) -> _ProcessCapture:
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    stdout = bytearray()
    stderr = bytearray()
    assert process.stdout is not None
    assert process.stderr is not None
    assert process.stdin is not None
    streams = {
        process.stdout: (stdout, "stdout"),
        process.stderr: (stderr, "stderr"),
    }
    stdout_truncated = False
    stderr_truncated = False
    stream_drain_timed_out = False
    input_offset = 0
    selector = selectors.DefaultSelector()
    for stream in streams:
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ)
    os.set_blocking(process.stdin.fileno(), False)
    selector.register(process.stdin, selectors.EVENT_WRITE)
    timed_out = False
    process_deadline = time.monotonic() + timeout_seconds
    drain_deadline: float | None = None
    try:
        while streams:
            now = time.monotonic()
            return_code = process.poll()
            if return_code is None and now >= process_deadline:
                timed_out = True
                _kill_process_group(process)
                process.wait()
                return_code = process.returncode
            if return_code is not None and drain_deadline is None:
                _kill_process_group(process)
                drain_deadline = now + 0.5
                try:
                    selector.get_key(process.stdin)
                except (KeyError, ValueError):
                    pass
                else:
                    selector.unregister(process.stdin)
                    process.stdin.close()
            if drain_deadline is not None and now >= drain_deadline:
                stream_drain_timed_out = True
                stdout_truncated = process.stdout in streams
                stderr_truncated = process.stderr in streams
                break

            deadlines = [process_deadline]
            if drain_deadline is not None:
                deadlines.append(drain_deadline)
            wait_seconds = max(0.0, min(deadlines) - now)
            for key, mask in selector.select(timeout=min(wait_seconds, 0.05)):
                stream = key.fileobj
                if stream is process.stdin and mask & selectors.EVENT_WRITE:
                    try:
                        written = os.write(
                            process.stdin.fileno(), payload[input_offset:]
                        )
                        input_offset += written
                    except BrokenPipeError:
                        input_offset = len(payload)
                    if input_offset >= len(payload):
                        selector.unregister(process.stdin)
                        process.stdin.close()
                    continue
                if mask & selectors.EVENT_READ:
                    try:
                        chunk = os.read(stream.fileno(), 65_536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(stream)
                        stream.close()
                        streams.pop(stream)
                        continue
                    target, channel = streams[stream]
                    remaining = MAX_STREAM_BYTES - len(target)
                    if remaining > 0:
                        target.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        if channel == "stdout":
                            stdout_truncated = True
                        else:
                            stderr_truncated = True
                        _kill_process_group(process)
        if process.poll() is None:
            _kill_process_group(process)
            process.wait()
    finally:
        for registered in list(selector.get_map().values()):
            try:
                selector.unregister(registered.fileobj)
            except (KeyError, ValueError):
                pass
            registered.fileobj.close()
        selector.close()
    return _ProcessCapture(
        exit_code=process.returncode,
        stdout=bytes(stdout),
        stderr=bytes(stderr),
        timed_out=timed_out,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        stream_drain_timed_out=stream_drain_timed_out,
    )


class CommandSemanticAdapter:
    """Run one configured semantic family through a JSON stdin/stdout protocol."""

    def __init__(
        self,
        *,
        family: str,
        provider: str,
        provider_version: str | None,
        model: str | None,
        command: Sequence[str],
        timeout_seconds: float,
        max_attempts: int,
        instruction_files: Sequence[Path],
        cwd: Path,
        env_allowlist: Sequence[str] = SEMANTIC_ENV_ALLOWLIST,
    ) -> None:
        self.family = family
        self.identity = VerifierIdentity(provider=provider, model=model)
        self.provider_version = provider_version
        normalized_command = list(command)
        executable = Path(normalized_command[0])
        if not executable.is_absolute() and executable.parent != Path("."):
            normalized_command[0] = (cwd / executable).resolve().as_posix()
        self.command = tuple(normalized_command)
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.instruction_files = tuple(instruction_files)
        self.env_allowlist = tuple(dict.fromkeys(env_allowlist))

    def run(
        self,
        requests: tuple[SemanticReviewRequest | SemanticJudgeRequest, ...],
    ) -> VerifierRun:
        role = "judge" if isinstance(requests[0], SemanticJudgeRequest) else "verifier"
        instructions = []
        for path in self.instruction_files:
            raw_instruction = path.read_bytes()
            try:
                instruction_text = raw_instruction.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ContractError(
                    f"semantic instruction file is not UTF-8: {path.name}"
                ) from exc
            instructions.append(
                {
                    "name": path.name,
                    "sha256": sha256_bytes(raw_instruction),
                    "content": instruction_text,
                }
            )
        payload = {
            "schema": COMMAND_SCHEMA,
            "role": role,
            "instructions": instructions,
            "requests": [request.to_dict() for request in requests],
        }
        prompt = canonical_json(payload)
        prompt_bytes = prompt.encode("utf-8")
        base_env = {
            key: os.environ[key]
            for key in self.env_allowlist
            if key in os.environ
        }
        if "PATH" not in base_env:
            base_env["PATH"] = os.defpath
        attempts: list[VerifierReceipt] = []
        attempt_streams: list[VerifierAttemptStream] = []
        command_sha256 = sha256_text(canonical_json(list(self.command)))
        for attempt_index in range(self.max_attempts):
            started = utc_now()
            timed_out = False
            stdout_truncated = False
            stderr_truncated = False
            stream_drain_timed_out = False
            exit_code: int | None
            stdout: bytes
            stderr: bytes
            failure_reason: str | None = None
            try:
                with tempfile.TemporaryDirectory(
                    prefix="tvl-semantic-command-"
                ) as temporary_directory:
                    isolated_cwd = Path(temporary_directory)
                    env = dict(base_env)
                    env["HOME"] = isolated_cwd.as_posix()
                    env["TMPDIR"] = isolated_cwd.as_posix()
                    completed = _run_bounded_command(
                        self.command,
                        cwd=isolated_cwd,
                        env=env,
                        payload=prompt_bytes,
                        timeout_seconds=self.timeout_seconds,
                    )
                exit_code = completed.exit_code
                stdout = completed.stdout
                stderr = completed.stderr
                timed_out = completed.timed_out
                stdout_truncated = completed.stdout_truncated
                stderr_truncated = completed.stderr_truncated
                stream_drain_timed_out = completed.stream_drain_timed_out
                if timed_out:
                    failure_reason = f"timeout_after_{self.timeout_seconds:g}s"
                elif stream_drain_timed_out:
                    failure_reason = "stream_drain_timeout"
                elif stdout_truncated or stderr_truncated:
                    failure_reason = "output_limit_exceeded"
            except OSError as exc:
                exit_code = None
                stdout = b""
                stderr = str(exc).encode("utf-8", errors="replace")
                failure_reason = "start_error"
            ended = utc_now()

            status = "timeout" if timed_out else "failed"
            raw_reviews: list[Any] = []
            usage: dict[str, Any] = {}
            if (
                exit_code not in (None, 0)
                and not timed_out
                and not (stdout_truncated or stderr_truncated)
            ):
                failure_reason = f"exit_code_{exit_code}"
            output: dict[str, Any] | None = None
            if not (stdout_truncated or stderr_truncated):
                try:
                    output = _parse_output(stdout)
                except ContractError as exc:
                    if exit_code == 0 and not timed_out:
                        failure_reason = str(exc)
            if output is not None and _usage_is_valid(output["usage"]):
                usage = output["usage"]
            elif output is not None and exit_code == 0 and not timed_out:
                failure_reason = "invalid_usage_contract"
            if (
                output is not None
                and exit_code == 0
                and not timed_out
                and _usage_is_valid(output["usage"])
            ):
                raw_reviews = output["reviews"]
                status = "succeeded"
            receipt = VerifierReceipt(
                family=self.family,
                provider=self.identity.provider,
                provider_version=self.provider_version,
                model=self.identity.model,
                prompt_sha256=sha256_text(prompt),
                instruction_hashes=tuple(item["sha256"] for item in instructions),
                output_sha256=sha256_bytes(stdout),
                started_at=started,
                ended_at=ended,
                status=status,
                exit_code=exit_code,
                timed_out=timed_out,
                usage=dict(usage),
                attempt_kind="primary" if attempt_index == 0 else "recovery",
                command_sha256=command_sha256,
                stderr_sha256=sha256_bytes(stderr),
                failure_reason=failure_reason,
                stdout_captured_bytes=len(stdout),
                stderr_captured_bytes=len(stderr),
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
                stream_limit_bytes=MAX_STREAM_BYTES,
            )
            if status == "succeeded":
                try:
                    reviews = tuple(
                        _review_from_output(
                            item,
                            family=self.family,
                            receipt=receipt,
                        )
                        for item in raw_reviews
                    )
                except ContractError:
                    receipt = replace(
                        receipt,
                        status="failed",
                        failure_reason="invalid_review_contract",
                    )
                else:
                    expected = [
                        (request.request_id, request.evidence_id)
                        for request in requests
                    ]
                    actual = [
                        (review.request_id, review.evidence_id)
                        for review in reviews
                    ]
                    if len(actual) != len(expected) or set(actual) != set(expected):
                        receipt = replace(
                            receipt,
                            status="failed",
                            failure_reason="invalid_review_batch",
                        )
                    else:
                        attempt_streams.append(
                            VerifierAttemptStream(
                                receipt_sha256=receipt.digest,
                                stdout=stdout,
                                stderr=stderr,
                                stdout_truncated=stdout_truncated,
                                stderr_truncated=stderr_truncated,
                            )
                        )
                        return VerifierRun(
                            receipt=receipt,
                            reviews=reviews,
                            prior_attempt_receipts=tuple(attempts),
                            attempt_streams=tuple(attempt_streams),
                        )
            attempt_streams.append(
                VerifierAttemptStream(
                    receipt_sha256=receipt.digest,
                    stdout=stdout,
                    stderr=stderr,
                    stdout_truncated=stdout_truncated,
                    stderr_truncated=stderr_truncated,
                )
            )
            attempts.append(receipt)

        terminal = attempts[-1]
        return VerifierRun(
            receipt=terminal,
            reviews=(),
            prior_attempt_receipts=tuple(attempts[:-1]),
            attempt_streams=tuple(attempt_streams),
        )


def _parse_output(stdout: bytes) -> dict[str, Any]:
    try:
        output = json.loads(stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("invalid_json") from exc
    output = _object(output, "semantic verifier output")
    if set(output) != {"schema", "reviews", "usage"}:
        raise ContractError("invalid_output_fields")
    if output.get("schema") != RESULT_SCHEMA:
        raise ContractError("invalid_output_schema")
    raw_reviews = output.get("reviews")
    usage = output.get("usage")
    if not isinstance(raw_reviews, list):
        raise ContractError("invalid_reviews_type")
    if not isinstance(usage, dict):
        raise ContractError("invalid_usage_type")
    return {"reviews": raw_reviews, "usage": usage}


def _review_from_output(
    value: Any,
    *,
    family: str,
    receipt: VerifierReceipt,
) -> SemanticReview:
    item = _object(value, "semantic review")
    expected = {"request_id", "evidence_id", "verdict", "rationale_summary"}
    if set(item) != expected:
        raise ContractError("semantic review fields do not match v1 contract")
    return SemanticReview(
        request_id=_text(item.get("request_id"), "semantic review request_id") or "",
        evidence_id=_text(item.get("evidence_id"), "semantic review evidence_id") or "",
        family=family,
        verdict=_text(item.get("verdict"), "semantic review verdict") or "",
        rationale_summary=(
            _text(item.get("rationale_summary"), "semantic review rationale_summary")
            or ""
        ),
        verifier_receipt_sha256=receipt.digest,
    )


def _adapter_from_config(
    value: Any,
    *,
    config_dir: Path,
    cwd: Path,
) -> CommandSemanticAdapter:
    item = _object(value, "semantic adapter config")
    if set(item) != ENTRY_FIELDS:
        raise ContractError("semantic adapter config fields do not match v1 contract")
    command = item.get("command")
    if not isinstance(command, list) or not command or not all(
        isinstance(argument, str) and argument and "\x00" not in argument
        for argument in command
    ):
        raise ContractError("semantic adapter command must be a non-empty argv array")
    if Path(command[0]).name.casefold() in FORBIDDEN_SHELL_EXECUTABLES:
        raise ContractError("semantic adapter shell executables are forbidden")
    timeout = item.get("timeout_seconds")
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ContractError("semantic adapter timeout_seconds must be finite and positive")
    attempts = item.get("max_attempts")
    if (
        not isinstance(attempts, int)
        or isinstance(attempts, bool)
        or not 1 <= attempts <= 3
    ):
        raise ContractError("semantic adapter max_attempts must be between 1 and 3")
    instruction_values = item.get("instruction_files")
    if not isinstance(instruction_values, list) or not all(
        isinstance(path, str) and path and not Path(path).is_absolute()
        for path in instruction_values
    ):
        raise ContractError("instruction_files must contain relative paths")
    resolved_config_dir = config_dir.resolve()
    instruction_files = tuple(
        (resolved_config_dir / path).resolve() for path in instruction_values
    )
    if any(
        not instruction_file.is_relative_to(resolved_config_dir)
        for instruction_file in instruction_files
    ):
        raise ContractError("instruction_files must remain inside the config directory")
    return CommandSemanticAdapter(
        family=_text(item.get("family"), "semantic adapter family") or "",
        provider=_text(item.get("provider"), "semantic adapter provider") or "",
        provider_version=_text(
            item.get("provider_version"),
            "semantic adapter provider_version",
            nullable=True,
        ),
        model=_text(item.get("model"), "semantic adapter model", nullable=True),
        command=command,
        timeout_seconds=float(timeout),
        max_attempts=attempts,
        instruction_files=instruction_files,
        cwd=cwd,
    )


def load_semantic_dispatcher(
    path: Path | str,
    *,
    cwd: Path | str,
) -> SemanticDispatcher:
    """Load one versioned config into the provider-neutral dispatcher."""

    config_path = Path(path).resolve()
    value = json.loads(config_path.read_text(encoding="utf-8"))
    config = _object(value, "semantic verifier config")
    if set(config) != {"schema", "verifiers", "judge", "max_judge_requests"}:
        raise ContractError("semantic verifier config fields do not match v1 contract")
    if config.get("schema") != CONFIG_SCHEMA:
        raise ContractError(f"semantic verifier config schema must be {CONFIG_SCHEMA}")
    raw_verifiers = config.get("verifiers")
    if not isinstance(raw_verifiers, list) or not raw_verifiers:
        raise ContractError("semantic verifier config requires verifiers[]")
    workdir = Path(cwd).resolve()
    if not workdir.is_dir():
        raise ContractError(f"semantic adapter cwd is not a directory: {workdir}")
    verifiers = tuple(
        _adapter_from_config(item, config_dir=config_path.parent, cwd=workdir)
        for item in raw_verifiers
    )
    verifier_identities = [verifier.identity for verifier in verifiers]
    if len(verifier_identities) != len(set(verifier_identities)):
        raise ContractError("semantic verifier identities must be unique")
    raw_judge = config.get("judge")
    judge = (
        None
        if raw_judge is None
        else _adapter_from_config(
            raw_judge,
            config_dir=config_path.parent,
            cwd=workdir,
        )
    )
    if judge is not None and judge.identity in set(verifier_identities):
        raise ContractError("semantic judge identity must be fresh")
    max_judge_requests = config.get("max_judge_requests")
    if (
        not isinstance(max_judge_requests, int)
        or isinstance(max_judge_requests, bool)
        or max_judge_requests <= 0
    ):
        raise ContractError("max_judge_requests must be a positive integer")
    return SemanticDispatcher(
        verifiers,
        judge=judge,
        max_judge_requests=max_judge_requests,
    )
