"""Record model of the news archive: canonical URLs, stable hashes and story keys."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import asdict, dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

COLLECTOR_VERSION = "0.1.0"

_TRACKING_PARAMS = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid", "cmpid"})


def canonical_url(url: str) -> str:
    """Normalize an http(s) URL so the same article dedupes across trackers.

    Scheme and host are lower-cased, the fragment and tracking parameters are dropped and
    the remaining query parameters are sorted. Any other URI (e.g. ``dila-amf:...``) is
    returned unchanged.
    """
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https"):
        return url
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMS
    ]
    query.sort()
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), "")
    )


def record_hash(source: str, key: str) -> str:
    """Stable identity of a record: sha256 of ``source|key``."""
    return hashlib.sha256(f"{source}|{key}".encode()).hexdigest()


def _normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFKC", title or "").casefold()
    text = "".join(" " if unicodedata.category(ch).startswith("P") else ch for ch in text)
    return " ".join(text.split())


def story_key(title: str) -> str:
    """Groups the same story across issuers and outlets; used for clustering, never deletion."""
    return hashlib.sha256(_normalize_title(title).encode()).hexdigest()


@dataclass(frozen=True)
class ArchiveRecord:
    """One archived item. ``day`` (UTC ISO date) decides the JSONL file it lands in."""

    source: str
    url: str
    title: str
    day: str
    published_at: str | None = None
    published_at_kind: str | None = None  # crawl | source | delivery
    published_at_raw: str | None = None
    first_seen_ts: str | None = None
    issuer_query: str | None = None
    issuer_isin: str | None = None
    match_alias: str | None = None
    match_confidence: str | None = None  # title_alias | query_only | None
    language: str | None = None
    country: str | None = None
    domain: str | None = None
    backfilled: bool = False
    run_id: str | None = None
    collector_version: str = COLLECTOR_VERSION
    dedupe_key: str = ""
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.dedupe_key:
            object.__setattr__(self, "dedupe_key", canonical_url(self.url))

    @property
    def record_hash(self) -> str:
        return record_hash(self.source, self.dedupe_key)

    @property
    def story_key(self) -> str:
        return story_key(self.title)

    def to_json(self) -> str:
        data = asdict(self)
        data["record_hash"] = self.record_hash
        data["story_key"] = self.story_key
        return json.dumps(data, sort_keys=True, ensure_ascii=False)
