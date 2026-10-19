# Phase 7: Rückkanal und Soll-Ist-Zusammenführung - Pattern Map

**Mapped:** 2026-10-19
**Files analyzed:** 17 (neu/geändert)
**Analogs found:** 16 / 17 (kein Analog nur für den Ein-Branch-Klon mit Commit/Push; Vorlage steht in RESEARCH Pattern 1 und Code Examples)

Alle Zeilenangaben beziehen sich auf den Arbeitsstand von `main` am 2026-10-19 (nach 06-10-Fixes). Sie weichen teils von RESEARCH ab (der Executor ist inzwischen gewachsen, z. B. `run_resolve_entry` liegt bei Z. 1639, nicht 1667). Tests und Lint laufen mit `.venv/Scripts/python.exe -m pytest|ruff` (nicht `uv run`).

## File Classification

| Neue/geänderte Datei | Rolle | Data Flow | Nächstes Analog | Match |
|---|---|---|---|---|
| `scripts/ibkr_publish.py` (NEU: Snapshot -> Klon -> Commit -> Push) | service (rein, Git-Runner injiziert) | file-I/O + request-response (Git) | `scripts/ibkr_paperlog.py` (`GitPaperLog`, injizierbarer `run`) | role-match |
| `scripts/ibkr_executor.py` (`publish`-Unterbefehl, `EXIT_PUBLISH = 11`, `default_publish_dir`, `load_publish_module`) | CLI / controller | request-response | `run_resolve_entry` (Lock + Ledger.open + `_fail`, Z. 1639-1708), `load_paperlog_module` (Z. 243), `_write_bytes_atomic` (Z. 2482) | exact |
| `scripts/ibkr_report.py` (NEU, nur lesend) | service / CLI | batch + transform (Join) | `_read_log_entries` (Executor Z. 2494-2524) + `GitPaperLog` + `Ledger.open` | role-match |
| `scripts/ibkr_decision.py` (`second_last_close_utc`) | utility (rein, Uhr als Parameter) | transform | `execution_session` / `freshness` / `_calendar_today` (Z. 534-601) | exact |
| `scripts/daily_paper_run.py` (`--portfolio-from-published`, `load_published_portfolio`, `summary["portfolio_feed"]`) | CLI + service | request-response, fail-open | `load_fresh_portfolio` (Z. 137-176) + `run_ticker`-Weitergabe (Z. 365-368) + `main` (Z. 453-460) | exact (Gegenstück fail-closed) |
| `scripts/state_maintenance.py` (`--ibkr-dir`, `--dry-run`, IBKR-Allow-Liste) | CLI / utility | file-I/O (Archiv) | `backup` + `_backup_included` (Z. 350-411), `prune`-Parser `--apply` (Z. 433-435) | exact |
| `.github/workflows/daily-paper-run.yml` (Pip-Schritt + ein Flag) | config (CI) | n/a | Schritte „Install the package“ und „Run the analysis“ (Z. 120-184) | exact |
| `scripts/IBKR_EXECUTION.md` (Invariante, `publish`, Exit-Zeile 11, Bericht, Backup, Jev-/Public-Hinweis) | doc (von Test geprüft) | n/a | Abschnitt „Exit codes“ (Z. 147-170), „Ledger and reconciliation“ (Z. 710) | exact |
| `tests/test_ibkr_publish.py` (NEU) | test | file-I/O (echtes Git gegen lokale Bare-Repos) + Runner-Fake | `tests/test_ibkr_paperlog.py` (`FakeRunner` Z. 27-38, `test_real_git_fetch_without_checkout` Z. 186-211) | role-match |
| `tests/test_ibkr_report.py` (NEU) | test | transform | `tests/test_ibkr_paperlog.py` Frozen-Fixture (Z. 214-270) + `tests/paper_log_fixture.py` | role-match |
| `tests/test_daily_paper_run.py` (Feed-Tests) | test | request-response | `TestPortfolio` (Z. 440-540), `_FakeGraph.portfolios` (Z. 58-63) | exact |
| `tests/test_state_maintenance.py` (IBKR-Backup, autouse-Isolation) | test | file-I/O | `test_backup_packs_the_allow_list_and_nothing_else` (Z. 543-588) | exact |
| `tests/test_ibkr_decision.py` (`second_last`) | test | transform | bestehende `freshness`-Tests mit `tests/calendar_stub.py::WeekdayCalendar` | exact |
| `tests/test_ibkr_isolation.py` (Exit-Tabelle 12 -> 13, Reinheit, Workflow-Pins) | test | n/a | Z. 83-88, 183-193, 268-292, 525-546 | exact |
| `tests/test_ibkr_executor*.py` (Parser/`main`-Meldung, `publish`-Exit-Pfade, no_gateway) | test | request-response | bestehende Executor-Tests mit `broker_factory`-Fake | role-match |
| `.planning/phases/07-.../07-NN-PLAN.md` (Operator-Checkpoint: erster echter `publish`) | plan (`autonomous: false`) | n/a | `06-09`/`06-10` bzw. `05-10-PLAN.md` (siehe 06-PATTERNS) | exact |

## Pattern Assignments

### `scripts/ibkr_publish.py` (service, file-I/O + Git, NEU)

**Analog:** `scripts/ibkr_paperlog.py` (Runner-Injektion, Whitelist, Fehlerklassen).

**Modul-Kopf und Reinheit** (Z. 1-24): bibliotheksfrei, Runner injiziert, kein `datetime.now`, kein `tradingagents`-Import auf Modulebene (Test `test_decision_modules_are_library_free`, isolation Z. 525-546; die Liste `(DECISION, PAPERLOG)` dort um `ibkr_publish.py` und `ibkr_report.py` erweitern):
```python
from __future__ import annotations
import os, re, subprocess, uuid
from pathlib import Path
_REF_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
```

**Whitelist vor jeder Kommandozeile** (Z. 42-63): `validate_ref_name` und `validate_blob_path` wiederverwenden (über `load_paperlog_module()` bzw. `importlib`), nicht duplizieren:
```python
def validate_ref_name(value: str, what: str) -> str:
    if (not value or value.startswith("-") or ".." in value or not _REF_RE.match(value)):
        raise ValueError(f"invalid {what}: {value!r}")
    return value
```

**Git-Aufruf über injizierbaren Runner** (Z. 80-106); für `publish` erweitern um `GCM_INTERACTIVE=never`, `-c core.autocrlf=false` und feste Identität per `-c user.name=... -c user.email=...` (RESEARCH Pattern 1, Pitfall 3/4):
```python
def _git(self, args: list[str], timeout: float):
    return self._run(
        ["git", *args],
        cwd=str(self._repo),
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        capture_output=True,
        timeout=timeout,
    )
```

**Fehlerklassen und Timeout-Behandlung** (Z. 26-39, 131-137): eigene `PublishError(Exception)` mit `reason`, `subprocess.TimeoutExpired`/`OSError` immer in `PublishError` übersetzen (Muster `PaperLogUnavailable`):
```python
except (subprocess.TimeoutExpired, OSError) as exc:
    raise PaperLogUnavailable(f"git unavailable: {exc}") from exc
```

**Erstanlage vs. Fortschreibung:** kein Analog im Repo. Vorlage: RESEARCH „Code Examples“ (`ls-remote --exit-code --heads`, Exit 2 = Erstanlage, Exit 0 = `fetch` + `reset --hard`). Push nur `git push fork HEAD:refs/heads/ibkr-log`, nie `--force`. Konstanten `fork`/`ibkr-log` im Modul, kein Env-Override (D-04).

**Bytes statt Text** (Executor `_write_bytes_atomic`, Z. 2482-2491): Temp-Datei + `os.replace`, nie `write_text` (CRLF); `.gitattributes` mit `* -text` im ersten Commit:
```python
temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
try:
    temp.write_bytes(data)
    os.replace(temp, path)
except BaseException:
    temp.unlink(missing_ok=True)
    raise
```

---

### `scripts/ibkr_executor.py` - `publish` (CLI, request-response)

**Analog:** `run_resolve_entry` (Z. 1639-1708) für Lock + Ledger-Validierung + `_fail`; Lazy-Loader (Z. 223-260); `build_parser`/`main` (Z. 771-943).

**Exit-Konstante** (Z. 98-109): `EXIT_PUBLISH = 11` nach `EXIT_POST_ORDER = 10`, Docstring-Tabelle im Modulkopf (Z. ~44-58, „10 post-order mismatch ...“) ergänzen:
```python
EXIT_FILL_TIMEOUT = 9
EXIT_POST_ORDER = 10
EXIT_NO_CREDENTIALS = 20
```

**Lazy-Loader** (Z. 223-260), zu spiegeln als `_PUBLISH_PATH` (neben Z. 132-135) und `load_publish_module()`; Reportmodul braucht keinen Loader im Executor:
```python
def load_paperlog_module():
    """The paper-log reader, loaded once under the name ``ibkr_paperlog``."""
    return _load_script_module("ibkr_paperlog", _PAPERLOG_PATH)
```

**Pfade im State-Ordner** (Z. 263-308): `default_publish_dir()` als `_ibkr_base(environ) / "publish"` (nicht `paper-log`, das ist die Verify-Kopie Z. 296-298). Portfolio-Datei `default_portfolio_file()` = `_ibkr_base() / "portfolio.json"` (heute nur `account --out`):
```python
def _ibkr_base(environ=None) -> Path:
    environ = os.environ if environ is None else environ
    base = environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "TradingEngineX" / "ibkr"
    return Path.home() / ".tradingenginex" / "ibkr"
```

**Unterparser ohne `--env-file`** (Z. 781-784 als Gegenbeispiel: `account` liest `IBKR_*`-Settings; `publish` darf sie nie lesen, kein Gateway). Parser-Muster:
```python
execute = sub.add_parser("execute", help=help_execute)
execute.add_argument("--log-file", type=Path, default=default_log_file())
```
Fehlertext in `main()` (Z. 886) um `publish` ergänzen (`"... account, resolve, preview, execute, publish"`). Dispatch (Z. 932-941) bekommt einen `publish`-Zweig vor dem `_resolve`-Fallthrough, innerhalb des `try/finally: close_logging()`.

**Lock nur um das Snapshot-Lesen, vor dem Netz freigeben** (Z. 1670-1688; `locked` aus `tradingagents.dataflows.files`, Z. 37-49 dort; `wait=False`, Exit 7 wenn gehalten):
```python
lock_stack = contextlib.ExitStack()
try:
    held = lock_stack.enter_context(locked(default_ledger_file(), wait=False))
except OSError as exc:
    lock_stack.close()
    return _fail(logger, EXIT_LOCKED, f'ibkr-state=LOCK_ERROR detail="{type(exc).__name__}: {exc}"', "execute: lock-error (not resolved)")
if not held:
    lock_stack.close()
    return _fail(logger, EXIT_LOCKED, f'ibkr-state=LOCK_HELD detail="{default_ledger_file()}.lock"', "execute: lock-held (another run holds the ledger lock)")
```
Abweichung: bei `publish` wird `with lock_stack:` nur um das Bytes-Lesen gelegt und vor `git` verlassen (D-03).

**Ledger-Validierung auf dem Snapshot** (Z. 1691-1708): `Ledger.open(<Temp-Kopie>, mode=MODE_LIVE, ...)`, `LedgerError` -> `EXIT_RECONCILE` (6), nichts veröffentlicht:
```python
except Exception as exc:  # noqa: BLE001 - an unreadable ledger is "corrupt"
    detail = (str(exc) if isinstance(exc, ledger_mod.LedgerError) else f"{type(exc).__name__}: {exc}")
    return _fail(logger, EXIT_RECONCILE, f'ibkr-state=LEDGER_CORRUPT detail="{detail}"', f"execute: ledger-corrupt ({detail})")
```

**State-Ordner-Prüfung** (Z. 1654-1669): `ledger_mod.ensure_outside_git(state_dir)` für `state_dir`, **nicht** für den Klon selbst (der ist selbst ein Git-Baum, Unterordner stört die Prüfung nicht). Fehlerform `_fail(logger, code, "ibkr-state=NAME detail", "console text")` (Z. 421) für alle `publish`-Ausgänge; Push-/Netzfehler -> `EXIT_PUBLISH`.

**Portfolio-Form** (Z. 468-480): `portfolio_json(ctx, as_of)` und `AS_OF_KEY = "as_of"` (Z. 125) sind die Quelle der Form; `publish` kopiert die Datei nur (D-19). `publish` loggt `as_of` und warnt, wenn `as_of` älter als der letzte Ledger-`ts` ist (Pitfall 2).

---

### `scripts/ibkr_report.py` (service/CLI, batch + transform, NEU, nur lesend)

**Analog 1 (Quellen lesen):** `GitPaperLog` (ibkr_paperlog.py Z. 80-171). Zwei Instanzen auf `REPO_ROOT`, Remote `fork`, Branches `paper-log` bzw. `ibkr-log` (Option `--paper-log-branch` / `--published-branch`):
```python
log = GitPaperLog(REPO, "fork", "paper-log"); sha = log.fetch(); blob = log.read("decision-log.md")
```
`BlobMissing` (Pfad fehlt) und `PaperLogUnavailable` (Branch/Git) getrennt behandeln wie `_read_log_entries`.

**Analog 2 (Decision-Log parsen):** `_read_log_entries` (Executor Z. 2494-2524): Blob -> Datei -> `TradingMemoryLog({"memory_log_path": str(copy)}).load_entries()`; im Bericht ohne `verify`, in ein `tempfile.TemporaryDirectory`:
```python
text = paperlog_mod.decode_utf8(blob, paperlog_mod.DECISION_LOG_PATH)
...
return TradingMemoryLog({"memory_log_path": str(copy)}).load_entries()
```
Entry-Felder: `date, ticker, rating, pending, raw, alpha, holding, resolved` (`tradingagents/memory/log.py:339-348`). `load_entries` dedupliziert **nicht** (Z. 89-100); der Guard gegen Doppel steht beim Schreiben in `store_decision` (log.py Z. 60-68: `line.startswith(f"[{trade_date} | {ticker} |")`). Der Bericht dedupliziert defensiv in Dateireihenfolge, erste Fassung gewinnt, Key `f"{date}|{ticker}"` (D-12). Nicht parsbare Blöcke zählen: `text.split("\n\n<!-- ENTRY_END -->\n\n")` gegen `len(entries)`.

**Analog 3 (Ledger lesen):** `Ledger.open(path, mode=..., clock=..., run_id=...)` (ibkr_ledger.py Z. 307-350). Toleriert Torn-Tail, wirft `LedgerError` bei kaputter Mitte -> Bericht bricht ab (Wahrheitsquelle). Nur `MODE_LIVE`. Blob zuerst in Temp-Datei schreiben (die Klasse liest nur von `path`); `clock` als Parameter (`lambda: datetime.now(UTC)` nur in `main`).

**Fill-Menge/Ø-Preis** (ibkr_ledger.py Z. 561-587): `effective_executions` über Records, die in `SimpleNamespace(exec_id=..., shares=filled_qty, price=...)` gewickelt werden (Objekte mit `.exec_id/.shares`):
```python
def effective_executions(executions) -> list:
    chosen: dict[str, object] = {}
    for execution in executions:
        family = exec_family(execution.exec_id)
        kept = chosen.get(family)
        if kept is None or correction_rank(execution.exec_id) >= correction_rank(kept.exec_id):
            chosen[family] = execution
    return list(chosen.values())
```
Zeilen ohne `exec_id` (nur Aggregat) zählen einmalig, wie `Ledger.filled_quantity` (Z. 481-510):
```python
with_id = [r for r in rows if r.get("exec_id")]
...
qty = float(r.get("filled_qty") or 0)
total += qty if r.get("side") == "BUY" else -qty
```
Lifecycle je Key: `Ledger.last_event(key)` / `attempt_of(key)` (Z. 458-464); `LIFECYCLE_EVENTS` (Z. 80) für den Zustand; Intent-Felder aus `intent_record` (Z. 513-540): `decision_key, ticker, trade_date, rating, paper_log_sha, side, quantity, con_id, order_ref, weekend_gap, rating_source`. Skipped/rejected-Zeilen tragen `state`, `detail`, `weekend_gap` (Executor `_ledger_row_finished`, Z. 1833-1867).

**Ziel/Ist-Leiter:** `BLOCKS[rating] * block_qty` (`ibkr_decision.py:323`, `plan_order` Z. 336-372; `block_qty` aus `CONTRACT_TABLE`, `ibkr_contracts.py:80-100`). `held_vorher = target - (±intent.quantity)`; nur mit Intent exakt, sonst Zelle leer + Fußnote (D-20, nichts aus `detail`-Freitext parsen).

**Kurs (fail-soft, D-14/D-16):** `tradingagents/memory/settlement.py` importiert `get_closes` auf Modulebene (Z. 9: `from tradingagents.dataflows.vendors.yahoo.market import get_closes`). **Über das Modulattribut aufrufen** (`settlement.get_closes(...)`), damit `monkeypatch.setattr(settlement, "get_closes", ...)` greift. Signatur Z. 268-272 in `market.py`: Enddatum exklusiv, leere Serie bei fehlenden Daten:
```python
def get_closes(symbol: str, start_date: str, end_date: str) -> pd.Series:
    """Daily closes from ``start_date`` up to, not including, ``end_date``."""
```
`tradingagents`-Importe lazy innerhalb von Funktionen oder nach `sys.path`-Setup; jede Ausnahme -> leere Zelle + Fußnote; `--no-prices` überspringt den Abruf.

**Modul-Laden:** `daily_paper_run.py` und Tests laden Scripts per `importlib.util.spec_from_file_location` (kein `import ibkr_paperlog` auf Top-Level; Test-Vorlage `tests/test_ibkr_paperlog.py` Z. 15-22). Dasselbe Muster für `ibkr_ledger`, `ibkr_paperlog`, `ibkr_contracts`, `ibkr_decision` im Bericht verwenden (Executor `_load_script_module`, Z. 223-235, kopieren oder dort laden).

**Handelszeit-Literale:** `test_no_hard_coded_trading_times_in_execution_code` (isolation Z. 268-281) verbietet `13:30`, `14:30`, `09:30`, `16:00` in `scripts/ibkr_*.py` (auch in Docstrings/Beispielzeitstempeln, also auch in `ibkr_report.py`/`ibkr_publish.py`).

---

### `scripts/ibkr_decision.py` - `second_last_close_utc` (utility, transform)

**Analog:** `execution_session` / `_calendar_today` (Z. 534-549) und das `SessionCalendar`-Protokoll (Z. 454-466). Reine Funktion, Uhr als Parameter, nur über das Protokoll:
```python
def _calendar_today(now_utc: datetime, calendar: SessionCalendar) -> date:
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must carry a time zone")
    return now_utc.astimezone(ZoneInfo(calendar.zone_name)).date()
```
Skizze (RESEARCH Z. 353-359): `calendar.sessions_between(today - timedelta(days=14), today)` rückwärts, Sitzungen mit `session_close_utc(d) <= now_utc` sammeln, zweite = Cutoff, weniger als zwei -> `CalendarRangeError` (Z. 450). Fehlerstil wie `freshness` (Z. 584-589, `except CalendarRangeError`). Modul bleibt bibliotheksfrei (`pandas`/`exchange_calendars` nur lazy in `XnysSessions`, Z. 469-531; `load_xnys_calendar` Z. 527 reicht `ImportError` durch).

**Testvorlage:** `tests/calendar_stub.py::WeekdayCalendar` (Mo-Fr Sitzung, Schluss 20 UTC, `holidays=`, `range_error=` des geladenen Moduls). Fälle: Di 06:30 UTC -> Cutoff Fr; Feiertags-Montag; weniger als zwei Sitzungen im Fenster.

---

### `scripts/daily_paper_run.py` - `--portfolio-from-published` (CLI/service, fail-open)

**Analog (fail-closed Gegenstück):** `load_fresh_portfolio` (Z. 137-176). Die neue Funktion spiegelt Struktur und Schema-Prüfung, fängt aber **alles**:
```python
data = json.loads(Path(path).read_text(encoding="utf-8"))
portfolio = PortfolioContext.model_validate(data)
...
raw = data.get(PORTFOLIO_AS_OF_KEY)
as_of = datetime.fromisoformat(raw)
if as_of.tzinfo is None: ...
age = now - as_of
if age < -PORTFOLIO_CLOCK_SKEW:   # Zukunft (5 min Toleranz, Z. 55)
```
Neu: `load_published_portfolio(repo, now, *, reader, calendar_loader) -> (PortfolioContext | None, dict)`, äußerer `try/except Exception` (D-07), Rückgabe `{"status": "skipped", "reason": <Kennung>}` bzw. `{"status": "used", "as_of", "cutoff", "sha", "positions": n}` (keine Beträge, landet öffentlich). Kennungen laut RESEARCH Pattern 2: `branch-unavailable`, `file-missing`, `invalid-json`, `invalid-schema`, `as-of-missing`, `as-of-invalid`, `as-of-in-future`, `stale`, `calendar-unavailable`. Gültig, wenn `as_of > second_last_close_utc(now, calendar)`.

**Konstanten** neben Z. 48-55: `PUBLISHED_STATE_REMOTE = "origin"`, `PUBLISHED_STATE_BRANCH = "ibkr-log"`, in Python, nie im Workflow (D-22). Das Lesen geht über `GitPaperLog(repo, remote, branch)` (`fetch()` in private Ref `refs/tengx/...`, `read("portfolio.json")`); das Modul per `importlib` aus `Path(__file__).with_name("ibkr_paperlog.py")` laden, nicht per Top-Level-Import (Tests laden `daily_paper_run` ebenfalls per `spec_from_file_location`, test_daily_paper_run.py Z. 26-30). `GitPaperLog.fetch` kennt kein `--depth`: optionaler additiver Parameter `depth`.

**Argparse** (Z. 421-433): neues Flag neben `--portfolio`, gegenseitig ausschließend (`ConfigError`):
```python
parser.add_argument("--portfolio", type=Path, default=None, help="Local PortfolioContext JSON ...")
```

**`main`-Einbindung** (Z. 453-460): `portfolio`-Variable existiert schon; nur wenn `args.portfolio_from_published` und nicht `--preflight` (kein Netz im Preflight) wird sie über die neue Funktion gesetzt:
```python
portfolio = None
if args.portfolio is not None:
    ...
    portfolio = load_fresh_portfolio(args.portfolio.resolve(), max_age=timedelta(minutes=args.portfolio_max_age_minutes))
```
`run_ticker` (Z. 346-368) bleibt unverändert: `portfolio` wird nur bei Vorhandensein weitergegeben, sonst identischer `propagate`-Aufruf. 

**summary.json additiv** (Z. 511-525): Feld `portfolio_feed` nur setzen, wenn das Flag gesetzt war (sonst bleibt das Summary byte-gleich); `SUMMARY_SCHEMA_VERSION = 1` (Z. 46) bleibt:
```python
summary = {"schema_version": SUMMARY_SCHEMA_VERSION, ..., "status": "ok", "totals": {}, "runs": []}
```
Ausgabezeile neben Z. 488-493 (`print(f"portfolio: ...")`) für `used`/`skipped` mit Grund.

**Testvorlage:** `_FakeGraph.propagate` zeichnet `kwargs.get("portfolio", "<absent>")` auf (test_daily_paper_run.py Z. 58-63); Fail-open-Beleg = `graph.portfolios == ["<absent>"]` (Z. 460-463); Hilfsfunktionen `_portfolio_file`, `_as_of`, `_book` (Z. 425-438); lokales `--portfolio` bleibt fail-closed (Tests Z. 465-540 unverändert grün).

---

### `scripts/state_maintenance.py` - `backup --ibkr-dir --dry-run` (CLI, file-I/O)

**Analog:** `backup` + `_backup_included` (Z. 350-411) und `prune --apply` (Z. 433-435, Dry-Run-Muster).

**Allow-Liste als explizite Mitgliederliste, kein Sweep** (Z. 381-393); IBKR-Mitglieder unter Archivpfad `ibkr/`:
```python
members: list[tuple[Path, str]] = []
for name in ("decision-log.md", "index.md"):
    path = state / name
    if path.is_file() and _backup_included(path):
        members.append((path, name))
```
Neu: `for name in ("ledger.jsonl", "ledger-dryrun.jsonl", "contracts.json", "contracts-history.jsonl")` unter `ibkr_dir`; nicht aufnehmen: `RELEASE`, `KILL`, `portfolio.json`, `preview.json`, `resolve.json`, `logs/`, `publish/`; `*.lock`/`.tmp` bleiben über `BACKUP_EXCLUDED_SUFFIXES` (Z. 68) draußen. Fehlender IBKR-Ordner/Datei ist kein Fehler (Hinweiszeile); der Gesamtfall `if not members` (Z. 395-397) bleibt.

**Default-Ordner:** Regel duplizieren (kein Rückimport aus dem Executor, der dieses Modul per `load_state_maintenance_module` lädt, Z. 248-250):
```python
base = environ.get("LOCALAPPDATA"); Path(base)/"TradingEngineX"/"ibkr" if base else Path.home()/".tradingenginex"/"ibkr"
```
Ein Test setzt beide gleich (`executor.default_ledger_file().parent == tool.default_ibkr_dir()`).

**Dry-Run:** `--dry-run` (`action="store_true"`) listet Mitglieder im selben Format (Z. 407-409), schreibt kein Archiv, legt `--out` nicht an; die Pflichtprüfung `--out` (Z. 366-368) entfällt im Dry-Run. Signatur `backup(out, state_dir, memory_log)` wird um `ibkr_dir`, `dry_run` erweitert, Aufruf in `main` (Z. 470-471) und Docstring-Kopf (Z. 14) nachziehen:
```python
backup_parser.add_argument("--memory-log", default=DEFAULT_CONFIG["memory_log_path"])
```
Ohne Lock lesen: ein Torn-Tail wird von `Ledger.open` toleriert (im Handbuch erwähnen).

---

### `.github/workflows/daily-paper-run.yml` (config)

**Analog:** Schritte „Install the package“ (Z. 120-123) und „Run the analysis“ (Z. 171-184):
```yaml
      - name: Install the package
        run: |
          python -m pip install --upgrade pip
          pip install .
```
Änderung: ein zusätzlicher Schritt direkt danach `pip install "exchange_calendars>=4.13,<5"` (gleiche Spanne wie `pyproject.toml:53`); im Schritt „Run the analysis“ nur ein Argument `--portfolio-from-published \` ergänzen, **nicht** im Preflight. Schritte „Restore the paper-log state branch“ (Z. 130-150) und der Commit-Schritt (Z. ~202-219, `git fetch --depth=1` -> `reset --hard` -> `push -q origin "HEAD:$STATE_BRANCH"`) bleiben byteweise unverändert. Kein Wort „ibkr“ (case-insensitiv) in der YAML, auch nicht in Kommentaren:
```python
assert "IBKR" not in text.upper(), f"{path.name} mentions IBKR"   # tests/test_ibkr_isolation.py:88
```
Pins als neue Tests dazu: Pip-Pin == `pyproject.toml`-Pin, Flag nur im Analyse-Schritt, Commit-Schritt-Text unverändert.

---

### `scripts/IBKR_EXECUTION.md` (doc, von Tests geprüft)

**Analog:** Abschnitt „Exit codes“ (Z. 147-170).
```
| 10 | `EXIT_POST_ORDER` | the state at IBKR after the order differs from the intent (D-09, REQ-65) |
| 20 | `EXIT_NO_CREDENTIALS` | IBKR settings missing or unreadable - ... |
```
Neue Zeile `| 11 | \`EXIT_PUBLISH\` | ... |` zwischen 10 und 20 (Regex im Test: `^\| {value} \| \`{name}\` \|`, isolation Z. 183-193, dort `len(codes) == 12` -> `13`). Rangsatz (Z. ~168: `4 > 7 > 6 > 10 > 9 > 8 > 3 > 1 > 5 > 2 > 0`) gilt für `execute`; `publish` hat keinen Rang, im Text klarstellen. Neue Abschnitte (vor „See also“ Z. 1054): Invariante „ein Schreiber pro Branch“ (`ibkr-log`: Ausführer, `paper-log`: CI), Betriebsablauf `execute` -> `account` -> `publish`, Bericht, Backup (`--ibkr-dir`, `--dry-run`), öffentliche Sichtbarkeit (D-17), Jev-Entfall bei gültigem Portfolio (D-18). Handbuch darf den Namen der Client-Bibliothek nicht enthalten (`test_handbook_does_not_name_the_client_library`).

---

### Tests

**`tests/test_ibkr_publish.py` (NEU)** - Analog `tests/test_ibkr_paperlog.py`:
- `FakeRunner` (Z. 27-38) für Befehlsfolge, `env`-Pins (`GIT_TERMINAL_PROMPT == "0"`), „kein `origin`/`paper-log`/`--force` in irgendeiner Argumentliste“:
```python
class FakeRunner:
    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        r = self.responses.pop(0)
        if isinstance(r, BaseException): raise r
        rc, out, err = r
        return subprocess.CompletedProcess(argv, rc, stdout=out, stderr=err)
```
- Echtes Git gegen lokale Bare-Repos als `fork` (Vorlage Z. 186-211, `g(cwd, *a)` mit `-c core.autocrlf=false`, `shutil.which("git")`-Skip): Erstanlage, Fortschreibung, leerer Diff = kein Commit, Non-FF = Exit 11, Bytes-Treue (`b"hello\r\n"` bleibt), `paper-log` unverändert, Klon enthält nur die Dateien.
- Exit 7 bei gehaltenem Lock, Exit 6 bei kaputtem Ledger, `no_gateway` (Broker-Factory nie aufgerufen).
- `tests/conftest.py` sperrt Sockets (`_no_network`, Z. 60-71) und setzt `LOCALAPPDATA` je Test auf tmp; lokale Git-Pfade bleiben möglich.

**`tests/test_ibkr_report.py` (NEU)** - Analog Frozen-Fixture (test_ibkr_paperlog.py Z. 214-270) und `tests/paper_log_fixture.py` (`FixturePaperLog` Z. 37-66, `write_paper_log`, `FROZEN_DIR`, `FROZEN_SHA`):
```python
src = FixturePaperLog(FROZEN_DIR, FROZEN_SHA); src.fetch(); src.read("decision-log.md")
```
Dedup-Test mit **rohem** Doppel im Decision-Log (der Produzent `store_decision` lässt keines zu) plus echte Bytes `tests/fixtures/paper_log_71df89d` als Gegenprobe; Ledger-Zeilen in der Form von `.planning/ibkr-konto-befund.md:704-712` (`intent -> placed -> filled -> alarm(post-order-mismatch, fills_booked) -> run_end`, Key `2026-10-16|AAPL`, Intent-Rating `Overweight` vs. Log-Rating `Hold`); Kurs via `monkeypatch.setattr(settlement, "get_closes", ...)` (Vorlage `tests/test_graph_end_to_end.py:317`); Pflichttext Top-of-Book im Kopf prüfen.

**`tests/test_state_maintenance.py`** - Analog Z. 543-588: gleiches Muster (`tool.main([...])`, `capsys`, `tarfile.open`, `getnames`), plus **autouse-Fixture**, die `LOCALAPPDATA` (und `HOME`/`USERPROFILE`) auf `tmp_path` setzt, damit der Default-IBKR-Ordner nie den echten State packt (Modul wird per `_load_tool()` geladen, Z. 26-33).

**`tests/test_ibkr_isolation.py`**: `len(codes) == 13` (Z. 191); `ibkr_publish.py`/`ibkr_report.py` in die Reinheits-/Uhr-Listen `(DECISION, PAPERLOG)` (Z. 525-546) aufnehmen; Workflow-Pins neben `test_ci_workflows_reference_no_ibkr_secret` (Z. 83-88).

---

## Shared Patterns

### Fail-Exit-Muster mit `ibkr-state=`-Logzeile
**Quelle:** `scripts/ibkr_executor.py` `_fail` (Z. 421), Nutzung Z. 1658-1688.
**Gilt für:** alle `publish`-Ausgänge (Config, Lock, Ledger, Git/Push).
`_fail(logger, EXIT_X, 'ibkr-state=NAME detail="..."', "console text")`; Konsolenzeile englisch, keine Secrets/URLs mit Token.

### Git ohne Prompt, ohne Checkout, mit Whitelist
**Quelle:** `scripts/ibkr_paperlog.py` Z. 42-63, 99-106, 112-146.
**Gilt für:** `publish` (Schreibpfad, plus `GCM_INTERACTIVE=never`, Timeout je Aufruf), Bericht (zwei `GitPaperLog`-Leser), CI-Lesepfad (`load_published_portfolio`).

### Atomares Schreiben und Bytes-Treue
**Quelle:** `ibkr_executor._write_bytes_atomic` (Z. 2482-2491), `write_portfolio_atomic` (Z. 483-504).
**Gilt für:** Kopien im Klon, Temp-Dateien im Bericht. Nie `write_text` für Ledger/Portfolio/Contracts.

### Reine Module: keine Client-Bibliothek, keine Uhr, keine Handelszeit-Literale
**Quelle:** `tests/test_ibkr_isolation.py` Z. 268-292, 525-546.
**Gilt für:** `ibkr_publish.py`, `ibkr_report.py`, `second_last_close_utc`. `datetime.now`, `time.time(`, `date.today` nur in `main`-Funktionen der CLI (nicht in den Modul-Quelltexten, die der Test prüft; sicherste Lösung: Uhr immer als Parameter).

### Lazy Modul-Laden per Dateipfad
**Quelle:** `ibkr_executor._load_script_module` (Z. 223-235), Tests `spec_from_file_location` (test_ibkr_paperlog.py Z. 15-22).
**Gilt für:** alle Scripts, die ein anderes Script brauchen (`daily_paper_run.py` -> `ibkr_paperlog`/`ibkr_decision`, `ibkr_report.py` -> `ibkr_ledger`/`ibkr_paperlog`/`ibkr_decision`).

### Exit-Tabellen und Handbuch halten Schritt
**Quelle:** `scripts/IBKR_EXECUTION.md` Z. 147-170, `tests/test_ibkr_isolation.py` Z. 183-193 (`len(codes)`).
**Gilt für:** `EXIT_PUBLISH = 11` (Executor-Konstante, Docstring-Kopf, Handbuchzeile, Test-Zahl).

### Fail-open mit Vermerk (CI-Eingang) vs. fail-closed (lokal)
**Quelle:** `load_fresh_portfolio` (fail-closed, `ConfigError`) bleibt unberührt; `load_published_portfolio` ist sein fail-open-Gegenstück (`except Exception` -> `(None, {"status": "skipped", "reason": ...})`). Test-Beleg: `graph.portfolios == ["<absent>"]`.

### Tests
Lauf: `.venv/Scripts/python.exe -m pytest tests/test_ibkr_publish.py tests/test_ibkr_report.py tests/test_state_maintenance.py tests/test_daily_paper_run.py tests/test_ibkr_isolation.py -x -q`; Lint: `.venv/Scripts/python.exe -m ruff check scripts tests`. Bekannt rot vorab (phasenfremd): `test_yfinance_keeps_its_cache_out_of_the_users_home`, `test_chatgpt_auth` x2, `test_cli_commands` x1, `test_cli_updates` x2.

## No Analog Found

| Datei / Teil | Rolle | Data Flow | Grund |
|---|---|---|---|
| Ein-Branch-Klon: `git init -b ibkr-log`, `ls-remote --exit-code` (Exit 2 = Erstanlage), Commit mit fester Identität, Push ohne Force | service | file-I/O + Git-Schreiben | Im Repo schreibt bisher nur die CI per Shell-YAML (`daily-paper-run.yml` Z. 130-150 als Gegenstück: `git init -q -b`, `fetch --depth=1`, `reset --hard FETCH_HEAD`) auf Git; Python-Code liest Git nur. Vorlage ist RESEARCH Pattern 1 und „Code Examples“; Befehlsgerüst für Init/Fetch/Reset aus dem CI-Schritt übernehmen, Runner-Struktur aus `GitPaperLog`. |

## Metadata

**Analog-Suchbereich:** `scripts/` (ibkr_paperlog, ibkr_executor, ibkr_ledger, ibkr_decision, daily_paper_run, state_maintenance, Handbuch), `.github/workflows/daily-paper-run.yml`, `tests/` (paperlog, isolation, daily_paper_run, state_maintenance, calendar_stub, paper_log_fixture), `tradingagents/memory/` (log, settlement), `tradingagents/dataflows/files.py`
**Gelesene Dateien:** 14 (teils gezielt per Zeilenbereich)
**Extraktionsdatum:** 2026-10-19
