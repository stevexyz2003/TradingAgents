#!/usr/bin/env bash
#
# End-to-end Docker smoke: one real CLI run *through the image*, against a stub
# LLM, on an --internal network — no API key, no internet.
#
# One script, two callers: a developer with Docker, and the CI job
# `docker-smoke` in .github/workflows/ci.yml. No host Python is needed; every
# assertion is `test`, `grep` or `docker exec`.
#
# What it proves
#   * the image builds, the entrypoint starts, paths and permissions inside the
#     container work, and the whole LLM client chain reaches a configured
#     openai_compatible endpoint
#   * no real LLM call happened: the run sits on an --internal network where
#     only `stub` resolves, and the stub's own counter must match exactly
#   * the smoke has signal: a built-in negative control against an unreachable
#     port must fail with a connection error (step 8)
#
# What it does NOT prove: analysis quality. Inside the isolated network every
# data vendor fails and `route_to_vendor` degrades to DATA_UNAVAILABLE strings,
# so the reports are structurally complete and factually empty. This is a
# plumbing test, not a model test.
#
# Knobs (all optional): SMOKE_IMAGE, SMOKE_TICKER, SMOKE_DATE,
# SMOKE_EXPECTED_CALLS, SMOKE_OUT, SMOKE_KEEP (=1 keeps the containers and the
# network for inspection; the next run's pre-flight teardown removes them).
#
# MSYS path rule — mandatory, keep it verbatim. Git Bash rewrites *bare
# container-side absolute paths* in the argument list. Measured in this shell
# (MINGW64, bash 5.3.15):
#
#     /stub_llm.py    ->  C:/Program Files/Git/stub_llm.py   broken
#     "/stub_llm.py"  ->  C:/Program Files/Git/stub_llm.py   quoting does NOT help
#     //stub_llm.py   ->  /stub_llm.py                       correct
#
# Hence the stub container's interpreter argument is written `//stub_llm.py`.
# On ubuntu-latest no rewriting happens, `//stub_llm.py` arrives as-is and the
# Linux kernel collapses the doubled leading slash to `/stub_llm.py`. The same
# spelling is therefore correct on both callers. Only bare absolute paths that
# are a standalone argument are affected — `tex-smoke-stub:/stub_llm.py`,
# `-e TRADINGAGENTS_LLM_BACKEND_URL=http://stub:8000/v1` and
# `-f '{{.State.Running}}'` are measured to be safe and must not be "fixed".

set -euo pipefail

# The script builds with `docker build .` and copies scripts/smoke/stub_llm.py,
# so it needs the repo root as cwd — while still being callable from anywhere.
cd "$(dirname "$0")/../.."

SMOKE_IMAGE="${SMOKE_IMAGE:-tex-smoke:local}"
SMOKE_TICKER="${SMOKE_TICKER:-AAPL}"
# Fixed, not `auto`: the date must be <= today, and since the isolated network
# loads no market data anyway it needs no market reality — a fixed value keeps
# the run reproducible.
SMOKE_DATE="${SMOKE_DATE:-2026-10-09}"
SMOKE_EXPECTED_CALLS="${SMOKE_EXPECTED_CALLS:-9}"
OUT="${SMOKE_OUT:-$(mktemp -d)}"

fail() {
    echo "SMOKE FAIL: $*" >&2
    exit 1
}

# Order matters: all containers first, then the network — `docker network rm`
# fails while a container is still attached. `docker rm -f` on a name that does
# not exist is harmless.
teardown() {
    docker rm -f tex-smoke-stub tex-smoke-run tex-smoke-neg >/dev/null 2>&1 || true
    docker network rm tex-smoke-net >/dev/null 2>&1 || true
}

# 0b. Idempotent pre-flight teardown, before anything else. Without it a second
#     run dies at the first `docker network create` under `set -euo pipefail`,
#     and leftovers happen routinely — deliberately with SMOKE_KEEP=1,
#     unavoidably on Ctrl-C. "Runs reproducibly" (DoD) means: green twice in a
#     row with no handwork in between.
teardown

# 0c. Registered before the first container exists. INT/TERM as well as EXIT, so
#     Ctrl-C cleans up even when the shell does not run EXIT traps for it.
if [ -z "${SMOKE_KEEP:-}" ]; then
    trap teardown INT TERM EXIT
else
    echo "SMOKE_KEEP is set — containers and network are kept for inspection."
fi

echo "== 1/9 build image $SMOKE_IMAGE"
docker build -t "$SMOKE_IMAGE" .

# 2. --internal: embedded DNS resolves `stub`, while *every* call to the outside
#    fails in 0.0 s (no timeout hang) — getaddrinfo -> gaierror, requests ->
#    ConnectionError, yfinance -> DNSError. `--network host` is rejected on
#    purpose: it leaves real outbound open and makes the run non-deterministic.
echo "== 2/9 create isolated network"
docker network create --internal tex-smoke-net >/dev/null

# 3. `docker cp` instead of a bind mount: a bind mount is subject to the MSYS
#    path rewriting on Windows and to the uid trap on the runner (runner = 1001,
#    image = 1000); `docker cp` avoids both. `-I` isolates the interpreter.
echo "== 3/9 start the stub LLM"
docker create --name tex-smoke-stub --network tex-smoke-net --network-alias stub \
  python:3.13-slim python -I //stub_llm.py >/dev/null
docker cp scripts/smoke/stub_llm.py tex-smoke-stub:/stub_llm.py
docker start tex-smoke-stub >/dev/null || {
    docker logs tex-smoke-stub 2>&1 || true
    fail "docker start tex-smoke-stub failed"
}

# 4. Prove the stub is alive instead of inferring it from the probe. A wrong
#    interpreter argument (one slash instead of two, under Git Bash) starts the
#    container with a host path that does not exist in the image: it dies
#    immediately and the readiness loop would otherwise wait 30 s for nothing.
stub_running_or_die() {
    if [ "$(docker inspect -f '{{.State.Running}}' tex-smoke-stub 2>/dev/null)" != "true" ]; then
        echo "---- docker logs tex-smoke-stub ----" >&2
        docker logs tex-smoke-stub >&2 2>&1 || true
        echo "---- docker inspect .Args ----" >&2
        docker inspect -f '{{json .Args}}' tex-smoke-stub >&2 2>&1 || true
        fail "stub container is not running — the interpreter argument is expected to arrive as /stub_llm.py inside the container, received: $(docker inspect -f '{{json .Args}}' tex-smoke-stub 2>/dev/null || echo unknown)"
    fi
}
stub_running_or_die

echo "== 4/9 wait for the stub to answer"
READY=0
for _ in $(seq 1 30); do
    # Re-check in every iteration: abort the moment the stub dies instead of
    # burning the full 30 s.
    stub_running_or_die
    if docker exec tex-smoke-stub python -c \
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/__count', timeout=1)" \
        >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 1
done
if [ "$READY" -ne 1 ]; then
    echo "---- docker logs tex-smoke-stub ----" >&2
    docker logs tex-smoke-stub >&2 2>&1 || true
    fail "stub did not answer GET /__count within 30 s"
fi

# 5. All seven env vars are required: without *both* round counts the
#    unattended gap check asks the depth question, without *both* model tiers the
#    other one falls back to a gpt-6-* name. `openai_compatible` is
#    key_optional=True / require_base_url=True — no key needed.
#    Never mount a host volume on /home/appuser/.tradingagents: a non-empty mount
#    with a foreign uid ends in PermissionError on cli_prefs.json.<uuid>.tmp.
echo "== 5/9 run the CLI through the image"
TIMEOUT=()
if command -v timeout >/dev/null 2>&1; then
    TIMEOUT=(timeout 300)
fi
RUN_RC=0
"${TIMEOUT[@]}" docker run --name tex-smoke-run --network tex-smoke-net \
  -e TRADINGAGENTS_OUTPUT_LANGUAGE=English \
  -e TRADINGAGENTS_MAX_DEBATE_ROUNDS=1 \
  -e TRADINGAGENTS_MAX_RISK_ROUNDS=1 \
  -e TRADINGAGENTS_LLM_PROVIDER=openai_compatible \
  -e TRADINGAGENTS_LLM_BACKEND_URL=http://stub:8000/v1 \
  -e TRADINGAGENTS_QUICK_THINK_LLM=stub-quick \
  -e TRADINGAGENTS_DEEP_THINK_LLM=stub-deep \
  "$SMOKE_IMAGE" --ticker "$SMOKE_TICKER" --date "$SMOKE_DATE" \
                 --analysts market --save --no-show --no-html || RUN_RC=$?

# 6. Pull the artefacts out of the stopped container. tex-smoke-run stays alive
#    on purpose (the trap removes it), which is why step 8 needs its own name.
echo "== 6/9 copy the artefacts out"
docker cp tex-smoke-run:/home/appuser/.tradingagents "$OUT"
TA="$OUT/.tradingagents"

echo "== 7/9 assertions"
# a) the run itself
test "$RUN_RC" -eq 0 || fail "the CLI run exited $RUN_RC (expected 0)"

# b) exactly one consolidated report tree, with a non-empty complete_report.md
shopt -s nullglob
REPORT_DIRS=("$TA"/logs/reports/"${SMOKE_TICKER}"_*)
shopt -u nullglob
test "${#REPORT_DIRS[@]}" -eq 1 || \
    fail "expected exactly one $TA/logs/reports/${SMOKE_TICKER}_* directory, found ${#REPORT_DIRS[@]}"
test -s "${REPORT_DIRS[0]}/complete_report.md" || \
    fail "missing or empty ${REPORT_DIRS[0]}/complete_report.md"

# c) the four per-run report files the CLI writes
for name in market_report investment_plan trader_investment_plan final_trade_decision; do
    f="$TA/logs/$SMOKE_TICKER/$SMOKE_DATE/reports/$name.md"
    test -s "$f" || fail "missing or empty $f"
done

# d) the pipeline's own state log carries the rating the stub returned
STATE_LOG="$TA/logs/$SMOKE_TICKER/TradingAgentsStrategy_logs/full_states_log_$SMOKE_DATE.json"
test -s "$STATE_LOG" || fail "missing or empty $STATE_LOG"
grep -q '"final_rating": "Overweight"' "$STATE_LOG" || \
    fail "no '\"final_rating\": \"Overweight\"' in $STATE_LOG"

# e) the decision reached the memory log
MEM_LOG="$TA/memory/trading_memory.md"
test -s "$MEM_LOG" || fail "missing or empty $MEM_LOG"
grep -qF "[$SMOKE_DATE | $SMOKE_TICKER | Overweight | pending]" "$MEM_LOG" || \
    fail "no entry [$SMOKE_DATE | $SMOKE_TICKER | Overweight | pending] in $MEM_LOG"

# f) the stub's own counter. *Fewer* than the expected number means a call did
#    not go to the stub (so possibly to a real endpoint); *more* means a decider
#    failed to parse the stub's arguments and invoke_structured retried once per
#    decider with error context. The counter is therefore both a schema and a
#    graph-shape sensor. The *proof* of "no real LLM call" is the --internal
#    network; the counter is the control that no call landed elsewhere.
CALLS=$(docker exec tex-smoke-stub python -c \
    "import json, urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/__count', timeout=5))['calls'])")
test "$CALLS" -eq "$SMOKE_EXPECTED_CALLS" || \
    fail "the stub served $CALLS calls, expected $SMOKE_EXPECTED_CALLS (set SMOKE_EXPECTED_CALLS to adjust after an upstream rebase)"

# 8. Negative control — proof that the smoke has signal. Own container
#    `tex-smoke-neg`: tex-smoke-run still exists at this point (step 6 needed
#    it), and a second `docker run --name tex-smoke-run` would return
#    "Conflict ... name is already in use" with exit 125. With "exit != 0" as the
#    only assertion the control would then pass without ever having touched port
#    9999 — the exact "green by construction" failure mode it exists to rule out.
echo "== 8/9 negative control against an unreachable endpoint"
NEG_RC=0
NEG_OUT=$(docker run --name tex-smoke-neg --network tex-smoke-net \
  -e TRADINGAGENTS_OUTPUT_LANGUAGE=English \
  -e TRADINGAGENTS_MAX_DEBATE_ROUNDS=1 \
  -e TRADINGAGENTS_MAX_RISK_ROUNDS=1 \
  -e TRADINGAGENTS_LLM_PROVIDER=openai_compatible \
  -e TRADINGAGENTS_LLM_BACKEND_URL=http://stub:9999/v1 \
  -e TRADINGAGENTS_LLM_MAX_RETRIES=0 \
  -e TRADINGAGENTS_QUICK_THINK_LLM=stub-quick \
  -e TRADINGAGENTS_DEEP_THINK_LLM=stub-deep \
  "$SMOKE_IMAGE" --ticker "$SMOKE_TICKER" --date "$SMOKE_DATE" \
                 --analysts market --save --no-show --no-html 2>&1) || NEG_RC=$?

if [ "$NEG_RC" -eq 0 ]; then
    printf '%s\n' "$NEG_OUT"
    fail "the negative control exited 0 — the smoke has no signal"
fi
if [ "$NEG_RC" -eq 125 ]; then
    printf '%s\n' "$NEG_OUT"
    fail "the negative control exited 125 — that is a docker start error, not a passed control"
fi
# Here-string, never `printf ... | grep -q`: grep -q exits on the first match
# and closes the pipe, printf dies of SIGPIPE (141), and under `set -o pipefail`
# that 141 becomes the pipeline's status — so `if !` would report FAILURE exactly
# when the marker WAS found. It stayed hidden locally because the shorter
# traceback fit the 64 KiB pipe buffer; on the runner it did not, and the first
# CI run failed with "printf: write error: Broken pipe" on this very line.
# A here-string has no pipe and no reader to lose.
#
# The marker list spans the wrapper names of several langchain-openai versions:
# the image is rebuilt on every run, so the exception class is whatever the
# current release raises (`OpenAIConnectionError` on the runner,
# `APIConnectionError` with an older local image) — the assertion must pin the
# CAUSE (a refused connection), not one library's spelling.
NEG_MARKERS='APIConnectionError|OpenAIConnectionError|Connection error|Connection refused|Failed to establish a new connection'
if ! grep -Eq "$NEG_MARKERS" <<<"$NEG_OUT"; then
    printf '%s\n' "$NEG_OUT"
    fail "the negative control exited $NEG_RC but without a connection-error marker — the cause must be the unreachable endpoint"
fi
NEG_MARKER=$(grep -Eo "$NEG_MARKERS" <<<"$NEG_OUT" | head -1)

echo "== 9/9 done"
echo "artefacts: $TA"
echo "SMOKE OK ($CALLS stub calls, exit 0, negative control exit $NEG_RC via $NEG_MARKER)"
