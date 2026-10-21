"""AMF regulated information via DILA Opendata (Licence Ouverte 2.0).

The deliveries ``amf-gz_DDMMYYYY_HHMM.tar.gz`` hold XML metadata plus content files. Raw
tarballs are kept locally only (directors' dealings contain personal data). The XML schema
is assumption A5 of the research: the tag candidate lists below are module constants so a
later run can adapt them.
"""

from __future__ import annotations

import io
import logging
import os
import re
import tarfile
import time as _time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from tradingagents.forecast.archive.http import FetchError, RateLimiter, get_with_retry
from tradingagents.forecast.archive.models import ArchiveRecord
from tradingagents.forecast.archive.status import DayStatus, write_day_status
from tradingagents.forecast.archive.store import atomic_write_json, read_json

log = logging.getLogger(__name__)

AMF_LISTING_URL = "https://echanges.dila.gouv.fr/OPENDATA/AMF/"

MAX_TARBALL_BYTES = 200 * 2**20
MAX_MEMBERS = 5000
MAX_MEMBER_BYTES = 50 * 2**20
MAX_TOTAL_BYTES = 500 * 2**20
MAX_FILE_ATTEMPTS = 3
STALE_BUSINESS_DAYS = 5

TITLE_TAGS = ("titre", "title", "libelle", "intitule", "objet")
DATE_TAGS = (
    "datepublication",
    "datediffusion",
    "datedepot",
    "datemiseenligne",
    "dateinformation",
    "date",
)
ISSUER_TAGS = ("societe", "emetteur", "raisonsociale", "nomsociete", "denomination", "issuer")
ISIN_TAGS = ("isin", "codeisin")
DOCTYPE_TAGS = ("typedocument", "typeinformation", "natureinformation", "nature", "type")
DOCID_TAGS = ("iddocument", "identifiant", "numdocument", "numero", "reference", "id")

_LISTING_RE = re.compile(
    r"""href\s*=\s*["']([^"']*?(amf-gz_(\d{8})_(\d{4})\.tar\.gz))["']""", re.IGNORECASE
)
_URL_RE = re.compile(r"https?://\S+")
_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%Y%m%d",
)
_PARIS = ZoneInfo("Europe/Paris")


@dataclass(frozen=True)
class AmfFile:
    name: str
    url: str
    delivered_at: datetime  # aware UTC


def _now_value(now) -> datetime:
    value = now() if callable(now) else now
    return value or datetime.now(UTC)


def _iso_z(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def paris_to_utc(naive: datetime) -> datetime:
    """Paris wall time to UTC with fold=0 (an ambiguous autumn hour takes summer time)."""
    return naive.replace(tzinfo=_PARIS, fold=0).astimezone(UTC)


def _listing_date(digits: str) -> date | None:
    for fmt in ("%d%m%Y", "%Y%m%d"):
        try:
            return datetime.strptime(digits, fmt).date()
        except ValueError:
            continue
    return None


def parse_listing(html: str, base_url: str = AMF_LISTING_URL) -> list[AmfFile]:
    files: dict[str, AmfFile] = {}
    for match in _LISTING_RE.finditer(html or ""):
        href, name, digits, hhmm = match.groups()
        day = _listing_date(digits)
        if day is None:
            continue
        try:
            clock = datetime.strptime(hhmm, "%H%M").time()
        except ValueError:
            continue
        delivered = paris_to_utc(datetime.combine(day, clock))
        files.setdefault(name, AmfFile(name, urljoin(base_url, href), delivered))
    return sorted(files.values(), key=lambda f: (f.delivered_at, f.name))


def _norm(tag: str) -> str:
    local = tag.rsplit("}", 1)[-1]
    return re.sub(r"[^a-z0-9]", "", local.casefold())


def _pick(fields: dict, candidates) -> str | None:
    normalized = {_norm(k): v for k, v in fields.items()}
    for candidate in candidates:
        if normalized.get(candidate):
            return normalized[candidate]
    return None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1]
    if re.search(r"[+-]\d{2}:\d{2}$", text):
        try:
            return datetime.fromisoformat(text).astimezone(UTC)
        except ValueError:
            return None
    text = text.split(".")[0]
    for fmt in _DATE_FORMATS:
        try:
            return paris_to_utc(datetime.strptime(text, fmt))
        except ValueError:
            continue
    return None


def _xml_record(text, *, member, tarname, delivered_at, run_id, backfilled, seen_ts):
    root = ET.fromstring(text)
    fields: dict[str, str] = {}
    for element in root.iter():
        if len(element) == 0 and (element.text or "").strip():
            fields.setdefault(element.tag.rsplit("}", 1)[-1], element.text.strip())
    doc_id = _pick(fields, DOCID_TAGS)
    url = next((m.group(0) for v in fields.values() for m in [_URL_RE.search(v)] if m), None)
    pseudo = f"dila-amf:{tarname}/{member}"
    raw_date = _pick(fields, DATE_TAGS)
    source_ts = _parse_date(raw_date)
    isin = _pick(fields, ISIN_TAGS)
    return ArchiveRecord(
        source="amf",
        url=url or pseudo,
        title=_pick(fields, TITLE_TAGS) or member,
        day=delivered_at.astimezone(UTC).date().isoformat(),
        published_at=_iso_z(source_ts or delivered_at),
        published_at_kind="source" if source_ts else "delivery",
        published_at_raw=raw_date,
        first_seen_ts=seen_ts,
        issuer_query=_pick(fields, ISSUER_TAGS),
        issuer_isin=isin.upper() if isin else None,
        country="FR",
        domain="echanges.dila.gouv.fr",
        backfilled=backfilled,
        run_id=run_id,
        dedupe_key=f"amf:{doc_id}" if doc_id else pseudo,
        extra={
            "fields": fields,
            "tarball": tarname,
            "member": member,
            "doc_type": _pick(fields, DOCTYPE_TAGS),
            "delivered_at": _iso_z(delivered_at),
        },
    )


def parse_tarball(
    data: bytes, *, tarname, delivered_at, run_id, backfilled, now
) -> tuple[list[ArchiveRecord], list[str]]:
    """Records from the XML members of one delivery, plus a list of errors.

    Members are read into memory via extractfile only - nothing is ever extracted to disk
    (no path traversal) - within member, count and total size limits. Each XML member
    must decode as strict UTF-8 and may not carry a DOCTYPE/ENTITY (billion laughs).
    """
    if len(data) > MAX_TARBALL_BYTES:
        return [], [f"{tarname}: tarball of {len(data)} bytes exceeds {MAX_TARBALL_BYTES}"]
    seen_ts = _iso_z(_now_value(now))
    records: list[ArchiveRecord] = []
    errors: list[str] = []
    content_members: list[str] = []
    try:
        # Closed by the ``with archive:`` block below; opening is separated so a broken
        # header is reported as such.
        archive = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")  # noqa: SIM115
    except (tarfile.TarError, OSError, EOFError) as exc:
        return [], [f"{tarname}: cannot open tarball: {exc}"]
    count = 0
    total = 0
    with archive:
        try:
            for member in archive:
                count += 1
                if count > MAX_MEMBERS:
                    return [], [f"{tarname}: more than {MAX_MEMBERS} members, aborted"]
                if not member.isreg():
                    continue
                total += member.size
                if total > MAX_TOTAL_BYTES:
                    return [], [f"{tarname}: members exceed {MAX_TOTAL_BYTES} bytes, aborted"]
                if not member.name.lower().endswith(".xml"):
                    content_members.append(member.name)
                    continue
                if member.size > MAX_MEMBER_BYTES:
                    errors.append(f"{member.name}: member too large ({member.size} bytes)")
                    continue
                handle = archive.extractfile(member)
                raw = handle.read(MAX_MEMBER_BYTES + 1) if handle else b""
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError as exc:
                    errors.append(f"{member.name}: not utf-8 ({exc.reason})")
                    continue
                if "<!DOCTYPE" in text or "<!ENTITY" in text:
                    errors.append(f"{member.name}: DOCTYPE/ENTITY not allowed, skipped")
                    continue
                try:
                    records.append(
                        _xml_record(
                            text.lstrip("﻿"),
                            member=member.name,
                            tarname=tarname,
                            delivered_at=delivered_at,
                            run_id=run_id,
                            backfilled=backfilled,
                            seen_ts=seen_ts,
                        )
                    )
                except ET.ParseError as exc:
                    errors.append(f"{member.name}: XML parse error: {exc}")
        except (tarfile.TarError, OSError, EOFError) as exc:
            errors.append(f"{tarname}: broken tarball: {exc}")
    if content_members:
        records = [
            replace(r, extra={**r.extra, "content_members": content_members}) for r in records
        ]
    return records, errors


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _checkpoint_path(base) -> Path:
    return Path(base) / "checkpoints" / "amf_seen.json"


def _business_days_before(today: date, n: int) -> date:
    day = today
    found = 0
    while found < n:
        day -= timedelta(days=1)
        if day.weekday() < 5:
            found += 1
    return day


def collect(
    days,
    *,
    get,
    store,
    base,
    run_id,
    now,
    today,
    backfilled=False,
    on_progress=None,
    limiter=None,
    sleep=_time.sleep,
) -> dict[date, DayStatus]:
    """Load the listing once, then every unseen delivery of the requested UTC days."""
    days = sorted(set(days))
    if not days:
        return {}
    limiter = limiter or RateLimiter(1.0)
    statuses = {d: DayStatus(source="amf", day=d.isoformat(), run_id=run_id) for d in days}

    def finish(default_status=None):
        stamp = _now_value(now)
        for st in statuses.values():
            if default_status:
                st.status = default_status
            st.finished_at = _iso_z(stamp)
            write_day_status(base, st, now=stamp)
        return statuses

    try:
        listing = get_with_retry(get, AMF_LISTING_URL, limiter=limiter, sleep=sleep)
    except FetchError as exc:
        for st in statuses.values():
            st.errors.append(f"listing: {exc}")
        return finish("missing")
    files = parse_listing(listing.text or "")
    if not files:
        for st in statuses.values():
            st.errors.append("listing_no_matches")
        return finish("missing")

    stale = max(f.delivered_at.date() for f in files) < _business_days_before(
        today, STALE_BUSINESS_DAYS
    )
    cp_path = _checkpoint_path(base)
    cp = read_json(cp_path) or {}
    seen = set(cp.get("seen", []))
    failed: dict[str, int] = dict(cp.get("failed", {}))
    gave_up = set(cp.get("gave_up", []))

    def save():
        atomic_write_json(
            cp_path,
            {
                "seen": sorted(seen),
                "failed": failed,
                "gave_up": sorted(gave_up),
                "updated_at": _iso_z(_now_value(now)),
            },
        )

    for day in days:
        st = statuses[day]
        problems = False
        if stale:
            st.errors.append("listing_stale")
            problems = True
        day_files = [f for f in files if f.delivered_at.date() == day]
        st.files = len(day_files)
        for amf_file in day_files:
            if amf_file.name in seen:
                continue
            if amf_file.name in gave_up:
                st.errors.append(f"gave_up: {amf_file.name}")
                problems = True
                continue
            errors: list[str] = []
            try:
                response = get_with_retry(get, amf_file.url, limiter=limiter, sleep=sleep)
                data = response.content or b""
                declared = int(response.headers.get("Content-Length") or 0)
                if max(declared, len(data)) > MAX_TARBALL_BYTES:
                    errors.append(f"{amf_file.name}: download exceeds {MAX_TARBALL_BYTES} bytes")
                    data = b""
            except FetchError as exc:
                errors.append(f"{amf_file.name}: download failed: {exc}")
                data = b""
            if data:
                _atomic_write_bytes(Path(base) / "raw" / "amf" / amf_file.name, data)
                records, parse_errors = parse_tarball(
                    data,
                    tarname=amf_file.name,
                    delivered_at=amf_file.delivered_at,
                    run_id=run_id,
                    backfilled=backfilled,
                    now=now,
                )
                errors.extend(parse_errors)
                appended = store.append(records)
                st.records_new += appended.new
                st.records_duplicate += appended.duplicate
            if errors:
                problems = True
                failed[amf_file.name] = failed.get(amf_file.name, 0) + 1
                st.errors.extend(errors[:5])
                if failed[amf_file.name] >= MAX_FILE_ATTEMPTS:
                    gave_up.add(amf_file.name)
                    st.errors.append(f"gave_up: {amf_file.name}")
            else:
                seen.add(amf_file.name)
                failed.pop(amf_file.name, None)
            save()
            if on_progress is not None:
                on_progress()
        st.status = "partial" if problems else "ok"
    save()
    return finish()
