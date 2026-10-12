---
phase: 04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev
reviewed: 2026-10-12T00:00:00Z
depth: deep
files_reviewed: 9
files_reviewed_list:
  - scripts/ibkr_broker.py
  - scripts/ibkr_contracts.py
  - scripts/ibkr_decision.py
  - scripts/ibkr_executor.py
  - scripts/ibkr_paperlog.py
  - pyproject.toml
  - .gitattributes
  - tests/test_ibkr_broker.py
  - tests/test_ibkr_preview.py
findings:
  critical: 0
  warning: 6
  info: 7
  total: 13
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-10-12
**Depth:** deep (Fokus Sicherheit)
**Files Reviewed:** 9 (Quellen plus die relevanten Testmodule; Review-Stand ist der committete Stand HEAD 8b2593c im sauberen Worktree, nicht der Hauptcheckout mit der uncommitteten `ibkr_broker.py`-Änderung)
**Status:** issues_found
**BLOCKER:** 0 (Frontmatter-Schlüssel `critical` = BLOCKER-Stufe)

## Summary

Die Schreibsperre hält. Gegen die installierte `ib_async==2.1.0` geprüft (`client.py` `send`, `sendMsg`, `placeOrder`, `whatIfOrderAsync`, `wrapper.error`, `wrapper.openOrder`):

- Die Feldindizes 53/61/65/70/71/73 stimmen mit dem Layout für Server >= 177 und Nicht-BAG-Kontrakt überein. Das String-Level (Kontrakt auf 12 Felder, secType bei `parts[4]`, Flag bei `parts[84]`) stimmt ebenfalls.
- Alle Blöcke, die die Position von `whatIf` verschieben könnten, sind vor Index 73 abgefangen. Die Blöcke hinter `whatIf` (PEG BENCH, Conditions, IBKRATS) sind harmlos.
- Bei Server < 177 (zusätzliches `faProfile`) verschiebt sich alles um eins, und die Prüfung scheitert fail-closed: Feldebene an Index 70 (`dnc` ist `False`, nicht leer), String-Ebene an Index 71 (`"0"` ist nicht leer).
- `send` und `sendMsg` sind auf der Instanz ersetzt. `send` ruft `self.sendMsg` und trifft daher die zweite Sperre. Die Throttle-Leerrunde (`sendMsg("")`) wird korrekt durchgelassen.
- 4, 19, 21 und 58 sind lückenlos gesperrt, 3 nur als STK-whatIf.
- Das openOrder-Tap wird in `finally` zurückgesetzt. Der Decoder löst `self.wrapper.openOrder` zur Laufzeit auf, das Tap greift also.
- Die Fehlerpfade 154, 10349 und 321 (nur bei Timeout) sind richtig verdrahtet. Bei einem Nicht-Warn-Fehler beendet `wrapper.error` den Request mit `[]`, daher ergibt sich `EMPTY` und danach der Zustand über `codes`.

Die Entscheidungslogik ist weitgehend korrekt. Unabhängig geprüft wurden Frische in Sessions, Toleranzband, Budgetvergleich und Exit-Rang 1 > 5 > 2 > 0. Das Git-Subprocess-Handling nutzt Listen-argv ohne Shell, validierte Namen und feste Pfade. Die Zielmenge stammt über SHA-gepinnte `cat-file blob <sha>:<path>`-Aufrufe.

Gefunden wurden keine BLOCKER. Die Warnungen betreffen vor allem Tests, die in CI stumm überspringen, ein SHA-Pinning mit Race-Fenster, eine tote Laufzeit-Validierung und Randfälle der Soll-Rechnung.

Testlauf im Worktree: 547 passed (broker, contracts, decision, executor, isolation, paperlog, preview, summary-contract).

## Warnings

### WR-01: Die sicherheitskritischen Barrier-Tests werden in CI übersprungen (laufen dort vakuös)

**File:** `tests/test_ibkr_broker.py:115-199, 421, 541, 993-1092`; `tests/test_ibkr_contracts.py:378, 386`; `tests/test_ibkr_decision.py:303`; `tests/test_ibkr_preview.py:430`; `pyproject.toml:33-52`; `.github/workflows/ci.yml:33-34`
**Issue:** Alle Tests am echten `ib_async.Client` stehen hinter `pytest.importorskip("ib_async")`. Das sind die Layout-Tests der Schreibsperre, die Nachweise "echte Order auf der Leitung abgelehnt" und die Erkennung einer Layoutänderung beim Upgrade. Dasselbe gilt für die XNYS-Parametrisierung der Frischetests und `test_real_branch_hold_with_the_xnys_calendar` über `exchange_calendars`. CI installiert nur `pip install -e ".[dev]"`. `ib_async` und `exchange_calendars` liegen im Extra `ibkr`. Dort überspringen also genau die Tests, die die einzige Schutzschicht prüfen (der Gateway-Schalter bleibt in Phase 4 laut D-14 aus). Der Kommentar in `ibkr_broker.py:74-75` ("The real-client test turns a layout change on upgrade into a red test") gilt damit nur lokal. Die Skips erscheinen nur als `-ra`-Zeilen und lassen CI grün.
**Fix:** Ein CI-Job mit `pip install -e ".[dev,ibkr]"`, der diese Tests ausführt. Zusätzlich ein Gate, das ein Skip der Barrier-Tests in diesem Job zum Fehler macht, etwa `-W error::pytest.PytestUnraisableExceptionWarning` oder ein Marker `requires_ibkr` mit einer `conftest`-Prüfung, die bei gesetztem `CI_IBKR=1` nicht skippt.

### WR-02: SHA-Pinning über `FETCH_HEAD` mit Race-Fenster

**File:** `scripts/ibkr_paperlog.py:111-138` (Zeilen 113-129)
**Issue:** `git fetch … +refs/heads/<branch>` schreibt nur nach `.git/FETCH_HEAD`. Danach löst ein zweiter Aufruf `rev-parse --verify FETCH_HEAD^{commit}` auf. `FETCH_HEAD` ist repo-global und wird von jedem anderen `git fetch` überschrieben, etwa dem Hintergrund-Fetch von PyCharm, einem zweiten Executor-Lauf oder einem manuellen `git fetch --all`. Zwischen den beiden Aufrufen kann ein fremder Fetch dazwischenkommen. Dann zeigt `rev-parse` auf die erste Zeile eines anderen Fetches, also einen anderen Branch oder Remote. Der gepinnte SHA, den `preview.json`, der Log und die Dry-Run-Aufzeichnung als Provenienz tragen, wäre dann falsch. Das Fenster ist klein, die SHA-Pinning-Invariante (D-02) soll aber ohne Race gelten.
**Fix:** In eine eigene Ref holen und diese auflösen, statt `FETCH_HEAD` zu lesen:
```python
ref = f"refs/tengx/paper-log-preview"
fetch_args = ["fetch", "--no-tags", "--quiet", self._remote,
              f"+refs/heads/{self._branch}:{ref}"]
...
rev = self._git(["rev-parse", "--verify", f"{ref}^{{commit}}"], self._read_timeout)
```
Alternativ `git ls-remote <remote> refs/heads/<branch>` für den SHA nehmen und per `fetch <remote> <sha>` holen. `fetch()` sollte `self.sha` bei einem Fehlschlag zusätzlich auf `None` zurücksetzen, damit nach einem zweiten fehlgeschlagenen Fetch nicht mit einem alten SHA weitergelesen wird.

### WR-03: `table_problems` ist zur Laufzeit toter Code; ein ungültiges `block_qty` endet als "unexpected"-Abbruch

**File:** `scripts/ibkr_contracts.py:103-113`, `scripts/ibkr_executor.py:1275-1277`, `scripts/ibkr_decision.py:305-306`
**Issue:** `table_problems` (T-04-11) wird nur von `tests/test_ibkr_contracts.py:957/962` aufgerufen, nicht von `ibkr_executor.py` oder irgendeinem anderen Skript. `ContractSpec.block_qty` hat den Default `0`. Ein Tabelleneintrag, der vergessen wird oder falsch ist, fällt zur Laufzeit erst in `plan_order` als `ValueError("block_qty must be positive")` auf. Das geschieht mitten im Gateway-Fenster nach dem Positions- und Open-Order-Read, mit der Gateway-Session offen. `_guarded` fängt das als `UNEXPECTED` und gibt `EXIT_GATEWAY` (3) zurück, obwohl es ein Konfigurationsfehler ist (1). Alle bereits fertigen Ticker-Zeilen gehen verloren, es wird kein Record geschrieben.
**Fix:** `run_preview` ruft `contracts_mod.table_problems()` vor dem Gateway-Kontakt auf und meldet Funde als `ConfigError` (Exit 1). Alternativ fängt `_preview_ticker` den `ValueError` und beendet die Zeile mit einem benannten Zustand.

### WR-04: Short-Bestand (negatives `held`) wird nicht abgewiesen; die Soll-Rechnung kauft auf ein Sell-Signal

**File:** `scripts/ibkr_decision.py:298-330`
**Issue:** Die Long-only-Invariante prüft nur `SELL > held`. Ein negatives `held_qty` (Short, per TWS oder Fremd-Client entstanden) wird nicht erkannt. Beispiel `Sell`, `held=-3`, `block_qty=1`: `target=0`, `diff=3`, `side="BUY"`, `quantity=3`. Es entsteht ein BUY-Intent auf ein Sell-Signal (Cover). Bei `block_qty>|held|` ergibt sich `within-tolerance`, der Short bleibt unbehandelt. Die `AssertionError`-Zeile 328-329 ist unerreichbar: `diff>0` gilt immer für `held<=target` und `quantity=held-target<=held` sonst. Die Invariante ist also nur scheinbar geprüft. Ein Short im Konto ist ein "fremder" Zustand wie `foreign-open-order` und `fractional-position`.
**Fix:** Vor der Berechnung ein benannter Zustand, z. B. `SHORT_POSITION`, mit Exit 2:
```python
if held_qty < 0:
    return Plan(SHORT_POSITION, held=held_qty, detail=f"held {held_qty:g} is short; long-only")
```
Zustand in `ALL_STATES`, `EXIT_BY_STATE` und dem Handbuch-Zustandstabellentest ergänzen.

### WR-05: `summary.trade_date` wird gelesen und validiert, aber nie gegen Pfad und Eintragsdatum geprüft

**File:** `scripts/ibkr_decision.py:195-196, 234-263`; `scripts/ibkr_executor.py:1131-1146, 1177-1188`
**Issue:** `read_summary` verlangt ein gültiges `trade_date`, das in `Summary.trade_date` steht. `_summary_reader(day)` liest aber `runs/<day>/summary.json` ohne Abgleich von `summary.trade_date == day`. `evaluate_decision` vergleicht Summary und Eintrag nur über Ticker und Signal, nie über das Datum. Die Dateikopie `runs/2026-10-12` mit Inhalt von `trade_date=2026-10-09` (Kopier- oder Runner-Fehler) würde für eine Entscheidung vom 2026-10-12 als "passend" gelten. Inkonsistent ist `newer_summary_state`: Dort entscheidet das Feld `newer_summary.trade_date` (`nd <= entry_date`), während die Auswahl der Datei über den Pfadnamen erfolgt. Ein Pfad/Feld-Mismatch kann ein neueres Summary als "nicht neuer" tarnen. Dann bleibt die Supersede-Erkennung (`log-missing-entry`) aus.
**Fix:** In `_summary_reader.read` nach `read_summary` prüfen und bei Abweichung abbrechen:
```python
summary = decision_mod.read_summary(text)
if summary.trade_date != day:
    raise _RunAbort(decision_mod.SUMMARY_CONTRACT,
                    f"{path}: trade_date {summary.trade_date} != path date {day}")
cache[day] = summary
```

### WR-06: `read()` bildet jeden `cat-file`-Fehler auf `BlobMissing` ab

**File:** `scripts/ibkr_paperlog.py:145-154`
**Issue:** `proc.returncode != 0` wird immer als `BlobMissing(path)` gemeldet. Ursachen wie fehlendes Objekt im Repo (flacher oder partieller Klon), beschädigtes Repo oder ein von Git angemahntes Locking-Problem werden dadurch zu "Datei fehlt": `log-finding`/`summary-missing` statt `paper-log-unavailable`. Für `summary-missing` wird die Datei sogar als `None` gecacht, und der Lauf behandelt "kein Summary" als fachlichen Befund. Das stderr (der Unterschied) wird verworfen. Es bleibt fail-closed (Exit 2), die Diagnose ist aber falsch und verdeckt Repo-Probleme.
**Fix:** `stderr` auswerten oder erst `git cat-file -e <sha>:<path>` prüfen:
```python
if proc.returncode != 0:
    err = self._err(proc).lower()
    if "does not exist" in err or "exists on disk, but not in" in err or "not a valid object name" in err:
        raise BlobMissing(path)
    raise PaperLogUnavailable(f"cat-file failed: {self._err(proc)}")
```

## Info

### IN-01: `validate_ref_name` und die Datums-Regexe nutzen `match` mit `$`

**File:** `scripts/ibkr_paperlog.py:17-19, 41-50, 65-68`; `scripts/ibkr_decision.py:134-163`
**Issue:** `$` passt auch vor einem abschließenden `\n`. `validate_ref_name("fork\n")` und `summary_path("2026-10-09\n")` laufen durch den Regex. Das ist keine Injektion (Listen-argv, die Werte kommen aus `.strip()`-ten Settings), aber unsauber. `\d` passt auf Unicode-Ziffern; `parse_trade_date` fängt das über `date.fromisoformat` ab, in `summary_path` verhindert es erst `validate_blob_path`. Außerdem lässt die Whitelist die Remote `.` oder Pfade wie `/abs/repo` zu. `git fetch . +refs/heads/paper-log` holt dann aus einer lokalen Branch-Ref, was D-02 ("kein Fallback auf lokale Ref") widerspricht. Es ist nur durch Operator-Konfiguration erreichbar.
**Fix:** `fullmatch` statt `match` mit `$`, `re.ASCII` für `\d`, und für die Remote zusätzlich `value not in {".", ".."}` und kein führendes `/`/`./`.

### IN-02: Modul-Docstring und Klassendoku von `ibkr_broker.py` sind veraltet

**File:** `scripts/ibkr_broker.py:5-8, 209-211, 492-498`
**Issue:** Der Docstring sagt "Phase 2 reads only. The adapter has no write API at all (no place, preview or cancel)". Der Adapter hat jetzt `preview_order`, und die Sperre lässt STK-whatIf auf Id 3 durch. `OpenOrder` sagt "phase 4 never sends", obwohl es sich auf die Phase-4-Sperre bezieht. Wer diese Datei als Sicherheitsvertrag liest, bekommt eine falsche Aussage.
**Fix:** Docstring auf "reads plus whatIf preview of stocks; every real order is refused" anpassen.

### IN-03: Das Feld-Level-Check sperrt keine NUL/Steuerzeichen in Stringfeldern

**File:** `scripts/ibkr_broker.py:469-486, 390-421`
**Issue:** `_whatif_in_fields` prüft die typisierten Felder, das Message-Level zerlegt per `split("\0")`. Ein Stringfeld (`orderRef`, `symbol`, `tif`, `account`) mit eingebettetem `\0` würde auf der Leitung die Positionen gegenüber dem Layout verschieben, während die Feldebene weiter das echte `whatIf=True` sieht. Die Feldebene geht dann durch, und das Gateway könnte `whatIf` an anderer Stelle lesen. In Phase 4 setzt nur `preview_order` Strings (feste Werte aus der Tabelle und aus dem Gateway-Identity-Check), daher nicht ausnutzbar. Als Defense-in-Depth fehlt es.
**Fix:** In `guarded_send` für Id 3 zusätzlich verlangen, dass kein String-Feld (außer dem Contract-Objekt) ein `"\0"` enthält. Alternativ in `_whatif_in_message` die Feldanzahl gegen die aus `fields` erwartete Länge prüfen.

### IN-04: `NaN` im Budgetvergleich ist nicht fail-closed

**File:** `scripts/ibkr_decision.py:392`; `scripts/ibkr_broker.py:780-781`
**Issue:** `preview.init_margin_change >= available_funds` ist bei `available_funds = nan` immer `False`, die Vorschau gälte als im Budget. `available_funds` kommt über `float(funds.value)` ohne NaN-/Inf-Prüfung (`_money` filtert nur die Preview-Zahlen). Ein ungültiger Wert wie `"abc"` löst im Gegenzug einen `ValueError` in `positions()` aus, der als "unexpected" endet statt als `SNAPSHOT_INCOMPLETE`.
**Fix:** `if not (preview.init_margin_change < available_funds): OVER_BUDGET`, und in `positions()` `cash` und `funds` über `_money` lesen und bei `None` `SNAPSHOT_INCOMPLETE` melden.

### IN-05: Das Budget wird pro Ticker isoliert gegen dieselbe `AvailableFunds`-Messung geprüft

**File:** `scripts/ibkr_executor.py:1370-1372, 1290-1295`
**Issue:** Ein Snapshot gilt für alle Ticker des Laufs. Die Summe der `initMarginChange` über mehrere BUY-Intents wird nicht gegen `available_funds` geprüft. Für den Dry-Run ist das akzeptabel, ein späterer Sende-Lauf (Phase 5) würde bei mehreren Käufen das Budget überschreiten.
**Fix:** Im Record den kumulierten Margin-Bedarf ausweisen oder in Phase 5 `available_funds` nach jedem akzeptierten Intent reduzieren. Als offener Punkt in `04-VERIFICATION.md` vermerken.

### IN-06: Die Entscheidungslog-Kopie ist ein geteilter Fixpfad; geparst wird von der Platte statt vom verifizierten Blob

**File:** `scripts/ibkr_executor.py:1103-1122`
**Issue:** Die Kopie wird vor der Prüfung nach `…/paper-log/decision-log.md` geschrieben (bleibt bei einem `verify`-Fehlschlag liegen), und `load_entries()` liest sie anschließend erneut vom selben Pfad. Zwei gleichzeitige Läufe können sich dazwischen überschreiben, die Einträge gehören dann zu einem anderen SHA als dem geloggten. Es gibt in Phase 4 bewusst kein Lock, daher nur ein Hinweis. CRLF ist unkritisch: Die Bytes bleiben unverändert, `read_text` normalisiert die Zeilenenden, und ein BOM führt zu einem verworfenen Eintrag, den `verify` als Fund meldet.
**Fix:** Den Blob in ein eindeutiges Tempfile schreiben (`verify` und `load_entries` darauf) oder `TradingMemoryLog._parse_entry` direkt auf `text.split(_SEPARATOR)` anwenden; die Kopie nur nach erfolgreicher Prüfung ablegen.

### IN-07: `_discard_previous(out)` löscht beliebige `--out`-Ziele ohne Plausibilitätsprüfung

**File:** `scripts/ibkr_executor.py:802-812, 1414-1423`
**Issue:** `preview --out <Pfad>` löscht die Datei vor jeder Validierung, auch wenn der Lauf danach an Argumenten scheitert (z. B. falsche Settings). Der Operator kann sich damit versehentlich eine fremde Datei löschen (`--out decision-log.md`). Das Muster stammt aus Phase 2 und ist bewusst (CR-02), aber `preview` verwendet es erstmals mit frei wählbarem Pfad neben einer produktiven Kopie.
**Fix:** Nur löschen, wenn die Datei als frühere Preview-Ausgabe erkennbar ist (JSON mit `"sent": false` und `schema_version`), sonst `EXIT_CONFIG`.

---

_Reviewed: 2026-10-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
