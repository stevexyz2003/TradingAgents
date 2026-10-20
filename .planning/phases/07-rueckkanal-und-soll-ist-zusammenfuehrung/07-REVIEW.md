---
phase: 07-rueckkanal-und-soll-ist-zusammenfuehrung
reviewed: 2026-10-20T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - scripts/ibkr_publish.py
  - scripts/ibkr_executor.py
  - scripts/ibkr_report.py
  - scripts/ibkr_decision.py
  - scripts/ibkr_paperlog.py
  - scripts/daily_paper_run.py
  - scripts/state_maintenance.py
  - .github/workflows/daily-paper-run.yml
findings:
  critical: 0
  warning: 6
  info: 3
  total: 9
status: issues_found
---

# Phase 7: Code-Review-Bericht

**Geprüft:** 2026-10-20
**Tiefe:** standard
**Dateien:** 8 Quelldateien (die Testdateien wurden gemäß Auftrag nicht inhaltlich bewertet)
**Status:** issues_found

## Zusammenfassung

Geprüft wurden der Git-Schreibpfad `ibkr_publish.py`, `run_publish` im Executor, der Soll/Ist-Bericht, der fail-open Leser in `daily_paper_run.py`, `state_maintenance backup` und der Workflow.

Einschränkungen dieses Reviews:
- Git Bash hing in dieser Sitzung. Ich konnte deshalb weder `git diff b346a33..HEAD` ausführen noch die Tests laufen lassen. Gelesen wurde der Stand von HEAD. Bei `ibkr_executor.py`, `ibkr_paperlog.py`, `ibkr_decision.py` und `state_maintenance.py` habe ich nur die Phase-7-Abschnitte gelesen.
- Das Gesamtbild stützt sich auf den Quelltext, nicht auf Testläufe.

Gesamteindruck: Die Sicherheitsgrenzen sind sauber gezogen.
- Remote und Branch sind Konstanten und werden über `validate_ref_name` geprüft.
- Der Push hat nur die Form `HEAD:refs/heads/ibkr-log`, ohne `+` und ohne `--force`.
- `fork == origin` wird abgelehnt.
- Die Workflow-Eingaben laufen ausschließlich über `env:`, es gibt keine Shell-Interpolation von `inputs.*`.
- Der Lock wird vor jedem Git-Aufruf freigegeben.

Kritische Befunde gibt es keine (kein erreichbarer Force-Push, kein Schreibzugriff auf `paper-log` oder `origin`, keine Token-Ausgabe über den Normalpfad). Es bleiben sechs Warnungen zu Datenfrische, Informationsabfluss und Robustheit.

## Warnings

### WR-01: `summary.json`-Vermerk kann Portfolio-Werte enthalten (Widerspruch zum Docstring)

**File:** `scripts/daily_paper_run.py:216-217, 256-257, 283-286`
**Issue:** Der Docstring (Zeile 226-227) verspricht "never amounts, because summary.json is published". Bei `invalid-schema` wird aber `str(ValidationError)` als `detail` übernommen (erste 200 Zeichen). Pydantic-Meldungen enthalten `input_value=...`, also die Rohwerte des fehlerhaften Felds (z. B. Cash oder Menge). Dasselbe gilt für `unexpected-error` mit `str(exc)` beliebiger Exceptions. `summary.json` wird nach `paper-log` archiviert und ist öffentlich (D-17 deckt nur Ledger und `portfolio.json` auf `ibkr-log` ab, nicht diesen Weg).
**Fix:** Bei Schema-Fehlern nur Feldpfad und Fehlertyp übernehmen, nie den Wert:
```python
except ValidationError as exc:
    locs = ",".join(".".join(map(str, e["loc"])) + ":" + e["type"] for e in exc.errors())
    raise _FeedSkip("invalid-schema", locs) from exc
```
Für `unexpected-error` nur `type(exc).__name__` ausgeben. Die Fehlerdetails von `invalid-json` und `as-of-invalid` enthalten dagegen keine Beträge, dort ist nichts zu ändern.

### WR-02: Gültigkeitsfenster (D-06) akzeptiert einen Stand, der eine ganze Sitzung alt sein kann

**File:** `scripts/daily_paper_run.py:269-275`, `scripts/ibkr_decision.py:540-558`
**Issue:** Der Stand gilt, wenn `as_of > Schluss der vorletzten Sitzung`. Beim Cron-Lauf am Dienstag 06:30 UTC ist die zuletzt geschlossene Sitzung der Montag, die vorletzte der Freitag. Ein Freitagabend-Snapshot ist also "frisch", obwohl alle Fills vom Montag fehlen. Der Text von D-06 ("aus dem letzten Handelstag") und die Implementierung ("nach der vorletzten Sitzung") gehen hier auseinander, und die Implementierung folgt dem Wortlaut. Das Portfolio geht dann ohne Warnung in den LLM-Prompt. Nach D-07 ist fail-open ohne Portfolio die sicherere Richtung als ein veraltetes Portfolio.
**Fix:** Mit dem Operator klären, ob "letzter Handelstag" die letzte geschlossene Sitzung meint. Dann den Cutoff auf den Schluss der letzten geschlossenen Sitzung ziehen (`closes[0]`), oder `as_of` zusätzlich gegen die Ledger-Spitze prüfen (WR-03). Falls die Lockerheit beabsichtigt ist, im Vermerk `age_hours` mitschreiben, damit der Befund sichtbar bleibt.

### WR-03: Veralteter Portfolio-Stand wird beim Publish nur gewarnt und kann auf dem Branch stehen bleiben

**File:** `scripts/ibkr_executor.py:1795-1815`, `scripts/ibkr_publish.py:200-209`
**Issue:**
1. `PUBLISH_PORTFOLIO_OLDER_THAN_LEDGER` ist nur ein `logger.warning`. Der Exit-Code bleibt 0 und der Stand wird veröffentlicht. Hat `execute` neue Fills geschrieben und ist `account` nicht gelaufen, liegt ein Ledger mit neuen Fills neben einem Portfolio ohne diese Fills auf dem Branch. Das fällt in das Fenster aus WR-02 und geht in CI als gültig durch.
2. Fehlt lokal `portfolio.json` (`portfolio is None`), schreibt `publish()` die Datei nicht und löscht sie auch nicht. Nach `reset --hard` auf den Remote-Stand bleibt das alte `portfolio.json` unverändert im Commit. Das Ledger wird weitergeschrieben, das Portfolio bleibt unbemerkt alt.
**Fix:** (1) Bei `as_of < last_ts` das Portfolio nicht mitveröffentlichen (`portfolio_bytes = None`) oder mit eigenem Exit-Code abbrechen. (2) In `publish()` ein nicht geliefertes `portfolio.json` aus dem Index entfernen (`git rm -q --ignore-unmatch -- portfolio.json`, anschließend `unlink`). Dann kann CI die Datei nicht mehr aus einem alten Commit lesen, und der Leser fällt mit `file-missing` sauber aus.

### WR-04: Keine Append-only-Prüfung gegen das bereits veröffentlichte Ledger

**File:** `scripts/ibkr_publish.py:183-209`
**Issue:** `publish()` setzt auf den Remote-Stand zurück und überschreibt dann `ledger.jsonl` mit dem lokalen Inhalt. Ist das lokale Ledger kürzer oder anders als das veröffentlichte (Restore aus einem alten Backup, anderer Rechner, per Hand gekürzte Datei), entsteht ein regulärer Fast-forward-Commit, der Historie verkürzt oder ersetzt. Der Push wird nicht abgelehnt, und es gibt keine Warnung. Das Ledger ist der Audit-Nachweis. `run_publish` prüft nur, dass das lokale Ledger in sich gültig ist (T-07-23).
**Fix:** Nach dem Reset `ledger.jsonl` des Remote-Stands lesen und prüfen, dass `snapshot.ledger.startswith(remote_bytes)` gilt. Andernfalls `PublishError("ledger-diverged", ...)` mit eigenem Zustand werfen. Der Fehler fällt dann unter `EXIT_PUBLISH`.

### WR-05: Berichtsziel wird aus der heutigen `CONTRACT_TABLE` abgeleitet

**File:** `scripts/ibkr_report.py:246-259, 617-619`
**Issue:** `target = multiplier * block_qty` nutzt die Blockgröße von heute. Wurde `block_qty` seit dem Handelstag geändert, ergibt sich ein falsches Ziel. Die Plausibilitätsprüfung ("held before ... whole non-negative") fängt das nur ab, wenn der Rest zufällig keine ganze Zahl oder negativ ist. Bei ganzzahligen Vielfachen entstehen stillschweigend falsche Werte für `Target`, `Held` und `Target - held`. D-20 verbietet zwar, den Ledger zu erweitern, aber der Bericht schreibt falsche Zahlen ohne Fußnote.
**Fix:** Mindestens eine Fußnote "Ziel mit heutiger Blockgröße berechnet" an jede Zeile mit abgeleitetem Ziel hängen. Besser: `contracts-history.jsonl` (existiert laut `state_maintenance.IBKR_BACKUP_FILES`) bzw. `contracts.json` von `ibkr-log` für den Handelstag verwenden und nur ableiten, wenn die Blockgröße zum Zeitpunkt feststeht.

### WR-06: URL-Schwärzung nur per exaktem String-Ersatz; URL wird in `.git/config` abgelegt

**File:** `scripts/ibkr_executor.py:1852-1860`, `scripts/ibkr_publish.py:166-170, 114-130`
**Issue:**
- `exc.detail.replace(url, pub.PUBLISH_REMOTE)` schwärzt nur die bytegleiche URL. Git gibt in `fatal:`-Meldungen die URL oft normalisiert aus (ohne Userinfo, mit abschließendem `/` oder ohne `.git`). Ist in `fork` ein Token eingebettet (`https://user:tok@...`), wird er nur dann entfernt, wenn Git ihn genauso ausgibt. Enthält `url` den leeren String, würde `replace("", ...)` zwischen jedes Zeichen einfügen.
- `git remote add/set-url` schreibt die URL samt Userinfo dauerhaft in `<state>/publish/.git/config`.
- `remote_url` steht als Positionsargument ohne `--` in der Git-Zeile. Eine URL, die mit `-` beginnt, würde als Option gelesen. Die Quelle ist die eigene Repo-Konfiguration, daher nur Defense-in-depth.
**Fix:** Zusätzlich zu `replace` ein Regex-Scrub vor jeder Ausgabe: `re.sub(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/@\s]+@", r"\1***@", text)`. `url` vor dem Ersetzen auf nicht leer prüfen. In `resolve_remote_url` eine URL mit führendem `-` ablehnen oder `git remote add -- fork <url>` verwenden. Idealerweise ein Credential-Helper statt Token in der URL; das ist in der Doku zu vermerken.

## Info

### IN-01: Kommentar im Workflow verspricht fail-open, der Schritt ist es nicht

**File:** `.github/workflows/daily-paper-run.yml:124-127`
**Issue:** Der Kommentar sagt "without it the run continues without a portfolio". Schlägt aber `pip install "exchange_calendars>=4.13,<5"` fehl (Netz, PyPI), bricht der Job ab, noch vor dem Preflight. Das widerspricht D-07 ("kein neuer Fehler im Produktivpfad"). Zusätzlich ist die Version nur nach oben begrenzt, nicht per Hash gepinnt.
**Fix:** Den Schritt mit `continue-on-error: true` versehen. `ImportError` wird in `load_published_portfolio` bereits zu `calendar-unavailable` und läuft damit fail-open.

### IN-02: Der Feed-Vermerk geht beim frühen Abbruch verloren

**File:** `scripts/daily_paper_run.py:629-661`
**Issue:** `load_published_portfolio` läuft vor dem Graph-Bau. Schlägt der Bau fehl (Zeile 658-661), kehrt `main` mit `EXIT_CONFIG` zurück, ohne `summary.json` zu schreiben. Der Feed-Status wird nur auf stdout ausgegeben. Der Vermerk ist dann nur im Job-Log zu finden. Der Netzzugriff (Fetch mit 60 s Timeout) findet außerdem schon statt, bevor der Graph überhaupt gebaut wurde.
**Fix:** Den Feed erst nach erfolgreichem Graph-Bau laden, oder den Vermerk im Fehlerpfad nachziehen.

### IN-03: Kleinigkeiten im Bericht

**File:** `scripts/ibkr_report.py:502, 633`
**Issue:** Die Fußnote für `ledger_only` (Zeile 502) und Alarm-Notizen laufen nicht durch `_cell`. Ein Zeilenumbruch oder `|` im Ledger-Feld `state` bricht die Markdown-Liste. Die Ledger-Daten stammen vom vertrauten Single-Writer, daher nur kosmetisch. `args.out.write_bytes(...)` (Zeile 633) fängt `OSError` nicht ab und liefert einen Traceback statt `EXIT_USAGE` oder `EXIT_SOURCE`. Der Bericht wurde dann schon auf stdout ausgegeben.
**Fix:** Fußnoten mit `.replace("\n", " ")` bereinigen. Den Schreibzugriff in `try/except OSError` fassen und einen definierten Exit-Code zurückgeben.

---

_Reviewed: 2026-10-20_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
