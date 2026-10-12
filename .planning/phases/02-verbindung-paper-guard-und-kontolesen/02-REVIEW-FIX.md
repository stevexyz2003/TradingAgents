---
phase: 02-verbindung-paper-guard-und-kontolesen
fixed_at: 2026-10-12T13:44:58Z
review_path: .planning/phases/02-verbindung-paper-guard-und-kontolesen/02-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 2: Bericht zu den Review-Korrekturen

**Korrigiert am:** 2026-10-12T13:44:58Z
**Quelle:** .planning/phases/02-verbindung-paper-guard-und-kontolesen/02-REVIEW.md
**Iteration:** 1

**Zusammenfassung:**
- Befunde im Umfang (CR-01, CR-02, WR-01..WR-07; die IN-* waren nicht beauftragt): 9
- Korrigiert: 9
- Übersprungen: 0

Gearbeitet wurde in einem isolierten Worktree. `main` wurde per Fast-Forward von `96089ca` auf `fdee790` gebracht. Kein Lauf hat das Gateway oder ein LLM erreicht. Alle Tests laufen gegen `FakeIB` oder gegen das unverbundene `ib_async`-Objekt (2.1.0). Für jede Sicherung wurde die Negativ-Kontrolle vor dem Fix geschrieben und am unveränderten Code als rot belegt (REQ-IBKR-66). Wo ein Test schon am alten Code grün war (Pinning), wurde die Wirksamkeit per Mutation belegt.

**Gates:**
- `ruff check .`: vor jedem Commit grün.
- Volle Suite nach dem letzten Fix: **1 failed, 1553 passed, 4 skipped** (1 deselected, 101 subtests passed).
- Basis vorher: 1 failed, 1494 passed, 4 skipped. Neu sind damit 59 Tests.
- Der eine Fehlschlag ist der bekannte `test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`.
- Die IBKR- und Paper-Run-Module im Hauptbaum nach dem Fast-Forward: 206 passed.

**Randbedingungen eingehalten:**
- `ib_async` wird weiterhin nur in `scripts/ibkr_broker.py` importiert.
- Der Adapter hat weiter genau drei öffentliche Methoden (`connect`, `positions`, `health`).
- Nicht angefasst: `tradingagents/reporting.py`, `tradingagents/portfolio.py`, `.github/workflows/`.

## Korrigierte Befunde

### CR-01: Snapshot wird mit Exit 0 geschrieben, auch wenn während der Lesezugriffe ein 1100/2110/1300 eintrifft

**Geänderte Dateien:** `scripts/ibkr_broker.py`, `scripts/IBKR_EXECUTION.md`, `tests/ibkr_fakes.py`, `tests/test_ibkr_broker.py`, `tests/test_ibkr_executor.py`
**Commit:** a1e4283
**Status:** korrigiert, Logik bitte menschlich gegenlesen
**Umgesetzt:**
- `_on_error` protokolliert jedes Ereignis aus `LINK_CODES` = {1100, 1101, 1102, 1300, 2110} in einer Liste.
- `positions()` liest nicht, solange ein Flag offen ist.
- Nach der letzten Antwort lässt `positions()` die Loop `SNAPSHOT_SETTLE_S` = 0,05 s weiterlesen. Das ist der Proactor-Einwand des Reviews.
- Lag ein Link-Ereignis im Fenster, verwirft `positions()` den Snapshot mit `GatewayUnavailable`. Den Zustand bestimmt das erste Ereignis, also bleibt „1100 → 1102" `CONNECTIVITY_LOST`.
- `health()` verwirft eine Probe-Antwort nach derselben Regel.

**Negativ-Kontrollen:**
- 13 Tests waren am alten Code rot: Ereignisse während positions/summary/probe, offene Flags vor dem Lesen, und im Executor Exit 3 ohne Datei.
- Der Test für einen 1100 knapp nach der letzten Antwort wird mit `settle=0` ebenfalls rot. Der Settle-Schritt trägt also.

### CR-02: Veraltete Portfolio-JSON wird ohne Frischebeweis in die Analyse übernommen

**Geänderte Dateien:** `scripts/ibkr_executor.py`, `scripts/daily_paper_run.py`, `scripts/IBKR_EXECUTION.md`, `tests/test_ibkr_executor.py`, `tests/test_daily_paper_run.py`
**Commit:** f5ef338
**Status:** korrigiert, Logik bitte menschlich gegenlesen
**Umgesetzt:** Beide Varianten des Reviews, jede für sich ausreichend.
1. Der Executor entfernt die `--out`-Datei eines früheren Laufs als ersten Schritt, noch vor dem Lesen der Settings (`_discard_previous`). Ein Fehllauf hinterlässt also keine Datei. Lässt sich die Datei nicht entfernen, endet der Lauf mit Exit 1, bevor eine Verbindung aufgebaut wird.
2. Der Executor schreibt `as_of` (UTC, ISO 8601) als zusätzlichen Top-Level-Schlüssel. `daily_paper_run.py --portfolio` liest die Datei genau einmal und verlangt ein `as_of` mit Zeitzone. Es darf höchstens 5 min in der Zukunft liegen und nicht älter sein als `--portfolio-max-age-minutes` (Standard 60). Das gilt auch unter `--preflight`.

**Entscheidung zum Schema:** `PortfolioContext` ist ein Pydantic-v2-Modell ohne `model_config`, und `extra="ignore"` ist der Standard (geprüft). `load_portfolio()` liest die Datei daher unverändert, und `fingerprint()` bleibt gleich. Deshalb kommt `as_of` als Extra-Schlüssel in die Datei selbst, ohne Sidecar und ohne Änderung an `tradingagents/portfolio.py`. Ein Test hält den Schlüsselnamen in beiden Skripten gleich und prüft, dass eine vom Executor geschriebene Datei den Frischetest besteht. Das Handbuch verkettet Snapshot und Paper-Run mit `&&`.
**Folge für den Betrieb:** Eine handgeschriebene `--portfolio`-Datei ohne `as_of` lehnt `daily_paper_run.py` jetzt ab. Für die Upstream-CLI `tradingagents --portfolio` ändert sich nichts.
**Negativ-Kontrollen:** 19 Tests waren am alten Code rot. Darunter fünf Fehlerpfade, die keine Datei hinterlassen dürfen, und die Fälle missing/null/garbage/naive/yesterday/just-stale/future.

### WR-01: Schreibsperre ist eine Sperrliste von vier Methodennamen, nicht eine Sperre auf Nachrichtentypen

**Geänderte Dateien:** `scripts/ibkr_broker.py`, `scripts/IBKR_EXECUTION.md`, `tests/ibkr_fakes.py`, `tests/test_ibkr_broker.py`
**Commit:** 54e1210
**Status:** korrigiert
**Umgesetzt:**
- Gegen den Quelltext bestätigt: Jede Anfrage läuft über `Client.send` und dann `Client.sendMsg`. `replaceFA` sendet die Nachricht 19, und die Methoden-Sperre deckt das nicht ab.
- `_arm_write_barrier` umhüllt jetzt zusätzlich `send` (über die Felder) und `sendMsg` (über die serialisierte Nachricht, ID vorn). Abgewiesen werden die Write-IDs 3, 4, 19, 21 und 58 (`_WRITE_MESSAGE_IDS`). Lesezugriffe gehen unverändert durch.

**Negativ-Kontrollen:**
- Am echten Client-Objekt: `send`/`sendMsg` mit jeder Write-ID und `client.replaceFA`. Das waren 6 Tests, am alten Code rot mit `ConnectionError` statt Abweisung.
- `reqPositions` (61) erreicht weiterhin das `send` der Bibliothek.

**Grenze:** Die Sperre bleibt eine Deny-Liste, jetzt auf Drahtebene. Eine Allow-Liste der Lese-IDs wäre der stärkere Beweis, setzt aber eine Messung voraus, welche IDs Handshake und Lesezugriffe am realen Gateway senden (REQ-IBKR-67). Das ist hier nicht gemessen und darum nicht gebaut.

### WR-02: „Frisch bei jedem Aufruf" für das Kontosummary ist nur am Fake bewiesen

**Geänderte Dateien:** `scripts/ibkr_broker.py`, `scripts/IBKR_EXECUTION.md`, `tests/ibkr_fakes.py`, `tests/test_ibkr_broker.py`
**Commit:** f3d2c6b
**Status:** korrigiert
**Umgesetzt:**
- Bestätigt: `accountSummaryAsync` fragt nur bei leerem `wrapper.acctSummary` (`ib.py:2232-2235`).
- `positions()` leert diesen Cache vor jedem Aufruf. So geht dieselbe Anfrage mit denselben Tags wie im gemessenen Erstlauf raus, und keine Zeile einer älteren Antwort überlebt.
- Den Vorschlag des Reviews, `reqAccountSummaryAsync` direkt aufzurufen, habe ich verworfen: Alte Zeilen blieben im Cache stehen.
- Der Fake cached jetzt wie die Bibliothek. Ein Test am echten `IB`-Objekt hält das Cache-Gate fest, auf dem der Fix aufbaut.

**Negativ-Kontrollen:** 2 Tests waren am alten Code rot. Der zweite Aufruf muss den neuen Kassenbestand liefern, und eine zweite Antwort ohne Cash-Zeile darf nicht auf den Cache zurückfallen.
**Bekannte Grenze (dokumentiert):** Die Bibliothek beendet das Summary-Abonnement nie, also bleibt pro Aufruf eines offen. Phase 2 ruft einmal pro Sitzung auf. Ein späterer Plan mit wiederholten Aufrufen muss die Abonnements beenden.

### WR-03: Unerwartete Fehler während des Connects enden als Exit 1 („nichts getan")

**Geänderte Dateien:** `scripts/ibkr_executor.py`, `scripts/ibkr_broker.py`, `scripts/IBKR_EXECUTION.md`, `tests/test_ibkr_executor.py`, `tests/test_ibkr_broker.py`
**Commit:** 2c6adde
**Status:** korrigiert, Logik bitte menschlich gegenlesen
**Umgesetzt:**
- `run_account` baut den Adapter zuerst und setzt dann `progress["connecting"]`. Ab da liefert der generische Zweig `EXIT_GATEWAY`. Ein Fehler vor dem Connect bleibt Exit 1, das hält ein eigener Pinning-Test fest.
- `ReadOnlyViolation` hat einen eigenen Zweig: `ibkr-state=WRITE_REFUSED`, Exit 3, im Handbuch dokumentiert.

**Zusatzbefund unterwegs:** Wirft `managedAccounts()`, blieb die Sitzung offen, denn `__exit__` läuft nicht, wenn `connect()` wirft. Das Lesen für den Guard trennt jetzt bei jedem Fehler die Verbindung (eigener Test, ohne den Fix rot).
**Negativ-Kontrollen:** 3 Tests waren am alten Code rot: ein Handshake-Fehler und zwei Wege, auf denen ein Schreibversuch abgewiesen wird.

### WR-04: Connect-Zeitgrenze ist faktisch 15 s statt der dokumentierten 10 s

**Geänderte Dateien:** `scripts/ibkr_broker.py`, `scripts/IBKR_EXECUTION.md`, `tests/ibkr_fakes.py`, `tests/test_ibkr_broker.py`
**Commit:** 46cef85
**Status:** korrigiert
**Umgesetzt:**
- Bestätigt: Die Bibliothek wartet in drei Schritten jeweils bis `timeout`.
- `CONNECT_GRACE_S = 5.0` ist jetzt eine benannte Konstante und als `connect_grace` injizierbar.
- Die Meldung `CONNECT_TIMEOUT` nennt die tatsächliche Grenze. Das Handbuch schreibt 10 s + 5 s = 15 s.
- `FakeIB` kennt jetzt `refuse="hang"`.

**Negativ-Kontrolle:** Ein hängender Connect mit 0,05 s + 0,05 s muss in unter 1 s mit `CONNECT_TIMEOUT` enden. Am alten Code dauerte derselbe Hang gemessen 5,07 s, während die Meldung „within 0.05s" lautete.

### WR-05: Negativ-Kontrollen für „keine Schreibaufrufe" teilweise wirkungslos; Guard-Test pinnt Listenvergleich nicht

**Geänderte Dateien:** `tests/ibkr_fakes.py`, `tests/test_ibkr_broker.py`
**Commit:** 411f8ea
**Status:** korrigiert
**Umgesetzt:**
- Jede verbotene `FakeIB`-Methode protokolliert erst ihren Namen und wirft dann.
- Neue Kontrollen:
  - Ein Schreibaufruf auf IB-Ebene erscheint in `calls` (mit dem alten Fake rot).
  - Ohne Sperre löst ein Client-Write während des Connects die Prüfung aus.
  - Mit Sperre kommt `ReadOnlyViolation`, und die Verbindung wird getrennt.
- Neue Guard-Fälle: Duplikat, Kleinschreibung, führender und nachgestellter Leerraum, längere ID, Präfix.

**Mutationsbeleg:** Die neuen Guard-Fälle sind am heutigen Code naturgemäß grün. Mit vorübergehend verändertem Vergleich scheitern 1 (`set()`), 3 (`strip().upper()`) bzw. 3 (Präfix-Match) von ihnen. Der Code wurde danach per `git checkout` zurückgesetzt.

### WR-06: Eigene Event-Loop bleibt als globale Loop geschlossen gesetzt; bei fehlender Bibliothek nie geschlossen

**Geänderte Dateien:** `scripts/ibkr_broker.py`, `tests/test_ibkr_broker.py`
**Commit:** 24b6771
**Status:** korrigiert
**Umgesetzt:**
- Der Aufruf von `_ib_factory()` steht in einem `try`, das bei Fehler trennt.
- `_disconnect()` lässt nach `ib.disconnect()` die Loop einmal laufen, damit `connection_lost` ausgeführt wird.
- Im `finally` schließt `_disconnect()` eine eigene Loop und ruft `set_event_loop(None)` auf.

**Negativ-Kontrollen:** 3 Tests waren am alten Code rot, jeder aus dem befundenen Grund: globale Loop nicht zurückgesetzt, Loop bei fehlendem Extra offen, `call_soon` aus `disconnect()` nicht gelaufen.
**Testtechnik:** Eine echte neue Loop öffnet unter Windows ein Loopback-Socketpaar, und die suiteweite Netzsperre blockiert das. Die Tests nutzen deshalb einen dünnen Loop-Stellvertreter über der Session-Loop.

### WR-07: Lokaler Lauf mit `--portfolio` schreibt Kontodaten in ein nicht ignoriertes Verzeichnis

**Geänderte Dateien:** `.gitignore`, `scripts/IBKR_EXECUTION.md`, `tests/test_ibkr_isolation.py`
**Commit:** fdee790
**Status:** korrigiert
**Umgesetzt:**
- Präzisierung des Befunds: Die Reports unter `<out>/reports/` fing die bestehende Regel `reports/` schon ab. Offen waren aber die Archivkopien unter `<state>/runs/<Datum>/<Ticker>.md` (`_archive`), das Decision-Log, die Summaries und die Graph-Logs.
- `.gitignore` führt jetzt `/results/paper-local/` und `/paper-state/`, mit deutschem Begründungskommentar wie die bestehenden Einträge.
- Ein Guard in `test_ibkr_isolation.py` liest jedes `--out`/`--state`-Verzeichnis aus dem Paper-Run-Befehl des Handbuchs und prüft mit `git check-ignore` vier repräsentative Dateien.
- Das Handbuch dokumentiert die Regel.

**Negativ-Kontrolle:** Vor der Ignore-Regel rot (`results/paper-local/runs/2026-10-12/AAPL.md is not ignored`). Ein erster Entwurf mit einer Probe unter `reports/` war fälschlich grün und wurde verschärft.
**`scripts/PAPER_RUN.md`:** nicht geändert. Seine Beispiele schreiben nach `/tmp` und `~/.tradingagents`, also außerhalb des Baums, und es erwähnt `--portfolio` nicht.

---

_Korrigiert: 2026-10-12T13:44:58Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
