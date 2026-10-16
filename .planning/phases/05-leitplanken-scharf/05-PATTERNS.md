# Phase 5: Leitplanken scharf - Pattern Map

**Mapped:** 2026-10-16
**Files analyzed:** 13 (6 neu, 7 geändert)
**Analogs found:** 13 / 13 (kein Teil ohne Vorlage; für die Ledger-Klasse und den Einmal-Permit gibt es nur Teil-Analoga)

Quelle der Datei-Liste: `05-CONTEXT.md` (D-01..D-11, D-17..D-23) und `05-RESEARCH.md` (Recommended Project Structure, Pattern 1-7, Pitfall 9/10, Wave-0-Gaps). Zeilennummern beziehen sich auf den Stand `HEAD` (`ee12f59`); für `tests/test_ibkr_isolation.py` und `scripts/IBKR_EXECUTION.md` wurde `git show HEAD:<pfad>` zitiert, der Operator-WIP ist unten gesondert vermerkt.

## File Classification

| Neue/geänderte Datei | Rolle | Datenfluss | Nächste Vorlage | Qualität |
|---|---|---|---|---|
| `scripts/ibkr_guards.py` (neu) | utility (reine Logik: Schalter, Größe, Schlüssel, Quellenvergleich) | transform | `scripts/ibkr_decision.py` | exakt (Rolle + bibliotheksfrei, Uhr als Parameter) |
| `scripts/ibkr_ledger.py` (neu) | utility/store (append-only JSONL, Zustand je Schlüssel, `resolve_entry`) | file-I/O + transform | `scripts/ibkr_contracts.py` (`_append_history`, `commit_contracts`) + `scripts/ibkr_decision.py` (reiner Teil) | Teil-Treffer (Append/fsync), Reconciliation hat keine Vorlage |
| `scripts/ibkr_broker.py` (geändert: `order_history`, `cancel_all` + Permit, `open_orders(con_id=None)`, `preview_order(order_ref=)`) | adapter/service | request-response (Lesefenster) + Schreibsperre | derselbe: `open_orders` `:846`, `preview_order` `:868`, `_arm_write_barrier` `:435`, `_read` `:1008` | exakt |
| `scripts/ibkr_executor.py` (geändert: Subkommando `execute`, `run_execute`, `DryPlacer`, State-Pfade) | controller/CLI-Kette | request-response + file-I/O | derselbe: `run_preview` `:1415`, `_preview` `:924`, `_guarded` `:815`, `default_*_file` `:215-249` | exakt |
| `scripts/IBKR_EXECUTION.md` (geändert) | config/Doku | — | derselbe: Abschnitte `## Exit codes` (`:123`), `## States and log format` (`:156`), `## preview` (`:365`) | exakt |
| `tests/test_ibkr_guards.py` (neu) | test | transform | `tests/test_ibkr_decision.py` | exakt |
| `tests/test_ibkr_ledger.py` (neu) | test | file-I/O | `tests/test_ibkr_paperlog.py` / `tests/test_ibkr_contracts.py` (Persistenz-Tests) | role-match |
| `tests/test_ibkr_execute.py` (neu) | test (CLI-Kette gegen `FakeIB`) | request-response | `tests/test_ibkr_preview.py` | exakt |
| `tests/ibkr_fakes.py` (geändert) | test-Helfer | — | derselbe: `FakeOrder` `:71`, `FakeIB` `:178`, `open_trade` `:135` | exakt |
| `tests/test_ibkr_broker.py` (ergänzt) | test | request-response | derselbe: `:115-175` (echter Client), `:1133-1177` (`open_orders`) | exakt |
| `tests/test_ibkr_isolation.py` (geändert) | test (statische Wächter) | static-analysis | derselbe (HEAD) | exakt |
| `.planning/REQUIREMENTS.md` / `ROADMAP.md` (Textpflege REQ-25/-33/-42) | Doku | — | Muster „Geändert 2026-10-..."-Vermerk aus Phase 3 (laut RESEARCH Open Question 8) | role-match |
| `.planning/ibkr-konto-befund.md` (Operator-Messung SC3, A2, A3) | Doku | — | bestehender Abschnitt „whatIf-Vorschau und Read-Only-Schalter" | role-match |

## Pattern Assignments

### `scripts/ibkr_guards.py` (utility, transform)

**Analog:** `scripts/ibkr_decision.py` (Modulkopf, benannte Zustände, Zustand-zu-Exit-Tabelle) und `scripts/ibkr_paperlog.py` (kleine Whitelist-Validatoren).

**Modulkopf und Importe** (`ibkr_decision.py:1-30`): Docstring nennt „library-free ... no clock", `from __future__ import annotations`, nur Standardbibliothek, `log = logging.getLogger(__name__)`.
```python
from __future__ import annotations

import importlib
import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from types import MappingProxyType
```
Der Wächter `test_decision_modules_are_library_free` (siehe unten) verbietet `ib_async`, `tradingagents`, `exchange_calendars`, `pandas` auf Modulebene und `datetime.now` / `time.time(` / `date.today` im Quelltext. `guards.py` darf keine dieser Zeichenketten enthalten, auch nicht in Docstrings.

**Benannte Zustände als Modulkonstanten + eine Tabelle** (`ibkr_decision.py:34-111`):
```python
SKIPPED_HOLD = "skipped-hold"
...
ALL_STATES = frozenset({...})
_EXIT_OK, _EXIT_CONFIG, _EXIT_PRECONDITION, _EXIT_REJECTED = 0, 1, 2, 5
EXIT_BY_STATE: Mapping[str, int] = MappingProxyType({
    **dict.fromkeys((SKIPPED_HOLD, ...), _EXIT_PRECONDITION),
    ...
})
```
Übernehmen für die neuen Zustände (`RELEASE_MISSING`, `RELEASE_UNREADABLE`, `RELEASE_INVALID`, `RELEASE_EXPIRED`, `RELEASE_ACCOUNT_MISMATCH`, `KILL_ACTIVE`, `KILL_UNREADABLE`, ...) in einer **eigenen** Tabelle `EXIT_BY_STATE` in `guards.py` (nicht in `ibkr_decision.EXIT_BY_STATE`, sonst verlangt `test_handbook_state_table_matches_decision_module` Handbuchzeilen für Phase-5-Zustände im Phase-4-Format; RESEARCH „Recommended Project Structure"). Die Werte 4/6/7 als lokale `_EXIT_*`-Literale wie `:87` führen und per Test gegen `executor.EXIT_KILL_SWITCH` etc. gleichsetzen (wie der Kommentar `:83-84` es für 0/1/2/5 ankündigt).

**Schalter-Parser (Kern):** wörtlich aus `05-RESEARCH.md` Pattern 1 (`read_kill` mit `os.stat` und drei Ausgängen, `read_release` mit `utf-8-sig`, exakter Schlüsselmenge `{"account","valid_until"}`, Regex vor `date.fromisoformat`, `MAX_RELEASE_BYTES`). Ergänzen nach D-20: `valid_until > today_utc + timedelta(days=90)` -> `invalid`. Kein Aufruf von `Path.exists()` für `KILL`.

**Größe** (RESEARCH Pattern 5): `MAX_QTY_PER_ORDER = 2`, `check_size(quantity) -> str | None`, Sentinel-Test `max(decision.BLOCKS.values()) * max(spec.block_qty ...) <= MAX_QTY_PER_ORDER`. `plan_order` (`ibkr_decision.py:300-336`) erzeugt `quantity = int(abs(diff))`; `check_size` prüft **danach**, ein Wert über 2 wird abgelehnt (`size_cap`, Exit 5), nie gekürzt.

**Whitelist-Validator-Stil** (`ibkr_paperlog.py:18-21, 42-63`) für `decision_key`-Bauteile und `trade_date`:
```python
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
def summary_path(trade_date: str) -> str:
    if not _DATE_RE.match(trade_date):
        raise ValueError(f"invalid trade date: {trade_date!r}")
```
`decision_key = f"{trade_date}|{ticker}"` (REQ-39; `|` ist ungemessen, Annahme A3, Trenner in einer Konstante halten, damit `_` ein Einzeiler bleibt).

**Mehrere Zustände zu einem Exit verdichten** (`ibkr_decision.py:113-122`): `_EXIT_RANK` + `worst_exit`. Für `execute` wird die Rangfolge `4/6/7 vor 1 > 5 > 2 > 0` gebraucht; hier eine zweite, getestete Funktion ergänzen, nicht `worst_exit` verbiegen (die kennt 4/6/7 nicht).

---

### `scripts/ibkr_ledger.py` (utility/store, file-I/O + transform)

**Analog:** `scripts/ibkr_contracts.py` für Append mit `fsync` und History-JSONL; Reconciliation (`resolve_entry`) hat keine Vorlage im Repo (RESEARCH Pattern 7 ist die Quelle).

**Append-Muster mit fsync** (`ibkr_contracts.py:486-490`):
```python
def _append_history(history: Path, lines: Sequence[str]) -> None:
    with open(history, "a", encoding="utf-8", newline="\n") as fh:
        fh.writelines(lines)
        fh.flush()
        os.fsync(fh.fileno())
```
Für den Ledger auf **Bytes** umstellen (`open(path, "ab")`, ein `write()` je Zeile, `flush`, `os.fsync`) und die Abgerissene-Zeile-Behandlung aus RESEARCH „Code Examples / Ledger-Anhängen" und Pitfall 4 ergänzen. Zeile = `json.dumps(record, sort_keys=True, ensure_ascii=False)` wie `_history_line` (`ibkr_contracts.py:474-483`), aber mit `separators=(",", ":")` laut RESEARCH.

**Atomar-Schreiben (nur wo ganze Dateien entstehen, nicht für den Ledger)** (`ibkr_contracts.py:448-471`): `_temp_for` (uuid4-Suffix), `write_json_atomic` (`mkdir(parents=True, exist_ok=True)`, `fsync`, `os.replace`, bei `BaseException` `temp.unlink`). Der Ledger ist append-only und nutzt dieses Muster **nicht**; es bleibt für `RELEASE`-Hilfen/`--out`-Datensätze.

**Lesen mit Vorab-Prüfung und benannten Fehlern** (`ibkr_contracts.py:359-369, 422-437`): eigene Ausnahmeklassen `ContractsFileMissing(FileNotFoundError)` / `ContractsFileError(ValueError)`. Für den Ledger analog `LedgerError` (Mittendefekt, `mode`-Mischung) mit Abbildung auf Exit 6 im Executor.

**Reiner Teil ohne Uhr:** die Uhr als Argument/Callable (`self._clock`) wie `ibkr_decision.freshness(parsed, ctx.now_utc, ctx.calendar)`; kein `datetime.now` (Wächter).

**Zwingend aus den Entscheidungen:**
- D-08: eine Klasse, zwei Pfade; `mode`-Feld in jeder Zeile (`"dryrun"`/`"live"`); echte Datei mit `mode:"dryrun"`-Zeile -> `LedgerError` -> Exit 6.
- D-23: optionales Feld `rating_source` im Schema, in Phase 5 nie befüllt.
- Zustand = letztes Ereignis je `decision_key`; „Versuch" = Schlüssel hat `intent` erreicht; `skipped` verbraucht ihn nicht (RESEARCH Pattern 4).
- Ledger-Pfad nie im Git-Baum: Laufzeitprüfung „kein `.git` in einem Elternverzeichnis" (RESEARCH Pitfall 8).

---

### `scripts/ibkr_broker.py` (adapter, request-response + Schreibsperre)

**Analog:** dieselbe Datei.

**Neue Lesemethode `order_history()`, Muster `open_orders`** (`ibkr_broker.py:846-866`):
```python
def open_orders(self, con_id: int) -> tuple[OpenOrder, ...]:
    trades = self._read("reqAllOpenOrders", lambda: self._ib.reqAllOpenOrdersAsync())
    return tuple(
        OpenOrder(
            con_id=int(t.contract.conId),
            action=_text(t.order, "action"),
            quantity=float(t.order.totalQuantity),
            order_type=_text(t.order, "orderType"),
            status=_text(t.orderStatus, "status"),
            client_id=int(t.order.clientId),
        )
        for t in trades
        if int(t.contract.conId) == con_id
        and t.orderStatus.status not in _DONE_ORDER_STATUSES
    )
```
Änderungen: `con_id: int | None = None` (ohne Filter = alle, für `cancel_all`-Nachlese und Reconciliation); `OpenOrder` (`:221-229`, frozen dataclass, „broker-neutral, keine Bibliotheksobjekte") um `order_ref: str = ""` erweitern, **mit Default**, damit bestehende `OpenOrder(...)`-Vergleiche in `tests/test_ibkr_broker.py:1141-1150` grün bleiben. `order_history()` ruft **drei** `self._read(...)`-Aufrufe (`"reqAllOpenOrders"`, `"reqCompletedOrders"`, `"reqExecutions"`) mit den `...Async`-Varianten (`reqCompletedOrdersAsync`, `reqExecutionsAsync`); jeder erbt Timeout, „kein offener Link vorher" und „Link-Ereignis verwirft die Antwort" (`_read`, `:1008-1032`). Neue Dataclasses `OrderRecord`/`ExecutionRecord` neben `OpenOrder` (`@dataclass(frozen=True)`, Felder siehe RESEARCH Pattern 6). Keine Nachricht 99/7/16 liegt in `_WRITE_MESSAGE_IDS` (`:68`).

**`preview_order(order_ref=...)`** (`:868-1006`): Signatur ist keyword-only; `order_ref: str = ""` anhängen. Order wird in `:914-920` gebaut:
```python
order = handles.order(
    action=action, totalQuantity=quantity, orderType="MKT", tif=PREVIEW_TIF, account=EXPECTED_ACCOUNT,
)
```
-> `orderRef=order_ref` ergänzen (nur wenn gesetzt, damit bestehende Aufrufe unverändert bleiben). Das Echo-Tap (`:921-930`, `capture(*args)` liest `echo_order.tif`) um `orderRef`/`account` erweitern (A5), im `finally` wie bisher zurücksetzen (`:941-942`). `FakeOrder` braucht dafür ein Feld (siehe `tests/ibkr_fakes.py`).

**Einmal-Permit in der Sperre, Muster `_arm_write_barrier`** (`:435-500`). Heute: `_WRITE_CALLS = ("cancelOrder", "reqGlobalCancel", "exerciseOptions")` (`:59`) werden in der Schleife `:463-470` durch `refuse` ersetzt, `guarded_send` (`:480-487`) und `guarded_send_msg` (`:489-497`) lehnen `msg_id in _WRITE_MESSAGE_IDS` mit `refuse_message` ab. Umbau laut RESEARCH Pattern 3:
- `_arm_write_barrier(client, permit=None)`: `reqGlobalCancel` aus der `refuse`-Schleife herausnehmen und durch `guarded_global_cancel` ersetzen (Original vorher sichern, wie `original_place = getattr(client, "placeOrder", None)` in `:445`).
- In `guarded_send` und `guarded_send_msg`: `elif msg_id == 58 and permit.open: durchlassen` **vor** dem `elif msg_id in _WRITE_MESSAGE_IDS`-Zweig; gezählt (`permit.sent += 1`, `permit.open = False`) wird nur auf der Drahtebene (`guarded_send_msg`).
- Der Aufruf `_arm_write_barrier(ib.client)` in `connect()` (`:580`) bekommt das Permit der Instanz (`self._permit = _CancelPermit()` in `__init__`, neben `self.link_lost` etc. `:540-550`).
- `cancel_all(self, *, kill_evidence)` wie in RESEARCH Pattern 3; Fehlerklassen: `ReadOnlyViolation` (`:168`) für „kein Beleg"/„zweiter Aufruf", `GatewayUnavailable(REQUEST_FAILED, None, ...)` (`:183`, `REQUEST_FAILED` `:160`) für „nicht genau einmal auf dem Draht". Logzeile im bestehenden Stil: `self._log.warning('ibkr-state=GLOBAL_CANCEL_SENT code=- detail="count=1 reason=kill_switch"')` (Stil von `:997-1005`).
- Der bestehende Test `test_write_barrier_on_the_real_client_object` (`tests/test_ibkr_broker.py:115-123`) ruft `broker._arm_write_barrier(ib.client)` **einstellig** und erwartet `ib.reqGlobalCancel()` -> `ReadOnlyViolation`. Der neue Parameter muss einen Default haben (`permit=None` = nie offen), sonst bricht dieser Test und `:101` (`lambda client: None` per monkeypatch) ebenfalls. `WRITE_MESSAGE_IDS = (4, 19, 21, 58)` (`:128`) bleibt: 58 muss **ohne** Permit weiter scheitern.

**Isolation:** `ib_async` wird nur in `_default_ib_factory` importiert (Wächter `test_only_the_adapter_imports_the_client_library`); die neuen Methoden fassen keine Bibliotheksnamen an.

---

### `scripts/ibkr_executor.py` (controller/CLI, request-response + file-I/O)

**Analog:** dieselbe Datei, `run_preview` (`:1415-1474`) und die Verdrahtung `_preview` (`:924-965`).

**Modullader und `mods`-Bündel** (`:185-212, 949-955`): neue Module über `_load_script_module("ibkr_guards", Path(__file__).with_name("ibkr_guards.py"))` laden, `_GUARDS_PATH`/`_LEDGER_PATH` neben `_DECISION_PATH` (`:113`) führen; `mods = SimpleNamespace(broker=..., contracts=..., decision=..., paperlog=..., maintenance=..., guards=..., ledger=...)`.

**State-Pfade, außerhalb jedes Git-Baums** (`:215-249`):
```python
def _ibkr_base(environ=None) -> Path:
    environ = os.environ if environ is None else environ
    base = environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "TradingEngineX" / "ibkr"
    return Path.home() / ".tradingenginex" / "ibkr"

def default_preview_file(environ=None) -> Path:
    return _ibkr_base(environ) / "preview.json"
```
Neu in genau diesem Stil: `default_release_file`, `default_kill_file`, `default_ledger_file` (`ledger.jsonl`), `default_dryrun_ledger_file` (`ledger-dryrun.jsonl`). Nicht das duplizierte Muster von `default_contracts_file`/`default_log_file` (`:233-248`) kopieren, sondern `_ibkr_base` benutzen. Lock-Pfad ist **immer** der des echten Ledgers (RESEARCH Pitfall 6).

**Exit-Konstanten schon vorhanden** (`:79-88`): `EXIT_KILL_SWITCH = 4`, `EXIT_RECONCILE = 6`, `EXIT_LOCKED = 7`. **Keine neuen `EXIT_*`** (Handbuchtest verlangt genau 10). Docstring `:44-55` an den drei Zeilen „(reserved for later phases)" anpassen, ebenso den Subkommando-Absatz (`:30-34`, Phase-5-Absatz analog zu `:18-26`).

**CLI-Verdrahtung** (`build_parser` `:704-736`, `main` `:739-799`):
```python
preview = sub.add_parser("preview", help=help_text)
preview.add_argument("tickers", nargs="*", metavar="TICKER")
preview.add_argument("--contracts", type=Path, default=None, help="contracts.json path")
preview.add_argument("--out", type=Path, default=None, help="dry-run record (JSON)")
preview.add_argument("--log-file", type=Path, default=default_log_file())
preview.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
```
`execute` bekommt dieselben Optionen **ohne** Schalter, der den Trockenzwang aufhebt (D-07: Phase 6 nimmt den Zwang heraus, kein CLI-Wert). `main` bekommt ein neues keyword-only `placer=None` (Naht für SC2, RESEARCH Pattern 2) neben `broker_factory`, `clock`, `paper_log_factory`, `calendar` (`:739-746`). Zusätzlich in `main`: Usage-Text `:758` („account, resolve, preview" -> mit `execute`; `tests/test_ibkr_preview.py:236-238` prüft den Teilstring `"account, resolve, preview"` und muss mit angepasst werden), und die Prüfung „`execute` braucht mindestens einen TICKER" nach dem Vorbild von `:765-768`. Dispatch in `:793-797` um `execute` erweitern.

**Fehlerabbildung wiederverwenden** (`_guarded`, `:815-854`): `AccountGuardViolation` -> Exit 8, `ReadOnlyViolation` -> `WRITE_REFUSED`/Exit 3, `GatewayUnavailable` -> Exit 3, `ConfigError` -> Exit 1, `except Exception` -> Traceback nur ins Log. `_preview` (`:924-965`) kapselt das als `lambda: run_preview(...)`; `_execute` genauso (`progress = {"connecting": False, "connected": False}`).

**Lauf-Lock ohne `except OSError` um den ganzen Lauf** (`tradingagents/dataflows/files.py:36-49`, `_hold_windows` `:67-88`). Die Funktion wirft unter Windows jeden `OSError` außer `EACCES`/`EDEADLOCK` und `FileNotFoundError`, wenn das Verzeichnis fehlt (`open(f"{path}.lock", "a+b")`, `:46`). Muster aus RESEARCH Pitfall 3 (`ExitStack`, nur den Sperrversuch in `try/except OSError`, `held is False` -> `EXIT_LOCKED`, Lauf außerhalb des `try`):
```python
from contextlib import ExitStack
stack = ExitStack()
try:
    held = stack.enter_context(locked(lock_path, wait=False))
except OSError:
    return EXIT_LOCKED          # LOCK_ERROR
if not held:
    stack.close()
    return EXIT_LOCKED          # LOCK_HELD
with stack:
    return run_chain(...)
```
Import: `from tradingagents.dataflows.files import locked` (der Executor importiert schon `tradingagents.memory.log`/`tradingagents.portfolio`, `:76-77`; `tradingagents` ist hier also erlaubt, nur den neuen reinen Modulen verboten). State-Ordner **vor** dem Sperrversuch anlegen (`mkdir(parents=True, exist_ok=True)`), Anlegefehler = nicht ausführen.

**Kette `run_execute`, wiederverwenden statt neu bauen** (RESEARCH „Don't Hand-Roll"): `_local_chain` (`:1160-1215`), `_load_stored_contracts` (`:1218-1234`), `_session_info` (`:1237-1246`), `_gateway_chain`-Struktur (`:1384-1412`, Kontextmanager `with adapter as broker:`, `broker.health()`, `EXIT_GATEWAY` bei `not health.ok`), `_resolve_and_preview` (`:1345-1381`) und `_preview_ticker` (`:1249-1342`) als Vorlage. Wichtige Stellen für die Einhängepunkte von `execute`:

- `_resolve_and_preview` `:1366-1378`: `closed = result.state == contracts_mod.CLOSED` markiert bisher nur („A closed market is a mark, not a stop: the preview still runs (D-08)", `:1366`). Für `execute` wird daraus `skipped outside_session` **vor** dem `whatIf` (D-10, REQ-42). Das ist die einzige Stelle, an der sich `execute` von `preview` im Verhalten unterscheidet; `preview` darf **unverändert** bleiben (D-07), also nicht in der gemeinsamen Funktion umschalten, sondern per Parameter/herausgelöster Funktion.
- `calendar_conflict`-Prüfung `:1372-1378` und `positions()`-Snapshot `:1379-1381` unverändert übernehmen.
- `_preview_ticker` `:1271` ruft `broker.open_orders(identity.con_id)` und `plan_order(... open_orders=len(orders) ...)` `:1284-1286`; `:1290-1298` `preview_order(...)` bekommt `order_ref=decision_key` (REQ-41).
- Größenprüfung zwischen `plan_order` (`:1284`) und `preview_order` (`:1290`): `guards.check_size(plan.quantity)`, bei Verletzung `_finish_row`-artiger Abschluss mit `size_cap`, **kein** `whatIf`, kein `intent`.
- Schalterprüfung an den drei Stellen aus D-21 (Preflight direkt nach dem Lock, vor der Reconciliation; Position nach REQ-45 zwischen Handelszeit und `whatIf`; unmittelbar vor `intent`).
- `intent` mit `fsync` **vor** `placer.complete(ctx, intent)`; `DryPlacer.complete` schreibt `dry_complete` und prüft `check_size` ein zweites Mal (RESEARCH Pattern 5, keine zweite Konstante im Adapter).
- Kill-Pfad: nur bei `kill.state == "active"` -> verbinden, `broker.cancel_all(kill_evidence=kill)`, `broker.open_orders(None)` mit Wiederholung, Ledger `kill_cancel` mit `remaining=<n>`, Exit 4; `KILL_UNREADABLE` und `RELEASE_*` -> Exit 4 **ohne** Storno (D-17). `cancel_all(` darf im Executor an genau **einer** Stelle stehen (AST-Wächter).

**Logzeilen und Konsole** (`_finish_row` `:1048-1062`, `_abort_run` `:991-1011`, `_fail` `:353-356`):
```python
ctx.logger.log(
    logging.WARNING if code else logging.INFO,
    "ibkr-state=PREVIEW ticker=%s state=%s sha=%s detail=%r",
    row["ticker"], state, ctx.sha, detail,
)
print(f"preview: {row['ticker']} {state}{_console_suffix(row)}")
```
Für `execute` Präfix `execute:` und Zustandsnamen `ibkr-state=EXECUTE ...`, `ibkr-state=RELEASE_EXPIRED ...`, `ibkr-state=LOCK_HELD`, `ibkr-state=RECONCILE_UNRESOLVED key=... open=... completed=... executions=...` (D-19: Schlüssel und Befund je Quelle eindeutig nennen). Das SHA des `paper-log` in jeder Zeile (`ctx.sha`).

**Datensatz `--out`** (`_preview_payload` `:968-980`, `_write_preview` `:983-988`): für `execute` kein JSON-`--out` nötig (der Ledger ist der Datensatz); falls doch, `contracts_mod.write_json_atomic` und `OutputError` wiederverwenden. Der Kommentar `:971` („Dry-run record, not the ledger (phase 5): no write-ahead, no lock") ist die Abgrenzung, die erhalten bleiben muss.

**`_discard_previous`** (`:802-812`) gehört zu `account`/`preview`-Ausgaben und **nicht** zum Ledger: ein Ledger wird nie gelöscht oder ersetzt.

---

### `scripts/IBKR_EXECUTION.md` (Doku, Wächter-gebunden)

**Analog:** HEAD-Fassung (Abschnitte: `## Gateway Read-Only switch` `:38`, `## clientId` `:73`, `## Settings` `:94`, `## Exit codes` `:123`, `## States and log format` `:156`, `## preview` `:365`, `### States (phase 4)` `:417`, `## Commands` `:464`).

**Exit-Tabellenzeilen, die Phase 5 ändern muss** (HEAD `:134, :136, :137`):
```
| 4 | `EXIT_KILL_SWITCH` | kill switch active or release missing (reserved for later phases) |
| 6 | `EXIT_RECONCILE` | reconciliation unresolved, run aborted (reserved for later phases) |
| 7 | `EXIT_LOCKED` | lock not acquired (second instance), clean exit (reserved for later phases) |
```
Das Zeilenpräfix `| <n> | \`EXIT_...\` |` ist testgebunden (`test_handbook_exit_table_matches_executor`, regex `^\| {value} \| \`{name}\` \|`). Nur den Text hinter dem zweiten `|` ändern, „reserved" streichen; neue Tests analog `test_handbook_exit_two_is_active`/`..._five_...` ergänzen.

**Neue Abschnitte** (englisch wie der Rest der Datei, vgl. bestehende Abschnittsüberschriften): `## RELEASE and KILL` (Dateien, Format JSON `{"account": "DUQ634065", "valid_until": "YYYY-MM-DD"}`, Einzeiler zum Anlegen als `python -c` oder `[IO.File]::WriteAllText(...)`, UTF-8 ohne BOM; **vor dem Dokumentieren auf diesem Rechner ausführen**, RESEARCH Pitfall 2), `## execute` (Kette, zwangsweise trocken, `ledger-dryrun.jsonl`), `## Ledger and reconciliation` (inkl. D-19-Auflösungsablauf: `ledger-dryrun.jsonl` löschen/umbenennen für den Trockenmodus; `--resolve` kommt in Phase 6), Zustandstabelle der neuen Zustände (eigener Handbuch-Test, siehe Isolation), Hinweis „Größengrenze lehnt ab, kürzt nicht; `SELL 5` wird `size_cap`" (RESEARCH Pattern 5), Zweite-Quelle-Tabelle (D-22). Keine Uhrzeit-Literale im Muster `HH:MM` aus der Verbotsliste (`test_no_hard_coded_trading_times_in_execution_code` prüft zwar nur `scripts/ibkr_*.py`, aber der Stil gilt), keinen Bibliotheksnamen `ib_async` (`test_handbook_does_not_name_the_client_library`).

---

### `tests/ibkr_fakes.py` (test-Helfer)

**Analog:** dieselbe Datei.

**Zu ändern** (RESEARCH Pitfall 10):
- `FakeOrder` (`:70-77`, `@dataclass`): `orderRef: str = ""` (und optional `account` ist schon da) ergänzen. Ohne dieses Feld scheitert `handles.order(..., orderRef=...)` mit `TypeError`.
- `FakeIB.__init__` (`:181-231`): neue Parameter `completed_orders=None`, `executions=None` (wie `open_orders`: Liste oder `"hang"`), Attribute `self.completed_orders`, `self.executions`; `emit_during`-Namen `completed_orders`, `executions`, `global_cancel` dokumentieren (Kommentar `:199-202`).
- Neue `async def reqCompletedOrdersAsync(self, apiOnly=False)` und `reqExecutionsAsync(self, execFilter=None)` nach dem Muster `reqAllOpenOrdersAsync` (`:361-366`):
```python
async def reqAllOpenOrdersAsync(self):
    self.calls.append("open_orders")
    self._emit_during("open_orders")
    if self.open_orders == "hang":
        await _forever()
    return list(self.open_orders)
```
- `reqGlobalCancel` auf `FakeIB`: ruft `self.client.reqGlobalCancel()` (damit die Sperre im Fake sichtbar wird, `client` ist `SimpleNamespace(**self._recorders)`, `:230-231`), danach ggf. offene Orders leeren (konfigurierbar, damit „Storno wirkt"/„Storno wirkungslos" beide testbar sind; A1).
- Die `_forbidden`-Attrappen `reqCompletedOrders`/`reqExecutions` (`:382-386`, **synchron**) bleiben, weil der Adapter die `...Async`-Varianten nutzt. `reqAllOpenOrders` (`:379`) ebenso.
- Neuer Zeilenbauer analog `open_trade` (`:135-145`) für `completed_trade(...)` (`order.orderRef`, `order.filledQuantity`, `orderStatus.status`) und `fill(...)` für Executions (`execution.orderRef`, `.shares`, `.execId`, `.side`, `.time`). `open_trade` selbst braucht `orderRef=""` im `SimpleNamespace` der Order (`:141-143`), sonst scheitert `_text(t.order, "orderRef")`-Lesen, falls `_text` kein Default hat (prüfen).
- Der `recorder` (`:233-242`) unterscheidet `placeOrder` mit `whatIf` von echten Orders (`calls`-Eintrag `"placeOrder(whatIf)"` vs `"placeOrder"`); die Phase-5-Tests verlangen `"placeOrder" not in fake.calls` und `calls.count("reqGlobalCancel") <= 1`.

---

### `tests/test_ibkr_execute.py` (test, CLI-Kette gegen `FakeIB`)

**Analog:** `tests/test_ibkr_preview.py` (Gerüst `:1-232`).

**Gerüst, 1:1 übernehmen** (`:11-98`): Modul-Lader `_load_executor` per `spec_from_file_location("ibkr_executor", _SCRIPT)`, `broker = executor.load_broker_module()`, `decision = executor.load_decision_module()`, `paperlog = paper_log_fixture._pl`, `pytestmark = pytest.mark.unit`, Konstanten (`OPEN_NOW`, `OPEN_HOURS`, `CLOSED_NOW`, `CLOSED_HOURS`, `CON_IDS`, `SHA`, `DEFAULT_ENV`), Fixtures:
```python
@pytest.fixture(scope="session")
def loop(): yield from ibkr_fakes.session_loop()

@pytest.fixture(autouse=True)
def _pin_modules(monkeypatch):
    monkeypatch.setattr(executor, "load_decision_module", lambda: decision)
    monkeypatch.setattr(executor, "load_paperlog_module", lambda: paperlog)

@pytest.fixture(autouse=True)
def _block_real_connect(monkeypatch): ibkr_fakes.block_real_ib_connect(monkeypatch)

@pytest.fixture(autouse=True)
def _close_logging(): yield; executor.close_logging()

@pytest.fixture(autouse=True)
def _local_app_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
```
Die `_local_app_data`-Fixture ist hier **Pflicht** (Pitfall 7): ohne sie landen `ledger-dryrun.jsonl`/`ledger.jsonl.lock`/`KILL`-Einflüsse im echten `%LOCALAPPDATA%\TradingEngineX\ibkr`. Für `_pin_modules` zusätzlich die neuen Lader (`load_guards_module`, `load_ledger_module`) auf die Instanzen dieser Datei festnageln.

**Hilfsfunktionen** (`:93-229`): `_env_file`, `_RecordingFactory` (Broker-Fabrik, die nie aufgerufen werden darf: Beleg für „kein Gateway-Kontakt"), `_fake_factory(fake, loop)` (baut `broker.IbkrBroker(..., ib_factory=ibkr_fakes.make_handles(fake), loop=loop, connect_timeout=0.05, request_timeout=0.05, probe_timeout=0.05)`), `_stub_calendar`, `_fixed(moment)`, `_PaperLogFactory`, `_summary`, `_paper`, `_buy_paper`. `_run_preview` (`:148-190`) als Vorlage für `_run_execute(tmp_path, factory, tickers, *, paper_log, placer=None, clock=OPEN_NOW, release=..., kill=False, ...)`: legt die Dateien `RELEASE`/`KILL` unter `tmp_path/"TradingEngineX"/"ibkr"` an (über `executor.default_release_file()`, nicht hartkodiert), ruft `executor.main(argv, broker_factory=..., clock=_fixed(clock), paper_log_factory=..., calendar=..., placer=placer)` und `executor.close_logging()`; gibt `(code, ledger_path, log_path)` zurück.

**Tests nach Wave-0-Tabelle und `-k`-Schlüsseln** (`05-RESEARCH.md` „Phase Requirements -> Test Map"): Testnamen müssen die Schlüsselwörter tragen, mit denen die Validierungsbefehle selektieren (`g3`, `kill_between`, `cancel_all`/`global_cancel`, `size`, `reconcil`, `write_ahead`, `lock`, `order_ref`/`decision_key`/`decision_changed`/`already_attempted`, `session`, `switch_state`, `source_conflict`, `negative_control`, `nothing_sent`/`forced_dry`, `dryrun`). Konkrete Prüfungen als Kopiervorlage:
- „nie gesendet": `assert "placeOrder" not in fake.calls` (Fake-Konvention `:236-240`; ein `placeOrder(whatIf)` ist erlaubt) und `not any(c in fake.calls for c in ("cancelOrder", "exerciseOptions"))`; `reqGlobalCancel` höchstens im Kill-Test, dann `fake.calls.count("reqGlobalCancel") == 1`.
- `orderRef` an der `whatIf`-Order: `fake.whatif_calls[-1][1].orderRef == "2026-10-09|AAPL"` (`whatif_calls` `:228`).
- Lock-Test (SC7): zweiten Lauf **verschachtelt im selben Prozess** starten (unter Windows liefert `locked(..., wait=False)` dann `False`, RESEARCH Pitfall 3 / Zeile 51), `OSError` per `monkeypatch` auf `files.locked`; Erwartung Exit 7, kein Ledger-Eintrag, kein Traceback.
- Test-Placer für SC2/`kill_between`: legt in `complete()` die Datei `KILL` an; erwartet Ledger `intent`+`dry_complete` für Ticker 1, für Ticker 2 `skipped kill_switch` ohne `intent`, Exit 4.
- Abbruchtest SC6: Placer, der nach `intent` wirft; Folgelauf liest den Ledger und endet mit Exit 6 (je Quelle ein Fall).
- Negativ-Kontrollen (REQ-66) als eigene Tests mit `negative_control` im Namen, je Schutz laut Tabelle in RESEARCH.

---

### `tests/test_ibkr_broker.py` (ergänzt)

**Analog:** dieselbe Datei.

**Echter Client, Sperre** (`:115-123`, `:131-141`): Form für die neuen Permit-Tests
```python
def test_write_barrier_on_the_real_client_object():
    ib_async = pytest.importorskip("ib_async")
    ib = ib_async.IB()
    broker._arm_write_barrier(ib.client)
    ...
    with pytest.raises(broker.ReadOnlyViolation):
        ib.reqGlobalCancel()

@pytest.mark.parametrize("msg_id", WRITE_MESSAGE_IDS)
def test_write_barrier_refuses_write_messages_on_the_wire(msg_id):
    ib_async = pytest.importorskip("ib_async")
    client = ib_async.IB().client
    broker._arm_write_barrier(client)
    with pytest.raises(broker.ReadOnlyViolation, match=f"message {msg_id}"):
        client.send(msg_id, 1, 42)
    with pytest.raises(broker.ReadOnlyViolation, match=f"message {msg_id}"):
        client.sendMsg(f"{msg_id}\0" + "1\0")
```
Neu, mit echter `Client`-Klasse und einem `permit`-Objekt: (a) Permit zu -> 58 scheitert auf Name, Feldebene und Draht; (b) Permit offen -> der Aufruf erreicht den nicht verbundenen Client und wirft `ConnectionError("Not connected")` (Muster von `:166-174`: „reaches the library's own send"), danach `permit.open` zu; (c) zweiter Aufruf scheitert; (d) `cancel_all(kill_evidence=None)` scheitert. Alle bestehenden einstelligen Aufrufe `broker._arm_write_barrier(client)` müssen weiter laufen (Default für `permit`).

**Lesemethoden-Tests, Muster `open_orders`** (`:1133-1177`): `_connected(fake, loop)`, `FakeIB(open_orders=[ibkr_fakes.open_trade(...)])`, `emit_during={"open_orders": [(-1, 1100, "lost", None)]}` -> `GatewayUnavailable.state == "CONNECTIVITY_LOST"`, `"hang"` -> `REQUEST_TIMEOUT`, ohne Verbindung -> `NOT_CONNECTED`. Dieselbe Viererfolge für `order_history()` (Timeout, Link-Ereignis, nicht verbunden, Erfolg), plus `assert not any(call in fake.calls for call in FORBIDDEN_CALLS)`.

---

### `tests/test_ibkr_isolation.py` (statische Wächter, HEAD-Fassung)

**Analog:** HEAD-Fassung `git show HEAD:tests/test_ibkr_isolation.py`.

**Zu ändernde bestehende Tests** (RESEARCH Pitfall 9):
- `test_adapter_has_at_most_ten_public_methods` (HEAD `:122-129`): pinnt die **exakte** Menge `{"connect", "positions", "health", "search_contract", "contract_details", "open_orders", "preview_order"}`; neue Menge zusätzlich `order_history`, `cancel_all` (9 von 10, Phase 6 behält Platz für `place`).
- `test_handbook_exit_table_matches_executor` (HEAD `:166-176`): `assert len(codes) == 10` -> keine neuen `EXIT_*`.
- `test_no_market_data_in_execution_path` (HEAD `:369-377`) und `test_decision_modules_are_library_free` / `test_decision_module_takes_the_clock_as_a_parameter` (`:339-366`): Tupel `(EXECUTOR, ADAPTER, DECISION)` bzw. `(DECISION, PAPERLOG)` um `GUARDS`/`LEDGER` erweitern. Die Muster „aus Teilen gebaut, damit die Testdatei die Zeichenketten nicht selbst enthält" (`:371-372`) übernehmen.
- `test_no_hard_coded_trading_times_in_execution_code` (`:218-232`) prüft bereits alle `scripts/ibkr_*.py` per Glob; die neuen Module sind automatisch erfasst (keine `09:30`-artigen Literale, auch nicht in Docstrings/Beispielen).

**Neue Wächter nach demselben Stil:** `cancel_all(`/`reqGlobalCancel` im Executor nur an genau einer Stelle (AST, Muster `_imports`-Walk `:70-77`); `ibkr_market_data.py` enthält weder `cancel_all` noch `reqGlobalCancel`; Handbuch-Zeilen 4/6/7 ohne „reserved" (Muster `test_handbook_exit_two_is_active`, HEAD `:178-186`); Handbuch-Zustandstabelle der neuen Module gleich Modultabelle (Muster `test_handbook_state_table_matches_decision_module`, HEAD `:287-296`, mit `_load_decision`-artigem Lader unter eigenem Probe-Namen, `sys.modules` vorher/nachher, weil `dataclasses` String-Annotationen darüber auflöst); State-Pfade nicht unter `ROOT` (`git status --porcelain` vor/nach vergleichen, nicht „leer" verlangen, Pitfall 8).

---

### `tests/test_ibkr_guards.py` und `tests/test_ibkr_ledger.py` (test, rein)

**Analog:** `tests/test_ibkr_decision.py` (reine Funktionen ohne Fake, parametrisiert) bzw. `tests/test_ibkr_paperlog.py`/Persistenz-Tests in `tests/test_ibkr_contracts.py` (Dateien in `tmp_path`). Beide tragen `pytestmark = pytest.mark.unit` (Config `--strict-markers`). Für `guards`: Parser-Matrix aus RESEARCH Pattern 1/Pitfall 2 (BOM akzeptiert, UTF-16 abgelehnt, Verzeichnis statt Datei, `PermissionError` per `monkeypatch` auf `os.stat`/`open`, falscher Schlüsselsatz, `20261031`-Format, Laufzeit > 90 Tage, `today > valid_until` aber gleicher Tag gültig). Für `ledger`: Reihenfolge-Test `intent` vor `Placer.complete`, abgerissene letzte Zeile toleriert, Mittendefekt -> `LedgerError`, `mode`-Mischung, Zustand je Schlüssel, `resolve_entry` je Quelle (offen, erledigt, Executions, `no_trace`, Kollision auf `conId`/Seite/Menge).

---

## Shared Patterns

### Fail-closed Lesen mit benannten Zuständen
**Quelle:** `scripts/ibkr_broker.py:1008-1032` (`_read`) und `scripts/ibkr_executor.py:815-854` (`_guarded`).
**Anwenden auf:** jede neue Gateway-Lesemethode und jedes neue Subkommando. Kein `except Exception` in der Schalterprüfung, das „erlaubt" ergibt; jede unerwartete Ausnahme in `read_kill`/`read_release` ist `unreadable`. Logzeile immer `ibkr-state=<LABEL> code=<n|-> detail="..."` (Stil `:829`, `:997`, `:1407`).

### State außerhalb jedes Git-Baums
**Quelle:** `scripts/ibkr_executor.py:215-249` (`_ibkr_base`, `default_*_file`).
**Anwenden auf:** `RELEASE`, `KILL`, `ledger.jsonl`, `ledger-dryrun.jsonl`, `ledger.jsonl.lock`. Tests biegen `LOCALAPPDATA` auf `tmp_path` um (autouse-Fixture, `tests/test_ibkr_preview.py:88-90`).

### Atomares/ durables Schreiben
**Quelle:** `scripts/ibkr_contracts.py:456-471` (`write_json_atomic`, ganze Dateien) und `:486-490` (`_append_history`, append mit `flush`+`fsync`); `scripts/ibkr_executor.py:1080-1089` (`_write_bytes_atomic`).
**Anwenden auf:** Ledger (append, Bytes), `--out`-Datensätze (atomar). Niemals eine Ledger-Zeile umschreiben.

### „Erwartete Bytes" / Mehrschreiber-Schutz
**Quelle:** `scripts/ibkr_contracts.py:493-563` (`_snapshot_bytes`, `commit_contracts(..., expected_bytes=...)`, O_EXCL-Lock `:533`, History-vor-Replace `:545-548`, `*-aborted`-Zeile bei Fehler `:549-559`).
**Anwenden auf:** Vorbild, **nicht** zu kopieren für den Ledger: der Ledger-Lock ist `locked(..., wait=False)` aus `tradingagents/dataflows/files.py` (prozessgebunden, vom OS beim Tod freigegeben), nicht eine O_EXCL-Datei, die nach einem Absturz liegen bleibt (RESEARCH „Don't Hand-Roll"). Übernehmen lässt sich der Gedanke „Protokollzeile vor der Wirkung und eine `-aborted`-Spur bei Scheitern" für `intent` -> Abschluss.

### Uhr und Kalender als Parameter
**Quelle:** `scripts/ibkr_executor.py:739-753` (`clock = clock or (lambda: datetime.now(UTC))`, `main(..., clock=None, calendar=None)`), `scripts/ibkr_contracts.py:286-291` (`evaluate_session(..., now_utc, buffer_minutes=SESSION_BUFFER_MINUTES)`).
**Anwenden auf:** `guards` (`today_utc`), `ledger` (`clock`), `execute`. D-10: Sitzungsfenster ausschließlich über `evaluate_session` und `SESSION_BUFFER_MINUTES` (`ibkr_contracts.py:38`), keine zweite Konstante.

### Zugangsdaten nicht kopieren
**Quelle:** `scripts/ibkr_executor.py:90-95, 254-295` (`REQUIRED_ENV`, `read_settings`, `validate_settings`). `execute` liest nur `IBKR_HOST`, `IBKR_PORT`, `IBKR_ACCOUNT_ID`, `IBKR_TRADING_MODE`; Kontonummer aus `broker_mod.EXPECTED_ACCOUNT` (`validate_settings(raw, mods.broker.EXPECTED_ACCOUNT)`, `:1435`) gegen `RELEASE.account` prüfen (D-02, zweite Konto-Quelle neben `managedAccounts`).

### Test-Fakes statt Gateway
**Quelle:** `tests/ibkr_fakes.py:178-366` (`FakeIB`, `make_handles`, `block_real_ib_connect`), `tests/conftest.py` (Sockets gesperrt). Gateway nur in ausdrücklichen Operator-Checkpoints (D-06, RESEARCH „Operator-Checkpoints").

---

## No Analog Found

| Datei/Teil | Rolle | Datenfluss | Grund |
|---|---|---|---|
| `resolve_entry` / Reconciliation über drei Quellen (`ibkr_ledger.py`) | transform | batch | Im Repo existiert keine Abgleichslogik zwischen lokalem Protokoll und Broker-Quellen; RESEARCH Pattern 7 ist die einzige Vorlage |
| Einmal-Permit für `reqGlobalCancel` (`_CancelPermit`, `cancel_all`) | adapter | request-response | Die Sperre kennt nur ein statisches Verbot plus die `whatIf`-Ausnahme für Id 3 (`guarded_place`, `:447-459`); ein zustandsbehafteter, gezählter Durchlass ist neu. Nächster Verwandter: die Id-3-Ausnahme in `guarded_send`/`guarded_send_msg` (`:480-497`) |
| Kill-Storno-Nachlese mit Wiederholung (`open_orders(None)` bis 10 s im 0,5-s-Takt) | service | polling | Kein Polling-Muster im Executor; zeitliche Steuerung nur über die Request-Timeouts des Adapters |
| `RELEASE`-Parser | utility | file-I/O | Nächstes Muster ist `_parse_contracts`/`load_contracts_file` (`ibkr_contracts.py:388-437`, strenge Schlüssel-/Typprüfung mit `ContractsFileError`), dort aber ohne BOM-/Encoding-Härtung und ohne Ablaufdatum; Pattern 1 aus RESEARCH liefert den Rest |

## Kollisionen mit dem Operator-WIP (nicht committet im Hauptbaum)

Stand `git status`: geändert `scripts/IBKR_EXECUTION.md` (+5 Zeilen) und `tests/test_ibkr_isolation.py` (+21 Zeilen); neu `scripts/ibkr_market_data.py`, `tests/test_ibkr_market_data.py`, `.planning/debug/`.

| Datei | WIP-Inhalt | Kollision mit Phase 5 | Umgang |
|---|---|---|---|
| `scripts/IBKR_EXECUTION.md` | Absatz zu clientId **20002** nach dem clientId-Abschnitt (HEAD-Zeile ca. `:73-93`, WIP fügt nach `:82` ein) | Phase 5 ändert andere Stellen (Exit-Tabelle `:134-137`, neue Abschnitte nach `## preview`/`## Commands`). Konfliktarm, aber derselbe Datei-Header-Bereich, falls ein Plan die Intro-Zeilen anfasst | Vor jedem Edit **neu lesen**; keine Edits in den ersten ca. 100 Zeilen; Absätze nie überschreiben; Exit-Tabellenzeilen per kleinem gezieltem Edit |
| `tests/test_ibkr_isolation.py` | am Dateiende: `MARKET_DATA`-Konstante, `test_execution_path_does_not_load_the_market_data_session` (iteriert `(EXECUTOR, ADAPTER, DECISION, PAPERLOG)`, prüft `MARKET_DATA.stem` nicht im Quelltext), `test_market_data_client_id_is_documented_and_distinct` (importiert `from tests.test_ibkr_market_data import md`) | Phase 5 ändert Tests in der Mitte (Methodenmenge, Handbuch) und erweitert Tupel am Ende. Der WIP-Test iteriert ein **festes** Tupel: die neuen Module `GUARDS`/`LEDGER` müssen dort aufgenommen werden, und `ibkr_guards.py`/`ibkr_ledger.py` dürfen die Zeichenkette `ibkr_market_data` nicht enthalten, auch nicht in Kommentaren | Erweiterung des Tupels erst nach Neu-Lesen und möglichst als eigener Commit nach dem WIP-Commit des Operators |
| `scripts/ibkr_market_data.py` | eigene `IbkrBroker`-Sitzung, clientId 20002, teilt `WINDOW_BENIGN_CODES`/`INFO_CODES` mit dem Adapter | `cancel_all` ist Methode von `IbkrBroker`, die der Stream instanziiert. Gegenmaßnahmen: Kill-Beleg als Pflichtargument, Einmal-Permit je Sitzung, Wächter „`ibkr_market_data.py` nennt weder `cancel_all` noch `reqGlobalCancel`". `WINDOW_BENIGN_CODES`/`INFO_CODES` (`ibkr_broker.py:139`) in Phase 5 **nicht ändern** | Wächtertest zuerst (RED) |
| `tests/test_ibkr_market_data.py` | neu | benutzt die gemeinsamen Fakes (`tests/ibkr_fakes.py`). Neue `FakeIB`-Parameter und `FakeOrder`-Felder müssen Defaults haben, damit seine Aufrufe unverändert laufen | Nur additive Änderungen an `ibkr_fakes.py` |

Absolute Aussagen der Art „`git status` ist leer" sind wegen dieses WIP dauerhaft rot und deshalb nicht zu testen; stattdessen `git status --porcelain` vor und nach dem Lauf vergleichen (RESEARCH Pitfall 8).

## Metadata

**Analog-Suchbereich:** `scripts/ibkr_*.py`, `scripts/IBKR_EXECUTION.md`, `tradingagents/dataflows/files.py`, `tests/ibkr_fakes.py`, `tests/test_ibkr_{preview,broker,isolation,resolve}.py`, WIP-Dateien (nur gelesen).
**Gelesene Dateien:** 12 (Teilbereiche der großen Dateien `ibkr_executor.py` 1478, `ibkr_broker.py` 1141, `ibkr_contracts.py` 867 Zeilen über Grep + gezielte Bereiche).
**Muster-Extraktion:** 2026-10-16
