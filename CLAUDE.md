# CLAUDE.md — TradingEngineX

> Projektregeln & Pointer für KI-Coding-Assistenten.

## Graphify — Wissensgraph (Architektur-Navigation)

Code-Knowledge-Graph zum Verstehen der Architektur. Output -> `graphify-out/` (gitignored, kein Source-Artefakt).

- **In Claude Code:** `/graphify .` (voller Build inkl. semantischer Edges) · `/graphify . --update` (inkrementell) · `/graphify query "..."` · `/graphify path "A" "B"` · `/graphify explain "X"`
- **CLI-Fallback (kein LLM, CI-tauglich):** `bash scripts/graphify.sh` (= `graphify update .`, reine AST/Code-Struktur)
- **Einmalig lokal installieren:** `uv tool install graphifyy` (oder `pip install graphifyy`)
- **Skill liegt projekt-lokal:** `.claude/skills/graphify/SKILL.md`

Graphify ist ein Navigations-/Analyse-Tool — kein Build- oder Merge-Gate.

## Serena — Symbol-genaue Code-Navigation (MCP, LSP)

Ergänzt Graphify: Graphify = globale Architektur-Karte, Serena = symbol-genaues `find_symbol` / `find_referencing_symbols` / `rename` / Edit über LSP. Registriert in `.mcp.json` als `serena`.

- **Einmalig lokal:** `uv tool install -p 3.13 serena-agent@latest --prerelease=allow && serena init`
- **CC-Tool-Bias-Workaround (empfohlen):** `claude --append-system-prompt "$(serena prompts print-cc-system-prompt-override)"` + Serena-Reminder-Hooks in `.claude/settings.json`
- **Verifizieren:** `/mcp` in Claude Code zeigt `serena` als connected.

Nur Navigation/Refactor — kein Build- oder Merge-Gate.
