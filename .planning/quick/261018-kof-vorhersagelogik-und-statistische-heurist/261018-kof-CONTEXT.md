# Quick Task 261018-kof: Vorhersagelogik und statistische/heuristische Methoden analysieren, mit Codex validieren und bei Bedarf nachschärfen - Context

**Gathered:** 2026-10-18
**Status:** Ready for research and planning (in a fresh session: `/gsd-quick resume vorhersagelogik-und-statistische-heurist`)

<domain>
## Task Boundary

Die Vorhersage-Engine von TradingEngineX analysieren — die Kette vom LLM-Rating bis zu
seiner statistischen Bewertung —, mit Codex unabhängig validieren und dort nachschärfen,
wo die Validierung Fehler oder Lücken belegt. Methodischer Kern laut Operator: **bestimmte
Muster sollen zu einer Vorhersageprognose führen.**

Bestand (gesichtet 2026-10-18, alles Upstream-Code außer Jev):
- Prognose: LLM-Agenten (Analysten → Bull/Bear-Debatte → Trader → Risiko-Debatte →
  Portfolio-Manager) liefern ein Rating der 5er-Skala Buy/Overweight/Hold/Underweight/Sell;
  `tradingagents/agents/rating.py` (`extract_rating`) liest es deterministisch, unlesbar →
  `REVIEW`, nie `Hold`.
- Statistik: `tradingagents/memory/settlement.py` bewertet jede Entscheidung nach der
  Haltedauer mit realisiertem Return und Alpha gegen einen regionalen Benchmark
  (`resolve_benchmark`, `fetch_returns`); seit v0.7.0 ab dem ersten Schlusskurs **nach**
  dem Entscheidungsdatum. `tradingagents/backtest.py` (`run_backtest`, `summarize`)
  aggregiert je Rating Trefferquote (Richtung) und mittleres Alpha; Hold zählt nicht als
  Richtung.
- Heuristik: technische Indikatoren (RSI, MACD, Bollinger, ATR, VWMA …) sind nur
  **Eingaben** für den Markt-Analysten (`agents/analysts/market_analyst.py`,
  `agents/tools.py`), keine Regeln. `agents/post_screen.py` und `tradingagents/jev/`
  (Strang, opt-in) prüfen Entscheidungen nach.

</domain>

<decisions>
## Implementation Decisions

### Methodik „Muster → Prognose"
- **Beides, Auswertung zuerst.** Schritt 1: explizite, testbare Marktmuster definieren
  (z. B. RSI-Extrem, MACD-Kreuzung, Ausbruch über ein n-Tage-Hoch, Trend über/unter
  SMA200) und **je Muster** messen, ob das Rating der Engine danach recht hatte
  (Trefferquote der Richtung, mittleres Alpha, Anzahl). Schritt 2: eine deterministische
  Muster-Schicht, die eine eigene Prognose liefert oder das LLM-Rating begrenzt (z. B. Veto
  bei Widerspruch), **nur für Muster, die sich in Schritt 1 belegen lassen.**
- Die Muster werden am Kurs **bis einschließlich** Entscheidungsdatum berechnet — nie mit
  Daten danach (kein Look-ahead); das ist eine der Prüfungen für Codex.

### Validierung
- **Code-Review durch Codex** der ganzen Kette Rating → Settlement → Backtest-Aggregation:
  Rechenfehler, Look-ahead, Benchmark-Wahl, Haltedauer, Umgang mit `REVIEW`/Hold,
  Survivorship, Mehrfachzählung, Rundung der Alpha-Strings. Codex-CLI 0.137.0 ist
  installiert, Default-Modell gpt-5.5 (ChatGPT-Konto akzeptiert es). Formvorlage für den
  Bericht: `.planning/phases/04-…/04-CODEX-REVIEW.md`.
- **Plus Auswertung der echten Historie** (`decision-log.md` auf `fork/paper-log`, lesen
  ohne Checkout per `git fetch fork paper-log` + `git show fork/paper-log:decision-log.md`,
  Muster wie D-01 aus Phase 4).
- **Kein neuer Backtest, keine LLM-Kosten** in dieser Aufgabe.

### Änderungsort
- **Strang-Module, Upstream minimal.** Muster-Definitionen, Muster-Auswertung und eine
  spätere Muster-Schicht kommen als eigene Module in den Strang (eigene Dateien, keine
  Edits in `rating.py`, `settlement.py`, `backtest.py`). Belegt Codex einen echten Fehler
  im Upstream-Code, wird er als **kleinstmöglicher Patch mit Test** behoben und als
  Upstream-Kandidat notiert (Rebase-Konfliktfläche klein halten).
- Nicht anfassen: `scripts/ibkr_*`, IBKR-Tests, `scripts/IBKR_EXECUTION.md` — dort arbeitet
  parallel die Phase-6-Session.

### Claude's Discretion
- Konkrete Muster-Auswahl (Startmenge 4–6), Fenstergrößen und Schwellen — begründet und
  als Code-Konstanten, nicht als Settings.
- Format der Muster-Auswertung (CLI-Skript oder Funktion + Test), solange sie auf dem
  Memory-Log-Format arbeitet und damit sowohl die Paper-Log-Historie als auch spätere
  Backtest-Logs lesen kann.

</decisions>

<specifics>
## Specific Ideas

**Datenlage — wichtig für Planung und Erwartung (gemessen 2026-10-18):** `decision-log.md`
auf `paper-log` hat erst **16 Einträge vom 2026-10-09 bis 2026-10-16** (AAPL, MSFT, NVDA je
5–6): 13× Hold (12 pending, 1 abgerechnet: +2,0 % / Alpha +4,0 %, 5 Tage), 3× Overweight
(alle pending). **Keine einzige abgerechnete Richtungsentscheidung.** Die Muster-Auswertung
kann heute also gebaut, getestet und einmal auf den echten Daten ausgeführt werden, aber
**keine statistisch tragfähige Aussage** liefern. Sie muss deshalb Stichprobengröße und
Unsicherheit (z. B. Konfidenzintervall der Trefferquote, Mindest-N je Muster) ausweisen und
„zu wenig Daten" als eigenes Ergebnis kennen, statt Trefferquoten aus 0–3 Fällen zu melden.
Schritt 2 (Muster-Schicht) folgt aus Schritt 1 erst, wenn genug abgerechnete
Richtungsentscheidungen vorliegen — durch den täglichen Lauf (einige Wochen) oder einen
später separat entschiedenen Backtest.

</specifics>

<canonical_refs>
## Canonical References

- `tradingagents/agents/rating.py` — Ratingskala, `extract_rating`, `REVIEW`.
- `tradingagents/memory/settlement.py`, `tradingagents/memory/reflection.py`,
  `tradingagents/memory/log.py` — Bewertung, Eintragsformat `[date | ticker | rating | …]`.
- `tradingagents/backtest.py` — Raster, `summarize`, `RatingScore` (hit_rate, mean_alpha).
- `tradingagents/agents/analysts/market_analyst.py`, `tradingagents/agents/tools.py` —
  Indikatoren als Analysten-Eingaben.
- `tradingagents/agents/post_screen.py`, `tradingagents/jev/` — Nachprüfung.
- `.planning/phases/04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev/04-CODEX-REVIEW.md`
  — Formvorlage Codex-Review.
- `scripts/PAPER_RUN.md` — lokale Läufe; das CA-Bündel aus dem lokalen `.env` ist nötig,
  damit yfinance lokal echte Kurse liefert (sonst Fallback-Daten, siehe dort).

</canonical_refs>
