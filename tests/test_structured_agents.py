"""Tests for structured-output agents (Trader and Research Manager).

The Portfolio Manager has its own coverage in tests/test_memory_log.py
(which exercises the full memory-log → PM injection cycle).  This file
covers the parallel schemas, render functions, and graceful-fallback
behavior we added for the Trader and Research Manager so all three
decision-making agents share the same shape.
"""

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.schemas import (
    PortfolioRating,
    ResearchPlan,
    TraderAction,
    TraderProposal,
    render_research_plan,
    render_trader_proposal,
)
from tradingagents.agents.trader.trader import create_trader
from tradingagents.agents.utils.structured import invoke_structured_or_freetext
from tradingagents.budget import BudgetExceededError


# ---------------------------------------------------------------------------
# Render functions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenderTraderProposal:
    def test_minimal_required_fields(self):
        p = TraderProposal(action=TraderAction.HOLD, reasoning="Balanced setup; no edge.")
        md = render_trader_proposal(p)
        assert "**Action**: Hold" in md
        assert "**Reasoning**: Balanced setup; no edge." in md
        # The trailing FINAL TRANSACTION PROPOSAL line is preserved for the
        # analyst stop-signal text and any external code that greps for it.
        assert "FINAL TRANSACTION PROPOSAL: **HOLD**" in md

    def test_optional_fields_included_when_present(self):
        p = TraderProposal(
            action=TraderAction.BUY,
            reasoning="Strong technicals + fundamentals.",
            entry_price=189.5,
            stop_loss=178.0,
            position_sizing="6% of portfolio",
        )
        md = render_trader_proposal(p)
        assert "**Action**: Buy" in md
        assert "**Entry Price**: 189.5" in md
        assert "**Stop Loss**: 178.0" in md
        assert "**Position Sizing**: 6% of portfolio" in md
        assert "FINAL TRANSACTION PROPOSAL: **BUY**" in md

    def test_optional_fields_omitted_when_absent(self):
        p = TraderProposal(action=TraderAction.SELL, reasoning="Guidance cut.")
        md = render_trader_proposal(p)
        assert "Entry Price" not in md
        assert "Stop Loss" not in md
        assert "Position Sizing" not in md
        assert "FINAL TRANSACTION PROPOSAL: **SELL**" in md


@pytest.mark.unit
class TestRenderResearchPlan:
    def test_required_fields(self):
        p = ResearchPlan(
            recommendation=PortfolioRating.OVERWEIGHT,
            rationale="Bull case carried; tailwinds intact.",
            strategic_actions="Build position over two weeks; cap at 5%.",
        )
        md = render_research_plan(p)
        assert "**Recommendation**: Overweight" in md
        assert "**Rationale**: Bull case carried" in md
        assert "**Strategic Actions**: Build position" in md

    def test_all_5_tier_ratings_render(self):
        for rating in PortfolioRating:
            p = ResearchPlan(
                recommendation=rating,
                rationale="r",
                strategic_actions="s",
            )
            md = render_research_plan(p)
            assert f"**Recommendation**: {rating.value}" in md


# ---------------------------------------------------------------------------
# Trader agent: structured happy path + fallback
# ---------------------------------------------------------------------------


def _make_trader_state():
    return {
        "company_of_interest": "NVDA",
        "investment_plan": "**Recommendation**: Buy\n**Rationale**: ...\n**Strategic Actions**: ...",
    }


def _structured_trader_llm(captured: dict, proposal: TraderProposal | None = None):
    """Build a MagicMock LLM whose with_structured_output binding captures the
    prompt and returns a real TraderProposal so render_trader_proposal works.
    """
    if proposal is None:
        proposal = TraderProposal(
            action=TraderAction.BUY,
            reasoning="Strong setup.",
        )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or proposal
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestTraderAgent:
    def test_structured_path_produces_rendered_markdown(self):
        captured = {}
        proposal = TraderProposal(
            action=TraderAction.BUY,
            reasoning="AI capex cycle intact; institutional flows constructive.",
            entry_price=189.5,
            stop_loss=178.0,
            position_sizing="6% of portfolio",
        )
        llm = _structured_trader_llm(captured, proposal)
        trader = create_trader(llm)
        result = trader(_make_trader_state())
        plan = result["trader_investment_plan"]
        assert "**Action**: Buy" in plan
        assert "**Entry Price**: 189.5" in plan
        assert "FINAL TRANSACTION PROPOSAL: **BUY**" in plan
        # The same rendered markdown is also added to messages for downstream agents.
        assert plan in result["messages"][0].content

    def test_prompt_includes_investment_plan(self):
        captured = {}
        llm = _structured_trader_llm(captured)
        trader = create_trader(llm)
        trader(_make_trader_state())
        # The investment plan is in the user message of the captured prompt.
        prompt = captured["prompt"]
        assert any("Proposed Investment Plan" in m["content"] for m in prompt)

    def test_falls_back_to_freetext_when_structured_unavailable(self):
        plain_response = (
            "**Action**: Sell\n\nGuidance cut hits margins.\n\n"
            "FINAL TRANSACTION PROPOSAL: **SELL**"
        )
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
        llm.invoke.return_value = MagicMock(content=plain_response)
        trader = create_trader(llm)
        result = trader(_make_trader_state())
        assert result["trader_investment_plan"] == plain_response


# ---------------------------------------------------------------------------
# Research Manager agent: structured happy path + fallback
# ---------------------------------------------------------------------------


def _make_rm_state():
    return {
        "company_of_interest": "NVDA",
        "investment_debate_state": {
            "history": "Bull and bear arguments here.",
            "bull_history": "Bull says...",
            "bear_history": "Bear says...",
            "current_response": "",
            "judge_decision": "",
            "count": 1,
        },
    }


def _structured_rm_llm(captured: dict, plan: ResearchPlan | None = None):
    if plan is None:
        plan = ResearchPlan(
            recommendation=PortfolioRating.HOLD,
            rationale="Balanced view across both sides.",
            strategic_actions="Hold current position; reassess after earnings.",
        )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or plan
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestResearchManagerAgent:
    def test_structured_path_produces_rendered_markdown(self):
        captured = {}
        plan = ResearchPlan(
            recommendation=PortfolioRating.OVERWEIGHT,
            rationale="Bull case is stronger; AI tailwind intact.",
            strategic_actions="Build position gradually over two weeks.",
        )
        llm = _structured_rm_llm(captured, plan)
        rm = create_research_manager(llm)
        result = rm(_make_rm_state())
        ip = result["investment_plan"]
        assert "**Recommendation**: Overweight" in ip
        assert "**Rationale**: Bull case" in ip
        assert "**Strategic Actions**: Build position" in ip

    def test_prompt_uses_5_tier_rating_scale(self):
        """The RM prompt must list all five tiers so the schema enum matches user expectations."""
        captured = {}
        llm = _structured_rm_llm(captured)
        rm = create_research_manager(llm)
        rm(_make_rm_state())
        prompt = captured["prompt"]
        for tier in ("Buy", "Overweight", "Hold", "Underweight", "Sell"):
            assert f"**{tier}**" in prompt, f"missing {tier} in prompt"

    def test_falls_back_to_freetext_when_structured_unavailable(self):
        plain_response = "**Recommendation**: Sell\n\n**Rationale**: ...\n\n**Strategic Actions**: ..."
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
        llm.invoke.return_value = MagicMock(content=plain_response)
        rm = create_research_manager(llm)
        result = rm(_make_rm_state())
        assert result["investment_plan"] == plain_response


# ---------------------------------------------------------------------------
# Schema hardening (#583): one retry with error context, then prose fallback
# ---------------------------------------------------------------------------


def _sample_plan():
    return ResearchPlan(
        recommendation=PortfolioRating.HOLD,
        rationale="Balanced view.",
        strategic_actions="Hold and reassess.",
    )


@pytest.mark.unit
class TestRetryThenFallback:
    def test_retry_succeeds_with_error_context_str_prompt(self):
        """First failure triggers exactly one retry whose prompt carries the error."""
        plan = _sample_plan()
        structured = MagicMock()
        structured.invoke.side_effect = [Exception("bad json"), plan]
        plain = MagicMock()

        result = invoke_structured_or_freetext(
            structured, plain, "original prompt", render_research_plan, "TestAgent"
        )

        assert result == render_research_plan(plan)
        plain.invoke.assert_not_called()
        assert structured.invoke.call_count == 2
        retry_prompt = structured.invoke.call_args_list[1].args[0]
        assert isinstance(retry_prompt, str)
        assert "original prompt" in retry_prompt
        assert "bad json" in retry_prompt

    def test_double_failure_falls_back_with_original_prompt(self):
        """Retry failure falls back to prose with the ORIGINAL prompt, no raise."""
        structured = MagicMock()
        structured.invoke.side_effect = [Exception("bad json"), Exception("still bad")]
        plain = MagicMock()
        plain.invoke.return_value = MagicMock(content="prose text")

        result = invoke_structured_or_freetext(
            structured, plain, "original prompt", render_research_plan, "TestAgent"
        )

        assert result == "prose text"
        assert structured.invoke.call_count == 2
        plain.invoke.assert_called_once_with("original prompt")

    def test_list_prompt_retry_appends_user_message_without_mutation(self):
        """Trader-form message lists get an appended user message; original unchanged."""
        plan = _sample_plan()
        structured = MagicMock()
        structured.invoke.side_effect = [Exception("bad json"), plan]
        plain = MagicMock()
        original = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "user input"},
        ]
        snapshot = [dict(m) for m in original]

        result = invoke_structured_or_freetext(
            structured, plain, original, render_research_plan, "TestAgent"
        )

        assert result == render_research_plan(plan)
        assert original == snapshot  # original list not mutated
        retry_prompt = structured.invoke.call_args_list[1].args[0]
        assert retry_prompt is not original
        assert retry_prompt[:2] == snapshot
        assert retry_prompt[-1]["role"] == "user"
        assert "bad json" in retry_prompt[-1]["content"]

    def test_budget_exceeded_propagates_without_retry(self):
        """A budget abort is not a schema failure: no retry, no prose fallback."""
        structured = MagicMock()
        structured.invoke.side_effect = BudgetExceededError("cost limit hit")
        plain = MagicMock()

        with pytest.raises(BudgetExceededError):
            invoke_structured_or_freetext(
                structured, plain, "p", render_research_plan, "TestAgent"
            )

        assert structured.invoke.call_count == 1
        plain.invoke.assert_not_called()

    def test_budget_exceeded_on_retry_propagates_without_fallback(self):
        structured = MagicMock()
        structured.invoke.side_effect = [
            Exception("bad json"),
            BudgetExceededError("cost limit hit"),
        ]
        plain = MagicMock()

        with pytest.raises(BudgetExceededError):
            invoke_structured_or_freetext(
                structured, plain, "p", render_research_plan, "TestAgent"
            )

        assert structured.invoke.call_count == 2
        plain.invoke.assert_not_called()
