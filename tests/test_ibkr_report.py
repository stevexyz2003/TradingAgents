"""Soll/Ist report data layer: decision-log parsing, ledger reading, the per-decision join."""

from __future__ import annotations

import ast
import importlib.util
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_LOG = ROOT / "tests" / "fixtures" / "paper_log_71df89d" / "decision-log.md"
SEP = "\n\n<!-- ENTRY_END -->\n\n"

_spec = importlib.util.spec_from_file_location("ibkr_report", ROOT / "scripts" / "ibkr_report.py")
report = importlib.util.module_from_spec(_spec)
sys.modules["ibkr_report"] = report
_spec.loader.exec_module(report)


def _entry(date: str, ticker: str, rating: str, tag: str = "pending") -> str:
    return f"[{date} | {ticker} | {rating} | {tag}]\n\nDECISION:\n**Rating**: {rating}"


def _log(*entries: str) -> str:
    return SEP.join(entries) + SEP


# --- parse_decisions -----------------------------------------------------------------------


def test_dedup_first_version_wins():
    """SC5: the triple 2026-10-09 | AAPL (written raw) yields one decision, the first version."""
    text = _log(
        _entry("2026-10-09", "AAPL", "Hold"),
        _entry("2026-10-09", "MSFT", "Buy"),
        _entry("2026-10-09", "AAPL", "Buy"),
        _entry("2026-10-09", "AAPL", "Sell"),
    )
    decisions, unparsed, duplicates = report.parse_decisions(text)
    assert [d.key for d in decisions] == ["2026-10-09|AAPL", "2026-10-09|MSFT"]
    assert decisions[0].rating == "Hold"
    assert duplicates == 2
    assert unparsed == 0


def test_parse_real_fixture_smoke():
    """Smoke only: the real bytes parse; this fixture holds each key once, so no dedup proof."""
    text = FIXTURE_LOG.read_bytes().decode("utf-8")
    decisions, unparsed, duplicates = report.parse_decisions(text)
    assert decisions
    keys = [d.key for d in decisions]
    assert len(keys) == len(set(keys))
    assert unparsed == 0
    assert duplicates == 0


def test_parse_counts_unparsable_blocks():
    text = _log(_entry("2026-10-09", "AAPL", "Hold"), "[2026-10-09 | MSFT | Buy]\n\nDECISION:\nx")
    decisions, unparsed, duplicates = report.parse_decisions(text)
    assert len(decisions) == 1
    assert unparsed == 1
    assert duplicates == 0


def test_parse_reads_settled_tag():
    text = _log(
        "[2026-10-09 | AAPL | Hold | +2.0% | +4.0% | 5d | resolved:2026-10-16]\n\nDECISION:\nx"
    )
    (decision,), _, _ = report.parse_decisions(text)
    assert decision.pending is False
    assert decision.raw == "+2.0%"
    assert decision.alpha == "+4.0%"
    assert decision.holding == "5d"
    assert decision.resolved == "2026-10-16"


def test_key_separator_matches_guards():
    guards = report._load("ibkr_guards", "ibkr_guards.py")
    assert report.KEY_SEPARATOR == guards.DECISION_KEY_SEPARATOR


# --- read_ledger ---------------------------------------------------------------------------


def _rec(seq: int, event: str, mode: str = "live", **fields) -> dict:
    return {
        "v": 1,
        "seq": seq,
        "ts": "2026-10-16T14:00:00+00:00",
        "run_id": "r1",
        "mode": mode,
        "event": event,
        **fields,
    }


def _blob(records: list[dict]) -> bytes:
    return b"".join((json.dumps(r) + "\n").encode("utf-8") for r in records)


def test_read_ledger_in_file_order():
    blob = _blob([_rec(1, "run_start"), _rec(2, "run_end")])
    assert [r["seq"] for r in report.read_ledger(blob)] == [1, 2]


def test_read_ledger_tolerates_torn_tail():
    blob = _blob([_rec(1, "run_start")]) + b'{"v":1,"seq":2,"ev'
    assert [r["seq"] for r in report.read_ledger(blob)] == [1]


def test_read_ledger_broken_middle_raises():
    good = _blob([_rec(1, "run_start")])
    blob = good + b"not json\n" + _blob([_rec(3, "run_end")])
    with pytest.raises(report._ledger().LedgerError):
        report.read_ledger(blob)


def test_read_ledger_rejects_dryrun_ledger():
    with pytest.raises(report._ledger().LedgerError):
        report.read_ledger(_blob([_rec(1, "run_start", mode="dryrun")]))


# --- build_rows ----------------------------------------------------------------------------

BLOCKS = {"AAPL": 1, "MSFT": 1, "NVDA": 1}
SHA = "71df89df8a078acdcea92f966c10332086f6cf43"


def _rows(decisions, records):
    ledger = report.read_ledger(_blob(records))
    return report.build_rows(decisions, ledger, block_qty_of=BLOCKS.get)


def _dec(date: str, ticker: str, rating: str) -> report.Decision:
    return report.Decision(date, ticker, rating, True, None, None, None, None)


def _intent(seq: int, key: str, *, rating="Overweight", side="BUY", qty=1, gap=False) -> dict:
    date, ticker = key.split("|")
    return _rec(
        seq,
        "intent",
        decision_key=key,
        ticker=ticker,
        trade_date=date,
        rating=rating,
        paper_log_sha=SHA,
        side=side,
        quantity=qty,
        con_id=265598,
        order_ref="ref",
        weekend_gap=gap,
        rating_source="engine",
    )


def _fill(seq: int, key: str, exec_id: str | None, qty: float, price: float, side="BUY") -> dict:
    fields = {"decision_key": key, "side": side, "filled_qty": qty, "price": price}
    if exec_id:
        fields["exec_id"] = exec_id
    return _rec(seq, "filled", **fields)


def _one(decision, records):
    rows, extra = _rows([decision], records)
    assert extra == []
    return rows[0]


def test_join_first_live_order_real_shape():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Hold"),
        [
            _intent(1, key),
            _rec(2, "placed", decision_key=key),
            _fill(3, key, "0001.01", 1, 270.5),
            _rec(4, "alarm", decision_key=key, state="post-order-mismatch", fills_booked=True),
            _rec(5, "run_end"),
        ],
    )
    assert row.state == "filled"
    assert row.ledger_rating == "Overweight"
    assert (row.target, row.held_before, row.held_after) == (1, 0, 1)
    assert (row.order_qty, row.filled_qty, row.avg_price, row.deviation) == (1, 1, 270.5, 0)
    assert any(
        "ledger rating Overweight != log rating Hold" in n and "71df89d" in n for n in row.notes
    )
    assert "alarm: post-order-mismatch" in row.notes


def test_join_hold_without_order():
    key = "2026-10-09|AAPL"
    row = _one(
        _dec("2026-10-09", "AAPL", "Hold"),
        [
            _rec(
                1,
                "skipped",
                decision_key=key,
                reason="hold",
                state="skipped-hold",
                weekend_gap=True,
            )
        ],
    )
    assert row.state == "skipped-hold"
    assert row.target is None and row.held_before is None and row.held_after is None
    assert row.weekend_gap is True
    assert "no intent: target/held not recorded (D-20)" in row.notes


def test_join_no_run():
    row = _one(_dec("2026-10-09", "MSFT", "Buy"), [])
    assert row.state == report.NO_RUN
    assert row.filled_qty is None and row.order_qty is None and row.target is None


def test_join_fill_timeout():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Overweight"),
        [
            _intent(1, key),
            _rec(2, "placed", decision_key=key),
            _rec(3, "alarm", decision_key=key, state="fill-timeout"),
        ],
    )
    assert row.state == "fill-timeout"
    assert row.filled_qty == 0


def test_join_place_rejected():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Overweight"),
        [_intent(1, key), _rec(2, "rejected", decision_key=key, state="place-rejected")],
    )
    assert row.state == "place-rejected"
    assert row.filled_qty == 0


def test_join_resolved():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Overweight"),
        [_intent(1, key), _rec(2, "resolved", decision_key=key, outcome="never_sent", note="n")],
    )
    assert row.state == "never_sent"


def test_join_correction_highest_wins():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Overweight"),
        [_intent(1, key), _fill(2, key, "0001.01", 1, 10), _fill(3, key, "0001.02", 1, 11)],
    )
    assert row.filled_qty == 1
    assert row.avg_price == 11


def test_join_aggregate_row_counts_once():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Overweight"), [_intent(1, key), _fill(2, key, None, 1, 10)]
    )
    assert row.filled_qty == 1
    assert row.avg_price == 10


def test_join_partial_average_price():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Buy"),
        [
            _intent(1, key, rating="Buy", qty=2),
            _fill(2, key, "0001.01", 1, 10),
            _fill(3, key, "0002.01", 1, 12),
        ],
    )
    assert row.filled_qty == 2
    assert row.avg_price == 11
    assert (row.target, row.held_before, row.held_after, row.deviation) == (2, 0, 2, 0)


def test_join_sell_ladder():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Sell"),
        [
            _intent(1, key, rating="Sell", side="SELL", qty=1),
            _fill(2, key, "0001.01", 1, 10, side="SELL"),
        ],
    )
    assert (row.target, row.held_before, row.held_after, row.deviation) == (0, 1, 0, 0)


def test_join_implausible_block_size():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Underweight"),
        [_intent(1, key, rating="Underweight", side="BUY", qty=1)],
    )
    assert row.held_before is None and row.held_after is None and row.deviation is None
    assert any("block size changed?" in n for n in row.notes)


def test_join_unknown_ticker():
    key = "2026-10-16|ZZZZ"
    row = _one(_dec("2026-10-16", "ZZZZ", "Overweight"), [_intent(1, key)])
    assert row.target is None and row.deviation is None
    assert any("ZZZZ" in n for n in row.notes)


def test_join_last_skip_wins():
    key = "2026-10-09|AAPL"
    row = _one(
        _dec("2026-10-09", "AAPL", "Hold"),
        [
            _rec(1, "skipped", decision_key=key, reason="stale", state="stale-source"),
            _rec(2, "skipped", decision_key=key, reason="hold", state="skipped-hold"),
        ],
    )
    assert row.state == "skipped-hold"


def test_join_ledger_only_keys_are_reported():
    rows, extra = _rows(
        [_dec("2026-10-09", "AAPL", "Hold")],
        [_rec(1, "skipped", decision_key="2026-10-02|NVDA", reason="hold", state="skipped-hold")],
    )
    assert [r.key for r in rows] == ["2026-10-09|AAPL"]
    assert extra == ["2026-10-02|NVDA"]


# --- metrics, slippage, footnotes, render ---------------------------------------------------


def _row(**kw) -> report.ReportRow:
    base = {
        "key": "2026-10-16|AAPL",
        "trade_date": "2026-10-16",
        "ticker": "AAPL",
        "log_rating": "Hold",
        "ledger_rating": "Overweight",
        "state": "filled",
        "side": "BUY",
        "target": 1.0,
        "held_before": 0.0,
        "held_after": 1.0,
        "order_qty": 1.0,
        "filled_qty": 1.0,
        "avg_price": 101.0,
        "deviation": 0.0,
        "weekend_gap": False,
        "notes": (),
    }
    base.update(kw)
    return report.ReportRow(**base)


def test_slippage_sign_buy_and_sell():
    assert report.slippage_bp("BUY", 101.0, 100.0) == pytest.approx(100.0)
    assert report.slippage_bp("SELL", 99.0, 100.0) == pytest.approx(100.0)
    assert report.slippage_bp("BUY", 99.0, 100.0) == pytest.approx(-100.0)
    assert report.slippage_bp("SELL", 101.0, 100.0) == pytest.approx(-100.0)


def test_slippage_missing_or_bad_close_is_none():
    assert report.slippage_bp("BUY", 101.0, None) is None
    assert report.slippage_bp("BUY", 101.0, 0.0) is None
    assert report.slippage_bp("BUY", 101.0, -5.0) is None
    assert report.slippage_bp("BUY", None, 100.0) is None


def test_metrics_fill_ratio_cases():
    assert report.fill_ratio(_row(order_qty=None, filled_qty=None)) is None
    assert report.fill_ratio(_row(order_qty=4.0, filled_qty=3.0, state="partial")) == 0.75
    assert report.fill_ratio(_row(state="fill-timeout", filled_qty=0.0)) == 0.0
    assert report.fill_ratio(_row(state="place-rejected", filled_qty=None)) == 0.0


def test_metrics_total_fill_ratio():
    rows = [
        _row(order_qty=2.0, filled_qty=2.0),
        _row(order_qty=2.0, filled_qty=0.0, state="fill-timeout"),
        _row(order_qty=None, filled_qty=None),
    ]
    assert report.total_fill_ratio(rows) == 0.5
    assert report.total_fill_ratio([_row(order_qty=None)]) is None


class _Series(list):
    @property
    def iloc(self):
        return self


def _patch_closes(monkeypatch, fake):
    from tradingagents.memory import settlement

    monkeypatch.setattr(settlement, "get_closes", fake)


def test_metrics_close_fetcher_value_and_cache(monkeypatch):
    calls = []

    def fake(symbol, start, end):
        calls.append((symbol, start, end))
        return _Series([100.0])

    _patch_closes(monkeypatch, fake)
    fetcher = report.CloseFetcher()
    assert fetcher.get("AAPL", "2026-10-16") == (100.0, None)
    assert fetcher.get("AAPL", "2026-10-16") == (100.0, None)
    assert calls == [("AAPL", "2026-10-16", "2026-10-17")]


def _raise_down(*_a):
    raise ConnectionError("down")


@pytest.mark.parametrize(
    "fake, suffix",
    [
        (lambda *a: _Series([]), ""),
        (lambda *a: _Series([0.0]), "unusable"),
        (lambda *a: _Series([float("nan")]), "unusable"),
        (_raise_down, "ConnectionError"),
    ],
)
def test_footnote_close_failures(monkeypatch, fake, suffix):
    _patch_closes(monkeypatch, fake)
    value, reason = report.CloseFetcher().get("AAPL", "2026-10-16")
    assert value is None
    assert reason.startswith("no close for AAPL on 2026-10-16 from the price source")
    assert suffix in reason


def _render(rows, *, prices, decisions=None, **kw):
    args = {
        "sources": {"Decision log fork/paper-log": "@ abc", "Ledger fork/ibkr-log": "@ def"},
        "period": (None, None),
        "prices": prices,
        "unparsed": 0,
        "duplicates": 0,
        "ledger_only": [],
    }
    args.update(kw)
    decs = decisions if decisions is not None else [_dec("2026-10-16", "AAPL", "Hold")]
    return report.render_markdown(rows, decs, **args)


def test_footnote_on_price_error(monkeypatch):
    _patch_closes(monkeypatch, lambda *a: _Series([]))
    text = _render([_row()], prices=report.CloseFetcher())
    assert "1. no close for AAPL on 2026-10-16 from the price source" in text


def test_render_slippage_value(monkeypatch):
    _patch_closes(monkeypatch, lambda *a: _Series([100.0]))
    text = _render([_row(avg_price=101.0)], prices=report.CloseFetcher())
    assert "| 100.0 |" in text


def test_render_no_prices_never_calls_source(monkeypatch):
    def boom(*a):
        raise AssertionError("price source must not be called")

    _patch_closes(monkeypatch, boom)
    text = _render([_row()], prices=None)
    assert "prices skipped (--no-prices)" in text


def test_render_two_separate_tables_and_notice_first():
    text = _render([_row()], prices=None)
    assert text.count("## Execution") == 1
    assert text.count("## Decision") == 1
    assert text.index(report.PAPER_FILL_NOTICE) < text.index("## Execution")
    execution, rest = text.split("## Decision")
    decision = rest.split("## Notes")[0]
    for header in (
        "Fill ratio",
        report.SLIPPAGE_HEADER,
        "Avg price",
        "weekend_gap",
        "Target - held",
    ):
        assert header in execution
        assert header not in decision
    for header in ("Realized return", "Alpha", "Holding", "Status"):
        assert header in decision
        assert header not in execution


def test_footnote_sources_and_pipes():
    row = _row(notes=("a|b",))
    text = _render([row], prices=None, unparsed=2, duplicates=1, ledger_only=["2026-10-01|XYZ"])
    assert "2 unreadable decision-log block(s)" in text
    assert "1 duplicate decision(s)" in text
    assert "2026-10-01|XYZ" in text
    assert "a|b" in text
    assert text.endswith("\n")


# --- CLI ---------------------------------------------------------------------------------


class _FakeReader:
    def __init__(self, files, error=None):
        self._files = files
        self._error = error

    def fetch(self):
        if self._error:
            raise self._error
        return "a" * 40

    def read(self, path):
        if path not in self._files:
            raise report._paperlog().BlobMissing(path)
        return self._files[path]


def _factory(log_text, ledger_blob, *, ledger_error=None):
    def make(_repo, _remote, branch):
        if branch == "paper-log":
            return _FakeReader({"decision-log.md": log_text.encode("utf-8")})
        files = {} if ledger_blob is None else {"ledger.jsonl": ledger_blob}
        return _FakeReader(files, ledger_error)

    return make


def _cli_data():
    key = "2026-10-16|AAPL"
    log = _log(
        _entry("2026-10-09", "MSFT", "Hold"),
        _entry("2026-10-16", "AAPL", "Overweight"),
        _entry("2026-10-20", "NVDA", "Hold"),
    )
    blob = _blob(
        [
            _intent(1, key),
            _rec(2, "placed", decision_key=key),
            _fill(3, key, "0001.01", 1, 270.5),
            _rec(4, "run_end"),
        ]
    )
    return log, blob


def _run(args, factory):
    out = io.StringIO()
    code = report.main(args, reader_factory=factory, stdout=out)
    return code, out.getvalue()


def test_cli_since_until_filters():
    log, blob = _cli_data()
    code, text = _run(
        ["--no-prices", "--since", "2026-10-10", "--until", "2026-10-16"], _factory(log, blob)
    )
    assert code == 0
    assert "AAPL" in text
    assert "MSFT" not in text
    assert "NVDA" not in text


def test_cli_prices_patched(monkeypatch):
    _patch_closes(monkeypatch, lambda *a: _Series([270.0]))
    log, blob = _cli_data()
    code, text = _run([], _factory(log, blob))
    assert code == 0
    assert "18.5" in text  # (270.5 - 270) / 270 * 1e4


@pytest.mark.parametrize(
    "args",
    [
        ["--since", "2026-10-16", "--until", "2026-10-10"],
        ["--since", "not-a-date"],
        ["--until", "2026-13-01"],
    ],
)
def test_cli_bad_dates_exit_1(args, capsys):
    log, blob = _cli_data()
    code, text = _run(["--no-prices", *args], _factory(log, blob))
    assert code == 1
    assert text == ""
    assert capsys.readouterr().err


def test_cli_missing_published_branch_exit_2(capsys):
    log, _ = _cli_data()
    err = report._paperlog().PaperLogUnavailable("git fetch failed")
    code, text = _run(["--no-prices"], _factory(log, None, ledger_error=err))
    assert code == 2
    assert text == ""
    assert "published branch fork/ibkr-log not readable" in capsys.readouterr().err


def test_cli_missing_ledger_blob_exit_2(capsys):
    log, _ = _cli_data()
    code, text = _run(["--no-prices"], _factory(log, None))
    assert code == 2
    assert text == ""
    assert "ledger.jsonl" in capsys.readouterr().err


def test_cli_corrupt_ledger_exit_2_no_partial_report(capsys):
    log, _ = _cli_data()
    bad = _blob([_rec(1, "run_start")]) + b"not json\n" + _blob([_rec(3, "run_end")])
    code, text = _run(["--no-prices"], _factory(log, bad))
    assert code == 2
    assert text == ""
    assert capsys.readouterr().err


@pytest.mark.parametrize(
    "args",
    [
        ["--remote", "-x"],
        ["--paper-log-branch", "a..b"],
        ["--published-branch", "bad name"],
    ],
)
def test_cli_rejects_bad_ref_names(args):
    called = []

    def factory(*a):
        called.append(a)
        raise AssertionError("no reader may be built")

    code, _ = _run(["--no-prices", *args], factory)
    assert code == 1
    assert called == []


def test_cli_out_dir_must_exist(tmp_path):
    log, blob = _cli_data()
    code, _ = _run(["--no-prices", "--out", str(tmp_path / "nope" / "r.md")], _factory(log, blob))
    assert code == 1


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _make_remote(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git not available")
    log, blob = _cli_data()
    bare, work, seed = tmp_path / "bare.git", tmp_path / "work", tmp_path / "seed"
    for d in (bare, work, seed):
        d.mkdir()
    _git(bare, "init", "-q", "--bare")
    _git(seed, "init", "-q", "-b", "paper-log")
    (seed / "decision-log.md").write_bytes(log.encode("utf-8"))
    _git(seed, "add", "decision-log.md")
    _git(seed, "commit", "-q", "-m", "log")
    _git(seed, "checkout", "-q", "-b", "ibkr-log")
    _git(seed, "rm", "-q", "decision-log.md")
    (seed / "ledger.jsonl").write_bytes(blob)
    _git(seed, "add", "ledger.jsonl")
    _git(seed, "commit", "-q", "-m", "ledger")
    _git(seed, "remote", "add", "bare", str(bare))
    _git(seed, "push", "-q", "bare", "paper-log", "ibkr-log")
    _git(work, "init", "-q")
    _git(work, "remote", "add", "fork", str(bare))
    return bare, work


def _tips(bare):
    return _git(bare, "for-each-ref", "refs/heads").stdout


def test_real_git_reads_two_branches_without_checkout(tmp_path, capsys):
    bare, work = _make_remote(tmp_path)
    tips_before = _tips(bare)
    code = report.main(["--repo", str(work), "--no-prices"])
    assert code == 0
    text = capsys.readouterr().out
    assert "## Execution" in text and "## Decision" in text
    assert "270.50" in text
    tip = _git(bare, "rev-parse", "ibkr-log").stdout.decode().strip()[:12]
    assert tip in text
    assert _git(work, "status", "--porcelain").stdout == b""
    assert sorted(p.name for p in work.iterdir()) == [".git"]
    assert _git(work, "for-each-ref", "refs/tengx").stdout == b""
    assert _tips(bare) == tips_before


def test_real_git_out_file_matches_stdout(tmp_path, capsys):
    _, work = _make_remote(tmp_path)
    out = tmp_path / "bericht.md"
    code = report.main(["--repo", str(work), "--no-prices", "--out", str(out)])
    assert code == 0
    stdout = capsys.readouterr().out
    assert out.read_bytes() == stdout.encode("utf-8")
    assert b"\r" not in out.read_bytes()


def test_real_git_missing_published_branch_exit_2(tmp_path, capsys):
    bare, work = _make_remote(tmp_path)
    _git(bare, "branch", "-q", "-D", "ibkr-log")
    code = report.main(["--repo", str(work), "--no-prices"])
    assert code == 2
    assert "published branch fork/ibkr-log not readable" in capsys.readouterr().err


def test_report_module_is_library_free_and_clockless():
    path = ROOT / "scripts" / "ibkr_report.py"
    source = path.read_text(encoding="utf-8")
    top_level = {
        name.split(".")[0]
        for node in ast.parse(source).body
        if isinstance(node, ast.Import | ast.ImportFrom)
        for name in (
            [a.name for a in node.names]
            if isinstance(node, ast.Import)
            else ([node.module] if node.module and not node.level else [])
        )
    }
    for forbidden in ("ib_async", "tradingagents", "pandas", "exchange_calendars"):
        assert forbidden not in top_level
    for forbidden in ("datetime.now", "time.time(", "date.today"):
        assert forbidden not in source
    for verb in ('"push"', '"checkout"', '"commit"'):
        assert verb not in source
