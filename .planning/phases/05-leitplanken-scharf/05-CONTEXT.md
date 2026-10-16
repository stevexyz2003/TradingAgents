# Phase 5: Leitplanken scharf - Context

**Gathered:** 2026-10-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Die vier Pflicht-Leitplanken sind scharf und **ohne eine einzige Order** bewiesen:
Freigabe und Kill-Switch (fail-closed, vor jeder einzelnen Order geprüft, scharfer
Arm `reqGlobalCancel`), harte Größengrenze pro Order, nicht-blockierender Lauf-Lock,
Write-Ahead-Ledger mit Startup-Reconciliation gegen alle drei Broker-Quellen — dazu
das Sitzungsfenster aus REQ-IBKR-25, das am 2026-10-16 aus Phase 4 hierher verschoben
wurde, weil eine Phase, die nichts sendet, kein Platzierungsfenster erfüllen kann.

Requirements: REQ-IBKR-32, -33, -34, -35, -36, -39, -40, -41, -42, -43, -44, -46,
-63, -64, -66 sowie -25 (Teil Sitzungsfenster). Am Ende steht Gate G3: alle vier
Leitplanken ohne Gateway testbar nachgewiesen, erst danach wird in Phase 6 das
API-Schreibrecht freigegeben.

Nicht in dieser Phase: keine echte Order (das Schreibrecht bleibt gesperrt), keine
Fill-Verarbeitung, kein Branch, kein Heartbeat, kein Scheduler, keine
Backup-Erweiterung (kommt mit Phase 7).

</domain>

<decisions>
## Implementation Decisions

### Freigabe und Kill-Datei (REQ-33, -34, -36, -64)
- **D-01:** Die Freigabe ist eine **Datei mit Ablaufdatum**, nicht eine
  Env-Variable: `%LOCALAPPDATA%\TradingEngineX\ibkr\RELEASE` nennt ein
  „gültig bis"-Datum. Fehlt die Datei, ist sie unlesbar, nicht parsebar oder
  abgelaufen → Exit 4, kein Platzierungsaufruf. Grund: Phase 8 läuft
  unbeaufsichtigt, eine tägliche Freigabe würde sie sabotieren; eine ewige
  Freigabe wird vergessen. Eine Freigabe wird Wochen im Voraus gesetzt.
  **REQ-IBKR-33** spricht von einer „Freigabe-Variable" und wird beim Planen auf
  „Freigabe-Datei" umformuliert; REQ-IBKR-64 („Freigabe vorhanden und lesbar",
  Test mit unlesbarer Freigabedatei) passt bereits wörtlich.
- **D-02:** Die Freigabe **nennt das Konto**, für das sie gilt (`DUQ634065`).
  Weicht das verbundene Konto ab → Exit 4. Das ist eine zweite Quelle für
  „richtiges Konto" im Sinne von REQ-63, neben dem Paper-Guard (Exit 8) beim
  Verbinden.
- **D-03:** Die Kill-Datei liegt im selben State-Ordner:
  `%LOCALAPPDATA%\TradingEngineX\ibkr\KILL`. Nur die **Existenz** zählt, der
  Inhalt ist egal. Ist der Ordner nicht prüfbar, gilt das als aktiv (Exit 4,
  REQ-33 „Zustand nicht lesbar"). Das Handbuch nennt den Einzeiler zum Anlegen.
- **D-04:** Freigabe und Kill-Datei werden **unmittelbar vor jeder einzelnen
  Order** neu geprüft (REQ-34), und jeder Lauf protokolliert den Zustand beider
  Schalter im Ledger, auch wenn sie inaktiv sind (REQ-36).

### `reqGlobalCancel` gegen die Socket-Sperre (REQ-35, SC3)
- **D-05:** `reqGlobalCancel` (Nachricht 58) bleibt in der Socket-Sperre
  gesperrt. **Nur im Kill-Pfad** — nachdem der Ausführer einen aktiven
  Kill-Switch festgestellt hat — öffnet der Adapter für **genau einen**
  protokollierten Aufruf, danach ist die Sperre wieder zu. Kein anderer
  Code-Pfad kann stornieren. Die Negativ-Kontrolle (REQ-66) belegt, dass 58
  außerhalb des Kill-Pfads weiter scheitert.
- **D-06:** Der echte SC3-Nachweis läuft so: Der **Operator legt in TWS Paper
  eine kleine `DAY`-Limit-Order weit vom Markt an**, legt `KILL` an, der Lauf
  startet; belegt wird Exit 4, die Order ist storniert, der Schalterzustand
  steht im Ledger. Phase 5 selbst sendet dabei nie eine Order. Eine `DAY`-Order
  bleibt auch außerhalb der Handelszeit offen, der Test braucht keine offene
  Börse.

### Kommando und Ledger (REQ-39..-46)
- **D-07:** Ein **neues Subkommando `execute`** fährt die volle Kette: Lock →
  Startup-Reconciliation → je Ticker Freigabe-/Kill-Prüfung, Größengrenze,
  Sitzungsfenster, `intent` schreiben → statt `placeOrder` ein
  **Trocken-Abschluss**. In Phase 5 ist `execute` **zwangsweise trocken**;
  Phase 6 nimmt nur diesen Zwang heraus. `preview` bleibt unverändert der reine
  `whatIf`-Trockenlauf aus Phase 4.
- **D-08:** Trockenläufe schreiben in eine **eigene Datei
  `ledger-dryrun.jsonl`**, über denselben Code-Pfad wie der echte Ledger
  `ledger.jsonl`. Der echte Ledger bleibt bis Phase 6 leer; die
  Startup-Reconciliation sieht nie einen Trocken-`intent` (der sonst
  unauflösbar wäre und jeden Lauf mit Exit 6 beenden würde). Ein
  Markierungsfehler kann einen Trockenlauf nicht zu einem echten machen.
  Beide Dateien liegen im State-Ordner außerhalb jedes Git-Baums (REQ-46).

### Größe, Sitzungsfenster, Widerspruch (REQ-32, -25, -63)
- **D-09:** `MAX_QTY_PER_ORDER = 2` als **Code-Konstante** (jede Änderung ist ein
  Commit, wie `block_qty` in D-09 aus Phase 4). 2 ist genau die größte Order,
  die D-10 aus Phase 4 heute erzeugen kann (`Buy` = 2 Blöcke à 1 Stück); jeder
  Tabellen- oder Rechenfehler darüber wird **abgelehnt und gemeldet, nicht
  gekürzt** (REQ-32). Wer `block_qty` erhöht, muss die Grenze bewusst
  mitziehen — ein Test soll das sichtbar machen.
- **D-10:** Das Sitzungsfenster für Markt-Orders übernimmt den **Phase-3-Puffer**:
  Beginn der regulären Sitzung +15 min bis Ende −15 min, über dieselbe Konstante
  `SESSION_BUFFER_MINUTES` und `evaluate_session` aus `scripts/ibkr_contracts.py`.
  Ein Halbtag verkürzt das Fenster automatisch. Außerhalb → `skipped` mit Grund
  `outside_session` (REQ-42).
- **D-11:** Quellen-Widerspruch (REQ-63): Widerspricht sich das **Konto**, stoppt
  der **ganze Lauf**. Widersprüche zu **Position**, „**schon ausgeführt?**" oder
  **Handelbarkeit** stoppen **nur diesen Ticker** (`skipped` mit Grund, gemeldet),
  die übrigen Ticker laufen weiter. Es gilt immer der vorsichtigere Wert.

### Claude's Discretion
- Dateiformat von `RELEASE` (z. B. zwei Zeilen `account=` / `valid_until=` oder
  kleines JSON) — solange Konto und Datum maschinell und streng geparst werden
  und jeder Parse-Fehler fail-closed endet.
- Exaktes Ledger-Schema (Feldnamen), solange REQ-41/-42 erfüllt sind: Zustand,
  `decision_key`, `paper-log`-SHA als Provenienz, `skipped`-Grund, Zeitstempel,
  Schalterzustand.
- Benannte Zustände und Logzeilen im Stil der bestehenden
  `ibkr-state=<LABEL>`-Zeilen; Zuordnung zu den reservierten Exit-Codes 4/6/7.
- Ob die `execute`-Kette Bausteine aus `run_preview` wiederverwendet oder
  herauslöst.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Vertrag der Phase
- `.planning/ROADMAP.md` §„Phase 5: Leitplanken scharf" — Ziel, 8 Success
  Criteria, Abgrenzung; §„Schnittprinzip" Regel 4 und Gate G3.
- `.planning/REQUIREMENTS.md` — REQ-IBKR-25 (Sitzungsfenster-Teil), -32 bis -36,
  -39 bis -44, -46, -63, -64, -66 mit Begründungen und Nachweis-Vorgaben.

### Vorgeschichte und Entscheidungen
- `.planning/phases/04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev/04-CONTEXT.md`
  — D-09/D-10 (`block_qty`, 1 Stück je Block), D-12 (offene Orders), D-13/D-14
  (Socket-Sperre, Read-Only-Schalter bleibt aus), D-16 (Exit 5).
- `.planning/phases/04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev/04-VERIFICATION.md`
  und `04-HUMAN-UAT.md` — SC2 umformuliert, 154-Override, Gate G2 geschlossen.
- `.planning/ibkr-konto-befund.md` — Abschnitt „whatIf-Vorschau und
  Read-Only-Schalter" (321-Messung), gemessene Codes.
- `.planning/ibkr-marktdaten-befund.md` — Befund 4 (`tif` explizit, 10349),
  Befund 1 korrigiert 2026-10-12 (verzögerte Quotes haben Bid/Ask).

### Betrieb und Handbuch
- `scripts/IBKR_EXECUTION.md` — Exit-Code-Tabelle, Zustände, Abschnitt
  „Gateway Read-Only switch"; wird um RELEASE/KILL und `execute` erweitert.
- `scripts/STATE_OPERATIONS.md` §200-205 — warum keine SQLite-Datei (REQ-46).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/ibkr_executor.py:79-88` — Exit-Codes `EXIT_KILL_SWITCH = 4`,
  `EXIT_RECONCILE = 6`, `EXIT_LOCKED = 7` sind bereits reserviert (Docstring
  `:50` „reserved for later phases").
- `scripts/ibkr_executor.py:216-249` — `_ibkr_base()` und die
  `default_*_file()`-Helfer für Pfade außerhalb jedes Git-Baums; hier kommen
  `RELEASE`, `KILL`, `ledger.jsonl`, `ledger-dryrun.jsonl` dazu.
- `scripts/ibkr_executor.py:1415` `run_preview` — die Kette Paper-Log →
  Entscheidung → Plan → `whatIf` → Urteil; Vorlage für `execute`.
- `scripts/ibkr_decision.py` — `EXIT_BY_STATE` (`:89`), `plan_order` (`:300`),
  `judge_preview` (`:350`), `freshness` (`:523`).
- `scripts/ibkr_contracts.py` — `SESSION_BUFFER_MINUTES = 15` (`:38`),
  `parse_liquid_hours` (`:266`), `evaluate_session` (`:286`), `CONTRACT_TABLE`
  mit `block_qty` (`:80-104`).
- `scripts/ibkr_broker.py` — `open_orders` (`:846`, liest
  `reqAllOpenOrdersAsync`), `positions` (`:707`); für REQ-43 fehlen noch
  `reqCompletedOrders` und `reqExecutions` als schmale Lesemethoden.
- `tradingagents/dataflows/files.py:37` `locked(path, wait=False)` — der
  Lauf-Lock aus REQ-44; Windows-Pfad `_hold_windows` (`:68`) wirft jeden
  `OSError` außer `EDEADLOCK` — muss zu „nicht ausführen" werden, nicht zum
  Absturz (SC7).
- `tradingagents/memory/log.py:47-57` — derselbe `(trade_date, ticker)`-Schlüssel
  mit „erste Fassung gewinnt"; `decision_key` folgt ihm (REQ-39, -40).
- `scripts/smoke/stub_llm.py` — Muster für den gateway-freien Stub (REQ-36-Nachweis).

### Established Patterns
- Socket-Sperre im Adapter: `_WRITE_CALLS` (`scripts/ibkr_broker.py:59`),
  `_WRITE_MESSAGE_IDS = {3, 4, 19, 21, 58}` (`:68`), `_arm_write_barrier` (`:435`),
  `guarded_place` (`:447`, Id 3 nur als STK-`whatIf`). D-05 öffnet 58 nur im
  Kill-Pfad für einen Aufruf.
- Fail-closed-Lesefenster seit `d344433`: jede System-Meldung außerhalb von
  `WINDOW_BENIGN_CODES` verwirft den Read. Die neuen Lesemethoden für
  `reqCompletedOrders`/`reqExecutions` erben das über `_read`.
- RED zuerst und Negativ-Kontrolle zu jeder Sicherung (REQ-66); Tests gegen
  `tests/ibkr_fakes.py` (`FakeIB` mit `emit_during`), nie gegen das echte Gateway
  außer in ausdrücklichen Operator-Checkpoints.
- Benannte Zustände als `ibkr-state=<LABEL> code=<n> detail="..."`-Logzeilen.

### Integration Points
- `scripts/ibkr_executor.py:739` `main` — neues Subkommando `execute` neben
  `account`, `resolve`, `preview`.
- `scripts/IBKR_EXECUTION.md` — Abschnitte für RELEASE/KILL (mit Einzeiler zum
  Anlegen) und `execute`.

</code_context>

<specifics>
## Specific Ideas

- Der SC3-Test ist ein Operator-Checkpoint: Order in TWS Paper anlegen, `KILL`
  anlegen, `execute` starten, Storno und Exit 4 prüfen. Er geht auch außerhalb der
  Handelszeit.
- Ein Test soll sichtbar machen, wenn `block_qty × 2` (Buy) die Konstante
  `MAX_QTY_PER_ORDER` übersteigt — damit eine spätere `block_qty`-Erhöhung die
  Grenze nicht still unterläuft, sondern bewusst mitgezogen wird.

</specifics>

<deferred>
## Deferred Ideas

- Kurs-Stream und Marktdaten-Modul (`scripts/ibkr_market_data.py`, laufende Arbeit
  des Operators): außerhalb des Order-Pfads (REQ-IBKR-26), nicht Teil von Phase 5.
  Offene Frage dort: Soll 2103 (Marktdaten-Farm kaputt) einen Stream beenden,
  obwohl er im Lesefenster als harmlos gilt?

</deferred>

---

*Phase: 05-leitplanken-scharf*
*Context gathered: 2026-10-16*
