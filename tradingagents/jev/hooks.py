"""Jev review of a finished run, called first thing in ``record_decision``.

One request per ticker over the run's analysis texts:

- ``final_rating``: FALLBACK. Only when the engine's rating is REVIEW and Jev
  names one of the five tiers at ``jev_min_confidence`` or above, that tier
  becomes the run's rating, marked ``final_rating_source = "jev"``.
- ``research_recommendation``, ``trader_action``, ``sentiment_band`` (and
  ``final_rating`` when it is not REVIEW): SHADOW. Recorded with agreement,
  never applied.

Off unless ``jev_enabled`` and ``JEV_API_KEY`` are both set; every failure is a
single redacted warning and leaves the run as it was.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from tradingagents.agents.rating import RATING_REVIEW, RATINGS_5_TIER, run_rating

logger = logging.getLogger(__name__)

# final_state field -> name in the request's state object. Nothing else is sent.
_STATE_FIELDS = {
    "final_trade_decision": "decision",
    "investment_plan": "plan",
    "trader_investment_plan": "proposal",
    "sentiment_report": "sentiment",
}

# Option order deliberately does not lead with the most common answer.
_TIERS = {
    "underweight": "Reduce exposure: trim the position or hold less than the benchmark weight.",
    "buy": "Open or add to a long position with conviction.",
    "hold": "Keep the current position unchanged; no action.",
    "sell": "Exit the position or avoid it entirely.",
    "overweight": "Lean bullish: hold more than the benchmark weight or add gradually.",
}

_QUESTIONS = {
    "final_rating": ("decision", {
        "type": "choice",
        "instructions": "Which single rating does `decision` itself commit to for the position "
                        "(not a rating it quotes from someone else)?",
        "criteria": {**_TIERS, "other": "No single own rating, or several conflicting ones."},
    }),
    "research_recommendation": ("plan", {
        "type": "choice",
        "instructions": "Which recommendation does `plan` commit to?",
        "criteria": {**_TIERS, "other": "No single recommendation, or several conflicting ones."},
    }),
    "trader_action": ("proposal", {
        "type": "choice",
        "instructions": "Which transaction does `proposal` itself propose?",
        "criteria": {
            "sell": "Sell or exit the position.",
            "buy": "Buy or add to the position.",
            "hold": "Keep the position as it is; no transaction.",
            "other": "No single transaction, or several conflicting ones.",
        },
    }),
    "sentiment_band": ("sentiment", {
        "type": "choice",
        "instructions": "Which overall sentiment band does `sentiment` conclude?",
        "criteria": {
            "mixed": "Strong bullish and bearish views are both present without a lean.",
            "bearish": "Clearly negative overall.",
            "mildly_bullish": "Somewhat positive, with reservations.",
            "neutral": "Little opinion either way.",
            "bullish": "Clearly positive overall.",
            "mildly_bearish": "Somewhat negative, with reservations.",
            "other": "No overall sentiment conclusion.",
        },
    }),
}

_RESEARCH_RE = re.compile(r"^\*\*Recommendation\*\*:\s*(\w+)", re.MULTILINE)
_TRADER_RE = re.compile(r"FINAL TRANSACTION PROPOSAL:\s*\*\*(BUY|HOLD|SELL)\*\*")
_SENTIMENT_RE = re.compile(r"\*\*Overall Sentiment:\*\*\s*\*\*([^*]+)\*\*")


def _match(pattern: re.Pattern, text) -> str | None:
    m = pattern.search(text or "")
    return m.group(1).strip() if m else None


def _existing(qid: str, final_state: dict) -> str | None:
    if qid == "final_rating":
        return run_rating(final_state)
    if qid == "research_recommendation":
        return _match(_RESEARCH_RE, final_state.get("investment_plan"))
    if qid == "trader_action":
        return _match(_TRADER_RE, final_state.get("trader_investment_plan"))
    return _match(_SENTIMENT_RE, final_state.get("sentiment_report"))


def _norm(value) -> str:
    return str(value).replace("_", " ").strip().lower()


def review_run(final_state: dict, config: dict) -> None:
    """Classify the run's texts with Jev; apply the REVIEW fallback; record the shadow checks."""
    if not config.get("jev_enabled"):
        return
    from tradingagents.jev import client

    key = client.get_api_key()
    if not key:
        return

    applied_tier = None
    try:
        state = {name: final_state[field] for field, name in _STATE_FIELDS.items()
                 if final_state.get(field)}
        questions = {qid: q for qid, (needs, q) in _QUESTIONS.items() if needs in state}
        if not questions:
            return
        body = client.build_request({"state": state, "questions": questions})
        t0 = time.perf_counter()
        resp, attempts = client.call_api(body, key, float(config.get("jev_timeout", 5.0)))
        latency_ms = round((time.perf_counter() - t0) * 1000)
        answers = client.summarize(resp)
        min_conf = float(config.get("jev_min_confidence", 0.9))

        records = {}
        for qid in questions:
            existing = _existing(qid, final_state)
            ans = answers.get(qid) or {}
            answer, conf = ans.get("answer"), ans.get("confidence")
            agree = None if existing is None or answer is None else _norm(existing) == _norm(answer)
            applied = False
            if (qid == "final_rating" and existing == RATING_REVIEW
                    and isinstance(answer, str) and answer.capitalize() in RATINGS_5_TIER
                    and isinstance(conf, (int, float)) and conf >= min_conf):
                applied = True
                applied_tier = answer.capitalize()
            elif agree is False:
                logger.info("Jev shadow disagreement on %s: engine %s, jev %s (conf %s)",
                            qid, existing, answer, conf)
            elif agree:
                logger.debug("Jev shadow agreement on %s: %s (conf %s)", qid, existing, conf)
            records[qid] = {"existing": existing, "jev": answer, "confidence": conf,
                            "agree": agree, "applied": applied}

        usage = resp.get("usage") or {}
        result = {
            "model": resp.get("model"),
            "input_tokens": usage.get("input_tokens"),
            "cost_usd": client.direct_cost(usage),
            "latency_ms": latency_ms,
            "attempts": attempts,
            "min_confidence": min_conf,
            "questions": records,
        }
    except Exception as exc:
        text = client.redact(f"{type(exc).__name__}: {exc}", key)
        logger.warning("Jev review skipped: %s", text)
        result = {"error": text}
        applied_tier = None

    if applied_tier:
        final_state["final_rating"] = applied_tier
        final_state["final_rating_source"] = "jev"
        conf = result["questions"]["final_rating"]["confidence"]
        logger.warning("Jev fallback: REVIEW -> %s (conf %.2f)", applied_tier, conf)
    final_state["jev"] = result
    _write_sidecar(final_state, config, result, key, client)


def _write_sidecar(final_state, config, result, key, client) -> None:
    """Persist the review next to the run's state log; a failure only warns."""
    try:
        from tradingagents.dataflows.symbols import safe_ticker_component

        path = (Path(config["results_dir"])
                / safe_ticker_component(final_state["company_of_interest"])
                / "TradingAgentsStrategy_logs"
                / f"jev_review_{final_state['trade_date']}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.warning("Jev review not saved: %s",
                       client.redact(f"{type(exc).__name__}: {exc}", key))
