---
phase: 02-verbindung-paper-guard-und-kontolesen
reviewed: 2026-10-12T12:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - .env.example
  - pyproject.toml
  - scripts/IBKR_EXECUTION.md
  - scripts/daily_paper_run.py
  - scripts/ibkr_broker.py
  - scripts/ibkr_executor.py
  - tests/ibkr_fakes.py
  - tests/test_daily_paper_run.py
  - tests/test_ibkr_broker.py
  - tests/test_ibkr_executor.py
  - tests/test_ibkr_isolation.py
  - tests/test_reporting.py
  - tradingagents/reporting.py
findings:
  critical: 2
  warning: 7
  info: 7
  total: 16
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-10-12
**Depth:** standard (vorbestehende Dateien nur im Diff `43ae64c..HEAD`, neue Dateien vollständig)
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Geprüft wurden der Adapter `scripts/ibkr_broker.py`, der Ausführer `scripts/ibkr_executor.py`, ihre Tests und Fakes, das Handbuch sowie die additiven Änderungen an `daily_paper_run.py` und `reporting.py`. Das Verhalten der gepinnten Bibliothek wurde gegen den installierten Quelltext (`.venv/Lib/site-packages/ib_async`, 2.1.0) gegengelesen, nicht gegen das Gateway. Es wurde nichts ausgeführt, was das Gateway oder ein LLM erreicht.

Was hält: Der Paper-Guard vergleicht die exakte Liste (`accounts != [EXPECTED_ACCOUNT]`), eine leere Liste und eine Obermenge scheitern, und `managedAccounts` kommt aus dem Handshake (`wrapper.py:521-522`). Die Schreibsperre steht vor `connectAsync` und greift auch über `IB.placeOrder`/`whatIfOrder`, weil diese `self.client.placeOrder` über das Instanzattribut auflösen (`ib.py:791`, `:2211`). 326 läuft in der echten Bibliothek tatsächlich als `TimeoutError` auf (`client.py:227`, `_onSocketDisconnected` setzt `apiStart` nie), die Zuordnung zu `CLIENT_ID_IN_USE` stimmt also. Jede Anfrage hat eine endliche Zeitgrenze, und im Ausführer ist kein Pfad zu sehen, auf dem ein Fehler als Traceback auf der Konsole landet oder in Exit 0 verschluckt wird. Benutzername und Passwort werden nicht kopiert.

Die Hauptkritik betrifft die Fail-closed-Regel („Freigabe braucht einen positiven Beweis"): (1) Der Snapshot gilt als gültig, sobald *vor* dem Lesen kein 1100/2110 offen war. Ein Verbindungsabbruch während der Lesezugriffe wird nie geprüft. (2) Eine Portfolio-JSON hat kein Datum. Nach einem Fehllauf bleibt die alte Datei stehen, und `daily_paper_run.py --portfolio` übernimmt sie ohne jeden Nachweis, dass sie aktuell ist. Dazu kommen eine Schreibsperre, die nur vier Methodennamen sperrt statt der Nachrichtentypen auf dem Draht, ein Test, der beim Kontosummary „frisch bei jedem Aufruf" am Fake belegt, obwohl die Bibliothek beim zweiten Aufruf den Cache zurückgibt, und einige Negativ-Kontrollen, die nicht scheitern können.

## Critical Issues

### CR-01: Snapshot wird mit Exit 0 geschrieben, auch wenn während der Lesezugriffe ein 1100/2110/1300 eintrifft

**File:** `scripts/ibkr_broker.py:321-329`, `scripts/ibkr_broker.py:347-391`, `scripts/ibkr_executor.py:290-296`
**Issue:** `health()` prüft die Flags `link_lost`/`server_link_broken`/`port_changed` nur **vor** der Probe. `positions()` prüft sie überhaupt nicht. Die Reihenfolge in `run_account` ist `health()` → `positions()` → Exit 0. Trifft ein 1100 nach dem Flag-Check ein (während der Probe, zwischen Probe und `reqPositions` oder während `accountSummary`), beantwortet das Gateway `reqPositions`/`reqAccountSummary` aus seinem lokalen Stand. Diese Antworten sind gültig geformt, also entsteht kein Fehler, und die JSON wird mit Exit 0 geschrieben. Genau den Fall nennt der Docstring selbst als Annahme A4 („only the 1100/2110 flags reveal it"), nur dass die Flags nach dem Lesen niemand mehr ansieht. Das verletzt REQ-IBKR-09 (Liveness über echte Antwort, keine Order/kein Ergebnis zwischen 1100 und 1101/1102) und die Fail-closed-Regel: Dass kein Fehler auftrat, wird als Beweis eines gesunden Snapshots gewertet.
Verschärfend: Der `asyncio.sleep(0)`-Tick in `health()` (`:321`) arbeitet nur Callbacks ab, die schon in der Schleife stehen. Auf der Windows-Proactor-Schleife braucht ein Socket-Lesevorgang mindestens eine Iteration für die Completion und eine weitere für `data_received`. Ein 1100, der noch im Socket-Puffer liegt, wird von einem einzigen Tick also nicht zuverlässig verarbeitet.
**Fix:** Die Flags nach jedem Lesezugriff erneut prüfen und den Snapshot nur übernehmen, wenn über das ganze Lesefenster kein Abbruch gesehen wurde. Zum Beispiel einen Zähler der Link-Ereignisse vor und nach dem Lesen vergleichen:
```python
def _link_open(self) -> str | None:
    if self.link_lost: return "CONNECTIVITY_LOST"
    if self.server_link_broken: return "SERVER_LINK_BROKEN"
    if self.port_changed: return "PORT_CHANGED"
    return None

def positions(self) -> AccountSnapshot:
    ...
    events_before = self._link_events          # in _on_error bei 1100/2110/1300 hochzählen
    raw = self._request("reqPositions", ib.reqPositionsAsync)
    values = self._request("accountSummary", ...)
    self._call(lambda: asyncio.sleep(0.05), self._probe_timeout)  # Socket wirklich abarbeiten
    if self._link_open() or self._link_events != events_before:
        raise GatewayUnavailable(self._link_open() or "CONNECTIVITY_LOST", None,
                                 "link event during the snapshot; snapshot discarded")
```
Dazu eine Negativ-Kontrolle: ein `FakeIB`, das in `reqPositionsAsync` `errorEvent.emit(-1, 1100, ...)` auslöst und trotzdem Positionen liefert. Erwartet werden Exit 3 und keine Datei. Mit dem heutigen Code scheitert dieser Test.

### CR-02: Veraltete Portfolio-JSON wird ohne Frischebeweis in die Analyse übernommen

**File:** `scripts/ibkr_executor.py:257-314`, `scripts/daily_paper_run.py:391-396` (Diff), `scripts/IBKR_EXECUTION.md:187-190`, `:209-217`, `tests/test_ibkr_executor.py:477-484`
**Issue:** Ein fehlgeschlagener `account`-Lauf (Exit 3/8/1) lässt die bestehende `--out`-Datei absichtlich stehen. Das ist so getestet (`test_existing_out_file_survives_a_failed_run`) und dokumentiert („A failed run leaves an existing file untouched"). Die JSON enthält **kein** `as_of`. `AccountSnapshot.as_of` landet nur im Log (`test_account_json_contains_only_schema_fields` stellt das sogar sicher). `daily_paper_run.py --portfolio` prüft nur das Schema. Das Handbuch zeigt beide Befehle als getrennte cmd-Zeilen ohne `&&`. Fällt der erste aus (Gateway zu, Guard verletzt), läuft der zweite also mit dem Buch von gestern, vorgestern oder letzter Woche, und die Agenten bekommen einen falschen Bestand als „Portfolio at the analysis date" vorgelegt. `portfolio.py:5-8` stuft genau das Erfinden eines Kontostands als den Fehler ein, den es zu vermeiden gilt. 02-PATTERNS.md:147 erkennt „alte Datei bleibt stehen" als falsch, verlässt sich aber allein auf den Exit-Code des Ausführers, den der Verbraucher nie sieht. Fail-closed verlangt hier einen positiven Frischebeweis beim Verbraucher.
**Fix:** Eine von zwei Varianten, am besten beide:
1. Der Ausführer entfernt `--out` zu Beginn jedes Laufs, also vor dem Connect. Ein Fehllauf hinterlässt dann *keine* Datei, und `daily_paper_run` bricht mit `ConfigError` ab. Den Test `test_existing_out_file_survives_a_failed_run` in die Gegenrichtung drehen.
2. `as_of` (UTC, ISO) mitschreiben, als optionales Feld in `PortfolioContext` oder als Sidecar `<out>.meta.json`, und in `daily_paper_run.main` ablehnen, wenn `as_of` fehlt oder nicht vom `trade_date`/heute stammt:
```python
if portfolio.as_of is None or portfolio.as_of.date() != datetime.now(UTC).date():
    raise ConfigError(f"portfolio file {args.portfolio} is not from today (as_of={portfolio.as_of})")
```
Im Handbuch die Befehle mit `&&` verketten.

## Warnings

### WR-01: Schreibsperre ist eine Sperrliste von vier Methodennamen, nicht eine Sperre auf Nachrichtentypen

**File:** `scripts/ibkr_broker.py:43-44`, `scripts/ibkr_broker.py:168-177`
**Issue:** `_arm_write_barrier` ersetzt nur `placeOrder`, `cancelOrder`, `reqGlobalCancel` und `exerciseOptions` auf dem Client. Offen bleiben `Client.replaceFA` (`client.py:805`, Nachricht 19, ändert die FA-Konfiguration), der rohe Sendeweg `Client.send`/`sendMsg` (`client.py:245`, `:323`), über den jede Order-Nachricht ohne die gesperrten Methoden abgehen kann, und jeder Schreibweg, den eine spätere Bibliotheksversion hinzufügt (Protobuf-Migration, REQ-IBKR-07). Weil `readonly=True` nichts sperrt und der Gateway-Schalter in den Phasen 2–4 nicht verlässlich an ist (REQ-IBKR-09-Korrektur, Handbuch:253-257 „No 321 at connect"), ist diese Sperrliste die einzige Barriere. Eine Sperrliste ist aber kein positiver Beweis, dass nichts schreiben kann.
**Fix:** Zusätzlich auf Drahtebene sperren, denn `send` ist der gemeinsame Engpass aller Anfragen:
```python
_WRITE_MSG_IDS = frozenset({3, 4, 19, 21, 58})  # PLACE_ORDER, CANCEL_ORDER, REPLACE_FA, EXERCISE_OPTIONS, REQ_GLOBAL_CANCEL

def _arm_write_barrier(client) -> None:
    ...  # bestehende Methoden-Sperre
    original_send = client.send
    def guarded_send(*fields, **kw):
        if fields and fields[0] in _WRITE_MSG_IDS:
            raise ReadOnlyViolation(f"read-only session: message {fields[0]} refused")
        return original_send(*fields, **kw)
    client.send = guarded_send
```
Dazu ein Test am echten `ib_async.Client`, der `client.send(3, ...)` direkt aufruft und `ReadOnlyViolation` erwartet.

### WR-02: „Frisch bei jedem Aufruf" für das Kontosummary ist nur am Fake bewiesen; die Bibliothek liefert beim zweiten Aufruf den Cache

**File:** `scripts/ibkr_broker.py:347-359`, `tests/test_ibkr_broker.py:295-301`, `tests/ibkr_fakes.py:144-148`
**Issue:** `ib.accountSummaryAsync()` sendet nur dann eine Anfrage, wenn `wrapper.acctSummary` leer ist (`ib.py:2232-2235`). Ab dem zweiten Aufruf in derselben Sitzung kommt der Bibliothekscache zurück. `test_positions_fresh_each_call` zählt Aufrufe am `FakeIB`, das bei jedem Aufruf `"account_summary"` protokolliert. Der Test belegt also eine Eigenschaft des Fakes, nicht die des Adapters. Der Docstring „asked fresh on every call (REQ-IBKR-12)" ist für den Kassenbestand falsch, sobald ein späterer Plan `positions()` zweimal pro Sitzung aufruft, etwa vor und nach einer Order. Das widerspricht REQ-IBKR-67 (Annahmen, auf die ein Test baut, müssen gemessen sein).
**Fix:** Die Anfrage explizit stellen und danach das Ergebnis lesen:
```python
self._request("accountSummary", ib.reqAccountSummaryAsync)
values = ib.accountSummary(EXPECTED_ACCOUNT)
```
Die Abonnements dabei sauber beenden oder den Cache vorher leeren. Im Fake `accountSummaryAsync` so modellieren wie die Bibliothek (Cache nach dem ersten Aufruf), damit der Test am heutigen Code scheitert.

### WR-03: Unerwartete Fehler während des Connects enden als Exit 1 („nichts getan"), obwohl eine Sitzung bestand

**File:** `scripts/ibkr_executor.py:375-404`, `scripts/ibkr_broker.py:288-290`
**Issue:** `progress["connected"]` wird erst gesetzt, wenn `__enter__` zurückgekehrt ist. Jede unerwartete Ausnahme innerhalb von `connect()` landet über `except BaseException: raise` im generischen Zweig und ergibt `EXIT_CONFIG`, laut Tabelle „configuration error – nothing was done". Gemeint sind etwa ein `ValueError` oder `AttributeError` aus dem Handshake-Parsing der Bibliothek, ein `ReadOnlyViolation` oder ein Fehler aus `ib.managedAccounts()`. Zu diesem Zeitpunkt stand aber schon ein Socket, und es liefen Handshake und Positionsabfrage (`ib.py:2056`). Ein Scheduler-Retry oder ein Operator, der nach Exit-Code verzweigt (REQ-IBKR-55: disjunkte Bedeutungen), liest das falsch. Ein `ReadOnlyViolation`, das sicherheitsrelevanteste Ereignis dieser Phase, hat zudem keinen eigenen Zustand und erscheint nur als `UNEXPECTED`.
**Fix:** `progress["connecting"] = True` vor dem `with` setzen und alles, was nach dem Start von `connect()` passiert, als `EXIT_GATEWAY` werten. Für `ReadOnlyViolation` einen eigenen `except`-Zweig mit `ibkr-state=WRITE_REFUSED` vorsehen, mit `EXIT_GATEWAY` oder einem eigenen, dokumentierten Code.

### WR-04: Connect-Zeitgrenze ist faktisch 15 s statt der dokumentierten 10 s, und kein Test deckt einen hängenden Connect ab

**File:** `scripts/ibkr_broker.py:242-263`, `scripts/IBKR_EXECUTION.md:173-174`, `tests/ibkr_fakes.py:114-126`
**Issue:** Die äußere Grenze ist `timeout + 5` (magische Zahl). Innen stapelt die Bibliothek bis zu drei eigene 10-s-Wartezeiten: TCP-Connect (`client.py:216`), `apiStart` (`:227`) und Startup-Positionen (`ib.py:2077`). Die äußere Grenze schneidet bei 15 s ab, und die Fehlermeldung behauptet „within 10.0s". Das ist sicherheitsneutral, aber Handbuch und Log nennen einen Wert, der nicht gilt. REQ-IBKR-62 fordert als Nachweis einen „Test mit nicht antwortender Gegenstelle". Für Probe und `reqPositions` gibt es ihn, für den Connect nicht: `FakeIB.connectAsync` kann nur sofort werfen, nie hängen. Ginge die äußere `wait_for`-Grenze verloren, bliebe kein Test rot.
**Fix:** Die Konstante benennen (`CONNECT_GRACE_S = 5.0`), im Handbuch „bis zu `CONNECT_TIMEOUT_S + CONNECT_GRACE_S`" schreiben und die Meldung auf die tatsächliche Grenze umstellen. Dazu ein Fake-Modus `refuse="hang"` (`await _forever()`) und ein Test mit `connect_timeout=0.05` und einer Grace, die im Test injizierbar ist, der `CONNECT_TIMEOUT` in unter 1 s erwartet.

### WR-05: Negativ-Kontrollen für „keine Schreibaufrufe" sind teilweise wirkungslos, und der Guard-Test pinnt Listen- statt Mengenvergleich nicht

**File:** `tests/test_ibkr_broker.py:21`, `:64`, `:81-96`; `tests/test_ibkr_executor.py:303`, `:400`; `tests/ibkr_fakes.py:105-106`, `:171-175`
**Issue:** `FORBIDDEN_CALLS` enthält `"whatIfOrder"` (und indirekt `placeOrder` auf IB-Ebene). `FakeIB.whatIfOrder`/`placeOrder` werfen aber `AssertionError`, statt in `calls` zu protokollieren. Der Eintrag `"whatIfOrder"` kann also nie in `fake.calls` stehen, und die Assertion `not any(... FORBIDDEN_CALLS)` kann für ihn nicht scheitern (REQ-IBKR-66). Auf Client-Ebene ersetzt die Sperre die Recorder vor dem Connect. Danach landet ein Schreibaufruf als `ReadOnlyViolation` und nicht in `calls`, und die Assertion prüft nur noch den Fall „Sperre fehlt". Beim Guard fehlt der Fall `["DUQ634065", "DUQ634065"]` (Duplikat). Eine Umstellung auf `set(accounts) == {EXPECTED_ACCOUNT}` bestünde alle heutigen Tests. Auch Groß/Klein (`"duq634065"`) und Leerraum (`" DUQ634065"`) sind nicht gepinnt.
**Fix:** In `FakeIB` jede IB-Schreibmethode protokollieren *und* werfen (`self.calls.append(name); raise AssertionError(...)`). Zusätzlich auf dem Fake-Client nach dem Lauf prüfen, dass jeder Sperraufruf, falls es einen gab, zu `ReadOnlyViolation` geführt hat. Die Guard-Parametrisierung um `["DUQ634065", "DUQ634065"]`, `["duq634065"]`, `[" DUQ634065"]` und `["DUQ6340650"]` ergänzen.

### WR-06: Eigene Event-Loop bleibt als globale Loop geschlossen gesetzt; bei fehlender Bibliothek wird sie nie geschlossen

**File:** `scripts/ibkr_broker.py:231-237`, `scripts/ibkr_broker.py:434-443`
**Issue:** `connect()` ruft `asyncio.set_event_loop(self._loop)` auf, und `_disconnect()` schließt die Loop, setzt die globale Loop aber nicht zurück. Ein zweiter `IbkrBroker` im selben Prozess, etwa ein Retry in späteren Phasen oder jeder Code, der `asyncio.get_event_loop()` nutzt, findet danach eine geschlossene Loop vor. Wirft `self._ib_factory()` (fehlendes `ibkr`-Extra, getesteter Pfad `test_missing_extra_exits_1_with_hint`), ist die Loop schon erzeugt und global gesetzt, wird aber nie geschlossen, weil der Ausnahmepfad vor dem `try` liegt. Außerdem plant `transport.close()` in `ib.disconnect()` (`connection.py:48`) `_call_connection_lost` per `call_soon` ein, und die Loop wird gleich danach geschlossen. Das Socket-Handle schließt dann erst beim Prozessende oder bei der GC (nach `write_eof` ist es halboffen).
**Fix:**
```python
def _disconnect(self) -> None:
    ib, self._ib = self._ib, None
    try:
        if ib is not None:
            with contextlib.suppress(ValueError, AttributeError):
                ib.errorEvent -= self._on_error
            ib.disconnect()
            if self._loop is not None and not self._loop.is_closed():
                self._loop.run_until_complete(asyncio.sleep(0))  # connection_lost laufen lassen
    finally:
        if self._owns_loop and self._loop is not None:
            self._loop.close()
            asyncio.set_event_loop(None)
            self._loop, self._owns_loop = None, False
```
In `connect()` den Aufruf von `self._ib_factory()` in das `try` mit `_disconnect()` aufnehmen.

### WR-07: Der lokale Lauf mit `--portfolio` schreibt Kontodaten in ein nicht ignoriertes Verzeichnis des öffentlichen Forks

**File:** `tradingagents/reporting.py:46-49` (Diff), `scripts/IBKR_EXECUTION.md:217`
**Issue:** `_header` übernimmt seit dieser Phase den gerenderten Portfolio-Block (Kassenbestand, Positionen, Durchschnittspreise) in `complete_report.md`. Der dokumentierte Befehl schreibt nach `results\paper-local` und `paper-state`, beide relativ zum Repo. `git check-ignore` meldet für keines davon eine Ignore-Regel. Ein `git add -A` mit Push auf `fork` (stevexyz2003/TradingAgents, öffentlich) veröffentlicht den Kontostand. Es ist ein Paper-Konto, aber der Kontext ist der Weg zu einem echten Konto.
**Fix:** Im Handbuch einen Pfad außerhalb des Git-Baums verwenden (`%LOCALAPPDATA%\TradingEngineX\paper-local`, analog zum Log), oder `results/paper-local/` und `paper-state/` in `.gitignore` aufnehmen und das mit einem `git check-ignore`-Test in `test_ibkr_isolation.py` absichern.

## Info

### IN-01: Zeilenverweis im Handbuch verschoben

**File:** `scripts/IBKR_EXECUTION.md:49`
**Issue:** `scripts/ibkr_broker.py:65-68` für den 321-Marker. Tatsächlich stehen Kommentar und Eintrag in Zeile 64-67. Das Handbuch beansprucht, dass jede Aussage nachprüfbar per `file:line` belegt ist.
**Fix:** Auf `:64-67` korrigieren. Besser noch: einen Test, der die `file:line`-Verweise des Handbuchs gegen die Symbole prüft, oder Verweise auf Symbolnamen statt Zeilennummern.

### IN-02: Keine Endlichkeitsprüfung für Kasse und Durchschnittskosten

**File:** `scripts/ibkr_broker.py:367-368`, `:388`
**Issue:** `float(cash.value)` akzeptiert `"nan"`/`"inf"`. Pydantic serialisiert NaN standardmäßig als `null`. Die Gegenprobe mit `load_portfolio` liest dann `cash=None` („unbekannt"), und der Lauf endet mit Exit 0. Ein leerer Wert (`""`) landet als `ValueError` im `UNEXPECTED`-Zweig statt als `SNAPSHOT_INCOMPLETE`.
**Fix:** `math.isfinite` prüfen, sonst `GatewayUnavailable(SNAPSHOT_INCOMPLETE, ...)`. `ValueError` beim Parsen in denselben Zustand umwandeln.

### IN-03: Doppelte Ticker im `PortfolioContext` möglich

**File:** `scripts/ibkr_executor.py:229-251`
**Issue:** Zwei STK-Zeilen mit gleichem `symbol` (gleiches Papier an zwei Börsen oder in zwei Währungen, unterschiedliche `conId`) werden zu zwei `Position(ticker=...)` mit gleichem Ticker. `position_in` liefert nur die erste, die zweite erscheint unter „Other positions" mit demselben Namen.
**Fix:** Nach `conId` deduplizieren oder bei Ticker-Kollision mit `SNAPSHOT_INCOMPLETE` abbrechen, bis Phase 3 die Allow-List bringt.

### IN-04: Code 2107 nicht zugeordnet

**File:** `scripts/ibkr_broker.py:49-75`
**Issue:** Im ersten echten Lauf beobachtet (Handbuch:250-252), erscheint als `UNKNOWN` auf WARNING-Ebene. Es ist schon als Folgearbeit vermerkt.
**Fix:** `2107: "FARM_INACTIVE"` aufnehmen und in `INFO_CODES` führen.

### IN-05: Isolationstests sind rein lexikalisch

**File:** `tests/test_ibkr_isolation.py:272-290`, `:306-310`
**Issue:** Der Importtest erkennt `importlib.import_module("ib_async")` und `__import__` nicht. Der Order-ID-Test sucht nur die Literale `orderId=` und `.orderId =`. `setattr(order, "orderId", 1)` oder `orderId = 5` mit Leerzeichen rutschen durch.
**Fix:** Im AST auch `Call`-Knoten auf `import_module`/`__import__` mit dem String `ib_async` prüfen. Für die Order-ID nach `Attribute(attr="orderId")`-Zuweisungen und Keyword-Argumenten `orderId` suchen.

### IN-06: Atomares Schreiben ohne `fsync`; verwaiste `.tmp` nach Abbruch

**File:** `scripts/ibkr_executor.py:266-276`
**Issue:** Vor `os.replace` steht kein `flush`/`fsync`. Bei Stromausfall kann eine leere Zieldatei entstehen. Beendet das Zeitlimit des Task Schedulers (REQ-IBKR-56) den Prozess hart, bleiben `portfolio.json.<uuid>.tmp`-Dateien liegen, weil `except BaseException` dann nicht läuft.
**Fix:** Mit `open(...)` schreiben, dann `f.flush(); os.fsync(f.fileno())`. Beim Start alte `<name>.*.tmp` neben dem Ziel entfernen.

### IN-07: `IBKR_HOST` wird nicht auf Loopback beschränkt

**File:** `scripts/ibkr_executor.py:142-162`
**Issue:** Jeder Host wird akzeptiert. Der Paper-Guard fängt ein fremdes Konto ab, aber eine `.env`, die auf ein entferntes Gateway zeigt, wird nicht bemerkt. Das ist im Zusammenhang mit der offenen Beobachtung relevant, dass das Gateway auf `:::7497` lauscht (Handbuch:42-45).
**Fix:** Für Phase 2 nur `127.0.0.1`/`::1`/`localhost` zulassen und Ausnahmen bewusst per Konstante freigeben.

---

_Reviewed: 2026-10-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
