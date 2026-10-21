"""GDELT collector: query building, window splitting, records, day collection, backfill."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from tradingagents.forecast.archive import gdelt
from tradingagents.forecast.archive.http import RateLimiter
from tradingagents.forecast.archive.seed import SeedIssuer
from tradingagents.forecast.archive.status import ensure_archive_start, read_day_status
from tradingagents.forecast.archive.store import ArchiveStore, read_json

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
DAY = date(2026, 10, 19)

ALPHA = SeedIssuer(isin="DE0007164600", name="Alpha SE", country="DE", aliases=("Alpha SE",))
BETA = SeedIssuer(isin="FR0000120271", name="Beta SA", country="FR", aliases=("Beta SA",))
GAMMA = SeedIssuer(isin="", name="Gamma plc", country="UK", aliases=("Gamma plc",))


class FakeResponse:
    def __init__(self, status_code=200, text="", content_type="application/json"):
        self.status_code = status_code
        self.text = text
        self.content = text.encode()
        self.headers = {"Content-Type": content_type}

    def json(self):
        return json.loads(self.text)


def _articles(n, *, title="Synthetic headline", prefix="a", seendate="20261019T101500Z"):
    return [
        {
            "url": f"https://news.example/{prefix}{i}",
            "title": f"{title} {i}",
            "seendate": seendate,
            "domain": "news.example",
            "language": "English",
            "sourcecountry": "Germany",
        }
        for i in range(n)
    ]


def _json(articles):
    return FakeResponse(text=json.dumps({"articles": articles}) if articles else "{}")


class FakeGet:
    """Maps each call to a response via ``handler(params)``; records params."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def __call__(self, url, params=None, timeout=None):
        self.calls.append(dict(params or {}))
        return self.handler(params or {})


def _limiter():
    return RateLimiter(0)


def _no_sleep(_seconds):
    return None


# --- build_query ----------------------------------------------------------------------


def test_build_query_variants():
    assert gdelt.build_query(SeedIssuer("", "SAP SE", "DE", aliases=("SAP SE",))) == '"SAP SE"'
    multi = SeedIssuer("", "A", "DE", aliases=("A", "B"))
    assert gdelt.build_query(multi) == '("A" OR "B")'
    neg = SeedIssuer("", "Shell plc", "UK", aliases=("Shell plc",), negative_terms=("x",))
    assert gdelt.build_query(neg) == '"Shell plc" -"x"'
    langs = SeedIssuer("", "A", "DE", aliases=("A",), gdelt_langs=("german", "english"))
    assert gdelt.build_query(langs) == '"A" (sourcelang:german OR sourcelang:english)'


# --- fetch_window ---------------------------------------------------------------------

START = datetime(2026, 10, 19, tzinfo=UTC)
END = datetime(2026, 10, 19, 23, 59, 59, tzinfo=UTC)


def test_fetch_window_empty_dict_is_zero():
    get = FakeGet(lambda p: FakeResponse(text="{}"))
    result = gdelt.fetch_window("q", START, END, get=get, limiter=_limiter())
    assert result.articles == [] and result.rejected == 0 and result.failed == 0


def test_fetch_window_html_is_rejected():
    get = FakeGet(lambda p: FakeResponse(text="Invalid query", content_type="text/html"))
    result = gdelt.fetch_window("q", START, END, get=get, limiter=_limiter())
    assert result.rejected == 1 and result.articles == []


def test_fetch_window_invalid_json_is_rejected():
    get = FakeGet(lambda p: FakeResponse(text="{not json"))
    result = gdelt.fetch_window("q", START, END, get=get, limiter=_limiter())
    assert result.rejected == 1 and result.failed == 0


def test_fetch_window_splits_full_page():
    responses = iter([_json(_articles(250)), _json(_articles(3)), _json(_articles(2, prefix="b"))])
    get = FakeGet(lambda p: next(responses))
    result = gdelt.fetch_window("q", START, END, get=get, limiter=_limiter())
    assert result.calls == 3 and len(result.articles) == 5 and result.truncated == 0
    assert get.calls[1]["startdatetime"] == "20261019000000"
    assert get.calls[2]["enddatetime"] == "20261019235959"


def test_fetch_window_one_hour_full_page_is_truncated():
    get = FakeGet(lambda p: _json(_articles(250)))
    end = START + timedelta(hours=1)
    result = gdelt.fetch_window("q", START, end, get=get, limiter=_limiter())
    assert result.calls == 1 and result.truncated == 1 and len(result.articles) == 250


def test_fetch_window_fetch_error_is_failed():
    get = FakeGet(lambda p: FakeResponse(status_code=404))
    result = gdelt.fetch_window("q", START, END, get=get, limiter=_limiter())
    assert result.failed == 1


def test_fetch_canary_single_call_without_split():
    get = FakeGet(lambda p: _json(_articles(10)))
    result = gdelt.fetch_canary(START, END, get=get, limiter=_limiter())
    assert len(get.calls) == 1 and get.calls[0]["maxrecords"] == "10"
    assert len(result.articles) == 10


# --- articles_to_records --------------------------------------------------------------


def test_articles_to_records_fields_and_matching():
    arts = [
        {"url": "https://n.example/1", "title": "Alpha SE beats", "seendate": "20261019T231500Z"},
        {"url": "https://n.example/2", "title": "Unrelated", "seendate": "20261019T231500Z"},
    ]
    recs = gdelt.articles_to_records(arts, ALPHA, run_id="r", backfilled=False, now=NOW)
    assert recs[0].published_at == "2026-10-19T23:15:00Z"
    assert recs[0].published_at_kind == "crawl" and recs[0].day == "2026-10-19"
    assert recs[0].issuer_isin == "DE0007164600"
    assert recs[0].match_confidence == "title_alias"
    assert recs[0].dedupe_key == "https://n.example/1|DE0007164600"
    assert recs[1].issuer_isin is None and recs[1].issuer_query == "DE0007164600"
    assert recs[1].match_confidence == "query_only"
    gamma = gdelt.articles_to_records(arts[:1], GAMMA, run_id="r", backfilled=False, now=NOW)
    assert gamma[0].dedupe_key == "https://n.example/1|name:gamma plc"


def test_same_url_for_two_issuers_gives_two_records(tmp_path):
    art = [
        {
            "url": "https://n.example/x",
            "title": "Alpha SE and Beta SA merge",
            "seendate": "20261019T101500Z",
        }
    ]
    with ArchiveStore(tmp_path) as store:
        a = gdelt.articles_to_records(art, ALPHA, run_id="r", backfilled=False, now=NOW)
        b = gdelt.articles_to_records(art, BETA, run_id="r", backfilled=False, now=NOW)
        assert store.append(a).new == 1
        assert store.append(b).new == 1
        assert store.append(a).new == 0
        rows = list(store.iter_day("gdelt", "2026-10-19"))
    assert len(rows) == 2 and rows[0]["story_key"] == rows[1]["story_key"]


# --- collect_day ----------------------------------------------------------------------


def _handler(canary_hits=5, rejected_for=None):
    def handle(params):
        if params["query"] == gdelt.CANARY_QUERY:
            return _json(_articles(canary_hits, prefix="canary"))
        if rejected_for and rejected_for in params["query"]:
            return FakeResponse(text="bad query", content_type="text/html")
        name = params["query"].strip('"').split('"')[0]
        return _json(_articles(2, title=name, prefix=name.replace(" ", "")))

    return handle


def _collect(tmp_path, get, issuers=(ALPHA, BETA, GAMMA), **kw):
    with ArchiveStore(tmp_path) as store:
        return gdelt.collect_day(
            DAY,
            list(issuers),
            get=get,
            limiter=_limiter(),
            store=store,
            base=tmp_path,
            run_id="run-1",
            now=lambda: NOW,
            sleep=_no_sleep,
            **kw,
        )


def test_collect_day_ok_and_idempotent(tmp_path):
    progress = []
    st = _collect(tmp_path, FakeGet(_handler()), on_progress=lambda: progress.append(1))
    assert st.status == "ok" and st.records_new == 6 and st.queries == 3
    assert len(progress) == 3
    with ArchiveStore(tmp_path) as store:
        urls = [r["url"] for r in store.iter_day("gdelt", "2026-10-19")]
    assert not any("canary" in u for u in urls)
    again = _collect(tmp_path, FakeGet(_handler()))
    assert again.records_new == 0 and again.records_duplicate == 6
    assert read_day_status(tmp_path, "gdelt", DAY).status == "ok"


def test_collect_day_without_canary_hits_is_partial(tmp_path):
    assert _collect(tmp_path, FakeGet(_handler(canary_hits=0))).status == "partial"


def test_collect_day_one_rejected_of_three_is_partial(tmp_path):
    st = _collect(tmp_path, FakeGet(_handler(rejected_for="Beta SA")))
    assert st.status == "partial" and st.rejected == 1


def test_collect_day_deadline_stops_before_next_issuer(tmp_path):
    ticks = iter([0, 10, 99, 99])
    st = _collect(tmp_path, FakeGet(_handler()), deadline=50, clock=lambda: next(ticks))
    assert st.status == "partial" and "max_runtime" in st.errors and st.queries == 2
    assert read_day_status(tmp_path, "gdelt", DAY).attempts == 0


# --- backfill -------------------------------------------------------------------------


def _bf(tmp_path, get, today, issuers=(ALPHA,), **kw):
    with ArchiveStore(tmp_path) as store:
        return gdelt.backfill(
            list(issuers),
            today=today,
            store=store,
            base=tmp_path,
            get=get,
            limiter=_limiter(),
            run_id="bf",
            now=lambda: NOW,
            sleep=_no_sleep,
            **kw,
        )


def _bf_handler(params):
    start = params["startdatetime"]
    return _json(_articles(1, prefix=start, seendate=start[:8] + "T000000Z"))


def test_backfill_requires_archive_start(tmp_path):
    with pytest.raises(ValueError):
        _bf(tmp_path, FakeGet(_bf_handler), date(2026, 10, 20))


def test_backfill_windows_end_before_archive_start(tmp_path):
    today = date(2026, 10, 20)
    ensure_archive_start(tmp_path, today - timedelta(days=60))
    get = FakeGet(_bf_handler)
    summary = _bf(tmp_path, get, today)
    cp = read_json(tmp_path / "checkpoints" / "backfill_gdelt.json")
    assert cp["anchor"] == (today - timedelta(days=89)).isoformat()
    limit = (today - timedelta(days=60)).strftime("%Y%m%d") + "000000"
    assert all(c["enddatetime"] < limit for c in get.calls)
    starts = [c["startdatetime"] for c in get.calls]
    assert starts == sorted(starts) and summary["done"] == summary["total"] == 5
    with ArchiveStore(tmp_path) as store:
        first = (today - timedelta(days=89)).isoformat()
        rows = list(store.iter_day("gdelt", first))
    assert rows and all(r["backfilled"] for r in rows)
    assert not (tmp_path / "status").exists()


def test_backfill_resumes_on_fixed_anchor_and_clips(tmp_path):
    today = date(2026, 10, 20)
    ensure_archive_start(tmp_path, today - timedelta(days=60))
    first = _bf(tmp_path, FakeGet(_bf_handler), today, issuers=(ALPHA, BETA), max_calls=1)
    assert first["stopped"] == "max_calls" and first["done"] == 1
    keys_before = set(read_json(tmp_path / "checkpoints" / "backfill_gdelt.json")["windows"])
    get = FakeGet(_bf_handler)
    second = _bf(tmp_path, get, today + timedelta(days=1), issuers=(ALPHA, BETA), max_calls=1)
    cp = read_json(tmp_path / "checkpoints" / "backfill_gdelt.json")
    assert cp["anchor"] == (today - timedelta(days=89)).isoformat()
    assert keys_before <= set(cp["windows"])
    clipped = (today + timedelta(days=1) - timedelta(days=89)).strftime("%Y%m%d") + "000000"
    assert get.calls[0]["startdatetime"] == clipped
    assert '"Beta SA"' in get.calls[0]["query"]
    assert second["done"] == 2


def test_backfill_marks_window_out_of_horizon_expired(tmp_path):
    today = date(2026, 10, 20)
    ensure_archive_start(tmp_path, today - timedelta(days=80))
    _bf(tmp_path, FakeGet(_bf_handler), today, issuers=(ALPHA, BETA), max_calls=1, window_days=1)
    get = FakeGet(_bf_handler)
    second = _bf(
        tmp_path, get, today + timedelta(days=1), issuers=(ALPHA, BETA), max_calls=1, window_days=1
    )
    anchor = (today - timedelta(days=89)).isoformat()
    cp = read_json(tmp_path / "checkpoints" / "backfill_gdelt.json")
    assert cp["windows"][f"FR0000120271|{anchor}"] == "expired"
    assert second["expired"] == 1
