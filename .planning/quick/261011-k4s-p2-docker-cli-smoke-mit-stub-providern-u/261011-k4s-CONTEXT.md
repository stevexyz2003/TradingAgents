# Quick Task 261011-k4s: P2 — Docker-/CLI-Smoke mit Stub-Providern + State-Retention/Backup/Recovery — Context

**Gathered:** 2026-10-11
**Status:** Ready for research

<domain>
## Task Boundary

Die beiden letzten offenen P2-Punkte des Meilensteins „Produktionsreife" (siehe
`.planning/MILESTONE.md`, DoD):

1. **Docker-/CLI-Smoke mit Stub-Providern läuft reproduzierbar.**
2. **State-Retention/Backup/Recovery (Decision-Log, Checkpoints) dokumentiert.**

Nicht Teil dieser Aufgabe: Observability/Alerting (P2 #6), Provider-Ausfall-Policy
(P2 #8) — die bleiben offen und werden nicht angefasst.

</domain>

<decisions>
## Implementation Decisions (vom Operator entschieden, nicht erneut aufrollen)

### Smoke-Umfang — CI-Job mit echtem Docker-Build
- Neuer CI-Job: Image bauen, deterministischen Stub-Server daneben starten, einen
  echten CLI-Lauf **durch das Image** gegen `provider=openai_compatible` fahren.
- Geprüft wird: Exit-Code, erzeugte Report-Dateien, kein echter LLM-Call.
- ~2–3 CI-Minuten pro Push sind bewusst akzeptiert, weil Unit-Tests Image,
  Entrypoint, Pfade/Permissions und die Client-Kette nicht abdecken — und genau
  das Dockerfile ist nach jedem Upstream-Rebase das Unbekannte.
- Technische Basis steht schon: `Dockerfile`, `docker-compose.yml`, und der
  Provider `openai_compatible` ist `key_optional=True` mit `require_base_url=True`
  (`tradingagents/llm_clients/openai_client.py:231`), braucht also keinen Key.

### State-Umfang — Runbook + ausführbares Wartungs-Skript mit Tests
- `scripts/state_maintenance.py` mit Unterbefehlen **prune / backup / verify**
  (SQLite-Integritätsprüfung, Decision-Log-Rotation) plus Runbook-Kapitel.
- Begründung des Operators: Die DoD verlangt nur Doku, aber „Recovery bei
  korrupten SQLite-Dateien" ist ohne ausführbares Werkzeug eine unüberprüfte
  Behauptung.
- **Nicht** in den täglichen Paper-Lauf einhängen (dritte Option wurde verworfen):
  der Produktivpfad läuft seit 2026-10-11 und bekommt keine neuen beweglichen
  Teile.

### Retention-Fristen
- **Decision-Log: unbegrenzt**, wird nie automatisch beschnitten — es ist der
  Track-Record und die Grundlage der Alpha-Auswertung.
- **Checkpoints: 7 Tage** — reine Wiederaufsetzpunkte, danach wertlos.
- **Reports: 90 Tage** — entspricht der Artefakt-Aufbewahrung des Workflows.

### Claude's Discretion
- Stub-Mechanik im Detail (ein kleiner Python-HTTP-Server mit
  OpenAI-kompatiblem `/chat/completions`; Antwortform so, dass die
  Entscheider-Schemata erfüllt sind).
- Ob der Smoke über `docker run --network host` oder über `docker-compose` läuft.
- Aufteilung in Commits und die genaue Struktur des Runbook-Kapitels.

</decisions>

<specifics>
## Specific Ideas / offene technische Frage für die Research-Phase

**Der CLI-Lauf braucht nicht nur einen LLM, sondern auch Marktdaten.** Ein
Smoke-Lauf ohne Netz muss also auch die Datenseite abdecken (yfinance / Alpha
Vantage / FRED / Reddit). Zu klären: vorbereiteter Daten-Cache im Image-Lauf,
Stub-Endpunkte, Reduktion auf einen Analysten, oder eine bestehende
Offline-/Fixture-Möglichkeit in v0.6.0. Das ist der kritische Pfad dieser
Aufgabe — ein Smoke, der am ersten Netz-Call scheitert, ist wertlos.

State-Pfade (aus `tradingagents/default_config.py`):
`~/.tradingagents/logs` (results), `~/.tradingagents/cache` (data),
`~/.tradingagents/memory/trading_memory.md` (Decision-Log),
`memory_log_max_entries` existiert bereits als Begrenzung;
Checkpoints sind SQLite pro Ticker (plus Sidecars, die upstream mit `bbcd666`
beim Clear mitentfernt werden).

</specifics>

<canonical_refs>
## Canonical References

- `.planning/MILESTONE.md` — DoD-Punkte, P2-Liste, Produktionsrisiken
- `scripts/PAPER_RUN.md` — Betriebshandbuch des täglichen Laufs (hier gehört das
  Retention-/Recovery-Kapitel thematisch angrenzend hin)
- `.github/workflows/ci.yml` — bestehende Job-Struktur (tests py3.11–3.14,
  clean-install smoke, ruff), in die der Docker-Smoke eingefügt wird

</canonical_refs>
