"""Per-run LLM budget enforcement (#582).

A :class:`SpendTracker` callback handler accumulates token usage (and, when
``model_cost_rates`` are configured, USD cost) across every LLM call of a run
and aborts the run with :class:`BudgetExceededError` *before* the next LLM
call once a limit is exceeded (check-before-spend).

There is deliberately no hardcoded price table: users supply
``model_cost_rates`` as ``{"<model>": {"input": usd_per_1M_input_tokens,
"output": usd_per_1M_output_tokens}}``.  When ``max_cost_per_run`` is set
without usable rates, :func:`build_spend_tracker` fails fast with
:class:`BudgetConfigError` at graph construction time — silent zero-cost
counting is never acceptable.
"""

import logging
import threading
from typing import Any, Dict, Iterable, List, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)


class BudgetExceededError(RuntimeError):
    """Raised before the next LLM call once a per-run budget is exhausted."""

    def __init__(
        self,
        message: str,
        *,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost: float = 0.0,
    ) -> None:
        super().__init__(message)
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.cost = cost


class BudgetConfigError(ValueError):
    """Raised when ``max_cost_per_run`` is set without usable model_cost_rates."""


def ensure_rates_configured(
    model_cost_rates: Optional[Dict[str, Any]], model_names: Iterable[str]
) -> None:
    """Fail fast unless every model has input+output rates configured.

    Raises:
        BudgetConfigError: naming each model that lacks a usable rate entry.
    """
    rates = model_cost_rates or {}
    missing = []
    for name in model_names:
        entry = rates.get(name)
        if not isinstance(entry, dict) or "input" not in entry or "output" not in entry:
            missing.append(str(name))
    if missing:
        raise BudgetConfigError(
            "max_cost_per_run is set but model_cost_rates lacks usable entries for: "
            + ", ".join(dict.fromkeys(missing))
            + '. Configure config["model_cost_rates"] as {"<model>": {"input": '
            "<usd_per_1M_input_tokens>, \"output\": <usd_per_1M_output_tokens>}} "
            "or use max_tokens_per_run for a rate-free limit."
        )


class SpendTracker(BaseCallbackHandler):
    """Callback handler enforcing per-run cost/token budgets (check-before-spend).

    Token usage is accumulated in ``on_llm_end``; the budget is checked in
    ``on_chat_model_start``/``on_llm_start`` so an exhausted budget aborts the
    run *before* the next expensive call goes out.
    """

    # CRITICAL: langchain_core's callback manager swallows handler exceptions
    # (logger.warning only) unless raise_error is True.  Without this class
    # attribute BudgetExceededError would never abort the run.  The flip side:
    # ANY unhandled exception inside this handler kills the run, so every
    # response extraction below must be defensive.
    raise_error = True

    def __init__(
        self,
        max_cost: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model_cost_rates: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self.max_cost = max_cost
        self.max_tokens = max_tokens
        self.model_cost_rates = model_cost_rates or {}
        self.tokens_in = 0
        self.tokens_out = 0
        self.cost = 0.0
        self._warned_models = set()

    def reset(self) -> None:
        """Zero the per-run counters.

        Budgets are per *run*: a reused graph instance must not inherit the
        spend of earlier ``propagate()``/``stream_run()`` calls, or the limit
        trips runs early (or immediately) after the first one.
        """
        with self._lock:
            self.tokens_in = 0
            self.tokens_out = 0
            self.cost = 0.0

    # -- budget check (before the next call goes out) ----------------------

    def _check_budget(self) -> None:
        with self._lock:
            tokens_in = self.tokens_in
            tokens_out = self.tokens_out
            cost = self.cost
        tokens_total = tokens_in + tokens_out
        if self.max_cost is not None and cost > self.max_cost:
            raise BudgetExceededError(
                f"Cost budget exceeded: accumulated ${cost:.4f} > "
                f"max_cost_per_run ${self.max_cost:.4f} "
                f"({tokens_in} input / {tokens_out} output tokens). "
                "Aborting before the next LLM call.",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost=cost,
            )
        if self.max_tokens is not None and tokens_total > self.max_tokens:
            raise BudgetExceededError(
                f"Token budget exceeded: accumulated {tokens_total} tokens "
                f"({tokens_in} input / {tokens_out} output) > "
                f"max_tokens_per_run {self.max_tokens}. "
                "Aborting before the next LLM call.",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost=cost,
            )

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        self._check_budget()

    def on_chat_model_start(
        self, serialized: Dict[str, Any], messages: List[List[Any]], **kwargs: Any
    ) -> None:
        self._check_budget()

    # -- accumulation -------------------------------------------------------

    def _resolve_rate(self, model_name: Optional[str]) -> Optional[Dict[str, Any]]:
        """Resolve the rate entry for ``model_name``.

        Providers routinely report revision/deployment names (e.g.
        ``gpt-5.4-2026-01-01``) that extend the configured name, so an exact
        miss falls back to a prefix match in either direction. A model that
        matches nothing is billed at the most expensive configured rate —
        overestimating is the only safe direction once ``max_cost_per_run``
        is active; counting zero would silently disable the budget.
        """
        if model_name:
            entry = self.model_cost_rates.get(model_name)
            if isinstance(entry, dict):
                return entry
            for configured, rates in self.model_cost_rates.items():
                if not isinstance(rates, dict) or not isinstance(configured, str):
                    continue
                if model_name.startswith(configured) or configured.startswith(
                    model_name
                ):
                    return rates

        usable = [r for r in self.model_cost_rates.values() if isinstance(r, dict)]
        if not usable:
            return None

        key = model_name or "<unknown model>"
        if key not in self._warned_models:
            self._warned_models.add(key)
            logger.warning(
                "No cost rate configured for model %s — billing it at the most "
                "expensive configured rate so max_cost_per_run stays enforced.",
                key,
            )

        def _rate_value(rate: Dict[str, Any]) -> float:
            try:
                return float(rate.get("input", 0) or 0) + float(
                    rate.get("output", 0) or 0
                )
            except (TypeError, ValueError):
                return 0.0

        return max(usable, key=_rate_value)

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Accumulate token usage/cost; must never raise on malformed input."""
        try:
            generation = response.generations[0][0]
        except (IndexError, TypeError, AttributeError):
            return

        message = None
        usage_metadata = None
        if hasattr(generation, "message"):
            message = generation.message
            usage_metadata = getattr(message, "usage_metadata", None)

        if not usage_metadata:
            return

        try:
            input_tokens = int(usage_metadata.get("input_tokens", 0) or 0)
            output_tokens = int(usage_metadata.get("output_tokens", 0) or 0)
        except (AttributeError, TypeError, ValueError):
            return

        call_cost = 0.0
        if self.max_cost is not None:
            model_name = (response.llm_output or {}).get("model_name")
            if not model_name:
                model_name = (getattr(message, "response_metadata", None) or {}).get(
                    "model_name"
                )
            rate = self._resolve_rate(model_name)
            if rate is not None:
                try:
                    call_cost = (
                        input_tokens * float(rate.get("input", 0) or 0)
                        + output_tokens * float(rate.get("output", 0) or 0)
                    ) / 1_000_000
                except (TypeError, ValueError):
                    call_cost = 0.0

        with self._lock:
            self.tokens_in += input_tokens
            self.tokens_out += output_tokens
            self.cost += call_cost


def build_spend_tracker(config: Dict[str, Any]) -> Optional[SpendTracker]:
    """Build a SpendTracker from config, or None when no limit is set.

    Validation authority for the cost path lives HERE so both the CLI and
    Python-API users fail fast at graph construction when
    ``max_cost_per_run`` is set without rates for the configured models.

    Raises:
        BudgetConfigError: when max_cost_per_run is set but model_cost_rates
            lacks entries for the deep/quick think models.
    """
    max_cost = config.get("max_cost_per_run")
    max_tokens = config.get("max_tokens_per_run")
    if max_cost is None and max_tokens is None:
        return None

    model_cost_rates = config.get("model_cost_rates") or {}
    if max_cost is not None:
        ensure_rates_configured(
            model_cost_rates,
            [config["deep_think_llm"], config["quick_think_llm"]],
        )

    return SpendTracker(
        max_cost=max_cost,
        max_tokens=max_tokens,
        model_cost_rates=model_cost_rates,
    )
