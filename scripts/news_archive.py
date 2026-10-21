"""News archive CLI: run (daily, with catch-up), backfill, status, smoke.

The archive lives under %LOCALAPPDATA%\\TradingEngineX\\archive (never in the repository).
See scripts/NEWS_ARCHIVE.md for the operator handbook.

Exit codes
  run:      0 all processed days ok, 1 a day partial, 2 a day missing,
            3 another run holds the lock, 4 configuration error (CA bundle, no archive_start)
  status:   0 fine, 1 a day partial/missing, 2 no finished run or the last one older than 36 h
  smoke:    0 GDELT and DILA both answered, 1 otherwise
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import sys
import time
from datetime import UTC, date, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if importlib.util.find_spec("tradingagents") is None:
    sys.path.insert(0, str(REPO))

from tradingagents.forecast.archive import amf, gdelt  # noqa: E402
from tradingagents.forecast.archive.http import (  # noqa: E402
    CaBundleMissing,
    RateLimiter,
    get_with_retry,
    make_session,
    resolve_ca_bundle,
)
from tradingagents.forecast.archive.seed import (  # noqa: E402
    SeedIssuer,
    default_seed_path,
    load_seed,
)
from tradingagents.forecast.archive.status import (  # noqa: E402
    MAX_ATTEMPTS,
    DayStatus,
    archive_start,
    days_needing_work,
    ensure_archive_start,
    gap_report,
    given_up_days,
    heartbeat_age,
    read_heartbeat,
    status_file,
    write_day_status,
    write_heartbeat,
)
from tradingagents.forecast.archive.store import (  # noqa: E402
    ArchiveStore,
    LockHeld,
    RunLock,
    archive_base,
    pid_alive,
)

log = logging.getLogger("news_archive")

SOURCES = ("gdelt", "amf")
GDELT_WINDOW_DAYS = 89
HEARTBEAT_MAX_AGE = timedelta(hours=36)

EXIT_OK, EXIT_PARTIAL, EXIT_MISSING, EXIT_LOCKED, EXIT_CONFIG = 0, 1, 2, 3, 4


def _iso_z(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="news_archive.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="collect the days that need work (catch-up always on)")
    run.add_argument("--catch-up", action="store_true", help="accepted for readability")
    run.add_argument("--sources", default="gdelt,amf")
    run.add_argument("--max-days", type=int, default=3)
    run.add_argument("--max-runtime", type=float, default=150, help="minutes")
    run.add_argument("--seed")
    run.add_argument("--limit-issuers", type=int)
    run.add_argument("--start", help="archive_start (YYYY-MM-DD) on the first run")

    backfill = sub.add_parser("backfill", help="GDELT 3-month backfill or AMF history")
    backfill.add_argument("--source", choices=SOURCES, required=True)
    backfill.add_argument("--max-calls", type=int)
    backfill.add_argument("--max-runtime", type=float, default=150, help="minutes")
    backfill.add_argument("--seed")
    backfill.add_argument("--since", help="AMF only: first day (YYYY-MM-DD)")

    status = sub.add_parser("status", help="gap report and heartbeat")
    status.add_argument("--days", type=int, default=14)

    smoke = sub.add_parser("smoke", help="one GDELT query + one DILA listing into archive/smoke")
    smoke.add_argument("--issuers", type=int, default=2)
    smoke.add_argument("--seed")
    return parser


def _setup_logging(base: Path):
    (base / "logs").mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(
        base / "logs" / "news_archive.log", maxBytes=5 * 2**20, backupCount=5, encoding="utf-8"
    )
    stream_handler = logging.StreamHandler(sys.stderr)
    handlers = [file_handler, stream_handler]
    root = logging.getLogger()
    previous_level = root.level
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    return handlers, previous_level


def _teardown_logging(handlers, previous_level) -> None:
    root = logging.getLogger()
    for handler in handlers:
        root.removeHandler(handler)
        handler.close()
    root.setLevel(previous_level)


class _Ctx:
    def __init__(self, *, base, get, now, clock, sleep, pid_alive):
        self.base = base
        self.get = get
        self.now = now
        self.clock = clock
        self.sleep = sleep
        self.pid_alive = pid_alive

    def lock(self) -> RunLock:
        return RunLock(self.base / "run.lock", now=self.now, pid_alive=self.pid_alive)

    def run_id(self, prefix="run") -> str:
        return f"{prefix}-{self.now().strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}"


def _issuers(seed, limit=None) -> list[SeedIssuer]:
    issuers = load_seed(Path(seed) if seed else default_seed_path())
    return issuers[:limit] if limit else issuers


def _mark(base, source, days, status, error, run_id, now, *, count_attempt=True):
    result = []
    for day in days:
        st = DayStatus(
            source=source,
            day=day.isoformat(),
            status=status,
            errors=[error],
            run_id=run_id,
            finished_at=_iso_z(now),
        )
        result.append(write_day_status(base, st, count_attempt=count_attempt, now=now))
    return result


def _exit_for(statuses) -> int:
    if any(st.status == "missing" for st in statuses):
        return EXIT_MISSING
    if any(st.status == "partial" for st in statuses):
        return EXIT_PARTIAL
    return EXIT_OK


def _counts(statuses) -> dict:
    counts: dict[str, dict] = {}
    for st in statuses:
        c = counts.setdefault(
            st.source, {"days": 0, "ok": 0, "partial": 0, "missing": 0, "records_new": 0}
        )
        c["days"] += 1
        c[st.status] = c.get(st.status, 0) + 1
        c["records_new"] += st.records_new
    return counts


def cmd_run(args, ctx: _Ctx) -> int:
    base = ctx.base
    today = ctx.now().date()
    run_id = ctx.run_id()
    deadline = ctx.clock() + args.max_runtime * 60
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    unknown = [s for s in sources if s not in SOURCES]
    if unknown:
        log.error("unknown sources: %s", unknown)
        return EXIT_CONFIG
    issuers = _issuers(args.seed, args.limit_issuers) if "gdelt" in sources else []
    lock = ctx.lock()
    try:
        lock.acquire()
    except LockHeld as exc:
        log.error("%s; another run is active", exc)
        return EXIT_LOCKED
    try:
        start = date.fromisoformat(args.start) if args.start else today - timedelta(days=1)
        ensure_archive_start(base, start)
        started_at = _iso_z(ctx.now())
        write_heartbeat(
            base,
            {
                "started_at": started_at,
                "finished_at": None,
                "run_id": run_id,
                "exit_code": None,
                "counts": {},
            },
        )
        statuses: list[DayStatus] = []
        store = ArchiveStore(base)
        try:
            if "gdelt" in sources:
                days = days_needing_work(
                    base, "gdelt", today, window_days=GDELT_WINDOW_DAYS, max_days=args.max_days
                )
                log.info("gdelt: days to collect %s", [d.isoformat() for d in days])
                limiter = RateLimiter(gdelt.MIN_INTERVAL, clock=ctx.clock, sleep=ctx.sleep)
                done: set[date] = set()
                try:
                    for day in days:
                        st = gdelt.collect_day(
                            day,
                            issuers,
                            get=ctx.get,
                            limiter=limiter,
                            store=store,
                            base=base,
                            run_id=run_id,
                            now=ctx.now,
                            deadline=deadline,
                            clock=ctx.clock,
                            on_progress=lock.touch,
                            sleep=ctx.sleep,
                        )
                        done.add(day)
                        statuses.append(st)
                        if "max_runtime" in st.errors:
                            break
                except Exception as exc:  # one broken source must not stop the other
                    log.exception("gdelt collector crashed")
                    rest = [d for d in days if d not in done]
                    statuses += _mark(
                        base, "gdelt", rest, "missing", f"crash: {exc!r}", run_id, ctx.now()
                    )
            if "amf" in sources:
                days = days_needing_work(
                    base, "amf", today, window_days=GDELT_WINDOW_DAYS, max_days=args.max_days
                )
                log.info("amf: days to collect %s", [d.isoformat() for d in days])
                if days and ctx.clock() >= deadline:
                    statuses += _mark(
                        base,
                        "amf",
                        days,
                        "partial",
                        "max_runtime",
                        run_id,
                        ctx.now(),
                        count_attempt=False,
                    )
                elif days:
                    try:
                        result = amf.collect(
                            days,
                            get=ctx.get,
                            store=store,
                            base=base,
                            run_id=run_id,
                            now=ctx.now,
                            today=today,
                            on_progress=lock.touch,
                            limiter=RateLimiter(1.0, clock=ctx.clock, sleep=ctx.sleep),
                            sleep=ctx.sleep,
                        )
                        statuses += list(result.values())
                    except Exception as exc:
                        log.exception("amf collector crashed")
                        statuses += _mark(
                            base, "amf", days, "missing", f"crash: {exc!r}", run_id, ctx.now()
                        )
        finally:
            store.close()
        exit_code = _exit_for(statuses)
        counts = _counts(statuses)
        write_heartbeat(
            base,
            {
                "started_at": started_at,
                "finished_at": _iso_z(ctx.now()),
                "run_id": run_id,
                "exit_code": exit_code,
                "counts": counts,
            },
        )
        print(json.dumps({"run_id": run_id, "exit_code": exit_code, "counts": counts}))
        return exit_code
    finally:
        lock.release()


def cmd_backfill(args, ctx: _Ctx) -> int:
    base = ctx.base
    start = archive_start(base)
    if start is None:
        print(
            "archive_start is not set: run `news_archive.py run` first "
            "(optionally with --start YYYY-MM-DD)",
            file=sys.stderr,
        )
        return EXIT_CONFIG
    today = ctx.now().date()
    run_id = ctx.run_id("backfill")
    lock = ctx.lock()
    try:
        lock.acquire()
    except LockHeld as exc:
        log.error("%s; another run is active", exc)
        return EXIT_LOCKED
    try:
        with ArchiveStore(base) as store:
            if args.source == "gdelt":
                summary = gdelt.backfill(
                    _issuers(args.seed),
                    today=today,
                    store=store,
                    base=base,
                    get=ctx.get,
                    limiter=RateLimiter(gdelt.MIN_INTERVAL, clock=ctx.clock, sleep=ctx.sleep),
                    run_id=run_id,
                    now=ctx.now,
                    max_calls=args.max_calls,
                    deadline=ctx.clock() + args.max_runtime * 60,
                    clock=ctx.clock,
                    on_progress=lock.touch,
                    sleep=ctx.sleep,
                )
                print(
                    f"backfill gdelt: done {summary['done']}/{summary['total']}, "
                    f"expired {summary['expired']}, open {summary['open']}, "
                    f"new {summary['records_new']}, stopped {summary['stopped']}"
                )
                return EXIT_OK if summary["open"] == 0 else EXIT_PARTIAL
            if not args.since:
                print("backfill --source amf needs --since YYYY-MM-DD", file=sys.stderr)
                return EXIT_CONFIG
            since = date.fromisoformat(args.since)
            # Days from archive_start on belong to the daily run; the backfill stops before.
            end = min(start, today)
            days = [since + timedelta(days=i) for i in range(max(0, (end - since).days))]
            if not days:
                print(f"backfill amf: nothing to do before archive_start {start}")
                return EXIT_OK
            result = amf.collect(
                days,
                get=ctx.get,
                store=store,
                base=base,
                run_id=run_id,
                now=ctx.now,
                today=today,
                backfilled=True,
                on_progress=lock.touch,
                limiter=RateLimiter(1.0, clock=ctx.clock, sleep=ctx.sleep),
                sleep=ctx.sleep,
            )
            statuses = list(result.values())
            print(
                f"backfill amf: {len(days)} days {days[0]}..{days[-1]}, counts {_counts(statuses)}"
            )
            return _exit_for(statuses)
    finally:
        lock.release()


def cmd_status(args, ctx: _Ctx) -> int:
    base = ctx.base
    now = ctx.now()
    today = now.date()
    start = archive_start(base)
    report = gap_report(base, SOURCES, days=args.days, today=today)
    print(f"archive: {base}")
    print(f"archive_start: {start.isoformat() if start else 'not set'}")
    by_day: dict[str, dict[str, DayStatus]] = {}
    for st in report:
        by_day.setdefault(st.day, {})[st.source] = st
    print(f"{'day':<12}" + "".join(f"{s:<44}" for s in SOURCES))
    for day in sorted(by_day):
        cells = []
        for source in SOURCES:
            st = by_day[day].get(source)
            if st is None:
                cells.append("-")
                continue
            cell = f"{st.status} att={st.attempts} new={st.records_new} dup={st.records_duplicate}"
            if source == "gdelt":
                cell += f" trunc={st.truncated} canary={st.canary_hits}"
            else:
                cell += f" files={st.files}"
            cells.append(cell)
        print(f"{day:<12}" + "".join(f"{c:<44}" for c in cells))
        for st in by_day[day].values():
            if st.status != "ok" and st.errors:
                print(f"{'':<12}{st.source}: {'; '.join(st.errors[:3])}")
    gave_up = given_up_days(base, SOURCES)
    if gave_up:
        print(f"GAVE UP (aufgegeben, attempts >= {MAX_ATTEMPTS}; catch-up skips these days):")
        for st in gave_up:
            print(f"  {st.source} {st.day} {st.status} attempts={st.attempts}")
            print(f"    reset: delete {status_file(base, st.source, st.day)}")
    hb = read_heartbeat(base)
    age = heartbeat_age(base, now)
    if hb:
        print(
            f"heartbeat: run_id={hb.get('run_id')} started={hb.get('started_at')} "
            f"finished={hb.get('finished_at')} exit={hb.get('exit_code')}"
        )
    else:
        print("heartbeat: none")
    print(
        f"heartbeat age (since last finished run): "
        f"{'never finished' if age is None else f'{age.total_seconds() / 3600:.1f} h'}"
    )
    cp = gdelt.read_backfill_checkpoint(base)
    if cp:
        print(
            f"gdelt backfill: anchor {cp.get('anchor')}, done {cp.get('done')}/"
            f"{cp.get('total')}, expired {cp.get('expired')}"
        )
    if age is None or age > HEARTBEAT_MAX_AGE:
        return EXIT_MISSING
    if any(st.status != "ok" for st in report):
        return EXIT_PARTIAL
    return EXIT_OK


def cmd_smoke(args, ctx: _Ctx) -> int:
    """One GDELT query (first N seed issuers in one OR group, yesterday UTC) plus the DILA
    listing. Writes only to archive/smoke (own index and JSONL)."""
    smoke_base = ctx.base / "smoke"
    issuers = _issuers(args.seed, args.issuers)
    now = ctx.now()
    yesterday = now.date() - timedelta(days=1)
    run_id = ctx.run_id("smoke")
    aliases = tuple(a for issuer in issuers for a in issuer.aliases)
    combined = SeedIssuer(
        isin="", name="smoke-combined", country="", aliases=aliases, source="smoke"
    )
    out: dict = {"gdelt": {}, "amf": {}}
    start = datetime.combine(yesterday, datetime.min.time(), tzinfo=UTC)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    result = gdelt.fetch_window(
        gdelt.build_query(combined),
        start,
        end,
        get=ctx.get,
        limiter=RateLimiter(0),
        min_split=timedelta(days=2),
        sleep=ctx.sleep,
    )
    records = []
    remaining = list(result.articles)
    for issuer in issuers:
        mine = [
            a
            for a in remaining
            if any(gdelt._alias_in_title(x, a.get("title") or "") for x in issuer.aliases)
        ]
        remaining = [a for a in remaining if a not in mine]
        records += gdelt.articles_to_records(mine, issuer, run_id=run_id, backfilled=False, now=now)
    records += gdelt.articles_to_records(
        remaining, combined, run_id=run_id, backfilled=False, now=now
    )
    with ArchiveStore(smoke_base) as store:
        appended = store.append(records)
    out["gdelt"] = {
        "query": gdelt.build_query(combined),
        "day": yesterday.isoformat(),
        "http_ok": result.failed == 0,
        "articles": len(result.articles),
        "new": appended.new,
        "duplicate": appended.duplicate,
        "rejected": result.rejected,
        "truncated": result.truncated,
        "error": result.errors[0] if result.errors else None,
    }
    try:
        listing = get_with_retry(
            ctx.get, amf.AMF_LISTING_URL, limiter=RateLimiter(0), sleep=ctx.sleep
        )
        files = amf.parse_listing(listing.text or "")
        out["amf"] = {
            "listing_ok": True,
            "files": len(files),
            "newest": files[-1].name if files else None,
            "newest_delivered_at": _iso_z(files[-1].delivered_at) if files else None,
            "error": None if files else "listing_no_matches",
        }
    except Exception as exc:
        out["amf"] = {
            "listing_ok": False,
            "files": 0,
            "newest": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    ok = (
        out["gdelt"]["http_ok"]
        and not out["gdelt"]["rejected"]
        and out["amf"]["listing_ok"]
        and out["amf"]["files"] > 0
    )
    return EXIT_OK if ok else EXIT_PARTIAL


COMMANDS = {"run": cmd_run, "backfill": cmd_backfill, "status": cmd_status, "smoke": cmd_smoke}


def main(
    argv=None,
    *,
    environ=None,
    get=None,
    now=None,
    clock=None,
    load_env=True,
    sleep=None,
    pid_alive=pid_alive,
) -> int:
    """Entry point. ``environ`` feeds the CA-bundle lookup only; the archive base comes
    from LOCALAPPDATA of the process environment."""
    args = _parser().parse_args(argv)
    if load_env:
        # Absolute path: the task scheduler starts without a shell environment.
        from dotenv import load_dotenv

        load_dotenv(REPO / ".env", override=False)
    env = os.environ if environ is None else environ
    base = archive_base()
    if args.command != "status":
        try:
            verify = resolve_ca_bundle(env)
        except CaBundleMissing as exc:
            print(f"error: {exc} (see scripts/PAPER_RUN.md)", file=sys.stderr)
            return EXIT_CONFIG
        if get is None:
            get = make_session(verify).get
    ctx = _Ctx(
        base=base,
        get=get,
        now=now or (lambda: datetime.now(UTC)),
        clock=clock or time.monotonic,
        sleep=sleep or time.sleep,
        pid_alive=pid_alive,
    )
    handlers, previous_level = _setup_logging(base)
    try:
        return COMMANDS[args.command](args, ctx)
    finally:
        _teardown_logging(handlers, previous_level)


if __name__ == "__main__":
    sys.exit(main())
