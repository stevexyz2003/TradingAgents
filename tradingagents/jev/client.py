"""Minimal stdlib client for the Jev decision model (direct TypeSafe API).

Ported from the operator's Jev skill (direct backend only): no keyring, no
OpenRouter, no .env parsing (the package loads .env on import). The key comes
only from ``JEV_API_KEY``. Upstream's TypeSafe key variable is deliberately not
read: setting it also turns on the upstream post screening (``agents/post_screen.py``).
"""

from __future__ import annotations

import json
import logging
import os
import re
import ssl
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

MODEL = "jev-latest"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
ENV_VAR = "JEV_API_KEY"
USD_PER_INPUT_TOKEN = 0.042 / 1_000_000  # output tokens are free per the docs
RETRY_CODES = (429, 502, 503, 524, 529)
RETRY_BACKOFF_S = 1.0
MAX_RETRIES = 1

_KEY_PATTERN = re.compile(r"(sk-or-|apikey_)[A-Za-z0-9_\-]+")


class JevError(Exception):
    """Any failure talking to Jev; its message is already redacted."""


def get_api_key() -> str | None:
    """The Jev key from ``JEV_API_KEY``, or None when unset or empty."""
    return os.environ.get(ENV_VAR) or None


def redact(text, key: str | None = None) -> str:
    """``text`` without ``key`` and without anything shaped like an API key."""
    text = str(text)
    if key:
        text = text.replace(key, "[REDACTED]")
    return _KEY_PATTERN.sub("[REDACTED]", text)


def validate(req) -> None:
    """Raise JevError unless ``req`` is a well-formed {state, questions} request."""
    if not isinstance(req, dict):
        raise JevError("request must be a JSON object with state and questions")
    state = req.get("state")
    if state is None or state == "" or state == [] or state == {}:
        raise JevError("state is empty")
    qs = req.get("questions")
    if not isinstance(qs, dict) or not qs:
        raise JevError("questions must be a non-empty object")
    for qid, q in qs.items():
        if not isinstance(q, dict):
            raise JevError(f"question '{qid}': must be an object")
        t = q.get("type")
        if t not in ("choice", "score", "noul"):
            raise JevError(f"question '{qid}': unknown type {t!r}")
        if not q.get("instructions"):
            raise JevError(f"question '{qid}': missing instructions")
        c = q.get("criteria")
        if t == "choice":
            if not isinstance(c, dict) or not (1 <= len(c) <= 255):
                raise JevError(f"question '{qid}': choice needs 1-255 options")
        elif t == "score":
            if not isinstance(c, list) or not (2 <= len(c) <= 10):
                raise JevError(f"question '{qid}': score needs 2-10 levels")
        elif not isinstance(c, dict) or "true" not in c or "false" not in c:
            raise JevError(f"question '{qid}': noul needs both 'true' and 'false' criteria")


def build_request(req: dict, model: str = MODEL) -> dict:
    validate(req)
    return {"model": model, "state": req["state"], "questions": req["questions"]}


def summarize(resp: dict) -> dict:
    """Per question: {type, answer, confidence[, label][, probabilities]}.

    A noul answer's confidence is ``abs(2p - 1)``.
    """
    answers = {}
    for qid, a in (resp.get("answers") or {}).items():
        t = a.get("type")
        out = {"type": t}
        if t == "noul":
            p = a.get("noul")
            out["answer"] = p
            conf = abs(2 * p - 1) if isinstance(p, (int, float)) else None
        elif t == "score":
            s = a.get("score")
            out["answer"] = s
            legend = a.get("legend") or {}
            if isinstance(s, (int, float)):
                out["label"] = legend.get(str(round(s)))
            conf = a.get("confidence")
        else:
            out["answer"] = a.get("choice")
            conf = a.get("confidence")
        out["confidence"] = conf
        if a.get("probabilities") is not None:
            out["probabilities"] = a["probabilities"]
        answers[qid] = out
    return answers


def direct_cost(usage: dict) -> float | None:
    tokens = usage.get("input_tokens")
    return round(tokens * USD_PER_INPUT_TOKEN, 8) if isinstance(tokens, (int, float)) else None


def make_ssl_context() -> ssl.SSLContext:
    """A verifying TLS context: JEV_CA_FILE, else the OS store via truststore, else default."""
    ca = os.environ.get("JEV_CA_FILE")
    if ca:
        return ssl.create_default_context(cafile=ca)
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def _render_http_error(code: int, body_text: str, key: str | None) -> str:
    try:
        err = json.loads(body_text).get("error", {})
        code = err.get("code", code)
        msg = err.get("message")
    except Exception:
        msg = (body_text or "")[:500]
    return redact(f"HTTP {code}: {msg}", key)


def _post(body: dict, key: str, ctx: ssl.SSLContext, timeout: float):
    data = json.dumps(body).encode("utf-8")
    r = urllib.request.Request(ENDPOINT, data=data, method="POST")
    r.add_header("Authorization", "Bearer " + key)
    r.add_header("Content-Type", "application/json")
    r.add_header("X-Title", "TradingEngineX")
    with urllib.request.urlopen(r, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_api(body: dict, key: str, timeout: float) -> tuple[dict, int]:
    """POST ``body``; return (response, attempts). One retry on a transient code."""
    ctx = make_ssl_context()
    attempts = 0
    while True:
        attempts += 1
        try:
            resp = _post(body, key, ctx, timeout)
        except urllib.error.HTTPError as e:
            try:
                text = e.read().decode("utf-8", "replace")
            except Exception:
                text = ""
            if e.code in RETRY_CODES and attempts <= MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_S)
                continue
            raise JevError(_render_http_error(e.code, text, key)) from None
        except ssl.SSLCertVerificationError:
            raise JevError("SSL certificate verification failed; set JEV_CA_FILE to a PEM "
                           "bundle that includes the intercepting CA") from None
        except urllib.error.URLError as e:
            if isinstance(e.reason, ssl.SSLCertVerificationError):
                raise JevError("SSL certificate verification failed; set JEV_CA_FILE to a PEM "
                               "bundle that includes the intercepting CA") from None
            raise JevError("network error: " + redact(e.reason, key)) from None
        except TimeoutError:
            raise JevError("request timed out") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise JevError("malformed response") from None
        if not isinstance(resp, dict):
            raise JevError("malformed response")
        return resp, attempts
