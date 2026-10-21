"""GDELT DOC 2.0 collector: article metadata only (URL, title, seendate, domain, language).

Daily collection per UTC day (canary + one query per issuer) and a resumable backfill
over the 3-month GDELT window in weekly windows on a fixed anchor.
"""

from __future__ import annotations

import json
import logging
import re
import time as _time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from tradingagents.forecast.archive.http import FetchError, get_with_retry
from tradingagents.forecast.archive.models import ArchiveRecord, canonical_url
from tradingagents.forecast.archive.status import (
    DayStatus,
    archive_start,
    classify_gdelt_day,
    write_day_status,
)
from tradingagents.forecast.archive.store import atomic_write_json, read_json

log = logging.getLogger(__name__)

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
CANARY_QUERY = '"European Central Bank"'
# GDELT asks for one call every 5 s, but at 6 s it answered 429 to almost every call
# on 2026-10-21; 15 s keeps a 62-issuer day near 16 minutes.
MIN_INTERVAL = 15.0
# GDELT rejects quoted phrases this short ("The specified phrase is too short"), e.g. "BASF".
MIN_PHRASE_LEN = 5
MAX_RECORDS = 250
CANARY_RECORDS = 10
MAX_ERRORS = 20
_FMT = "%Y%m%d%H%M%S"


def _now_value(now) -> datetime:
    value = now() if callable(now) else now
    return value or datetime.now(UTC)


def _iso_z(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_query(issuer) -> str:
    # Short aliases still serve title matching (articles_to_records), just not the query.
    aliases = tuple(a for a in issuer.aliases if len(a) >= MIN_PHRASE_LEN) or (issuer.name,)
    quoted = [f'"{alias}"' for alias in aliases]
    query = quoted[0] if len(quoted) == 1 else "(" + " OR ".join(quoted) + ")"
    for term in issuer.negative_terms:
        query += f' -"{term}"'
    langs = tuple(issuer.gdelt_langs)
    if len(langs) == 1:
        query += f" sourcelang:{langs[0]}"
    elif langs:
        query += " (" + " OR ".join(f"sourcelang:{lang}" for lang in langs) + ")"
    return query


@dataclass
class WindowResult:
    articles: list = field(default_factory=list)
    calls: int = 0
    failed: int = 0
    rejected: int = 0
    truncated: int = 0
    errors: list = field(default_factory=list)


def _call(query, start, end, *, get, limiter, maxrecords, sleep, result: WindowResult):
    """One API call; returns the article list or None (failed/rejected are counted)."""
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": str(maxrecords),
        "sort": "DateAsc",
        "startdatetime": start.strftime(_FMT),
        "enddatetime": end.strftime(_FMT),
    }
    result.calls += 1
    try:
        response = get_with_retry(get, GDELT_URL, params=params, limiter=limiter, sleep=sleep)
    except FetchError as exc:
        result.failed += 1
        result.errors.append(str(exc))
        log.warning("GDELT call failed for %s: %s", query, exc)
        return None
    content_type = (response.headers.get("Content-Type") or "").lower()
    text = response.text or ""
    if "json" not in content_type:
        result.rejected += 1
        result.errors.append(f"rejected non-json response: {text[:120].strip()}")
        log.warning("GDELT rejected query %s: %s", query, text[:200])
        return None
    try:
        data = json.loads(text) if text.strip() else {}
    except ValueError:
        result.rejected += 1
        result.errors.append("rejected invalid json")
        log.warning("GDELT returned invalid JSON for %s", query)
        return None
    if not isinstance(data, dict):
        result.rejected += 1
        result.errors.append("rejected json that is not an object")
        return None
    articles = data.get("articles") or []
    return [a for a in articles if isinstance(a, dict)]


def _window(query, start, end, *, get, limiter, min_split, sleep, result):
    articles = _call(
        query,
        start,
        end,
        get=get,
        limiter=limiter,
        maxrecords=MAX_RECORDS,
        sleep=sleep,
        result=result,
    )
    if articles is None:
        return
    if len(articles) >= MAX_RECORDS:
        if end - start > min_split:
            mid = (start + (end - start) / 2).replace(microsecond=0)
            _window(
                query,
                start,
                mid,
                get=get,
                limiter=limiter,
                min_split=min_split,
                sleep=sleep,
                result=result,
            )
            _window(
                query,
                mid + timedelta(seconds=1),
                end,
                get=get,
                limiter=limiter,
                min_split=min_split,
                sleep=sleep,
                result=result,
            )
            return
        result.truncated += 1
    result.articles.extend(articles)


def fetch_window(
    query, start, end, *, get, limiter, min_split=timedelta(hours=1), sleep=_time.sleep
) -> WindowResult:
    """All articles of ``[start, end]``; a full page (250) halves the window recursively.

    A window of at most ``min_split`` that still returns 250 counts as ``truncated``.
    """
    result = WindowResult()
    _window(
        query, start, end, get=get, limiter=limiter, min_split=min_split, sleep=sleep, result=result
    )
    return result


def fetch_canary(start, end, *, get, limiter, sleep=_time.sleep) -> WindowResult:
    """One call with maxrecords=10 and no split; hits prove GDELT delivered that day."""
    result = WindowResult()
    articles = _call(
        CANARY_QUERY,
        start,
        end,
        get=get,
        limiter=limiter,
        maxrecords=CANARY_RECORDS,
        sleep=sleep,
        result=result,
    )
    if articles:
        result.articles.extend(articles)
    return result


def _alias_in_title(alias: str, title: str) -> bool:
    pattern = r"(?<!\w)" + re.escape(alias.casefold()) + r"(?!\w)"
    return re.search(pattern, title.casefold()) is not None


def articles_to_records(
    articles, issuer, *, run_id, backfilled, now, fallback_day: date | None = None
) -> list[ArchiveRecord]:
    seen_ts = _iso_z(_now_value(now))
    records = []
    for article in articles:
        url = article.get("url")
        if not url:
            continue
        title = article.get("title") or ""
        raw = article.get("seendate")
        published_at = None
        day = fallback_day
        if raw:
            try:
                ts = datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
                published_at = _iso_z(ts)
                day = ts.date()
            except ValueError:
                pass
        if day is None:
            continue
        alias = next((a for a in issuer.aliases if _alias_in_title(a, title)), None)
        isin = (issuer.isin or None) if alias else None
        issuer_query = issuer.key
        records.append(
            ArchiveRecord(
                source="gdelt",
                url=url,
                title=title,
                day=day.isoformat(),
                published_at=published_at,
                published_at_kind="crawl",
                published_at_raw=raw,
                first_seen_ts=seen_ts,
                issuer_query=issuer_query,
                issuer_isin=isin,
                match_alias=alias,
                match_confidence="title_alias" if alias else "query_only",
                language=article.get("language"),
                country=article.get("sourcecountry"),
                domain=article.get("domain"),
                backfilled=backfilled,
                run_id=run_id,
                # One article naming two issuers is evidence for both; story_key groups it.
                dedupe_key=f"{canonical_url(url)}|{isin or issuer_query}",
            )
        )
    return records


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1) - timedelta(seconds=1)


def collect_day(
    day,
    issuers,
    *,
    get,
    limiter,
    store,
    base,
    run_id,
    now,
    deadline=None,
    clock=_time.monotonic,
    on_progress=None,
    sleep=_time.sleep,
) -> DayStatus:
    """Canary plus one query per issuer for the UTC day; writes and returns its DayStatus."""
    start, end = _day_bounds(day)
    st = DayStatus(source="gdelt", day=day.isoformat(), run_id=run_id)

    def _errors(items):
        room = MAX_ERRORS - len(st.errors)
        if room > 0:
            st.errors.extend(items[:room])

    canary = fetch_canary(start, end, get=get, limiter=limiter, sleep=sleep)
    st.canary_hits = len(canary.articles)
    _errors([f"canary: {e}" for e in canary.errors])
    for issuer in issuers:
        if deadline is not None and clock() >= deadline:
            st.status = "partial"
            st.errors.append("max_runtime")
            st.finished_at = _iso_z(_now_value(now))
            write_day_status(base, st, count_attempt=False, now=_now_value(now))
            return st
        result = fetch_window(
            build_query(issuer), start, end, get=get, limiter=limiter, sleep=sleep
        )
        st.queries += 1
        if result.failed:
            st.failed += 1
        elif result.rejected:
            st.rejected += 1
        st.truncated += result.truncated
        _errors([f"{issuer.key}: {e}" for e in result.errors])
        records = articles_to_records(
            result.articles, issuer, run_id=run_id, backfilled=False, now=now, fallback_day=day
        )
        appended = store.append(records)
        st.records_new += appended.new
        st.records_duplicate += appended.duplicate
        if on_progress is not None:
            on_progress()
    st.status = classify_gdelt_day(st.queries, st.failed, st.rejected, st.canary_hits)
    if st.canary_hits == 0 and "canary: no hits" not in st.errors:
        st.errors.append("canary: no hits")
    st.finished_at = _iso_z(_now_value(now))
    write_day_status(base, st, now=_now_value(now))
    return st


def _checkpoint_path(base) -> Path:
    return Path(base) / "checkpoints" / "backfill_gdelt.json"


def read_backfill_checkpoint(base) -> dict | None:
    return read_json(_checkpoint_path(base))


def backfill(
    issuers,
    *,
    today,
    store,
    base,
    get,
    limiter,
    run_id,
    now,
    window_days=7,
    horizon_days=89,
    max_calls=None,
    deadline=None,
    clock=_time.monotonic,
    on_progress=None,
    sleep=_time.sleep,
) -> dict:
    """Backfill before archive_start in windows on a fixed anchor, oldest first.

    The anchor (today - horizon_days on the first call) is stored in the checkpoint, so a
    later call resumes with the same window keys. Windows end exclusively at
    archive_start; the part that fell out of the GDELT horizon is clipped, a window that
    fell out completely is marked ``expired``. No day status files are written.
    """
    start_day = archive_start(base)
    if start_day is None:
        raise ValueError("archive_start is not set; run the daily collector first")
    path = _checkpoint_path(base)
    cp = read_json(path) or {}
    if not cp.get("anchor"):
        cp = {
            "anchor": (today - timedelta(days=horizon_days)).isoformat(),
            "window_days": window_days,
            "windows": {},
        }
    cp.setdefault("windows", {})
    anchor = date.fromisoformat(cp["anchor"])
    step = int(cp.get("window_days") or window_days)
    horizon_start = today - timedelta(days=horizon_days)

    windows = []
    k = 0
    while anchor + timedelta(days=k * step) < start_day:
        ws = anchor + timedelta(days=k * step)
        windows.append((ws, min(ws + timedelta(days=step), start_day)))
        k += 1

    summary = {"calls": 0, "records_new": 0, "records_duplicate": 0, "failed": 0, "stopped": None}

    def save():
        states = cp["windows"]
        cp["total"] = len(windows) * len(issuers)
        cp["done"] = sum(1 for v in states.values() if v == "done")
        cp["expired"] = sum(1 for v in states.values() if v == "expired")
        cp["last_run_id"] = run_id
        cp["updated_at"] = _iso_z(_now_value(now))
        atomic_write_json(path, cp)

    for ws, we in windows:
        for issuer in issuers:
            key = f"{issuer.key}|{ws.isoformat()}"
            if cp["windows"].get(key) in ("done", "expired"):
                continue
            eff_start = max(ws, horizon_start)
            if we <= eff_start:
                cp["windows"][key] = "expired"
                save()
                continue
            if max_calls is not None and summary["calls"] >= max_calls:
                summary["stopped"] = "max_calls"
                break
            if deadline is not None and clock() >= deadline:
                summary["stopped"] = "max_runtime"
                break
            q_start = datetime.combine(eff_start, time.min, tzinfo=UTC)
            q_end = datetime.combine(we, time.min, tzinfo=UTC) - timedelta(seconds=1)
            result = fetch_window(
                build_query(issuer), q_start, q_end, get=get, limiter=limiter, sleep=sleep
            )
            summary["calls"] += result.calls
            records = articles_to_records(
                result.articles, issuer, run_id=run_id, backfilled=True, now=now
            )
            appended = store.append(records)
            summary["records_new"] += appended.new
            summary["records_duplicate"] += appended.duplicate
            if result.failed or result.rejected:
                summary["failed"] += 1  # stays open; a later call retries it
            else:
                cp["windows"][key] = "done"
            save()
            if on_progress is not None:
                on_progress()
        if summary["stopped"]:
            break
    save()
    summary.update(
        anchor=cp["anchor"],
        total=cp["total"],
        done=cp["done"],
        expired=cp["expired"],
        open=cp["total"] - cp["done"] - cp["expired"],
    )
    return summary
