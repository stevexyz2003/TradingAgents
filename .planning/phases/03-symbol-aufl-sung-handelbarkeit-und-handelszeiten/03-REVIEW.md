---
phase: 03-symbol-aufl-sung-handelbarkeit-und-handelszeiten
reviewed: 2026-10-12T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - scripts/IBKR_EXECUTION.md
  - scripts/ibkr_broker.py
  - scripts/ibkr_contracts.py
  - scripts/ibkr_executor.py
  - tests/ibkr_fakes.py
  - tests/test_ibkr_broker.py
  - tests/test_ibkr_contracts.py
  - tests/test_ibkr_isolation.py
  - tests/test_ibkr_resolve.py
findings:
  critical: 0
  warning: 7
  info: 8
  total: 15
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-10-12
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Geprüft wurde der Phase-3-Diff `efdb93f..HEAD` für den Resolver (`ibkr_contracts.py`), die beiden neuen Lesemethoden des Adapters, das Subkommando `resolve`, das Handbuch und die Tests. Gegengeprüft wurde auch gegen die installierte Bibliothek ib_async 2.1.0 (`qualifyContractsAsync`, `Wrapper.error`).

Die zentralen Sicherheitseigenschaften halten:
- Paper-Guard vor `reqMarketDataType(3)`.
- Kein Order-Pfad. Die Message-IDs 9 und 59 sind keine Schreib-IDs.
- Genau ein Treffer wird erzwungen.
- Drift wird pro Ticker abgewiesen und nie automatisch repariert.
- `--init` überschreibt nie.
- Die Sitzung kommt nur aus `liquidHours`.
- Die Dateien werden erst nach dem Disconnect geschrieben.

Einen BLOCKER habe ich nicht gefunden. Die Warnungen betreffen vor allem drei Dinge:
- **Haltbarkeit der Identitäts-Baseline:** kein fsync vor `os.replace`, Lost-Update ohne Lock und der Wiederherstellungspfad über `--init`. In bestimmten Randfällen lässt sich das Ziel von D-12/D-17 („keine stille Neu-Lernung") so doch aushebeln.
- **Falsche Fehlerklassen:** Ein Request, der mit einem Fehlercode endet, erscheint als „Drift". Ein Validierungsfehler beim Commit erscheint als Exit 3.
- **Ein Handbuchfehler.**

Gesperrtes Verhalten aus 03-CONTEXT.md habe ich nicht als Defekt gewertet: Auto-Learn neuer Ticker (D-10), Exit 0 bei `closed` (D-29), Exit 2 bei fehlender Datei (D-12) und kein Halt-Check in Phase 3 (D-20).

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: Ein mit Fehlercode beendeter Details-Request wird als „Drift" gemeldet, mit Rebaseline-Empfehlung

**File:** `scripts/ibkr_contracts.py:716-720` (zusammen mit `scripts/ibkr_broker.py:607-619`)
**Issue:** ib_async beendet einen Request bei jedem Nicht-Warnungs-Fehlercode mit leerer Liste (`Wrapper.error` → `_endReq(reqId)`, `RaiseRequestErrors=False`). Beispiele sind 200, 162, 321 als Error-Variante, Pacing und „Error processing request". `contract_details()` gibt dann `()` zurück. Im Run-Modus wird daraus `len(found) != 1` und damit ein DRIFT mit dem Text „persisted conId unknown to the gateway; check, then resolve --rebaseline AAPL".

Ein vorübergehender Gateway-Fehler wird so als Identitätsabweichung ausgegeben, und der Operator wird direkt zum Rebaseline aufgefordert. Das ist fail-closed, aber die Diagnose ist falsch: Auf einen Gateway-Fehler hin wird eine Identitätsänderung nahegelegt. Dasselbe gilt für `len(found) > 1`: Der Text sagt dann ebenfalls „unknown to the gateway".
**Fix:** Der Adapter soll für jede Leseanfrage melden, welche Fehlercodes in ihrem Fenster kamen. `_seen_codes`-Marke wie bei `_link_codes` setzen und bei einem Nicht-INFO-Code außer 200 `GatewayUnavailable("REQUEST_FAILED", code, ...)` werfen. Im Resolver nur `len(found) == 0` bei Code 200 als „conId unbekannt" melden, `len(found) > 1` getrennt benennen:
```python
if not found:
    drift_detail = f"... seen=none (persisted conId unknown to the gateway)"
elif len(found) > 1:
    drift_detail = f"... seen={len(found)} detail rows for one conId"
```

### WR-02: Der empfohlene Wiederherstellungspfad nach Verlust von contracts.json setzt die Identitätsprüfung zurück

**File:** `scripts/ibkr_executor.py:442-449, 429-438`; `scripts/ibkr_contracts.py:350`
**Issue:** D-12 soll verhindern, dass ein versehentliches Löschen die Identitätsprüfung still zurücksetzt. Fehlt die Datei, empfiehlt die Konsole jedoch wörtlich `resolve --init AAPL MSFT NVDA`. `--init` prüft nur, ob `contracts.json` existiert. Ob `contracts-history.jsonl` daneben eine frühere Baseline belegt, wird ignoriert.

Wer der Meldung folgt, lernt MSFT/NVDA neu, ohne Vergleich mit der letzten bekannten Identität. Nur AAPL ist durch den Anker geschützt. Eine Drift seit dem Verlust wird so als neue Baseline übernommen. Dasselbe passiert nach WR-03 (korrupte Datei, die gelöscht wird).
**Fix:** In `--init` die History prüfen. Gibt es dort Einträge, entweder abbrechen (Exit 2, Verweis auf manuelle Wiederherstellung) oder die neu gelernten Identitäten mit der letzten `new`-Identität pro Ticker aus der History vergleichen und bei Abweichung als `drift` abweisen. Die Konsolenmeldung bei `CONTRACTS_MISSING` sollte auf eine vorhandene History hinweisen.

### WR-03: Kein fsync der Temp-Datei vor `os.replace`, die Baseline ist nicht crash-fest

**File:** `scripts/ibkr_contracts.py:489-495` (und `write_json_atomic` 446-451)
**Issue:** `temp.write_text()` schreibt ohne `flush`/`os.fsync`, danach folgt sofort `os.replace`. Bei Stromausfall oder BSOD kann NTFS nach dem Rename eine leere oder genullte `contracts.json` hinterlassen, weil nur die Metadaten journalisiert werden. Die History wird bewusst gefsynct, die eigentliche Baseline aber nicht.

Der nächste Lauf stoppt dann mit `CONTRACTS_INVALID` (Exit 1). Der naheliegende Ausweg ist Löschen plus `--init`, also WR-02.
**Fix:**
```python
with open(temp, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(_dump(payload))
    fh.flush()
    os.fsync(fh.fileno())
load_contracts_file(temp)
...
os.replace(temp, path)
```

### WR-04: Lost Update bei parallelem Lauf, weil Read-Modify-Write ohne Lock läuft

**File:** `scripts/ibkr_executor.py:441, 497-499`; `scripts/ibkr_contracts.py:476-495`
**Issue:** `run_resolve` liest `contracts.json` ganz am Anfang und schreibt den gesamten Stand am Ende zurück. Es gibt keinen Lock und keine Prüfung, ob sich die Datei zwischenzeitlich geändert hat.

Ein Beispiel: Prozess B lädt, nachdem A sich getrennt, aber bevor A committet hat. Dann überschreibt B das `learn` oder `rebaseline` von A. Die History enthält den Eintrag, die Datei nicht. Ein so verlorener Ticker wird beim nächsten Lauf still per `learn` neu gelernt, und ein verlorenes Rebaseline erscheint wieder als Drift. Der gemeinsame clientId (326) verkleinert das Fenster, schließt es aber nicht. Phase 4 ruft `resolve_all` zusätzlich aus dem Heartbeat auf.
**Fix:** Beim Commit eine Lock-Datei exklusiv anlegen (`os.open(lock, O_CREAT|O_EXCL)`), danach die Datei neu laden und mit dem eingelesenen Stand vergleichen (mtime/Hash). Bei Abweichung abbrechen statt überschreiben.

### WR-05: Validierungsfehler beim Commit wird als Gateway-Fehler (Exit 3) gemeldet, die Ergebnisse gehen verloren

**File:** `scripts/ibkr_executor.py:497-500`; `scripts/ibkr_contracts.py:682, 491`
**Issue:** Der Lernpfad übernimmt `identity_of(detail_info)` ungeprüft. Bei der Suche wird `primaryExchange` gegen den Suchschlüssel geprüft, `localSymbol` aber nicht. Meldet das Gateway ein leeres `localSymbol` (bei Suche und Details gleich, also kein Diff), entsteht eine Identität mit `""`. `commit_contracts` validiert die Temp-Datei und wirft `ContractsFileError` (ein `ValueError`, kein `OSError`).

Der Executor fängt nur `OSError`. Der Fehler landet deshalb im generischen Zweig von `_guarded` und ergibt `EXIT_GATEWAY` (3) mit „unexpected ...". Keine Ergebniszeile wird ausgegeben, auch nicht für die anderen Ticker.
**Fix:** Im Resolver vor dem Lernen alle vier Felder auf nicht-leer bzw. `conId > 0` prüfen, sonst `reject(NOT_FOUND|DRIFT, "incomplete identity ...")`. Im Executor zusätzlich `except (OSError, contracts_mod.ContractsFileError)` auf `OutputError` mappen.

### WR-06: Das Handbuch ordnet `^GSPC`/`XAUUSD+` falsch `not-mapped` zu

**File:** `scripts/IBKR_EXECUTION.md:277`
**Issue:** In der Zustandstabelle steht bei `not-mapped`: „this also stops `^GSPC`, `XAUUSD+` and the like". Nach D-04 stehen beide in `CONTRACT_TABLE` und werden als `not-allowed` abgewiesen. So zeigt es auch der reale Lauf (c) im selben Dokument. Wer nach dem Handbuch eine Allow-List-Erweiterung plant, wird über den Erweiterungspfad (D-04) in die Irre geführt.
**Fix:** Den Zusatz in die `not-allowed`-Zeile verschieben: „the security type is not on the allow-list (e.g. `^GSPC` IND, `XAUUSD+` CMDTY)".

### WR-07: `tradingClass`/`longName` werden im Run-Modus praktisch nie geloggt (D-09)

**File:** `scripts/ibkr_contracts.py:754-763`
**Issue:** D-09 verlangt, dass `tradingClass` und `longName` geloggt, aber nicht geprüft werden. Im Run-Modus geschieht das nur, wenn Details und Suchtreffer **im selben Lauf** voneinander abweichen. Beide kommen aus derselben Gateway-Antwort, eine Abweichung tritt also faktisch nie auf. Persistiert werden die Werte nicht.

Eine Umfirmierung (Änderung gegenüber dem Lernzeitpunkt) erscheint damit nirgends im Log. Auch die `RESOLVED`-Zeile des Executors (`ibkr_executor.py:510-518`) enthält die Felder nicht, und `test_resolve_trading_class_and_long_name_change_is_not_drift` prüft nur den Zustand, nicht das Log.
**Fix:** Die beiden Werte bei jedem `ok`/`closed`-Ergebnis auf INFO loggen, z. B. in der `RESOLVED`-Zeile `tradingClass=%s longName=%s` ergänzen, und die Bedingung entfernen.

## Info

### IN-01: Das Altformat über Mitternacht wird nicht geparst

**File:** `scripts/ibkr_contracts.py:239-246`
**Issue:** Beim Altformat wird das Ende auf das Startdatum gesetzt. Ein Fenster wie `20090507:1700-0500` wirft deshalb `SessionParseError` und ergibt `session-unknown`. Das ist fail-closed, D-23 nennt aber „Fenster über Mitternacht".
**Fix:** Bei `end <= start` im Altformat einen Tag addieren, oder die Einschränkung im Docstring/Handbuch festhalten.

### IN-02: Bei Crash zwischen History-Append und Replace bleibt eine verwaiste History-Zeile ohne `-aborted`

**File:** `scripts/ibkr_contracts.py:492-506`; `scripts/IBKR_EXECUTION.md` (Abschnitt contracts.json)
**Issue:** Das Handbuch sagt, ein `-aborted`-Suffix markiere unvollständige Schreibvorgänge. Bei einem Prozessabbruch (kill/Crash) zwischen fsync und `os.replace` fehlt diese Markierung. Die History behauptet dann eine Änderung, die nie in der Datei ankam.
**Fix:** Die Grenze im Handbuch dokumentieren: „Die History ist eine Obermenge, maßgeblich ist contracts.json."

### IN-03: Der Anker-Ticker ist doppelt hart kodiert

**File:** `scripts/ibkr_executor.py:624`
**Issue:** `"AAPL" not in args.tickers` dupliziert `contracts_mod.ANCHOR_TICKER`.
**Fix:** Die Prüfung nach `run_resolve` verlegen (dort ist `contracts_mod` geladen) oder die Konstante verwenden.

### IN-04: Die Logmeldung spricht beim resolve-Output von „portfolio"

**File:** `scripts/ibkr_executor.py:655` (aufgerufen aus 419)
**Issue:** `_discard_previous` loggt „previous portfolio removed" auch für `resolve --out`. Das führt bei der Log-Analyse in die Irre.
**Fix:** Den Text parametrisieren oder neutral formulieren („previous output removed").

### IN-05: Die Konsolenmeldung bei Commit-Fehler nennt die falsche Datei

**File:** `scripts/ibkr_executor.py:499-501, 683-689`
**Issue:** Scheitert `commit_contracts`, lautet die Konsolenmeldung „resolve output not written: …". Betroffen ist aber `contracts.json`, nicht `--out`. Zudem fehlen dann alle Ergebniszeilen.
**Fix:** Eigenen Fehlertyp oder `output_what` je Schritt setzen und die Ergebnisse vor dem Commit loggen.

### IN-06: `ambiguous`-Kandidaten mit `None` werden still verworfen

**File:** `scripts/ibkr_broker.py:603-605`
**Issue:** `found = [c for c in slot if c is not None]`. Laut Typ der Bibliothek (`list[Contract | None]`) kann eine Mehrdeutigkeitsliste `None` enthalten. Zwei Slots, davon einer `None`, würden zu „genau einem Treffer". Praktisch unwahrscheinlich, weil `details.contract` immer gesetzt ist. Trotzdem schwächt das die Exactly-One-Garantie.
**Fix:** Bei einer Liste mit `None`-Element nicht filtern, sondern `GatewayUnavailable`/`ambiguous` melden.

### IN-07: Nicht abgedeckte Zweige im Lernpfad

**File:** `scripts/ibkr_contracts.py:665-681`; `tests/test_ibkr_contracts.py`
**Issue:** Zwei DRIFT-/NOT_FOUND-Zweige des Lernpfads haben keinen Test: „search and details disagree" und „returned N detail rows". Der Run-Modus-Zweig „symbol search points elsewhere" ist nur im Stub-Test abgedeckt (`test_resolve_manipulated_conid_is_drift_and_others_continue`). Der End-to-End-Test `test_drift_is_reported_and_the_file_stays` trifft dagegen nur den Pfad `len(found) != 1`.
**Fix:** Zwei Stub-Tests für die Lernpfad-Zweige ergänzen.

### IN-08: Zeitbasierte Assertion kann auf langsamen CI-Runnern flaken

**File:** `tests/test_ibkr_broker.py` (`test_resolution_request_timeout`)
**Issue:** `time.monotonic() - started < 1.0` bei einem Timeout von 0,05 s ist großzügig, hängt aber trotzdem an der Wall-Clock.
**Fix:** Die Schwelle aus `request_timeout` ableiten und großzügiger wählen, oder nur den Zustand `REQUEST_TIMEOUT` prüfen.

---

_Reviewed: 2026-10-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
