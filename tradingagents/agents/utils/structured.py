"""Shared helpers for invoking an agent with structured output and a graceful fallback.

The Portfolio Manager, Trader, and Research Manager all follow the same
canonical pattern:

1. At agent creation, wrap the LLM with ``with_structured_output(Schema)``
   so the model returns a typed Pydantic instance. If the provider does
   not support structured output (rare; mostly older Ollama models), the
   wrap is skipped and the agent uses free-text generation instead.
2. At invocation, run the structured call and render the result back to
   markdown. If the structured call fails (malformed JSON from a weak
   model, transient provider issue), retry once with the validation error
   appended to the prompt, then fall back to a plain ``llm.invoke`` so
   the pipeline never blocks. Budget aborts (``BudgetExceededError``)
   are re-raised untouched — they must end the run, not degrade to prose.

Centralising the pattern here keeps the agent factories small and ensures
all three agents log the same warnings when fallback fires.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, TypeVar

from pydantic import BaseModel

from tradingagents.budget import BudgetExceededError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _with_error_context(prompt: Any, exc: Exception) -> Any:
    """Return a retry prompt carrying the schema-validation error.

    Prompt-form agnostic: strings get the context appended, message-dict
    lists (Trader form) get a new user message appended to a NEW list —
    the original list is never mutated. Unknown shapes are returned as-is.
    """
    context = (
        f"Your previous response failed schema validation with this error: {exc}. "
        "Respond again and strictly match the required schema."
    )
    if isinstance(prompt, str):
        return prompt + "\n\n" + context
    if isinstance(prompt, list):
        return list(prompt) + [{"role": "user", "content": context}]
    return prompt


def bind_structured(llm: Any, schema: type[T], agent_name: str) -> Optional[Any]:
    """Return ``llm.with_structured_output(schema)`` or ``None`` if unsupported.

    Logs a warning when the binding fails so the user understands the agent
    will use free-text generation for every call instead of one-shot fallback.
    """
    try:
        return llm.with_structured_output(schema)
    except (NotImplementedError, AttributeError) as exc:
        logger.warning(
            "%s: provider does not support with_structured_output (%s); "
            "falling back to free-text generation",
            agent_name, exc,
        )
        return None


def invoke_structured_or_freetext(
    structured_llm: Optional[Any],
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
) -> str:
    """Run the structured call; retry once with error context, then fall back to prose.

    ``prompt`` is whatever the underlying LLM accepts (a string for chat
    invocations, a list of message dicts for chat models that take that
    shape). The free-text fallback always receives the ORIGINAL prompt —
    the prose LLM is not schema-bound, so error context would be noise.

    ``BudgetExceededError`` is re-raised untouched at both stages: a budget
    abort must end the run, never be repackaged as a schema failure.
    """
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            return render(result)
        except BudgetExceededError:
            raise
        except Exception as exc:
            logger.warning(
                "%s: structured-output invocation failed (%s); retrying once with error context",
                agent_name, exc,
            )
            try:
                result = structured_llm.invoke(_with_error_context(prompt, exc))
                return render(result)
            except BudgetExceededError:
                raise
            except Exception as retry_exc:
                logger.warning(
                    "%s: structured retry failed (%s); falling back to free text",
                    agent_name, retry_exc,
                )

    response = plain_llm.invoke(prompt)
    return response.content
