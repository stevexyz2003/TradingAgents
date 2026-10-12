"""Jev review of a finished run: REVIEW fallback, shadow checks, never fatal, no leaks."""

import copy
import io
import json
import logging
import urllib.error
from unittest.mock import MagicMock

import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.jev import client, hooks

FAKE_KEY = "apikey_TESTFAKE_123"
SIDE = ("AAPL", "TradingAgentsStrategy_logs", "jev_review_2026-10-12.json")
DECISION_FIELDS = ("final_rating", "final_trade_decision", "investment_plan",
                   "trader_investment_plan", "sentiment_report")


def _state(**over):
    s = {
        "company_of_interest": "AAPL",
        "trade_date": "2026-10-12",
        "final_trade_decision": "We lean towards adding to the position on strength.",
        "investment_plan": "**Recommendation**: Hold\n\nWait for earnings.",
        "trader_investment_plan": "Entry 180.\n\nFINAL TRANSACTION PROPOSAL: **BUY**",
        "sentiment_report": "**Overall Sentiment:** **Mildly Bullish** (Score: 6.5/10)\n\nok",
        "final_rating": "REVIEW",
        "portfolio_context": "",
        "run_settings": {"llm_provider": "anthropic"},
    }
    s.update(over)
    return s


def _cfg(tmp_path, **over):
    c = {"jev_enabled": True, "jev_min_confidence": 0.9, "jev_timeout": 5.0,
         "results_dir": str(tmp_path)}
    c.update(over)
    return c


def _resp(**answers):
    """answers: qid -> (choice, confidence)."""
    return {"model": "jev-1.13.0",
            "answers": {q: {"type": "choice", "choice": c, "confidence": conf}
                        for q, (c, conf) in answers.items()},
            "usage": {"input_tokens": 5000, "output_tokens": 40}}


@pytest.fixture
def jev(monkeypatch):
    """Fake transport: set ``.result`` (dict returned, exception raised); ``.bodies`` records."""
    class _Fake:
        result: object = None
        bodies: list = []

    fake = _Fake()
    fake.bodies = []

    def fake_post(body, key, ctx, timeout):
        fake.bodies.append(body)
        if isinstance(fake.result, BaseException):
            raise fake.result
        return fake.result

    monkeypatch.setattr(client, "_post", fake_post)
    monkeypatch.setattr(client.time, "sleep", lambda s: None)
    monkeypatch.setenv("JEV_API_KEY", FAKE_KEY)
    return fake


# ------------------------------------------------------------------ (a) gate
@pytest.mark.unit
def test_disabled_does_nothing(jev, tmp_path):
    s = _state()
    before = copy.deepcopy(s)
    hooks.review_run(s, _cfg(tmp_path, jev_enabled=False))
    assert s == before and jev.bodies == []
    assert not tmp_path.joinpath(*SIDE).exists()


@pytest.mark.unit
def test_enabled_without_a_key_does_nothing(jev, tmp_path, monkeypatch):
    monkeypatch.delenv("JEV_API_KEY")
    s = _state()
    before = copy.deepcopy(s)
    hooks.review_run(s, _cfg(tmp_path))
    assert s == before and jev.bodies == []
    assert not tmp_path.joinpath(*SIDE).exists()


@pytest.mark.unit
def test_nothing_to_classify_sends_nothing(jev, tmp_path):
    s = {"company_of_interest": "AAPL", "trade_date": "2026-10-12"}
    hooks.review_run(s, _cfg(tmp_path))
    assert jev.bodies == [] and "jev" not in s


# -------------------------------------------------------------- (b)(c) fallback
@pytest.mark.unit
@pytest.mark.parametrize("over", [{}, {"final_rating": None}])
def test_review_falls_back_to_a_confident_jev_tier(jev, tmp_path, caplog, over):
    jev.result = _resp(final_rating=("overweight", 0.95))
    s = _state(**over)
    with caplog.at_level(logging.WARNING, logger="tradingagents.jev.hooks"):
        hooks.review_run(s, _cfg(tmp_path))
    assert s["final_rating"] == "Overweight"
    assert s["final_rating_source"] == "jev"
    rec = s["jev"]["questions"]["final_rating"]
    assert rec["applied"] is True and rec["existing"] == "REVIEW" and rec["jev"] == "overweight"
    assert "Jev fallback: REVIEW -> Overweight" in caplog.text


@pytest.mark.unit
@pytest.mark.parametrize("answer", [("overweight", 0.6), ("other", 0.99), ("overweight", None)])
def test_review_stays_without_a_confident_tier(jev, tmp_path, answer):
    jev.result = _resp(final_rating=answer)
    s = _state()
    hooks.review_run(s, _cfg(tmp_path))
    assert s["final_rating"] == "REVIEW"
    assert "final_rating_source" not in s
    assert s["jev"]["questions"]["final_rating"]["applied"] is False


# --------------------------------------------------------------- (d) failures
@pytest.mark.unit
@pytest.mark.parametrize("result", [
    urllib.error.HTTPError(client.ENDPOINT, 500, "err", {}, io.BytesIO(b"boom")),
    TimeoutError(),
    {"answers": "garbage"},
    RuntimeError("unexpected"),
])
def test_a_failure_is_one_warning_and_changes_nothing(jev, tmp_path, caplog, result):
    jev.result = result
    s = _state()
    before = {k: s[k] for k in DECISION_FIELDS}
    with caplog.at_level(logging.WARNING, logger="tradingagents.jev"):
        hooks.review_run(s, _cfg(tmp_path))
    assert {k: s[k] for k in DECISION_FIELDS} == before
    assert "final_rating_source" not in s
    assert set(s["jev"]) == {"error"}
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "Jev review skipped" in warnings[0].getMessage()


# ----------------------------------------------------------------- (e) shadow
@pytest.mark.unit
def test_shadow_records_agreement_and_never_changes_decisions(jev, tmp_path):
    jev.result = _resp(final_rating=("buy", 0.97), research_recommendation=("sell", 0.93),
                       trader_action=("buy", 0.99), sentiment_band=("mildly_bullish", 0.9))
    s = _state(final_rating="Buy")
    before = {k: s[k] for k in DECISION_FIELDS}
    hooks.review_run(s, _cfg(tmp_path))
    assert {k: s[k] for k in DECISION_FIELDS} == before
    assert "final_rating_source" not in s
    q = s["jev"]["questions"]
    assert q["final_rating"] == {"existing": "Buy", "jev": "buy", "confidence": 0.97,
                                 "agree": True, "applied": False}
    assert q["research_recommendation"]["existing"] == "Hold"
    assert q["research_recommendation"]["agree"] is False
    assert q["trader_action"]["existing"] == "BUY" and q["trader_action"]["agree"] is True
    assert q["sentiment_band"]["existing"] == "Mildly Bullish"
    assert q["sentiment_band"]["agree"] is True
    assert all(r["applied"] is False for r in q.values())
    assert s["jev"]["input_tokens"] == 5000 and s["jev"]["cost_usd"] == 0.00021
    assert s["jev"]["attempts"] == 1 and s["jev"]["model"] == "jev-1.13.0"


@pytest.mark.unit
def test_shadow_without_a_header_has_no_existing_value(jev, tmp_path):
    jev.result = _resp(sentiment_band=("neutral", 0.95), final_rating=("buy", 0.95))
    s = _state(sentiment_report="Sentiment is broadly neutral.", final_rating="Buy")
    hooks.review_run(s, _cfg(tmp_path))
    rec = s["jev"]["questions"]["sentiment_band"]
    assert rec["existing"] is None and rec["agree"] is None


@pytest.mark.unit
def test_a_question_jev_did_not_answer_has_no_agreement(jev, tmp_path):
    jev.result = _resp(final_rating=("buy", 0.95))
    s = _state(final_rating="Buy")
    hooks.review_run(s, _cfg(tmp_path))
    rec = s["jev"]["questions"]["trader_action"]
    assert rec["jev"] is None and rec["agree"] is None


# --------------------------------------------------------------- (f) no leaks
@pytest.mark.unit
def test_the_key_never_leaks(jev, tmp_path, caplog):
    jev.result = urllib.error.URLError("refused for " + FAKE_KEY)
    s = _state()
    with caplog.at_level(logging.DEBUG):
        hooks.review_run(s, _cfg(tmp_path))
    assert FAKE_KEY not in caplog.text
    assert FAKE_KEY not in json.dumps(s["jev"])

    jev.result = _resp(final_rating=("overweight", 0.95))
    s = _state()
    with caplog.at_level(logging.DEBUG):
        hooks.review_run(s, _cfg(tmp_path))
    assert FAKE_KEY not in caplog.text
    assert FAKE_KEY not in tmp_path.joinpath(*SIDE).read_text(encoding="utf-8")


# ----------------------------------------------------------- (g) data sent
@pytest.mark.unit
def test_only_the_analysis_texts_are_sent(jev, tmp_path):
    jev.result = _resp(final_rating=("buy", 0.95))
    hooks.review_run(_state(trader_investment_plan=""), _cfg(tmp_path))
    (body,) = jev.bodies
    assert set(body["state"]) == {"decision", "plan", "sentiment"}
    assert set(body["questions"]) == {"final_rating", "research_recommendation", "sentiment_band"}
    sent = json.dumps(body)
    for secret in ("anthropic", FAKE_KEY, "results_dir"):
        assert secret not in sent
    for q in body["questions"].values():
        assert "other" in q["criteria"]


@pytest.mark.unit
def test_a_run_with_a_portfolio_context_is_not_sent(jev, tmp_path):
    # Any of the analysis texts may quote the holdings the run was given.
    jev.result = _resp(final_rating=("buy", 0.95))
    s = _state(portfolio_context="Current position in AAPL: 120 units; cash 50,000 (account U1234567)",
               final_trade_decision="Hold the 120 units in account U1234567.",
               trader_investment_plan="Keep 120 units.\n\nFINAL TRANSACTION PROPOSAL: **HOLD**")
    before = copy.deepcopy(s)
    hooks.review_run(s, _cfg(tmp_path))
    assert jev.bodies == []
    assert s == before
    assert not tmp_path.joinpath(*SIDE).exists()


# ----------------------------------------------------------------- (i) sidecar
@pytest.mark.unit
def test_the_review_is_written_next_to_the_state_log(jev, tmp_path):
    jev.result = _resp(final_rating=("overweight", 0.95))
    s = _state()
    hooks.review_run(s, _cfg(tmp_path))
    assert json.loads(tmp_path.joinpath(*SIDE).read_text(encoding="utf-8")) == s["jev"]


@pytest.mark.unit
def test_a_sidecar_failure_keeps_the_fallback(jev, tmp_path, monkeypatch):
    jev.result = _resp(final_rating=("overweight", 0.95))
    s = _state(company_of_interest="../evil")
    hooks.review_run(s, _cfg(tmp_path))
    assert s["final_rating"] == "Overweight" and s["final_rating_source"] == "jev"
    assert "questions" in s["jev"]


# ------------------------------------------------------------------ (h) wiring
def _graph(tmp_path, **cfg):
    graph = object.__new__(TradingAgentsGraph)
    graph.config = _cfg(tmp_path, **cfg)
    graph.memory_log = MagicMock()
    graph._log_state = lambda *a: None
    return graph


@pytest.mark.unit
def test_record_decision_stores_the_fallback_rating(jev, tmp_path):
    jev.result = _resp(final_rating=("overweight", 0.95))
    graph = _graph(tmp_path)
    graph.record_decision("AAPL", "2026-10-12", _state())
    assert graph.memory_log.store_decision.call_args.kwargs["rating"] == "Overweight"


@pytest.mark.unit
def test_record_decision_without_jev_keeps_review(jev, tmp_path):
    graph = _graph(tmp_path, jev_enabled=False)
    graph.record_decision("AAPL", "2026-10-12", _state())
    assert graph.memory_log.store_decision.call_args.kwargs["rating"] == "REVIEW"
    assert jev.bodies == []
