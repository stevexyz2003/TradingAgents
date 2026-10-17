---
phase: 05-leitplanken-scharf
reviewed: 2026-10-17T12:15:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - scripts/ibkr_guards.py
  - scripts/ibkr_ledger.py
  - scripts/ibkr_broker.py
  - scripts/ibkr_executor.py
  - scripts/smoke/ibkr_order_probe.py
  - tests/ibkr_fakes.py
  - tests/test_ibkr_broker.py
  - tests/test_ibkr_execute.py
  - tests/test_ibkr_guards.py
  - tests/test_ibkr_isolation.py
  - tests/test_ibkr_ledger.py
  - tests/test_ibkr_order_probe.py
  - tests/test_ibkr_preview.py
findings:
  critical: 3
  warning: 7
  info: 3
  total: 13
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-10-17T12:15:00Z
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Narrative Findings (AI reviewer)

## Summary

Geprüft wurde der Phase-5-Diff (`git diff fecb76b HEAD`) der Leitplanken-Schicht: Freigabe-/Kill-Datei,
Größengrenze, Lauf-Lock, Write-Ahead-Ledger mit Reconciliation, die einmalige
`reqGlobalCancel`-Erlaubnis im Adapter und die `execute`-Kette. Die Phase-Tests laufen grün
(605 passed). Die Socket-Sperre für Nachricht 58 ist sauber gebaut (die Erlaubnis gilt für genau einen
`sendMsg` und ist im `finally` wieder zu), und der `intent` wird vor dem Placer mit fsync geschrieben.

Drei Befunde blockieren. Zwei davon sind mit einem Probe-Test gegen Fakes nachgewiesen:

1. Ein Ledger, das nicht als `LedgerError` scheitert, umgeht den Kill-Pfad. Exit 1 statt 4, kein Storno.
2. Ein Ticker aus der eigenen `CONTRACT_TABLE` (`^GSPC`, `XAUUSD+`) lässt den ganzen `execute`-Lauf
   mit Exit 1 abstürzen.

Der dritte ist ein Logikfehler in der Reconciliation: Ein teilgefüllter, dann stornierter Auftrag
gilt als `not_filled`, die Fills gehen verloren.

Dazu kommen Haltbarkeitslücken im Ledger. Ein fehlgeschlagener Append kann das Ledger dauerhaft
korrumpieren, und ein verwaister Trocken-`intent` erzeugt dauerhaft Exit 6. Außerdem gibt es eine
Windows-typische Fail-open-Falle bei der Kill-Datei (`KILL.txt`).

## Critical Issues

### CR-01: Ledger-Lesefehler außerhalb von `LedgerError` umgehen Kill-Pfad und Exit 4

**File:** `scripts/ibkr_executor.py:1394-1412`, `scripts/ibkr_ledger.py:203`, `scripts/ibkr_ledger.py:251-261`
**Issue:** `_run_locked` fängt beim Öffnen des Ledgers nur `ledger_mod.LedgerError` ab. Andere
Fehler fliegen ungefangen bis `_guarded` und enden als `UNEXPECTED` mit Exit 1, ohne Storno.
Bei aktivem `KILL` ist das genau der falsche Ausgang. Laut D-21 soll der Preflight den
Storno-Pfad auslösen, und laut Rangtabelle gewinnt 4 immer. Betroffen sind:

- `int(r.get("seq", 0))` in `Ledger.__init__` (`ibkr_ledger.py:203`): Eine syntaktisch gültige
  Zeile mit `"seq": "x"` oder `"seq": null` wirft `ValueError` bzw. `TypeError`. `_check` prüft
  `seq` nicht.
- `PermissionError` oder `OSError` aus `path.read_bytes()`. Unter Windows reicht dafür ein Programm,
  das die Datei exklusiv offen hält (Excel, Virenscanner).
- Später `KeyError` in `resolve_entry` (`entry["side"]`, `entry["quantity"]`, `entry["con_id"]`),
  wenn ein `intent` ohne diese Felder im Ledger steht. Dann kommt Exit 1 statt 6.

Nachgewiesen mit einem Probe-Test: Ledger-Zeile `{"v":1,"seq":"x",...}` plus `KILL`. Ergebnis: Exit 1,
`ibkr-state=UNEXPECTED ValueError`, die Broker-Factory wird nie aufgerufen, also wird nichts storniert.
**Fix:** `_check` muss das Schema vollständig prüfen und jeden Verstoß als `LedgerError` melden:
`seq` ist ein `int` (kein `bool`) und größer als 0, und `intent` hat `decision_key`, `side`,
`quantity` und `con_id` mit den richtigen Typen. Außerdem gehören `OSError` und jeder andere
Lesefehler in denselben Zweig wie `LedgerError`:
```python
try:
    ctx.ledger = ledger_mod.Ledger.open(...)
except Exception as exc:  # noqa: BLE001 - every unreadable ledger is "corrupt", never a crash
    logger.error('ibkr-state=LEDGER_CORRUPT detail="%s: %s"', type(exc).__name__, exc)
    ...  # same branch: 6 if allowed, else report + _kill_path + 4
```
Dazu ein RED-Test „KILL + Ledger mit nicht-ganzzahligem `seq`" und „KILL + unlesbares Ledger
(PermissionError)", beide mit Exit 4 und `cancel_all` aufgerufen.

### CR-02: Nicht-Aktien-Ticker der Vertragstabelle lassen den ganzen `execute`-Lauf abstürzen

**File:** `scripts/ibkr_executor.py:1568`, `scripts/ibkr_guards.py:321`
**Issue:** `_check_attempts` ruft `guards.decision_key(row["trade_date"], ticker)` für jeden
Ticker auf, der die lokale Kette überlebt hat. Das passiert vor der Auflösung, die `^GSPC` und
`XAUUSD+` mit `not-allowed` ablehnen würde. `_TICKER_RE` lässt `^` und `+` nicht zu, also wirft
`decision_key` einen `ValueError`, der nirgends gefangen wird. Folge: `run_end outcome=error`,
Exit 1, und alle übrigen Ticker des Laufs werden nicht mehr bearbeitet. Das widerspricht D-11,
nach dem ein Ticker-Problem nur diesen Ticker stoppt. Beide Symbole stehen bewusst in
`CONTRACT_TABLE`, weil sie im Paper-Log-Universum vorkommen. Ein unbeaufsichtigter Lauf über alle
Ticker (Phase 8) würde also nie handeln.

Nachgewiesen mit einem Probe-Test: Paper-Log mit `^GSPC` (Buy, frisch) und `AAPL` (Hold),
`execute ^GSPC AAPL`. Ergebnis: Exit 1, `ibkr-state=UNEXPECTED ValueError: invalid ticker: '^GSPC'`,
kein Ledger-Eintrag für `^GSPC`.
**Fix:** Einen ungültigen Schlüssel pro Ticker abfangen und als eigenen Zustand beenden, zum
Beispiel `not-allowed` bzw. `review`. Besser noch die Prüfung erst nach der
Allow-List/Auflösung ausführen:
```python
try:
    key = guards.decision_key(row["trade_date"], ticker)
except ValueError as exc:
    _finish_row(ctx, row, decision_mod.INVALID_TRADE_DATE if ... else contracts_mod.NOT_ALLOWED, str(exc))
    continue
```
Dazu ein Regressionstest mit `^GSPC` und `XAUUSD+` neben einem handelbaren Ticker.

### CR-03: Reconciliation stuft „teilgefüllt, dann storniert" als `not_filled` ein

**File:** `scripts/ibkr_ledger.py:425-436`
**Issue:** Im `completed`-Zweig wertet `resolve_entry` `order.filled` nur bei `status == "Filled"` aus.
Ein Auftrag mit `Cancelled`, `ApiCancelled` oder `Inactive` und `filled > 0` landet bei
`NOT_FILLED`, und `_reconcile` schreibt `rejected state=not-filled`.
`reqExecutions` liefert nur die Ausführungen des laufenden Tages. Am Folgetag ist der
Completed-Eintrag deshalb oft die einzige Quelle. Teilfill plus Storno, etwa ein Market-Order-Rest
zum Sitzungsende oder ein Kill-Storno, ist ein realistischer Fall. Die gefüllte Menge geht dabei
verloren: Der Ledger kennt keinen Bestand, und die Positionsregel aus D-18 sieht nichts. Diese
Reconciliation ist Teil des G3-Nachweises.
**Fix:**
```python
for order in completed:
    filled = order.filled
    if order.status in _CANCELLED and filled is not None and float(filled) > 0:
        if float(filled) >= quantity:
            return result(CONTRADICTION, "cancelled order reports a full fill")
        return result(PARTIAL_OUT, f"cancelled after {float(filled):g} filled")
```
Mehrere `completed`-Einträge mit derselben `orderRef` sollten als `COLLISION` gelten. Bisher
entscheidet stillschweigend der erste Eintrag. Dazu ein Test mit `completed_trade(status="Cancelled",
filled=1, quantity=2)` und ohne Executions.

## Warnings

### WR-01: Ein fehlgeschlagener Append kann das Ledger dauerhaft korrumpieren (Exit 6 für immer)

**File:** `scripts/ibkr_ledger.py:283-291`, `scripts/ibkr_executor.py` (`_run_locked`, `except Exception` → `RUN_END outcome=error`)
**Issue:** Scheitert `fh.write(line)`, `flush` oder `fsync` mitten in der Zeile (volle Platte,
Netzlaufwerk), kann eine halbe Zeile ohne `\n` auf der Platte liegen. `_needs_newline` bleibt
`False`. Der Fehler-Handler von `_run_locked` hängt sofort `RUN_END` an, und zwar direkt hinter
die halbe Zeile. So entsteht eine kaputte Zeile in der Mitte der Datei, die nicht versiegelt ist.
Ab dem nächsten Lauf endet jeder Lauf mit `LedgerError` und Exit 6, auflösbar nur durch Editieren
von Hand.
**Fix:** Im `except` von `append` den Zustand auf „unsicher" setzen
(`self._needs_newline = True`, `self._torn_line = <Zeilennummer>`) oder das Objekt vergiften, sodass
weitere Appends dieses Laufs verweigert werden. Alternativ vor jedem Append prüfen, ob die Datei
mit `\n` endet (`seek(-1, SEEK_END)`).

### WR-02: Ein verwaister Trocken-`intent` erzeugt dauerhaft Exit 6, entgegen der Begründung von D-08

**File:** `scripts/ibkr_executor.py:1051-1063`, `2213-2222`, `_reconcile`
**Issue:** `_reconcile` läuft auf dem Trocken-Ledger. Bricht ein Lauf zwischen `intent` und
`dry_complete` ab (Absturz, Stromausfall, Fehler beim `dry_complete`-Append, oder der zweite
Größencheck in `DryPlacer.complete` wirft einen `ValueError` nach dem `intent`), bleibt der
`intent` offen. Jeder weitere Lauf fragt dann den Broker, bekommt `NO_TRACE` und endet mit
Exit 6. `--resolve` gibt es erst in Phase 6 (D-19). D-08 begründet die getrennte Datei gerade
damit, dass ein Trocken-`intent` „sonst unauflösbar wäre und jeden Lauf mit Exit 6 beenden würde".
**Fix:** Im Modus `dryrun` gilt ein offener `intent` ohne Broker-Spur als `never_sent`. Das wird
deterministisch aufgelöst, mit einem eigenen Ereignis und ohne Gateway-Kontakt. Außerdem den
zweiten Größencheck vor das `intent`-Append ziehen.

### WR-03: Fail-open bei `KILL.txt` (Windows blendet Dateiendungen aus)

**File:** `scripts/ibkr_guards.py:131`, `162-177`
**Issue:** Nur die exakte Datei `KILL` zählt. Legt der Operator im Explorer „Neu > Textdokument"
an und tippt `KILL`, entsteht bei ausgeblendeten Endungen (Windows-Standard) `KILL.txt`.
`read_kill` meldet dann `kill-absent`, der Handel läuft weiter und es wird nicht storniert.
Ausgerechnet der Notschalter scheitert so an der häufigsten Windows-Bedienung.
**Fix:** Jeden Eintrag im State-Ordner als aktiv werten, dessen Name ohne Beachtung der
Groß-/Kleinschreibung mit `KILL` beginnt (`KILL`, `KILL.txt`, `kill.TXT`). Ein Fehler beim Listen
des Ordners zählt als `kill-unreadable`. Dazu ein Test für `KILL.txt`.

### WR-04: Das Echo der `orderRef` wird erfasst, aber nie mit dem Schlüssel verglichen

**File:** `scripts/ibkr_executor.py:2146-2157`
**Issue:** Die ganze Reconciliation hängt am exakten `orderRef == decision_key`, inklusive des
nicht gemessenen Trenners `|` (Annahme A3). `preview.echo_order_ref` landet zwar in `row["preview"]`,
wird aber nicht geprüft. Kürzt oder verändert das Gateway die Referenz, schreibt Phase 6 einen
`intent`, platziert und findet die Order beim nächsten Lauf nie wieder (`NO_TRACE`, Exit 6).
**Fix:** Ist ein Echo vorhanden und gilt `echo_order_ref != key`, endet der Ticker als
`source-conflict` („orderRef echo differs"), bevor ein `intent` geschrieben wird. Fehlt das Echo,
bleibt es wie in D-22 optional.

### WR-05: Sitzungsfenster und Frische werden mit dem Startzeitpunkt des Laufs bewertet

**File:** `scripts/ibkr_executor.py:1171`, `2124`, `2245`
**Issue:** `now_utc` wird einmal vor dem Lock gelesen. `resolve_all(now_utc=ctx.now_utc)` entscheidet
über `closed`, und `freshness` über `stale`. Bis zum `intent` laufen aber noch Lock,
Reconciliation, Git-Fetch des Paper-Logs, Auflösung, Positionen und je Ticker ein whatIf, alles mit
Timeouts. Die Schalter werden dagegen ausdrücklich vor dem `intent` neu gelesen (D-04). Das
Sitzungsfenster nicht: Ein Lauf, der kurz vor Fensterende startet, kann außerhalb des Fensters
platzieren. In Phase 6 ist das relevant.
**Fix:** Unmittelbar vor dem `intent` mit `ctx.clock()` und den gespeicherten Liquid Hours erneut
`evaluate_session` aufrufen. Bei `closed` ergibt das `outside-session`.

### WR-06: `order_history` filtert erledigte Status nicht und liest nicht atomar

**File:** `scripts/ibkr_broker.py:986-1032`, `scripts/ibkr_ledger.py:414-415`
**Issue:** `open_orders()` verwirft `_DONE_ORDER_STATUSES`, `order_history()` nimmt dagegen jede
Zeile von `reqAllOpenOrders` als „offen". Eine gerade gefüllte Order kann im Open-Ergebnis mit
`Filled` stehen und zugleich in `reqCompletedOrders`. Dasselbe passiert, wenn sie zwischen den
drei aufeinanderfolgenden Reads den Zustand wechselt. `resolve_entry` meldet dann
`CONTRADICTION`, also Exit 6. Das ist fail-closed, aber unnötig.
**Fix:** Die Open-Liste in `order_history` wie in `open_orders` um erledigte Status bereinigen.
`resolve_entry` soll „open (Filled/Cancelled) und completed" nicht als Widerspruch werten, solange
`permId` und Menge übereinstimmen.

### WR-07: `filled_quantity` summiert auch Verkäufe und verrechnet nie; ein Ticker blockiert dauerhaft

**File:** `scripts/ibkr_ledger.py:325-332`, `scripts/ibkr_guards.py:351-359`
**Issue:** `filled_quantity` addiert `filled_qty` aller `FILLED`/`PARTIAL` für eine `conId`,
ohne `side`. Nach einem gefüllten Verkauf oder einem manuellen Verkauf in TWS gilt
`ledger_filled_qty > broker_held`. Der Ticker endet dann in jedem künftigen Lauf als
`source-conflict` und lässt sich ohne `--resolve` nicht entsperren. D-18 verschiebt die Schärfung
auf Phase 6/7. Der heutige Mechanismus führt dort aber in eine dauerhafte Sperre statt nur in eine
unscharfe Regel.
**Fix:** Spätestens mit dem Placer in Phase 6 vorzeichenbehaftet summieren (BUY +, SELL -),
`side` in `FILLED`/`PARTIAL` mitschreiben und dafür einen Test anlegen. Bis dahin den Befund als
offenen Punkt für den Eingang von Phase 6 festhalten.

## Info

### IN-01: `$` in den Whitelist-Regexen lässt ein abschließendes `\n` durch

**File:** `scripts/ibkr_guards.py:137`, `320-321`
**Issue:** `decision_key("2026-10-09", "AAPL\n")` liefert `'2026-10-09|AAPL\n'`. In Python passt `$`
auch vor einem abschließenden Zeilenumbruch. Beim Datum fängt `date.fromisoformat` das ab, beim
Ticker greift nichts. Ein Schlüssel mit Zeilenumbruch würde als `orderRef` gesendet.
**Fix:** `re.fullmatch(...)` verwenden oder `\Z` statt `$`.

### IN-02: Ein auf dem Draht gezählter Cancel kann bei Drosselung nur eingereiht sein

**File:** `scripts/ibkr_broker.py:604-608`
**Issue:** `ib_async` `Client.sendMsg` reiht Nachrichten bei Drosselung (`MaxRequests`) nur ein und
sendet sie später. Die Sperre zählt `permit.sent += 1` trotzdem, und das Ledger schreibt `sent=1`.
Der Re-Read der offenen Orders mildert das ab, aber `outcome="sent"` kann falsch sein.
**Fix:** Im Docstring bzw. im Ledger-Feld als „an den Client übergeben" benennen, oder vor dem
Cancel `client._msgQ` und die Drosselung prüfen.

### IN-03: Der Rang-Kommentar „The kill switch always wins" stimmt nicht für alle Pfade

**File:** `scripts/ibkr_guards.py:100-101`, `scripts/ibkr_executor.py:1271-1278`
**Issue:** Mit `KILL` aktiv enden ein `AccountGuardViolation` (Exit 8, im Docstring von
`_kill_path` gewollt), ein Lock-Fehler (Exit 7, vor dem Preflight) und CR-01 (Exit 1) nicht mit 4.
Wer nur `worst_run_exit` liest, nimmt ein Invariant an, das nicht gilt.
**Fix:** Den Kommentar auf „unter den Ticker- und Lauf-Exits" einschränken und die Ausnahmen im
Handbuch nennen.

---

_Reviewed: 2026-10-17T12:15:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
