"""The fork's Jev client: request validation, answer summaries, key redaction, retries."""

import io
import json
import urllib.error

import pytest

from tradingagents.default_config import DEFAULT_CONFIG, build_default_config
from tradingagents.jev import client

FAKE_KEY = "apikey_TESTFAKE_123"


def _choice(**over):
    q = {"type": "choice", "instructions": "i", "criteria": {"a": "A", "other": "O"}}
    q.update(over)
    return q


def _req(q, state="x"):
    return {"state": state, "questions": {"qq": q}}


# ---------------------------------------------------------------- validation
@pytest.mark.unit
@pytest.mark.parametrize("q", [
    {"type": "zzz", "instructions": "i", "criteria": {}},
    {"type": "noul", "criteria": {"true": "t", "false": "f"}},
    _choice(criteria={}),
    _choice(criteria={str(i): None for i in range(256)}),
    {"type": "score", "instructions": "i", "criteria": ["a"]},
    {"type": "score", "instructions": "i", "criteria": list("abcdefghijk")},
    {"type": "noul", "instructions": "i", "criteria": {"true": "t"}},
])
def test_validate_rejects_a_malformed_question_naming_it(q):
    with pytest.raises(client.JevError, match="qq"):
        client.validate(_req(q))


@pytest.mark.unit
@pytest.mark.parametrize("req", [
    "not a dict",
    {"state": "", "questions": {"qq": _choice()}},
    {"state": {}, "questions": {"qq": _choice()}},
    {"state": "x", "questions": {}},
])
def test_validate_rejects_an_empty_request(req):
    with pytest.raises(client.JevError):
        client.validate(req)


@pytest.mark.unit
def test_build_request_adds_the_model():
    req = _req(_choice())
    assert client.build_request(req) == {
        "model": "jev-latest", "state": "x", "questions": req["questions"]}


# ------------------------------------------------------------------- summary
@pytest.mark.unit
def test_summarize_reads_each_answer_form():
    resp = {"answers": {
        "is_bug": {"type": "noul", "noul": 0.96},
        "team": {"type": "choice", "choice": "payments", "confidence": 0.75},
        "urgency": {"type": "score", "score": 1.99, "confidence": 0.99,
                    "legend": {"0": "low", "1": "mid", "2": "high"}},
    }}
    ans = client.summarize(resp)
    assert ans["team"]["answer"] == "payments" and ans["team"]["confidence"] == 0.75
    assert ans["urgency"]["label"] == "high" and ans["urgency"]["confidence"] == 0.99
    assert ans["is_bug"]["answer"] == 0.96
    assert abs(ans["is_bug"]["confidence"] - 0.92) < 1e-9


@pytest.mark.unit
def test_direct_cost_is_input_tokens_at_the_published_rate():
    assert client.direct_cost({"input_tokens": 1_000_000}) == 0.042
    assert client.direct_cost({}) is None


# ------------------------------------------------------------------ redaction
@pytest.mark.unit
def test_redact_removes_the_exact_key_and_key_shaped_tokens():
    out = client.redact("boom secretXYZ apikey_OTHER_9 sk-or-v1-abc", "secretXYZ")
    assert "secretXYZ" not in out and "apikey_OTHER_9" not in out and "sk-or-v1-abc" not in out
    assert out.count("[REDACTED]") == 3


# ------------------------------------------------------------------- key
@pytest.mark.unit
def test_key_comes_only_from_jev_api_key(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-other")
    assert client.get_api_key() is None
    monkeypatch.setenv("JEV_API_KEY", "")
    assert client.get_api_key() is None
    monkeypatch.setenv("JEV_API_KEY", FAKE_KEY)
    assert client.get_api_key() == FAKE_KEY


@pytest.mark.unit
def test_key_loses_a_bom_and_surrounding_whitespace(monkeypatch):
    # Seen in the paper run: a secret piped in from PowerShell began with U+FEFF,
    # and the request failed encoding the Authorization header.
    monkeypatch.setenv("JEV_API_KEY", "﻿" + FAKE_KEY + "\r\n")
    assert client.get_api_key() == FAKE_KEY
    monkeypatch.setenv("JEV_API_KEY", " ﻿ ")
    assert client.get_api_key() is None


# ------------------------------------------------------------------ transport
def _http_error(code, body=b'{"error": {"message": "nope"}}'):
    return urllib.error.HTTPError(client.ENDPOINT, code, "err", {}, io.BytesIO(body))


@pytest.fixture
def transport(monkeypatch):
    """Queue results on ``.queue`` (dicts are returned, exceptions raised)."""
    class _Calls(list):
        queue: list = []
        sleeps: list = []

    calls = _Calls()
    calls.queue, calls.sleeps = [], []

    def fake_post(body, key, ctx, timeout):
        calls.append((body, key, timeout))
        item = calls.queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(client, "_post", fake_post)
    monkeypatch.setattr(client.time, "sleep", calls.sleeps.append)
    return calls


@pytest.mark.unit
def test_call_api_returns_the_response_and_attempts(transport):
    transport.queue.append({"answers": {}})
    assert client.call_api({"b": 1}, FAKE_KEY, 5.0) == ({"answers": {}}, 1)
    assert transport[0] == ({"b": 1}, FAKE_KEY, 5.0)


@pytest.mark.unit
@pytest.mark.parametrize("code", [429, 502, 503, 524, 529])
def test_call_api_retries_once_on_a_transient_code(transport, code):
    transport.queue += [_http_error(code), {"answers": {}}]
    assert client.call_api({}, FAKE_KEY, 5.0) == ({"answers": {}}, 2)
    assert transport.sleeps == [1.0]


@pytest.mark.unit
def test_call_api_gives_up_after_one_retry(transport):
    transport.queue += [_http_error(503), _http_error(503), {"answers": {}}]
    with pytest.raises(client.JevError, match="HTTP 503"):
        client.call_api({}, FAKE_KEY, 5.0)
    assert len(transport) == 2


@pytest.mark.unit
def test_call_api_maps_a_client_error_with_the_key_redacted(transport):
    transport.queue.append(_http_error(401, json.dumps(
        {"error": {"message": "bad key " + FAKE_KEY}}).encode()))
    with pytest.raises(client.JevError) as exc:
        client.call_api({}, FAKE_KEY, 5.0)
    assert str(exc.value).startswith("HTTP 401: bad key")
    assert FAKE_KEY not in str(exc.value)
    assert len(transport) == 1


@pytest.mark.unit
def test_call_api_maps_network_timeout_and_malformed_responses(transport):
    transport.queue.append(urllib.error.URLError("refused " + FAKE_KEY))
    with pytest.raises(client.JevError, match="network error") as exc:
        client.call_api({}, FAKE_KEY, 5.0)
    assert FAKE_KEY not in str(exc.value)

    transport.queue.append(TimeoutError())
    with pytest.raises(client.JevError, match="request timed out"):
        client.call_api({}, FAKE_KEY, 5.0)

    transport.queue.append(json.JSONDecodeError("bad", "doc", 0))
    with pytest.raises(client.JevError, match="malformed response"):
        client.call_api({}, FAKE_KEY, 5.0)

    transport.queue.append(["not", "a", "dict"])
    with pytest.raises(client.JevError, match="malformed response"):
        client.call_api({}, FAKE_KEY, 5.0)


# -------------------------------------------------------------------- config
@pytest.mark.unit
def test_jev_config_defaults_are_off_and_typed():
    assert DEFAULT_CONFIG["jev_enabled"] is False
    assert DEFAULT_CONFIG["jev_min_confidence"] == 0.9
    assert isinstance(DEFAULT_CONFIG["jev_min_confidence"], float)
    assert DEFAULT_CONFIG["jev_timeout"] == 5.0
    assert isinstance(DEFAULT_CONFIG["jev_timeout"], float)


@pytest.mark.unit
def test_jev_config_env_overrides_coerce(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_JEV_ENABLED", "true")
    monkeypatch.setenv("TRADINGAGENTS_JEV_MIN_CONFIDENCE", "0.8")
    monkeypatch.setenv("TRADINGAGENTS_JEV_TIMEOUT", "7")
    cfg = build_default_config()
    assert cfg["jev_enabled"] is True
    assert cfg["jev_min_confidence"] == 0.8
    assert cfg["jev_timeout"] == 7.0 and isinstance(cfg["jev_timeout"], float)


@pytest.mark.unit
def test_jev_config_rejects_an_invalid_boolean(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_JEV_ENABLED", "treu")
    with pytest.raises(ValueError, match="TRADINGAGENTS_JEV_ENABLED"):
        build_default_config()


@pytest.mark.unit
def test_the_key_is_never_a_config_entry():
    assert not any("key" in k for k in DEFAULT_CONFIG if k.startswith("jev_"))
