# Phase 7: Rückkanal und Soll-Ist-Zusammenführung - Context

**Gathered:** 2026-10-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Soll und Ist stehen in einem Bericht nebeneinander, ohne dass ein Prozess in den Branch
eines anderen schreibt. Der Ausführer veröffentlicht Ledger und Portfolio auf einem
eigenen Branch, ein lokales Berichtsskript führt beim **Lesen** `paper-log` und diesen
Branch zusammen, und die CI-Analyse bekommt die echte Position als `portfolio`
übergeben (fail-open). Dazu nimmt `state_maintenance.py backup` Ledger und
Contract-Cache in die Allow-Liste auf.

Requirements: REQ-IBKR-49, -50, -51, -52 (Success Criteria 1-6 in `.planning/ROADMAP.md`
§ Phase 7).

Nicht in dieser Phase: kein Schreiben auf `paper-log` und keine Änderung an dessen
CI-Commit-Schritt (`fetch --depth=1` → `reset --hard` → `push` bleibt); keine
Alpha-/Backtest-Auswertung aus Fills; kein Alarm und kein Heartbeat (Phase 8, REQ-53);
kein Scheduler (Phase 8).

Abhängigkeit: Phase 6 ist im Code fertig (06-01..06-08 plus Review-Fixes), die Messpläne
06-09/06-10 stehen aus. 06-10 kann das execId-Fixture an die gemessene Rohform anpassen
(D-13 aus Phase 6). Planen ist jetzt möglich; **ausgeführt wird Phase 7 erst nach 06-10**,
damit sie gegen das endgültige Ledger-Format baut.

</domain>

<decisions>
## Implementation Decisions

### Veröffentlichungsbranch (REQ-52, SC1)
- **D-01:** Der Branch heißt **`ibkr-log`**. Der Ausführer ist sein einziger Schreiber;
  die Invariante „ein Schreiber pro Branch“ steht im Handbuch
  (`scripts/IBKR_EXECUTION.md`) ausdrücklich als Invariante, nicht als Gewohnheit,
  zusammen mit `paper-log` (Schreiber: CI) als Gegenstück.
- **D-02:** Inhalt: **`ledger.jsonl` als vollständige Kopie** (der Live-Ledger, nicht
  `ledger-dryrun.jsonl`), **`portfolio.json`** (der frische Stand aus dem Lauf, Form wie
  `portfolio_json()` in `scripts/ibkr_executor.py` mit `as_of`) und die
  **Contract-Datei** (`contracts.json`). Keine abgeleitete Zweitdarstellung: der
  Bericht joint gegen den echten Ledger.
- **D-03:** Gepusht wird über einen **eigenen Befehl `ibkr_executor.py publish`**,
  getrennt vom Orderlauf. Ein Git- oder Netzfehler kann `execute` nie beeinflussen,
  und die Exit-Codes von `execute` bleiben unverändert. Phase 8 hängt `publish` an den
  Zeitplan.
- **D-04:** Der Git-Arbeitsbaum ist ein **eigener Klon nur dieses Branches im
  State-Ordner** (`%LOCALAPPDATA%\TradingEngineX\ibkr\...`), nie ein Worktree des
  Entwicklungs-Repos und nie im Code-Checkout. Gepusht wird ausschließlich auf den
  Remote `fork` (stevexyz2003/TradingAgents), nie auf `origin`.

### Portfolio-Rückkanal (SC6)
- **D-05:** Nur der **CI-Lauf** (`.github/workflows/daily-paper-run.yml`) liest
  `portfolio.json` von `ibkr-log`, rein lesend, und übergibt es an die Analyse.
  Lokale Läufe behalten das heutige `--portfolio` mit 60 Minuten Höchstalter
  (`DEFAULT_PORTFOLIO_MAX_AGE`) unverändert.
- **D-06:** Gültigkeit in CI: ein Stand ist gültig, wenn sein `as_of` **nach dem
  Schluss der vorletzten regulären Sitzung** liegt (also aus dem letzten Handelstag
  stammt). Keine feste Stundenzahl; Wochenenden und Feiertage ergeben sich aus dem
  Börsenkalender.
- **D-07:** **Fail-open mit Vermerk** in jedem Fehlerfall: Datei oder Branch fehlt,
  Stand veraltet, JSON kaputt, `as_of` fehlt oder liegt in der Zukunft → der Lauf läuft
  exakt wie heute ohne Portfolio, und `summary.json` vermerkt den Grund (additives
  Feld). Der Pfad über `ibkr-log` darf keinen neuen Fehler in den Produktivpfad
  bringen; das heutige fail-closed von `load_fresh_portfolio` für lokales
  `--portfolio` bleibt unberührt.

### Berichtsform (REQ-49, SC2, SC5)
- **D-08:** Ausgabe als **Markdown auf stdout**, mit `--out <datei>` zusätzlich als
  Datei. Kein CSV, kein HTML.
- **D-09:** Standard-Zeitraum ist **alles**, filterbar mit `--since`/`--until`
  (trade_date, inklusiv).
- **D-10:** Die Ausführungstabelle hat **eine Zeile pro Entscheidung**
  `(trade_date, ticker)` aus `decision-log.md`, auch Hold und Tage ohne Order; der
  Zustand aus dem Ledger steht in einer eigenen Spalte (z. B. `skipped-hold`, `filled`,
  `fill-timeout`, `place-rejected`, „kein Lauf“). Spalten laut SC2: Rating,
  Zielposition, Ist-Position, Ordermenge, Fill-Menge, Durchschnittspreis, Abweichung
  Ziel↔Ist, `weekend_gap`.
- **D-11:** Der Bericht läuft **nur lokal**. Er liest `fork/paper-log` und
  `fork/ibkr-log` per `git fetch` + `git show` (ohne Checkout, ohne Schreibzugriff);
  kein neuer CI-Job.
- **D-12:** Duplikate werden beim Lesen dedupliziert: eine Zeile pro
  `decision_key = "<trade_date>|<ticker>"`, **erste Fassung gewinnt** (REQ-39/-40,
  wie `log.py:47-55`). Der Fall `2026-10-09 | AAPL` (dreifach in `index.md`) muss eine
  Zeile ergeben.

### Metriken und Slippage (REQ-50, SC3)
- **D-13:** Zwei **getrennte Tabellen**: Ausführung (Slippage, Fill-Quote, Abweichung
  Ziel↔Ist) und Entscheidung (realisierter Return, Alpha aus `settlement.py`). Nie in
  dieselbe Spalte. Der Bericht trägt den Hinweis, dass Paper-Fills aus
  Top-of-Book-Simulation stammen und systematisch nach oben verzerrt sind (Test der
  Mechanik, keine Messung der Ausführungsqualität).
- **D-14:** Slippage-Referenz ist der **Schlusskurs am `trade_date`**, geholt beim Lesen
  aus derselben Kursquelle wie `tradingagents/memory/settlement.py` (`get_closes`).
  Beschriftet als „Entscheidungskurs → Fill“, ausdrücklich inklusive Übernacht-Gap.
  Vorzeichen so, dass „schlechter als Referenz“ für BUY und SELL gleich gerichtet ist.
- **D-15:** Fill-Quote = **`filled_quantity / intent.quantity` je Order**, im Kopf als
  Summe über den Zeitraum. Fill-Timeout ohne Fill und bestätigte Ablehnung zählen als 0.
- **D-16:** Fehlende Kursinformation: **Zelle leer, Fußnote mit Grund**. Der Bericht
  scheitert nie an der Kursquelle, und es wird nichts geschätzt (S-08 / REQ-IBKR-68).

### Claude's Discretion
- Backup (REQ-51, SC4): wie `state_maintenance.py backup` Ledger (`ledger.jsonl`, auch
  `ledger-dryrun.jsonl`?) und `contracts.json`/`contracts-history.jsonl` aufnimmt —
  vermutlich eine eigene Option bzw. ein Default auf den IBKR-State-Ordner, da diese
  Dateien nicht unter `--state-dir` liegen. `--dry-run` muss sie listen.
- Verhalten von `publish` bei Push-Fehlern, leerem Diff (kein Commit) und fehlendem
  Remote-Branch (Erstanlage); Commit-Message-Format; Lock gegen parallelen `execute`.
- Wie CI `ibkr-log` liest (z. B. `git fetch --depth=1 origin ibkr-log` + `git show`),
  solange es rein lesend bleibt und den `paper-log`-Schritt nicht berührt.
- Name und Ort des Berichtsskripts (z. B. `scripts/ibkr_report.py`), Spaltenformat,
  Rundung.
- Wie Ist-Position und Zielposition je Zeile aus Ledger/Portfolio rekonstruiert werden.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Anforderungen und Ziel
- `.planning/ROADMAP.md` § Phase 7 — Ziel, Success Criteria 1-6, „Was diese Phase NICHT tut“
- `.planning/REQUIREMENTS.md` — REQ-IBKR-39/-40 (Schlüssel, erste Fassung), -49, -50, -51, -52 (mit Begründung zum CI-Commit-Schritt), -68 (nichts schätzen); Tabelle „bewusst nicht“ (Fill-Verweise auf `paper-log`, Alpha aus Fills)
- `.planning/phases/06-die-erste-echte-order/06-CONTEXT.md` — Ledger-Modell, Live-/Dry-Ledger (D-01), D-13 execId-Fixture

### Betrieb und Invarianten
- `scripts/IBKR_EXECUTION.md` — Handbuch; State-Ordner, Ledger-Events, Zustände; hier kommt die Invariante „ein Schreiber pro Branch“ und `publish` hinein
- `scripts/STATE_OPERATIONS.md` (233-245) — Lücke beim zweiten Schreiber, „production path gets no new moving parts“
- `scripts/PAPER_RUN.md` — „One writer only.“; lokaler Lauf mit `--portfolio`
- `.github/workflows/daily-paper-run.yml` (62-73, 144-211) — `paper-log`-Commit-Schritt, darf nicht verändert werden außer dem rein lesenden Portfolio-Abruf

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/ibkr_paperlog.py` (`GitPaperLog`, `validate_ref_name`, `validate_blob_path`, `decode_utf8`): liest Blobs eines Branches per Git ohne Checkout — Vorlage für das Lesen von `paper-log` und `ibkr-log` im Bericht.
- `scripts/ibkr_ledger.py` (`effective_executions`, `filled_quantity`, `fill_records`, Ledger-Lesen): Fill-Mengen und Durchschnittspreise je `decision_key`.
- `scripts/ibkr_executor.py` (`portfolio_json`, `AS_OF_KEY`, Pfade unter `LOCALAPPDATA` um Zeilen 265-313): Form und Ort von Portfolio, Ledger, Contracts.
- `tradingagents/memory/log.py` (`TradingMemoryLog.load_entries`, Dedup „erste Fassung“): Entscheidungen lesen.
- `tradingagents/memory/settlement.py` (`get_closes`, `fetch_returns`, `resolve_benchmark`): Schlusskurse und Entscheidungsmetriken.
- `scripts/daily_paper_run.py` (`load_fresh_portfolio`, `PORTFOLIO_AS_OF_KEY`, `DEFAULT_PORTFOLIO_MAX_AGE`): bestehender Portfolio-Eingang (fail-closed, lokal) — CI braucht einen fail-open-Zweig daneben.
- `scripts/state_maintenance.py` (`_backup_included`, `backup`, Allow-Liste 350-400): Erweiterungspunkt für REQ-51.

### Established Patterns
- State nie in einem Git-Tree des Codes; IBKR-State unter `%LOCALAPPDATA%\TradingEngineX\ibkr\`.
- Append-only Ledger, fsync; Tests nur gegen Fakes, nie gegen ein echtes Gateway.
- Exit-Codes und Zustände sind in Handbuch und Isolationstests festgenagelt — neue Werte überall konsistent nachziehen.
- Code, Kommentare, Commits englisch; `.planning/` deutsch.

### Integration Points
- Neuer Unterbefehl `publish` in `scripts/ibkr_executor.py` (oder eigenes Modul), ohne `ib_async`-Import außerhalb des Adapters.
- CI-Schritt vor der Analyse in `daily-paper-run.yml`: `ibkr-log` lesend holen, `--portfolio`-Äquivalent fail-open übergeben; `summary.json` bekommt ein additives Feld (Schema-Version bleibt 1, falls additiv).
- `state_maintenance.py backup`: IBKR-State-Dateien in die Allow-Liste.

</code_context>

<specifics>
## Specific Ideas

- Testfall aus dem Bestand: `2026-10-09 | AAPL` steht dreifach in `index.md` → genau eine Berichtszeile.
- Die Slippage-Spalte heißt so, dass niemand sie als reine Ausführungsqualität liest („Entscheidungskurs → Fill, inkl. Gap“).

</specifics>

<deferred>
## Deferred Ideas

- Eröffnungskurs als zweite Referenz (Gap und Ausführung getrennt) — erst sinnvoll mit Live-Fills.
- CSV-/HTML-Ausgabe und ein CI-Job für den Bericht.
- Laufprotokoll je Lauf auf `ibkr-log` → Heartbeat in Phase 8 (REQ-53).
- `publish` automatisch nach `execute` → Zeitplan in Phase 8.

### Reviewed Todos (not folded)
- `05-wr07-signed-fills.md` — gehört zu Phase 6 (`resolves_phase: 6`), umgesetzt in 06-01; bei der Verifikation von Phase 6 schließen.
- `2026-10-16-mark-or-exclude-jev-fallback-ratings-in-ibkr-preview.md` — Phase 6, umgesetzt in 06-02; bei der Verifikation von Phase 6 schließen.
- `06-open-info-findings-phase-2-4.md` — Phase 6 (`resolves_phase: 6`); Restpunkte bei der Verifikation von Phase 6 triagieren.

</deferred>

---

*Phase: 07-rueckkanal-und-soll-ist-zusammenfuehrung*
*Context gathered: 2026-10-19*
