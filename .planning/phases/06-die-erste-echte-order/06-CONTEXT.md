# Phase 6: Die erste echte Order - Context

**Gathered:** 2026-10-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Eine echte Markt-Order gegen `DUQ634065` wird platziert, gefüllt und vollständig im
Ledger wiedergefunden. Ein zweiter Lauf am selben Tag erzeugt keine zweite Order.
Die Phase schaltet um und baut keine neuen Leitplanken: alle Leitplanken aus Phase 5
(Gate G3) bleiben unverändert scharf.

Requirements: REQ-IBKR-10, -45, -47, -48, -65. Dazu kommen zwei Eingangsaufgaben
vor der ersten echten Order: die Behandlung der Jev-Fallback-Ratings (D-23 aus
Phase 5) und die Review-Restpunkte aus Phase 5 (WR-07 Fills mit Vorzeichen und die
erneute Frische-Prüfung vor dem `intent`).

Nicht in dieser Phase: kein Scheduler, kein Push, kein Heartbeat, kein
Soll-Ist-Bericht, keine Limit-Order, kein zweiter Ticker als Pflicht, keine
Ausweitung der Leiter oder der Blockgröße (`MAX_QTY_PER_ORDER = 2` bleibt).

</domain>

<decisions>
## Implementation Decisions

### Scharfschalten (REQ-10, -45)
- **D-01:** Scharf wird `execute` über ein **Flag `--live` pro Lauf**. Ohne das Flag
  bleibt jeder Lauf trocken und schreibt nur nach `ledger-dryrun.jsonl`. Mit `--live`
  schreibt er nach `ledger.jsonl` und platziert. Eine gültige `RELEASE` ist weiterhin
  Pflicht, und `KILL` gewinnt weiterhin. Die Konstante `EXECUTE_FORCED_DRY` wird zum
  Default „trocken, solange `--live` fehlt“; ein globales Umschalten im Code gibt es
  nicht.
- **D-02:** Die allererste echte Order löst Claude **von Hand** aus
  (`execute --live`), während der Operator TWS bzw. Gateway beobachtet. Das passiert
  an einem Handelstag im Sitzungsfenster, als Checkpoint-Plan nach dem Muster von
  05-10. Der Operator nimmt den Fill direkt ab.
- **D-03:** Die erste Order kommt aus dem, was der Paper-Log am Tag hergibt: die
  jüngste frische Entscheidung, die eine BUY-Order ergibt. Ein Ticker genügt. Gibt
  es am Tag keine solche Entscheidung, wird nicht künstlich eine erzeugt.
- **D-04:** „Read-Only API“ bleibt nach der Freischaltung **aus**. Geschützt wird über
  `RELEASE` und `KILL`. Wer den Schalter wieder einschaltet, tut das bewusst und
  notiert es im Betriebshandbuch.

### Jev-Fallback-Ratings (D-23 aus Phase 5)
- **D-05:** Der Executor gleicht jede Entscheidung mit
  `runs/<date>/summary.json` → `record.rating_source` ab (Weg b aus dem Todo). Steht
  dort `jev`, endet der Ticker als `skipped` und wird nicht gehandelt. Das Log-Format
  von `decision-log.md` (`tradingagents/memory/log.py`, eine Upstream-Datei) bleibt
  unverändert.
- **D-06:** Fehlt `summary.json` oder ist sie nicht lesbar, gilt **fail-closed**: der
  Ticker wird `skipped` mit Grund `review`. Es gibt keinen Nachweis für ein
  Engine-Rating, also wird nicht gehandelt (Prinzip „positiver Nachweis“).
- **D-07:** Das in Phase 5 vorgesehene Ledger-Feld `rating_source` wird **befüllt**
  (`engine` bzw. `jev`), damit der Ledger nachweist, woher eine Entscheidung kam.

### Nach der Order (REQ-47, -48, -65)
- **D-08:** Nach dem Platzieren wartet der Lauf **bis zu 60 s** auf den Fill. Bleibt
  die Order länger offen, endet der Lauf mit eigenem Zustand und eigenem Exit (ein
  Alarm). Die Order bleibt bestehen und wird **nicht** storniert. Der nächste Lauf
  gleicht sie per Reconciliation ab. Eine zweite Schreiböffnung (`cancelOrder`) gibt
  es nicht.
- **D-09:** Weicht die Kontrolle nach der Order (Status, Stückzahl, `orderRef`,
  REQ-65) von der Absicht ab, endet der **ganze Lauf** mit eigenem Zustand (etwa
  `post-order-mismatch`) und Ledger-Eintrag. Weitere Ticker desselben Laufs werden
  nicht mehr platziert.
- **D-10:** Executions und abgeschlossene Orders werden **im selben `execute`-Lauf**
  direkt nach der Fill-Bestätigung persistiert: `filled`/`partial` je `execId` ins
  Ledger, mit Dedup und Korrekturregel (REQ-47). Ein eigenes Subkommando `sync` gibt
  es in dieser Phase nicht.

### Nachweise (SC1, SC5, SC7)
- **D-11:** Fehler 321 wird **am Tag der ersten Order frisch gemessen**. Der Operator
  schaltet Read-Only ein, `execute --live` scheitert beim Platzieren mit 321, dann
  schaltet der Operator Read-Only aus. Datum, Grund und Vorher/Nachher kommen ins
  Betriebshandbuch, und erst danach folgt die echte Order. Die whatIf-Messung aus
  Phase 4 (D-14) allein reicht nicht.
- **D-12:** **Klarstellung zu Roadmap-SC7:** Der whatIf-Reject im scharfen Pfad wird
  per **Fixture und Stub-Broker** nachgewiesen. Der Stub liefert einen whatIf mit
  `rejectReason`, der Lauf endet mit Exit 5 und ruft `placeOrder` nicht auf. Ein
  echter IBKR-Reject am Konto wird nicht provoziert: dafür müsste eine eigene
  Leitplanke (`MAX_QTY_PER_ORDER = 2` stoppt schon vor dem whatIf) für den Test
  aufgeweicht werden. Das ist eine bewusste Abweichung vom Roadmap-Wortlaut
  („bewusst über ein Limit getrieben, das IBKR ablehnt“). Die Verifikation soll sie
  nicht als Lücke werten.
- **D-13:** Die `execId`-Korrektur (SC5) wird gegen echte Daten belegt, falls eine
  Korrektur auftritt. Sonst dient ein Fixture aus der gemessenen Rohform von
  Executions und abgeschlossenen Orders (Befund 2026-10-17 plus erster echter Fill)
  mit einer künstlichen Korrektur `.01` → `.02`.

### Claude's Discretion
- Namen und Exit-Codes der neuen Zustände (Fill-Timeout, Abweichung nach der Order),
  solange sie in `EXIT_BY_STATE`, der Ledger-Grund-Tabelle und dem Handbuch
  konsistent sind (der Isolationstest prüft das).
- Wie die Schreiböffnung für `placeOrder` in der Socket-Sperre gebaut wird. Sie folgt
  dem Muster des Einmal-Permits von `cancel_all` aus 05-03: genau eine Stelle, nur im
  `--live`-Pfad, mit Negativ-Kontrollen gegen die echte Client-Klasse.

### Folded Todos
- **Signed fills in the ledger (WR-07)** (`.planning/todos/pending/05-wr07-signed-fills.md`):
  `filled_quantity` summiert heute Käufe und Verkäufe gleich. Ein Verkauf würde einen
  Ticker dauerhaft als `source-conflict` blockieren. Der Fix ist eine
  vorzeichenbehaftete Summe mit `side` in `filled`/`partial`. Dazu kommt (aus WR-05)
  die erneute Frische-Prüfung mit `ctx.clock()` unmittelbar vor dem `intent`.
  Beides ist Pflicht vor der ersten echten Order.
- **Mark or exclude Jev fallback ratings** (`.planning/todos/pending/2026-10-16-mark-or-exclude-jev-fallback-ratings-in-ibkr-preview.md`):
  wird mit D-05 bis D-07 umgesetzt.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase-Rahmen
- `.planning/ROADMAP.md` §„Phase 6: Die erste echte Order“: Ziel, SC1 bis SC7, die
  Klarstellung vom 2026-10-17 zu den vier Abweichungen von der REQ-45-Reihenfolge
  (Pflicht für den Reihenfolgetest), und was die Phase nicht tut
- `.planning/REQUIREMENTS.md`: REQ-IBKR-10, -45, -47, -48, -65

### Vorphase
- `.planning/phases/05-leitplanken-scharf/05-CONTEXT.md`: D-01 bis D-23 (Freigabe,
  Kill, Größe, Sitzung, Ledger, Reconciliation, Quellen; D-08 getrennte Ledger je
  Modus; D-19 Auflösung bei Exit 6; D-23 Jev)
- `.planning/phases/05-leitplanken-scharf/05-VERIFICATION.md`: was belegt ist,
  einschließlich des Nachtrags nach dem Review
- `.planning/phases/05-leitplanken-scharf/05-REVIEW.md` und `05-REVIEW-FIX.md`:
  behobene Befunde und die bekannte Kill-Grenze (KILL erst nach einem Halt wegen
  ungültiger Freigabe)

### Messungen am Konto
- `.planning/ibkr-konto-befund.md`: Phase-4-Abschnitt D-14 (Read-Only, Fehler 321
  per whatIf) und Phase-5-Abschnitt D-06 (Kill-Storno, Rohform von
  Executions/abgeschlossenen Orders, `orderRef` mit `|`)

### Betrieb
- `scripts/IBKR_EXECUTION.md`: Betriebshandbuch (RELEASE und KILL, execute,
  Ledger und Reconciliation, Zustandstabelle, Read-Only-Schalter). Dort werden die
  Freischaltung (SC1) und `--live` dokumentiert.

### Eingefaltete Todos
- `.planning/todos/pending/05-wr07-signed-fills.md`
- `.planning/todos/pending/2026-10-16-mark-or-exclude-jev-fallback-ratings-in-ibkr-preview.md`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/ibkr_executor.py`: `execute` mit der vollen Kette (Lock, Schalter-Preflight,
  Reconciliation, lokale Kette, Schlüsselprüfung, Gateway-Kette, Größe, Sitzung
  mit Neuprüfung vor dem `intent`, whatIf mit `orderRef`, `intent` mit fsync) und
  die **Placer-Naht** `DryPlacer.complete(ctx, intent)`. Phase 6 setzt dort einen
  echten Placer ein. `EXECUTE_FORCED_DRY` (etwa Z. 131/1161) ist die eine Stelle,
  die den Live-Pfad heute sperrt.
- `scripts/ibkr_broker.py`: Socket-Sperre mit Einmal-Permit für `reqGlobalCancel`
  (`cancel_all(kill_evidence=...)`), `order_history()`, `open_orders()`,
  `preview_order(order_ref=...)` mit Echo. Als Muster für die `placeOrder`-Öffnung.
- `scripts/ibkr_ledger.py`: `Ledger` (append-only, fsync, Siegel nach abgerissenem
  Ende), `resolve_entry` (Reconciliation je Quelle, inkl. Teilfüllung nach Storno),
  `filled_quantity` (wird mit WR-07 vorzeichenbehaftet), Feld `rating_source`.
- `scripts/ibkr_guards.py`: `EXIT_BY_STATE`, `check_size`, `decision_key`,
  Quellenvergleiche.
- `scripts/smoke/ibkr_order_probe.py`: Lesesonde für Historie und whatIf. Für die
  Abnahme am Tag der ersten Order.
- `summary.json` liest der Executor schon seit Phase 4 (Zustände `summary-missing`,
  `summary-schema`, `summary-contract`). Die Jev-Prüfung hängt sich dort an.

### Established Patterns
- Jeder Zustand steht in `EXIT_BY_STATE`, in der Ledger-Grund-Tabelle und in der
  Zustandstabelle des Handbuchs. `tests/test_ibkr_isolation.py` prüft Handbuch
  gegen Code.
- Schreiböffnungen in der Socket-Sperre gibt es nur als Einmal-Permit an genau einer
  Stelle. Ein AST-Test pinnt die Anzahl der Aufrufstellen. Negativ-Kontrollen laufen
  gegen die echte `ib_async`-Client-Klasse.
- Operator-Messungen am echten Konto laufen als Checkpoint-Plan
  (`autonomous: false`). Das Ergebnis kommt datiert in
  `.planning/ibkr-konto-befund.md`.
- Tests: `tests/conftest.py` setzt `LOCALAPPDATA` für jeden Test auf tmp. Kein Test
  berührt den echten State-Ordner.

### Integration Points
- Die Placer-Naht in `execute` (nach dem `intent`), das Ledger-Ziel je Modus
  (`ledger.jsonl` vs. `ledger-dryrun.jsonl`), die Socket-Sperre im Adapter,
  `_reconcile` für offene Orders aus dem Fill-Timeout (D-08).

</code_context>

<specifics>
## Specific Ideas

- Der Ablauf am Tag der ersten Order folgt dem Muster von 05-10:
  1. Vorprüfungen (Suite, ruff, State-Ordner)
  2. Read-Only an, `execute --live` scheitert mit 321
  3. Read-Only aus, Eintrag ins Handbuch
  4. `RELEASE` anlegen und `execute --live` ausführen
  5. Historie per Sonde lesen; der Operator nimmt in TWS bzw. Gateway ab
  6. Zweiter Lauf am selben Tag: keine zweite Order
  7. Befund in `.planning/ibkr-konto-befund.md`
- Mit TWS und Gateway läuft pro Benutzer nur eine Sitzung (Befund 2026-10-17). Für
  die Abnahme reicht die Sonde über das Gateway (serverseitig), TWS ist optional.

</specifics>

<deferred>
## Deferred Ideas

- Gezieltes Stornieren einer nicht gefüllten Order (`cancelOrder` als zweite
  Schreiböffnung) wurde verworfen (D-08). Falls nötig, später als eigene Phase oder
  in Phase 7.
- Subkommando `sync` als Nachholpfad für die Tageshistorie (D-10). Falls Läufe in
  der Praxis vor der Persistenz abbrechen, kandidiert es für Phase 7 (Rückkanal).
- Kill-Grenze aus Phase 5: Erscheint `KILL` erst nach einem Halt wegen ungültiger
  Freigabe, storniert erst der Folgelauf. Das wird bewusst nicht in Phase 6 geändert.

</deferred>

---

*Phase: 06-die-erste-echte-order*
*Context gathered: 2026-10-18*
