#!/usr/bin/env bash
# graphify.sh — Wissensgraph fuer TradingEngineX reproduzierbar bauen/aktualisieren.
#
# Voraussetzung (einmalig, lokal):  uv tool install graphifyy   (oder: pip install graphifyy)
#
# Zwei Wege:
#   1. In Claude Code:  /graphify .            -> voller Build inkl. semantischer LLM-Edges
#                       /graphify . --update   -> inkrementell
#   2. CLI-Fallback (dieses Script):  reine AST/Code-Struktur, deterministisch, kein LLM,
#      CI-tauglich. `graphify update` baut bei fehlendem Graph komplett neu, sonst inkrementell.
#
# Output landet in graphify-out/ (per .gitignore ausgeschlossen).
set -euo pipefail
cd "$(dirname "$0")/.."
echo "graphify update TradingEngineX (AST/Code, kein LLM) ..."
graphify update . "$@"
