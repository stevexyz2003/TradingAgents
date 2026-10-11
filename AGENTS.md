# AGENTS.md — TradingEngineX

> Projektregeln & Pointer für KI-Coding-Assistenten.

## Graphify — Wissensgraph (Architektur-Navigation)

Code-Knowledge-Graph zum Verstehen der Architektur. Output -> `graphify-out/` (gitignored, kein Source-Artefakt).

- **In Codex:** `/graphify .` (voller Build inkl. semantischer Edges) · `/graphify . --update` (inkrementell) · `/graphify query "..."` · `/graphify path "A" "B"` · `/graphify explain "X"`
- **CLI-Fallback (kein LLM, CI-tauglich):** `bash scripts/graphify.sh` (= `graphify update .`, reine AST/Code-Struktur)
- **Einmalig lokal installieren:** `uv tool install graphifyy` (oder `pip install graphifyy`)
- **Skill liegt projekt-lokal:** `.agents/skills/graphify/SKILL.md` (nicht im Repo,
  siehe `.gitignore`)

Graphify ist ein Navigations-/Analyse-Tool — kein Build- oder Merge-Gate.

## Serena — Symbol-genaue Code-Navigation (MCP, LSP)

Ergänzt Graphify: Graphify = globale Architektur-Karte, Serena = symbol-genaues `find_symbol` / `find_referencing_symbols` / `rename` / Edit über LSP. Registriert in `.codex/config.toml` bzw. `.mcp.json` als `serena` — beide enthalten einen maschinenspezifischen Pfad und bleiben deshalb lokal (`.gitignore`).

- **Einmalig lokal:** `uv tool install -p 3.13 serena-agent@latest --prerelease=allow && serena init`
- **Tool-Bias-Workaround:** Serena bringt einen System-Prompt-Override mit (`serena prompts print-cc-system-prompt-override`); wie er eingehängt wird, hängt vom Client ab — in Claude Code via `--append-system-prompt` plus Reminder-Hooks in `.claude/settings.json`.
- **Verifizieren:** die MCP-Server-Liste des Clients zeigt `serena` als connected.

Nur Navigation/Refactor — kein Build- oder Merge-Gate.
