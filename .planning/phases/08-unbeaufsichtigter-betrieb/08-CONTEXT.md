# Phase 8: Unbeaufsichtigter Betrieb - Context

**Gathered:** 2026-10-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Der Ausführer läuft eine Woche ohne Eingriff aus dem Windows Task Scheduler, pusht bei
**jedem** Lauf einen Heartbeat auf `ibkr-log`, und ein CI-Wächter ohne Secrets wird rot,
wenn der Heartbeat ausbleibt oder Fehler meldet. Ein verpasster Lauf wird als Lücke
protokolliert, ohne nachzuholen. Das Handbuch `scripts/IBKR_EXECUTION.md` wird um
Scheduler, Heartbeat, Wochenlogin, Fehlerbilder und das Wochenprotokoll ergänzt.

Nicht in dieser Phase (aus ROADMAP): neue Instrumente, größere Leiter, Live-Konto;
Observability der Analyseseite (P2 #6 Rest); Provider-Ausfall-Policy (P2 #8);
IBC-Einbau (nur eine schriftliche Entscheidung am Ende, siehe D-24).

</domain>

<decisions>
## Implementation Decisions

### Laufkette & Zeitplan
- **D-01:** Neuer Unterbefehl **`ibkr_executor.py daily`**: `execute` → `account` → `publish`,
  Heartbeat inklusive. Der Task ruft ausschließlich diesen Befehl auf; die Lauflogik
  (Vorbedingungen, REQ-57) liegt im Ausführer, nicht im Scheduler.
- **D-02:** Scheitert `execute`: `account` nur, wenn das Gateway erreichbar ist; `publish`
  und Heartbeat laufen **immer** (REQ-53 „Gateway nicht erreichbar“). Gesamt-Exit-Code =
  Code von `execute`, außer `publish` selbst scheitert (dann `EXIT_PUBLISH = 11`).
- **D-03:** Start **16:30 Ortszeit Berlin, Mo–Fr** (ganzjährig sicher in der US-Sitzung,
  auch in der Woche abweichender Sommerzeitumstellung). Montags läuft die Entscheidung vom
  Freitag (CI schreibt sie Samstag früh).
- **D-04:** Task-Einstellungen: „Run **only** when user is logged on“, „Do not start a new
  instance“, „Run task as soon as possible after a scheduled start is missed“, „Restart on
  failure“ **alle 15 min, höchstens 3×**, „Stop task if it runs longer than“ **30 min**,
  „Wake the computer to run this task“ **an**. „Run whether user is logged on or not“ ist
  ausgeschlossen (REQ-56). Export per `schtasks /query /xml` ins Handbuch.
- **D-05:** Der Task läuft aus einem **eigenen Betriebs-Klon** mit eigenem venv
  (Vorschlag: `%LOCALAPPDATA%\TradingEngineX\runtime`), ausgecheckt auf einem **Tag**
  (`ops-YYYY-MM-DD`), den der Operator nach grünem Testlauf setzt. Update nur manuell
  über ein kleines Skript (fetch → checkout Tag → venv sync). Der Entwicklungsbaum handelt nie.
- **D-06:** `.env` liegt im State-Ordner (`%LOCALAPPDATA%\TradingEngineX\ibkr\.env`) und wird
  per `--env-file` übergeben; Entwicklungs- und Betriebs-Klon teilen sie wie den Ledger.
- **D-07:** **Sofort scharf**, kein Trocken-Rollout. Die Betriebswoche (SC6) zählt ab dem
  ersten geplanten Lauf.
- **D-08:** `publish` pusht mit der gespeicherten GCM-Anmeldung des angemeldeten Nutzers,
  nicht interaktiv (`GCM_INTERACTIVE=never` gibt es schon); kein Token in der Remote-URL.
  Fehlt die Anmeldung → Exit 11, Wächter rot.
- **D-09:** `daily` startet das Gateway **nicht** selbst. Fehlt es → Exit 3, Heartbeat
  „unreachable“; Start/Login bleibt Sache des Wochenlogins.
- **D-10:** Manueller `execute` am selben Tag: die vorhandene Idempotenz (Ledger-Key +
  `orderRef`-Suche, REQ-63) reicht; der Task meldet „schon ausgeführt“ mit Exit 0. Kein
  zusätzliches PAUSE-Signal.

### Heartbeat & Wächter
- **D-11:** Auf `ibkr-log` liegen **`heartbeat.json`** (je Lauf überschrieben, nur sie liest
  der Wächter) und **`runs.jsonl`** (eine Zeile je Lauf, append-only, Quelle für Lücken und
  Wochenbilanz). Ein Commit pro Lauf ist akzeptiert. `runs.jsonl` fällt unter dieselbe
  Append-only-Prüfung wie der Ledger (WR-04-Fix aus Phase 7).
- **D-12:** Heartbeat-Felder: Pflicht aus REQ-53 (Zeitstempel UTC, Gateway-/Session-Zustand,
  Zahl offener Orders, Kill-Switch-Zustand, Exit-Code) **plus** verarbeiteter
  `decision_key` und Aktion (`ordered` / `nothing-to-do` / `already-done` / `superseded` /
  `error` …), Commit-SHA + Tag des Betriebs-Klons, `release_valid_until`, Laufdauer in
  Sekunden und Versuchsnummer (1–4).
- **D-13:** Unbekanntes bleibt unbekannt: Gateway nicht erreichbar → `open_orders: null`,
  `gateway: "unreachable"` mit Fehlercode. Nichts wird aus dem Ledger geschätzt.
- **D-14:** „Zu alt“ = **Werktagsregel**: erwartet wird ein Heartbeat vom letzten Werktag
  (Mo–Fr) ab der geplanten Startzeit + **3 h Kulanz**. Kein Börsenkalender im Wächter
  (US-Feiertage sind Läufe mit „nichts zu tun“).
- **D-15:** Wächter-Cron **Mo–Fr 18:00 UTC** plus **Sa 06:00 UTC** (fängt einen
  ausgefallenen Freitag vor Montag).
- **D-16:** Rot bei: Heartbeat veraltet **oder** `exit_code ≠ 0` **oder** KILL aktiv **oder**
  RELEASE läuft in **< 7 Tagen** ab. „nichts zu tun“ und „schon ausgeführt“ sind Exit 0.
  Der Grund steht in der Job-Zusammenfassung; Benachrichtigung über GitHubs eigene Mail
  bei fehlgeschlagenem Workflow.
- **D-17:** Nachweis SC3 per `workflow_dispatch` mit optionaler Eingabe **`now`**: Der Job
  liest den echten Branch und rechnet mit der übersteuerten Zeit. Es wird kein alter
  Heartbeat gepusht und kein Test-Branch angelegt. Dazu kommen Unit-Tests der Prüflogik.
- **D-18:** Wächter-Job: `permissions: contents: read`, keine `secrets.*`, kein `pip install`;
  das Prüfskript nutzt nur die Standardbibliothek und `git fetch --depth=1`. Ein
  Isolationstest pinnt beides; der `gh`-Beleg für SC3 ist `gh secret list` plus der Workflow-Text.
- **D-19 (übernommen, Phase-7-D-22):** In Workflow-Dateien darf „IBKR“ nicht vorkommen,
  auch nicht klein im Branchnamen. Branchname und Prüflogik liegen in einem Skript unter
  `scripts/`; der Workflow ruft es neutral benannt auf.

### Lücken & Catch-up
- **D-20:** Der nächste Lauf vergleicht mit dem letzten Lauf und schreibt für Werktage
  **ganz ohne Lauf** (Rechner aus, Task nicht gestartet) ein Ledger-Ereignis **`kind: gap`**
  mit den verpassten Daten, **bevor** er handelt; dazu ein Feld im Heartbeat. Ein Lauf mit
  Fehler-Exit ist **keine** Lücke (er steht mit Code in `runs.jsonl` und ist schon rot).
- **D-21:** Ältere, nie ausgeführte Entscheidungen bekommen je einen Ledger-Eintrag
  **`superseded`** mit Verweis auf die Entscheidung, nach der stattdessen gehandelt wurde.
  Nichts wird nachgeholt; gehandelt wird nach der **aktuellen** Entscheidung (Frische nach
  REQ-19/`freshness()`).
- **D-22:** `ibkr_report.py` zeigt `gap` und `superseded` als eigene Zustände (bisher
  `no-run`) mit Fußnote auf die geltende Entscheidung.
- **D-23:** SC4 wird mit einem **geplanten Aussetzer** belegt: An einem festen Werktag der
  Betriebswoche wird der Task deaktiviert. Am Folgetag müssen `gap`, `superseded` und die
  hergestellte Zielposition sichtbar sein; das Ergebnis wird im Handbuch protokolliert.

### Wochenlogin vs. IBC
- **D-24:** In dieser Phase **manueller Wochenlogin** als benannte Betriebsaufgabe (REQ-59).
  Am Phasenende steht eine kurze schriftliche Entscheidung „IBC ja/nein“ mit Begründung
  (Grundlage: Phase 1 hat keinen Zweitfaktor gemessen). Ein Einbau wäre eine eigene Phase
  oder ein Quick-Task, kein Teil von Phase 8.
- **D-25:** Login **montags vor 16:30** (nach dem Samstagnacht-Reset, vor dem ersten Lauf).
- **D-26:** Ein vergessener Login wird zum benannten Zustand **`login-required`** (Muster
  `Soft token=0` / 1100 / 502, **vor** dem Test am realen Gateway gemessen nach REQ-67),
  Exit 3 mit Klartext im Heartbeat. Der Wächter nennt „Wochenlogin fehlt“. Fehlerbild und
  Behebung stehen im Handbuch.
- **D-27:** Gateway-Einstellungen aus REQ-59 (Never lock, täglicher Auto-Restart,
  Order-Precautions, `ClosedownAt` Freitagabend) als **Checkliste im Handbuch** mit Wert und
  Menüpfad, vom Operator einmal mit Datum abgehakt. Kein Auslesen der `jts.ini`.

### Claude's Discretion
- Logrotation der Ausführer-Logdatei.
- Der Task startet `python.exe` direkt (keine `cmd`-Hülle), damit „Last Run Result“ den
  Exit-Code des Ausführers zeigt (SC5).
- Zeitzonen-Darstellung in Log und Heartbeat (UTC im Datensatz).
- Woran der „letzte Lauf“ für die Lückenerkennung gemessen wird (lokale `runs.jsonl` im
  State-Ordner oder Ledger) und wie der allererste Lauf ohne Vorgänger behandelt wird.
- Name des Wächter-Workflows und des Prüfskripts (neutral, ohne „IBKR“).

### Folded Todos
- **`06-read-only-321-in-read-window.md`:** Eine 321 ohne Request-ID im Lesefenster beendet
  das Fenster sofort als `READ_ONLY_API` (Exit 5) statt nach 10 s als `REQUEST_TIMEOUT`
  (Exit 3). Dazu ein Test mit der gemessenen Reihenfolge, der korrigierte Kommentar in
  `test_live_read_only_ends_at_the_preview` und die Handbuch-Anpassung. Passt, weil im
  unbeaufsichtigten Betrieb ein falscher Exit-Code Wächter und Fehlerbilder verfälscht.
- **`06-mark-pipeline-test-orders-in-the-ledger.md`:** **Ausschlussliste im Repo** (z.B.
  `scripts/ibkr_report_exclusions.json`) mit Key `2026-10-16|AAPL`, `paper_log_sha`
  `8453e7642f257f6cf1cdd5ebb1738feee3632b3f` und Begründung. Der Bericht markiert die Zeile
  als `pipeline-test` und zählt sie nicht zur Engine-Bilanz. Der Ledger bleibt unverändert,
  und es gibt keinen neuen `rating_source`.
- **`06-paper-run-same-date-overwrites-summary.md`:** `daily_paper_run.py` führt eine
  vorhandene `summary.json` desselben `trade_date` **zusammen**: `runs` nach Ticker
  vereinigt, der neuere Lauf gewinnt je Ticker, `totals` neu berechnet,
  `started_at`/`finished_at` je Lauf als Liste. Dazu ein Test mit disjunkten und
  überlappenden Tickern. Passt, weil der unbeaufsichtigte Ausführer sonst an `summary-missing`
  scheitert, sobald jemand den Tag nachdispatcht (am 2026-10-20 geschehen: `runs/2026-10-19`
  enthält nur noch AAPL).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Anforderungen & Roadmap
- `.planning/ROADMAP.md` §„Phase 8: Unbeaufsichtigter Betrieb“ — Ziel, 7 Erfolgskriterien, „Was diese Phase NICHT tut“
- `.planning/REQUIREMENTS.md` — REQ-IBKR-53, -54, -56, -57, -58, -59, -60 (dazu -55 Exit-Codes, -63 Mehrquellen, -64 Kill-Switch, -66 Negativ-Kontrollen, -67 gemessene Fehlercodes)

### Vorentscheidungen
- `.planning/phases/07-rueckkanal-und-soll-ist-zusammenfuehrung/07-CONTEXT.md` — D-01..D-22 (ein Schreiber pro Branch, `publish` ohne Gateway, D-17 öffentlich, D-22 kein „IBKR“ im Workflow)
- `.planning/phases/07-rueckkanal-und-soll-ist-zusammenfuehrung/07-REVIEW.md` + `07-REVIEW-FIX.md` — WR-02/WR-03 bewusst offen (Cutoff D-06, warn-only bei altem Portfolio); `daily` (D-01) führt `account` vor `publish` aus und entschärft WR-03 im Normalbetrieb
- `.planning/ibkr-konto-befund.md` — Phase-1-Messung „kein Zweitfaktor“ (Grundlage für D-24), Messungen zu 321/Read-Only

### Betrieb & Code
- `scripts/IBKR_EXECUTION.md` — bestehendes Handbuch; wird ergänzt (SC7)
- `scripts/PAPER_RUN.md` — Vorbild für Handbuchstruktur und CI-Abschnitte
- `scripts/ibkr_executor.py` — Unterbefehle, Exit-Codes (0–11, 20), Lock, `run_publish`
- `scripts/ibkr_publish.py` — Schreibweg `ibkr-log`, Append-only-Prüfung (WR-04), URL-Schwärzung
- `scripts/ibkr_decision.py` — `freshness()`, `second_last_close_utc`, Session-Kalender
- `scripts/ibkr_report.py` — Zustände der Ausführungstabelle (D-22, Ausschlussliste)
- `scripts/daily_paper_run.py` — Summary-Schreiber (Folded Todo)
- `tests/test_ibkr_isolation.py` — Reinheits- und Workflow-Regeln (D-18, D-19)
- `.github/workflows/daily-paper-run.yml` — Muster für den Wächter-Workflow

### Todos (aufgenommen)
- `.planning/todos/pending/06-read-only-321-in-read-window.md`
- `.planning/todos/pending/06-mark-pipeline-test-orders-in-the-ledger.md`
- `.planning/todos/pending/06-paper-run-same-date-overwrites-summary.md`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ibkr_executor.py run_publish` / `ibkr_publish.publish()`: Klon nur von `ibkr-log`, Commit nur bei Diff, Push ohne Force. `heartbeat.json` und `runs.jsonl` kommen als weitere Snapshot-Dateien dazu.
- Exit-Code-Tabelle und `_fail()`-Muster in `ibkr_executor.py`; der Handbuch-Pin in `test_ibkr_isolation.py` zählt die Codes (aktuell 13).
- `ibkr_decision.freshness()` und der Session-Kalender: Frische der aktuellen Entscheidung, Grundlage für `superseded`.
- Ledger-Idempotenz (`trade_date|ticker`, `orderRef`) und der Lock: decken manuelle Läufe und Retries ab (D-10).
- `daily_paper_run.py` mit `--portfolio-from-published`: Muster für Lesen per `git fetch --depth=1` und das neutrale Flag im Workflow.

### Established Patterns
- Ein Schreiber pro Branch; `ibkr-log` gehört dem Ausführer, `paper-log` der CI.
- Fail-closed beim Handeln, fail-open mit Vermerk beim Berichten oder Lesen.
- Jede Sicherung braucht eine Negativ-Kontrolle (REQ-66); Fehlercodes werden am realen Gateway gemessen, bevor Tests darauf bauen (REQ-67).
- Isolationstests pinnen Handbuchtexte und verbieten Uhr- und Force-Aufrufe in reinen Modulen.

### Integration Points
- Neuer Unterbefehl `daily` in `ibkr_executor.py`.
- Neuer Workflow für den Wächter (neutral benannt) plus Prüfskript unter `scripts/`.
- Ledger-Ereignistypen `gap` und `superseded` (`ibkr_ledger.py`, Validierung und Abgleich).
- `ibkr_report.py`: neue Zustände und die Ausschlussliste.
- Betriebs-Klon + Update-Skript (`scripts/`, PowerShell oder Python), Task-XML im Handbuch.

</code_context>

<specifics>
## Specific Ideas

- Wochenprotokoll (SC6) im Handbuch: Datum, Zahl der Läufe, Zahl der Orders, Zeitpunkt des Wochenlogins, Wochenwechsel, Fehlerbild „vergessener Login“ mit Behebung. Quelle ist `runs.jsonl`.
- Am Ende der Phase steht eine schriftliche IBC-Entscheidung (D-24).

</specifics>

<deferred>
## Deferred Ideas

- IBC-Einbau (automatischer Login): nur nach der Entscheidung aus D-24, als eigene Phase oder als Quick-Task.
- Eigener `rating_source: pipeline-test` mit Flag im Executor: erst bei einem weiteren Pipeline-Test.
- Windows-Erinnerungsdialog für den Wochenlogin: verworfen zugunsten von Wächter und `login-required`.
- Observability der Analyseseite (P2 #6 Rest) bleibt laut ROADMAP offen.

</deferred>

---

*Phase: 08-unbeaufsichtigter-betrieb*
*Context gathered: 2026-10-21*
