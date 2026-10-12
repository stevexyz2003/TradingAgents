"""Manual one-shot live smoke of the Jev run review (not collected by pytest).

    .venv/Scripts/python.exe scripts/smoke/jev_live_smoke.py

Needs JEV_API_KEY (env or the gitignored .env, which the package loads on
import); without it the smoke prints SKIPPED and exits 0. The fixture is made
up and carries no portfolio or account data. The key is never printed.
"""

from __future__ import annotations

import copy
import datetime
import json
import logging
import sys
import tempfile

import tradingagents  # noqa: F401  (loads .env)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.jev import client, hooks

DECISION = """## Portfolio Manager Decision for AAPL

After weighing the debate, we want more exposure than the benchmark weight but
not a full-conviction entry: services growth and buybacks support the case,
while China demand and the valuation argue for building the position gradually
rather than all at once. Add in tranches over the coming weeks.
"""

PLAN = "**Recommendation**: Hold\n\nWait for the earnings print before adding."
PROPOSAL = "Entry near support, stop below the 50-day average.\n\nFINAL TRANSACTION PROPOSAL: **HOLD**"
SENTIMENT = ("**Overall Sentiment:** **Neutral** (Score: 5.0/10)\n\n"
             "Retail chatter is balanced between upgrade hopes and China worries.")


def main() -> int:
    key = client.get_api_key()
    if not key:
        print("SKIPPED: JEV_API_KEY not set")
        return 0
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config = copy.deepcopy(DEFAULT_CONFIG)
    config.update(jev_enabled=True, results_dir=tempfile.mkdtemp(prefix="jev-smoke-"))
    state = {
        "company_of_interest": "AAPL",
        "trade_date": datetime.date.today().isoformat(),
        "final_trade_decision": DECISION,
        "investment_plan": PLAN,
        "trader_investment_plan": PROPOSAL,
        "sentiment_report": SENTIMENT,
    }
    hooks.review_run(state, config)
    out = {
        "final_rating": state.get("final_rating"),
        "final_rating_source": state.get("final_rating_source"),
        "jev": state.get("jev"),
    }
    print(client.redact(json.dumps(out, indent=2, ensure_ascii=False), key))
    return 0 if "error" not in (state.get("jev") or {}) else 1


if __name__ == "__main__":
    sys.exit(main())
