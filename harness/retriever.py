"""Deterministic source capture used to verify search-model citations.

Search output is treated as an untrusted list of candidates. This retriever captures the
cited URL independently, blocks obvious SSRF targets, stores raw bytes, and checks that
the proposed quote is present in the captured representation.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import ipaddress
import re
import socket
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .model import ContractError, sha256_bytes, utc_now

ALLOWED_MEDIA_TYPES = {
    "text/html",
    "text/plain",
    "application/json",
    "application/ld+json",
    "application/xml",
    "text/xml",
    "application/pdf",
}


class RetrievalError(RuntimeError):
    """Raised when a candidate source cannot produce a valid receipt."""


class _TextExtractor(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "svg", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[no-untyped-def]
        if tag.lower() in self.SKIP_TAGS:
            self._skip_depth += 1
        elif not self._skip_depth and tag.lower() in {"p", "div", "li", "br", "tr", "h1", "h2", "h3"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif not self._skip_depth and tag.lower() in {"p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return normalize_text(" ".join(self.parts))


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def extract_text(raw: bytes, media_type: str, charset: str | None = None) -> str | None:
    if media_type == "application/pdf":
        return None
    encoding = charset or "utf-8"
    try:
        decoded = raw.decode(encoding, errors="replace")
    except LookupError:
        decoded = raw.decode("utf-8", errors="replace")
    if media_type == "text/html":
        parser = _TextExtractor()
        parser.feed(decoded)
        parser.close()
        return parser.text()
    return normalize_text(decoded)


def locate_quote(quote: str, normalized_source_text: str | None) -> tuple[int, int] | None:
    if normalized_source_text is None:
        return None
    needle = normalize_text(quote)
    start = normalized_source_text.find(needle)
    if start < 0:
        return None
    return start, start + len(needle)


def quote_present(quote: str, normalized_source_text: str | None) -> bool:
    return locate_quote(quote, normalized_source_text) is not None


def _is_public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_url(
    url: str,
    *,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
    https_only: bool = True,
) -> str:
    parsed = urlsplit(url)
    allowed_schemes = {"https"} if https_only else {"http", "https"}
    if parsed.scheme not in allowed_schemes:
        raise RetrievalError(f"URL scheme is not allowed: {parsed.scheme or '<missing>'}")
    if not parsed.hostname:
        raise RetrievalError("URL hostname is missing")
    if parsed.username or parsed.password:
        raise RetrievalError("URL userinfo is forbidden")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise RetrievalError("local hostnames are forbidden")
    try:
        addresses = {entry[4][0] for entry in resolver(hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
    except (socket.gaierror, OSError) as exc:
        raise RetrievalError(f"hostname could not be resolved: {hostname}") from exc
    if not addresses:
        raise RetrievalError(f"hostname resolved to no addresses: {hostname}")
    invalid = sorted(address for address in addresses if not _is_public_ip(address))
    if invalid:
        raise RetrievalError(f"hostname resolves to a non-public address: {invalid[0]}")
    return url


class _ValidatingRedirectHandler(HTTPRedirectHandler):
    def __init__(self, *, https_only: bool) -> None:
        super().__init__()
        self.https_only = https_only
        self.redirects = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        self.redirects += 1
        if self.redirects > 5:
            raise RetrievalError("too many redirects")
        absolute = urljoin(req.full_url, newurl)
        validate_public_url(absolute, https_only=self.https_only)
        return super().redirect_request(req, fp, code, msg, headers, absolute)


@dataclass(frozen=True)
class FetchedSource:
    requested_uri: str
    final_uri: str
    media_type: str
    charset: str | None
    raw: bytes
    normalized_text: str | None
    retrieved_at: str
    status_code: int

    @property
    def content_sha256(self) -> str:
        return sha256_bytes(self.raw)


class SafeHttpRetriever:
    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        max_bytes: int = 2_000_000,
        https_only: bool = True,
        user_agent: str = "truth-verify-loop/0.2 (+evidence-receipt)",
        allow_environment_proxy: bool = False,
    ) -> None:
        if timeout_seconds <= 0:
            raise ContractError("timeout_seconds must be positive")
        if max_bytes <= 0:
            raise ContractError("max_bytes must be positive")
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.https_only = https_only
        self.user_agent = user_agent
        self.allow_environment_proxy = allow_environment_proxy

    def fetch(self, uri: str) -> FetchedSource:
        validate_public_url(uri, https_only=self.https_only)
        redirect_handler = _ValidatingRedirectHandler(https_only=self.https_only)
        proxy_handler = ProxyHandler() if self.allow_environment_proxy else ProxyHandler({})
        opener = build_opener(proxy_handler, redirect_handler)
        request = Request(
            uri,
            headers={
                "User-Agent": self.user_agent,
                "Accept": ", ".join(sorted(ALLOWED_MEDIA_TYPES)),
            },
            method="GET",
        )
        try:
            with opener.open(request, timeout=self.timeout_seconds) as response:
                final_uri = response.geturl()
                validate_public_url(final_uri, https_only=self.https_only)
                status = int(getattr(response, "status", 200))
                content_type = response.headers.get_content_type().lower()
                charset = response.headers.get_content_charset()
                if content_type not in ALLOWED_MEDIA_TYPES:
                    raise RetrievalError(f"unsupported media type: {content_type}")
                raw = response.read(self.max_bytes + 1)
                if len(raw) > self.max_bytes:
                    raise RetrievalError(f"source exceeds max_bytes={self.max_bytes}")
        except RetrievalError:
            raise
        except HTTPError as exc:
            raise RetrievalError(f"HTTP error {exc.code} for {uri}") from exc
        except URLError as exc:
            raise RetrievalError(f"network error for {uri}: {exc.reason}") from exc
        return FetchedSource(
            requested_uri=uri,
            final_uri=final_uri,
            media_type=content_type,
            charset=charset,
            raw=raw,
            normalized_text=extract_text(raw, content_type, charset),
            retrieved_at=utc_now().isoformat().replace("+00:00", "Z"),
            status_code=status,
        )
