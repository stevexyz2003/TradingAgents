"""AMF/DILA collector: listing, Paris time, tarball parsing with limits, collection."""

from __future__ import annotations

import io
import tarfile
from datetime import UTC, date, datetime

import pytest

from tradingagents.forecast.archive import amf
from tradingagents.forecast.archive.http import RateLimiter
from tradingagents.forecast.archive.status import read_day_status
from tradingagents.forecast.archive.store import ArchiveStore, read_json

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 21, 6, 30, tzinfo=UTC)
TODAY = date(2026, 10, 21)
DELIVERED = datetime(2026, 10, 19, 23, 30, tzinfo=UTC)

XML_A = (
    '<?xml version="1.0" encoding="UTF-8"?><info xmlns="urn:x"><id_document>D1</id_document>'
    "<titre>Synthetic notice one</titre><date_publication>2026-10-20T01:00:00</date_publication>"
    "<societe>Synthetic SA</societe><isin>FR0000120271</isin></info>"
)
XML_B = "<info><titre>Synthetic notice two</titre></info>"


def _tar(members) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _parse(data, name="amf-gz_20102026_0130.tar.gz"):
    return amf.parse_tarball(
        data, tarname=name, delivered_at=DELIVERED, run_id="r", backfilled=False, now=NOW
    )


# --- listing and time -----------------------------------------------------------------


def test_parse_listing_ddmmyyyy_with_day_change():
    html = (
        '<a href="../">Parent</a><a href="amf-gz_20102026_0130.tar.gz">x</a>'
        '<a href="readme.txt">r</a><a href="amf-gz_20102026_0130.tar.gz">dup</a>'
    )
    files = amf.parse_listing(html)
    assert len(files) == 1
    assert files[0].delivered_at == datetime(2026, 10, 19, 23, 30, tzinfo=UTC)
    assert files[0].url == amf.AMF_LISTING_URL + "amf-gz_20102026_0130.tar.gz"


def test_parse_listing_yyyymmdd_variant():
    files = amf.parse_listing("<a href='amf-gz_20261020_1400.tar.gz'>x</a>")
    assert files[0].delivered_at == datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def test_paris_to_utc_ambiguous_and_nonexistent():
    assert amf.paris_to_utc(datetime(2026, 10, 25, 2, 30)) == datetime(
        2026, 10, 25, 0, 30, tzinfo=UTC
    )
    # 02:30 does not exist on 2026-03-29; zoneinfo with fold=0 applies the offset in
    # force before the gap (+01:00).
    assert amf.paris_to_utc(datetime(2026, 3, 29, 2, 30)) == datetime(
        2026, 3, 29, 1, 30, tzinfo=UTC
    )


# --- parse_tarball --------------------------------------------------------------------


def test_parse_tarball_two_xml_and_a_pdf():
    data = _tar([("a.xml", XML_A.encode()), ("b.xml", XML_B.encode()), ("a.pdf", b"%PDF-1")])
    records, errors = _parse(data)
    assert errors == []
    assert len(records) == 2
    first, second = records
    assert first.source == "amf" and first.published_at_kind == "source"
    assert first.published_at == "2026-10-19T23:00:00Z"
    assert first.dedupe_key == "amf:D1" and first.issuer_isin == "FR0000120271"
    assert first.day == "2026-10-19"
    assert second.published_at_kind == "delivery"
    assert second.dedupe_key == "dila-amf:amf-gz_20102026_0130.tar.gz/b.xml"
    assert first.extra["content_members"] == ["a.pdf"]


def test_parse_tarball_rejects_entities_latin1_and_broken_xml():
    evil = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaa">]><x>&a;</x>'
    latin = "<info><titre>Soci\xe9t\xe9</titre></info>".encode("latin-1")
    data = _tar(
        [
            ("evil.xml", evil),
            ("latin.xml", latin),
            ("broken.xml", b"<info><titre>"),
            ("ok.xml", XML_B.encode()),
        ]
    )
    records, errors = _parse(data)
    assert len(records) == 1
    joined = " ".join(errors)
    assert "DOCTYPE/ENTITY" in joined and "not utf-8" in joined and "parse error" in joined


def test_parse_tarball_member_limits(monkeypatch):
    monkeypatch.setattr(amf, "MAX_MEMBERS", 2)
    records, errors = _parse(_tar([(f"{i}.xml", XML_B.encode()) for i in range(3)]))
    assert records == [] and "members" in errors[0]


def test_parse_tarball_total_limit(monkeypatch):
    monkeypatch.setattr(amf, "MAX_TOTAL_BYTES", 60)
    records, errors = _parse(_tar([("a.xml", XML_B.encode()), ("b.xml", XML_B.encode())]))
    assert records == [] and "exceed" in errors[0]


def test_parse_tarball_too_large_is_rejected_before_parsing(monkeypatch):
    monkeypatch.setattr(amf, "MAX_TARBALL_BYTES", 10)
    records, errors = _parse(b"x" * 11)
    assert records == [] and "exceeds" in errors[0]


# --- collect --------------------------------------------------------------------------

NAME = "amf-gz_20102026_0130.tar.gz"
DAY = date(2026, 10, 19)


class FakeResponse:
    def __init__(self, status_code=200, text="", content=b""):
        self.status_code = status_code
        self.text = text
        self.content = content or text.encode()
        self.headers = {}


class FakeGet:
    def __init__(self, listing, files):
        self.listing = listing
        self.files = files
        self.calls = []

    def __call__(self, url, params=None, timeout=None):
        self.calls.append(url)
        if url == amf.AMF_LISTING_URL:
            if isinstance(self.listing, int):
                return FakeResponse(status_code=self.listing)
            return FakeResponse(text=self.listing)
        return FakeResponse(content=self.files[url.rsplit("/", 1)[-1]])


def _listing(*names):
    return "".join(f'<a href="{n}">{n}</a>' for n in names)


def _run(base, get, days=(DAY,)):
    with ArchiveStore(base) as store:
        return amf.collect(
            list(days),
            get=get,
            store=store,
            base=base,
            run_id="r",
            now=lambda: NOW,
            today=TODAY,
            limiter=RateLimiter(0),
            sleep=lambda _s: None,
        )


def test_collect_stores_raw_and_marks_seen(tmp_path):
    get = FakeGet(_listing(NAME), {NAME: _tar([("a.xml", XML_A.encode())])})
    result = _run(tmp_path, get)
    assert result[DAY].status == "ok" and result[DAY].files == 1
    assert result[DAY].records_new == 1
    assert (tmp_path / "raw" / "amf" / NAME).exists()
    assert NAME in read_json(tmp_path / "checkpoints" / "amf_seen.json")["seen"]
    get2 = FakeGet(_listing(NAME), {})
    assert _run(tmp_path, get2)[DAY].status == "ok"
    assert get2.calls == [amf.AMF_LISTING_URL]


def test_collect_retries_unparsable_file_then_gives_up(tmp_path):
    bad = _tar([("broken.xml", b"<info>")])
    for attempt in range(1, amf.MAX_FILE_ATTEMPTS + 1):
        get = FakeGet(_listing(NAME), {NAME: bad})
        result = _run(tmp_path, get)
        assert result[DAY].status == "partial"
        assert len(get.calls) == 2, attempt
        cp = read_json(tmp_path / "checkpoints" / "amf_seen.json")
        assert NAME not in cp["seen"] and cp["failed"][NAME] == attempt
    assert NAME in cp["gave_up"]
    get = FakeGet(_listing(NAME), {NAME: bad})
    result = _run(tmp_path, get)
    assert get.calls == [amf.AMF_LISTING_URL]
    assert result[DAY].status == "partial" and f"gave_up: {NAME}" in result[DAY].errors


def test_collect_listing_error_is_missing(tmp_path):
    result = _run(tmp_path, FakeGet(404, {}))
    assert result[DAY].status == "missing" and "listing" in result[DAY].errors[0]
    assert read_day_status(tmp_path, "amf", DAY).status == "missing"


def test_collect_listing_without_matches_is_missing(tmp_path):
    result = _run(tmp_path, FakeGet("<a href='other.zip'>x</a>", {}))
    assert result[DAY].status == "missing" and result[DAY].errors == ["listing_no_matches"]


def test_collect_stale_listing_is_partial(tmp_path):
    old = "amf-gz_01102026_0130.tar.gz"
    result = _run(tmp_path, FakeGet(_listing(old), {}))
    assert result[DAY].status == "partial" and "listing_stale" in result[DAY].errors
