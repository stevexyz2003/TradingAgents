#!/usr/bin/env python3
"""Deterministic OpenAI-compatible LLM stub for the Docker smoke run.

Operational tooling, not part of the ``tradingagents`` library. Pure stdlib, so
it runs inside a bare ``python:3.13-slim`` container with nothing installed.

It serves exactly two things:

* ``POST <any prefix>/chat/completions`` — the only counted endpoint. Answers
  either with a tool call (the three decider schemas) or with plain text (every
  analyst), see ``_reply_for`` below.
* ``GET /__count`` — side-effect-free readiness probe *and* proof source,
  returns ``{"calls": n}``.

Everything else is a 404. Started by ``scripts/smoke/docker_smoke.sh`` on an
``--internal`` Docker network, so the run under test cannot reach a real
endpoint even by accident.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8000

#: The three deciders (research manager, trader, portfolio manager) each get
#: *exactly one* bound tool that carries its schema name; the analysts get their
#: data tools. So the role is read off ``request["tools"]``, never off the URL —
#: observed in the stub log during research: call 4 arrives with
#: ``tools=['ResearchPlan']``, call 5 with ``['TraderProposal']``, call 9 with
#: ``['PortfolioDecision']``.
#: Arguments are the minimum that satisfies tradingagents/agents/schemas.py.
#: Note ``strategic_actions`` is a ``str`` there, not a list.
SCHEMA_ARGS: dict[str, dict[str, str]] = {
    "ResearchPlan": {
        "recommendation": "Overweight",
        "rationale": "Stub rationale for the Docker smoke run.",
        "strategic_actions": "Keep the position and re-assess after the next print.",
    },
    "TraderProposal": {
        "action": "Buy",
        "reasoning": "Stub reasoning for the Docker smoke run.",
    },
    "PortfolioDecision": {
        "rating": "Overweight",
        "executive_summary": "Stub executive summary for the Docker smoke run.",
        "investment_thesis": "Stub investment thesis for the Docker smoke run.",
    },
}

#: Canonical minimal analyst answer, verbatim from tests/test_graph_end_to_end.py:32.
#: An analyst must get *plain text*: ``_tools_or_done`` only ends an analyst once
#: ``tool_calls`` is empty (tradingagents/graph/setup.py:48-50), so answering an
#: analyst with a tool call makes it request data tools forever.
PLAIN_TEXT = "Report.\n\n**Rating**: Overweight\n\nFINAL TRANSACTION PROPOSAL: **BUY**"

_lock = threading.Lock()
_calls = 0


def _count_call() -> int:
    """Count one served chat completion and return the new total."""
    global _calls
    with _lock:
        _calls += 1
        return _calls


def _read_count() -> int:
    """Read the counter without touching it."""
    with _lock:
        return _calls


def _tool_names(body: dict) -> list[str]:
    """Names of the tools bound to this request, in request order."""
    names = []
    for tool in body.get("tools") or []:
        if isinstance(tool, dict):
            name = (tool.get("function") or {}).get("name")
            if name:
                names.append(name)
    return names


def _reply_for(names: list[str]) -> tuple[dict, str, str]:
    """Return (message, finish_reason, log label) for the bound tool names."""
    schema = [n for n in names if n in SCHEMA_ARGS]
    if len(schema) == 1:
        name = schema[0]
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call_{uuid.uuid4().hex[:16]}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(SCHEMA_ARGS[name])},
                }
            ],
        }
        return message, "tool_calls", name
    return {"role": "assistant", "content": PLAIN_TEXT}, "stop", "text"


def _completion(model: str, message: dict, finish_reason: str) -> dict:
    """Minimal chat-completion envelope the client chain accepts."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        # The SpendTracker reads usage; the budget is off by default.
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


class StubHandler(BaseHTTPRequestHandler):
    """OpenAI-compatible handler. One POST route, one GET probe, 404 for the rest."""

    protocol_version = "HTTP/1.1"
    timeout = 30

    def log_message(self, fmt, *args):
        """Silence the per-request access log; the STUB call lines are the log."""

    def _send(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        """Serve the counter.

        ``GET /__count`` must stay side-effect free: the readiness loop in
        docker_smoke.sh fires up to 30 of these per run. If the probe counted,
        the ``== 9`` assertion would depend on how fast the stub came up that
        day — i.e. flaky. So the counter is only ever bumped by a served POST.
        """
        if self.path.rstrip("/") == "/__count":
            self._send(200, {"calls": _read_count()})
            return
        self._send(404, {"error": {"message": f"no such route: {self.path}"}})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._send(404, {"error": {"message": f"no such route: {self.path}"}})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            body = {}
        model = body.get("model") or "stub"
        names = _tool_names(body)
        message, finish_reason, label = _reply_for(names)
        n = _count_call()
        print(f"STUB call {n} model={model} tools={names} -> {label}", flush=True)
        self._send(200, _completion(model, message, finish_reason))


def main() -> None:
    # ThreadingHTTPServer, never plain HTTPServer: the analysts hang off the
    # graph as parallel START edges (tradingagents/graph/setup.py:160-166), so
    # several concurrent keep-alive connections arrive at once. Measured during
    # research: single-threaded HTTPServer deadlocked (aborted after 400 s, 2 of
    # 14 calls served); with ThreadingHTTPServer and nothing else changed, exit 0
    # after 3 s and all 14 calls served. This is the difference between green and
    # a CI timeout, not a style choice.
    server = ThreadingHTTPServer(("", PORT), StubHandler)
    server.daemon_threads = True
    print(f"STUB listening on port {PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
