# Phase 4: Entscheidungsübernahme und Soll-Rechnung bis zum `whatIf`-Preview - Pattern Map

**Kartiert:** 2026-10-12
**Dateien analysiert:** 14 (5 neu im Code, 4 neue Testdateien, 5 geänderte)
**Analoga gefunden:** 14 / 14 (alle Dateien haben ein Analog im Repo; nur einzelne Teilmuster sind neu, siehe Abschnitt "Kein Analog")

## Dateiklassifikation

| Neue/geänderte Datei | Rolle | Datenfluss | Nächstes Analog | Qualität |
|----------------------|-------|------------|-----------------|----------|
| `scripts/ibkr_decision.py` (NEU) | service (reine Fachlogik, bibliotheksfrei) | transform | `scripts/ibkr_contracts.py` (Frozen-Dataclasses, benannte Zustände, injizierte Uhr) | exact |
| `scripts/ibkr_broker.py` (ÄNDERUNG: `_arm_write_barrier`, `preview_order`, `open_orders`, `available_funds`, `BrokerPosition.con_id`, `IbHandles.order`) | adapter/middleware | request-response | derselbe Datei: `search_contract`/`contract_details` + `_read`/`_request` + `_arm_write_barrier` | exact |
| `scripts/ibkr_contracts.py` (ÄNDERUNG: `block_qty`, `SessionVerdict.session_day`) | model/config | transform | derselbe Datei: `ContractSpec`, `CONTRACT_TABLE`, `evaluate_session` | exact |
| `scripts/ibkr_executor.py` (ÄNDERUNG: Subkommando `preview`, git-Zugriff, Settings, Exit-Mapping, Protokoll) | controller (CLI) | request-response + file-I/O | derselbe Datei: `run_resolve`, `_resolve`, `_guarded`, `_resolve_payload` | exact |
| `pyproject.toml` (ÄNDERUNG: `exchange_calendars` im Extra `ibkr`) | config | - | Extra `ibkr` (Zeilen 42-50) | exact |
| `scripts/IBKR_EXECUTION.md` (ÄNDERUNG: Exit 5 aktiv, Zustandstabelle, `preview`) | doc | - | bestehendes Handbuch, gepinnt durch `tests/test_ibkr_isolation.py` | exact |
| `tests/ibkr_fakes.py` (ÄNDERUNG: `whatIfOrderAsync`, `reqAllOpenOrdersAsync`, `position(conId)`, Order-Fabrik) | test-helper | request-response | derselbe Datei: `FakeIB.qualifyContractsAsync`, `reqContractDetailsAsync`, `_forbidden` | exact |
| `tests/test_ibkr_decision.py` (NEU) | test | transform | `tests/test_ibkr_contracts.py` (reine Funktionen, injizierte Uhr) | role-match |
| `tests/test_ibkr_paperlog.py` (NEU) | test | file-I/O (Subprozess git) | `tests/test_ibkr_resolve.py` (tmp_path, Fabrik-Injektion) | role-match |
| `tests/test_ibkr_preview.py` (NEU) | test | request-response (E2E mit `FakeIB`) | `tests/test_ibkr_resolve.py` (`_run`, `_fake_factory`, `_fixed`) | exact |
| `tests/test_paper_summary_contract.py` (NEU) | test | transform (Erzeuger-Verbrauchervertrag) | `tests/test_daily_paper_run.py` (`_load_runner`, `_run_main`) | role-match |
| `tests/test_ibkr_broker.py` (ÄNDERUNG: Barrier-Tests, preview/open_orders/tif/halted) | test | request-response | derselbe Datei, Zeilen 69-170 (Barrier-Tests) | exact |
| `tests/test_ibkr_contracts.py` (ÄNDERUNG: `block_qty`, `session_day`) | test | transform | derselbe Datei | exact |
| `tests/test_ibkr_isolation.py` (ÄNDERUNG: Public-Methoden-Menge, Exit-5-Wächter, Library-Free-Wächter, no-market-data) | test (AST-/Text-Wächter) | static analysis | derselbe Datei | exact |

## Pattern-Zuweisungen

### `scripts/ibkr_decision.py` (service, transform) NEU

**Analog:** `scripts/ibkr_contracts.py`

**Modulkopf und Importe** (`ibkr_contracts.py` Zeilen 1-28): Docstring mit "Library-free", `from __future__ import annotations`, nur Standardbibliothek, `log = logging.getLogger(__name__)`. Der Wächter `test_resolver_is_library_free` (`test_ibkr_isolation.py:239-243`) verbietet `ib_async` und `tradingagents` auf Top-Level; bei Ausdehnung auf `ibkr_decision.py` also **kein** `tradingagents`-Import. Geparste Einträge (`list[dict]`) kommen vom Executor (RESEARCH §Struktur). `exchange_calendars`/`pandas` werden injiziert (Kalender als Parameter) oder lazy importiert.
```python
from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from types import MappingProxyType

log = logging.getLogger(__name__)
```

**Benannte Zustände als Modulkonstanten** (`ibkr_contracts.py` Zeilen 47-65): jeder Grund ist ein String-Konstante, plus eine `frozenset` der ablehnenden Zustände. In Phase 4 analog: `SKIPPED_HOLD = "skipped-hold"`, `RATING_REVIEW_STATE = "rating-review"`, `RUN_NOT_OK = "run-not-ok"`, `SIGNAL_DIVERGENCE`, `STALE_DECISION`, `FOREIGN_OPEN_ORDER`, `WITHIN_TOLERANCE`, `LONG_ONLY_NOOP`, `PREVIEW_EMPTY`, `PREVIEW_REJECTED`, `OVER_BUDGET`, `HALTED` (bereits in `ibkr_contracts.py:60` als "never set in phase 3"; wiederverwenden, nicht neu definieren), `PAPER_LOG_UNAVAILABLE`, `CALENDAR_CONFLICT`, `SUMMARY_MISSING`, `NO_DECISION`. Dazu eine einzige Tabelle `EXIT_BY_STATE` (RESEARCH Pitfall 8).
```python
OK = "ok"
NOT_TRADABLE = "not-tradable"
CLOSED = "closed"
SESSION_UNKNOWN = "session-unknown"
HALTED = "halted"
REJECTED_STATES = frozenset({NOT_MAPPED, NOT_ALLOWED, ..., HALTED})
```

**Frozen-Dataclass-Ergebniswerte** (`ibkr_contracts.py` Zeilen 100-107, 567-591): `@dataclass(frozen=True)` mit `state`, `detail`, und `@property rejected`. Für `Plan`, `Freshness`, `PreviewVerdict`, `DecisionResult` kopieren.
```python
@dataclass(frozen=True)
class ResolveResult:
    ticker: str
    state: str
    detail: str
    identity: Identity | None = None
    ...
    @property
    def rejected(self) -> bool:
        return self.state in REJECTED_STATES
```

**Uhr nur als Parameter** (`evaluate_session`, `ibkr_contracts.py:270-288`, Wächter `test_resolver_takes_the_clock_as_a_parameter` Zeilen 273-277): `datetime.now`, `time.time(`, `date.today` dürfen im Fachmodul nicht vorkommen; naive `now_utc` wird mit `ValueError` abgewiesen.
```python
def evaluate_session(liquid_hours, time_zone_id, now_utc, buffer_minutes=SESSION_BUFFER_MINUTES):
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must carry a time zone")
```

**Keine Uhrzeit-Literale** (`test_no_hard_coded_trading_times_in_execution_code`, `test_ibkr_isolation.py:256-270`): `13:30`, `14:30`, `09:30`, `16:00` dürfen in keiner `scripts/ibkr_*.py` stehen, auch nicht in Docstrings oder Kommentaren von `ibkr_decision.py`.

**Zielrechnung / Aktualität / Konsumentenvertrag:** Es gibt kein Code-Analog für den Inhalt; die Skizzen aus RESEARCH Muster 4, 5 und "Konsumentenvertrag" sind die Vorlage (`execution_session`, `freshness`, `plan_order`, `SUMMARY_FIELDS`, `RUN_FIELDS`, `read_summary`). Strukturell nach `ibkr_contracts.py`: reine Funktionen, Frozen-Werte, Detailtext je Zustand.

**Quellen für den Vertrag (Erzeugerseite, nicht ändern):**
- `scripts/daily_paper_run.py:46` `SUMMARY_SCHEMA_VERSION = 1`
- `daily_paper_run.py:354-375` Run-Record: `ticker`, `status`, `signal`, `report` (nicht lesen, REQ-18)
- `daily_paper_run.py:508-520` Summary-Kopf: `schema_version`, `trade_date`, `status`
- `daily_paper_run.py:115-123` `previous_weekday` kennt keine Feiertage (Aktualitätsregel muss das berücksichtigen)
- `tradingagents/agents/rating.py:22-24` `RATINGS_5_TIER`, `:30` `RATING_REVIEW = "REVIEW"`, `:115` `is_review`

---

### `scripts/ibkr_broker.py` (adapter, request-response) ÄNDERUNG

**Analog:** dieselbe Datei.

#### A) Schreibsperre "Id 3 nur mit `whatIf`" (D-13)

**Ist-Zustand** (`ibkr_broker.py:58, 66, 261-301`): `_WRITE_CALLS` ersetzt vier Clientmethoden durch `refuse`; `guarded_send`/`guarded_send_msg` prüfen `_message_id(...) in _WRITE_MESSAGE_IDS`. Umbau-Stelle:
```python
_WRITE_CALLS = ("placeOrder", "cancelOrder", "reqGlobalCancel", "exerciseOptions")
_WRITE_MESSAGE_IDS = frozenset({3, 4, 19, 21, 58})

for name in _WRITE_CALLS:
    def refuse(*_args, _name=name, **_kwargs):
        raise ReadOnlyViolation(
            f"read-only session: {_name} refused before it reached the gateway"
        )
    setattr(client, name, refuse)

original_send = client.send
original_send_msg = client.sendMsg

def guarded_send(*fields, **kwargs):
    msg_id = _message_id(fields[0]) if fields else None
    if msg_id in _WRITE_MESSAGE_IDS:
        refuse_message(msg_id)
    return original_send(*fields, **kwargs)

def guarded_send_msg(msg, *args, **kwargs):
    head = msg.split("\0", 1)[0] if isinstance(msg, str) else None
    msg_id = _message_id(head) if head else None
    if msg_id in _WRITE_MESSAGE_IDS:
        refuse_message(msg_id)
    return original_send_msg(msg, *args, **kwargs)

client.send = guarded_send
client.sendMsg = guarded_send_msg
```
Umbau: `placeOrder` aus `_WRITE_CALLS` nehmen und stattdessen `original_place = client.placeOrder` merken und durch einen Wächter ersetzen, der nur bei `getattr(order, "whatIf", None) is True` an `original_place` weiterreicht (sonst `ReadOnlyViolation`). In `guarded_send` und `guarded_send_msg` gilt Id 3 nur mit gesetztem `whatIf`-Feld (Layout-Prüfung `_whatif_in_fields`, fail-closed bei unbekanntem Layout; Skizze RESEARCH Muster 1). Ids 4/19/21/58 bleiben unverändert hart gesperrt. `_message_id` (Zeilen 251-258) wiederverwenden. Die Kommentare an `_WRITE_MESSAGE_IDS` und `INFO_CODES` (Zeilen 60-66, 100-103: "The halt code 154 stays unmapped here; it is measured at the whatIf preview in phase 4") mitziehen.

**Falle:** `test_adapter_hard_codes_no_order_id` (`test_ibkr_isolation.py:131-135`) verbietet `orderId=` und `.orderId =` im Adaptertext; Parameter `order_id` verwenden, kein Keyword `orderId=`.

#### B) `preview_order` und `open_orders` (neue Lesemethoden)

**Analog:** `search_contract` und `contract_details` (`ibkr_broker.py:583-628`): innere Funktion `ask()` baut ein frisches Objekt über `self._handles.contract(...)`, die Bibliotheks-Coroutine läuft über `self._read(name, ask)`, Rückgabe in broker-neutralen Frozen-Dataclasses.
```python
def contract_details(self, con_id: int, exchange: str) -> tuple[ContractInfo, ...]:
    def ask():
        contract = self._handles.contract(conId=con_id, exchange=exchange)
        return self._ib.reqContractDetailsAsync(contract)

    rows = self._read("reqContractDetails", ask)
    return tuple(_info_from_contract(d.contract, d) for d in rows)
```

**Fail-closed-Lesefenster** (`_read`, `ibkr_broker.py:630-654`): kein offener Link vorher (`_open_link`), `mark = len(self._link_codes)` und `code_mark = len(self._request_errors)`, nach der Antwort Link-Ereignis verwerfen (`_link_event_since`) und Request-Fehler abbilden. `preview_order` darf `_read` **nicht** unverändert nutzen, weil 154/10349/321 dort als generisches `REQUEST_FAILED` enden würden; es kopiert das Fenster (Marken setzen, `_request`, Link-Check) und wertet Fehlercodes selbst aus (RESEARCH Muster 2, Reihenfolge 154, 10349, Timeout+321, leer, Link). `_request_error_since` (Zeilen 656-665) und `STATE_BY_CODE` (Zeilen 71-98) um 154 (`HALTED`) und 10349 (`TIF_OVERRIDDEN`) erweitern; beide aus `_request_error_since` heraushalten.
```python
mark = len(self._link_codes)
code_mark = len(self._request_errors)
result = self._request(name, make_awaitable)
event = self._link_event_since(mark)
if event is not None:
    state, code = event
    raise GatewayUnavailable(state, code, f"link event {code} while {name} was in flight; answer discarded")
```

**Request-Fehlertexte:** `_on_error` (Zeilen 714-731) speichert nur Codes (`_seen_codes`, `_request_errors`). Für den "Ablehnungsgrund" (RESEARCH Pitfall 1: `OrderState` hat kein `rejectReason`) braucht es eine parallele Textliste `(code, errorString)` für `reqId >= 0`; dieselbe Stelle erweitern:
```python
self._seen_codes.append(errorCode)
if isinstance(reqId, int) and reqId >= 0:
    self._request_errors.append(errorCode)
```

**`IbHandles` erweitern** (Zeilen 150-156): neues Feld `order: Any = None` mit Default, damit bestehende Fakes (`make_handles` in `tests/ibkr_fakes.py:302-309`) weiterlaufen. `_default_ib_factory` (Zeilen 245-248) importiert `Order` aus `ib_async` an derselben einzigen Importstelle.
```python
@dataclass(frozen=True)
class IbHandles:
    ib: Any
    contract: Any
    fetch_none: Any
```

**`BrokerPosition` und `AccountSnapshot`** (Zeilen 159-168, 225-233, `positions()` Zeilen 551-581): `con_id: int` ergänzen (`p.contract.conId`); `available_funds`/`available_funds_currency` aus der `AvailableFunds`-Zeile, nach dem Muster der `TotalCashValue`-Prüfung "genau eine Zeile, sonst `SNAPSHOT_INCOMPLETE`":
```python
cash_rows = [v for v in mine if v.tag == "TotalCashValue"]
if len(cash_rows) != 1:
    raise GatewayUnavailable(SNAPSHOT_INCOMPLETE, None,
        f"expected one TotalCashValue row for {EXPECTED_ACCOUNT}, got {len(cash_rows)}")
...
for v in mine:
    if v.tag in ("AvailableFunds", "NetLiquidation"):
        self._log.info("ibkr-account %s=%s %s (log only)", v.tag, v.value, v.currency)
```
(die "log only"-Schleife wird für `AvailableFunds` zur echten Auswertung).

**Öffentliche Methoden:** `test_adapter_has_at_most_ten_public_methods` (`test_ibkr_isolation.py:118-128`) pinnt die Menge exakt; auf `{connect, positions, health, search_contract, contract_details, preview_order, open_orders}` anheben (7 <= 10).

---

### `scripts/ibkr_contracts.py` (model, transform) ÄNDERUNG

**Analog:** dieselbe Datei.

**`block_qty` je Eintrag** (`ContractSpec` Zeilen 71-85, `CONTRACT_TABLE` Zeilen 88-97): Feld an `ContractSpec` ergänzen (Default `0` für nicht handelbare Einträge `^GSPC`/`XAUUSD+`, die `ContractSpec(...)` direkt positionell bauen) und `_stock()` um `block_qty=1` (D-10) erweitern. Test: jeder Eintrag, der `classify(...).state == OK` liefert, hat `block_qty > 0`.
```python
@dataclass(frozen=True)
class ContractSpec:
    symbol: str
    sec_type: str
    exchange: str
    currency: str
    primary_exchange: str

def _stock(ticker: str) -> ContractSpec:
    return ContractSpec(ticker, "STK", SMART, "USD", "NASDAQ")
```

**`session_day` für den Kalenderabgleich (D-05):** `SessionVerdict` (Zeilen 210-215) und `ResolveResult` (Zeilen 567-580) um `session_day: bool | None` erweitern. Die Information liegt in `evaluate_session` (Zeilen 296-316) bereits vor (`parsed.closed_dates`, Fenster des heutigen Tages, `covered`). Bestehende Zweige unverändert lassen, nur das Feld setzen (heute hat Fenster: True; heute `:CLOSED`: False; kein Eintrag: None).
```python
zone = ZoneInfo(time_zone_id)
today = now_utc.astimezone(zone).date()
covered = today in parsed.closed_dates or any(
    w.start.date() <= today <= w.end.date() for w in parsed.windows
)
```
Der Docstring von `resolve_all` (Zeile 660: "Phase 4 calls this function directly (D-30)") bestätigt die Einbindung: Aufruf mit `broker=broker`, `contracts=...`, `now_utc`, `logger`, `mode=MODE_RUN`.

**Pitfall 9 (Lernmodus):** `resolve_all` lernt im `MODE_RUN` fehlende Ticker. Executor prüft vorher `ticker in contracts` (siehe `run_resolve`, Zeilen 449-477, für Laden und Fehlerabbildung).

---

### `scripts/ibkr_executor.py` (controller, request-response + file-I/O) ÄNDERUNG

**Analog:** dieselbe Datei, Familie `account`/`resolve`.

**Importe** (Zeilen 46-58): `argparse`, `importlib.util`, `json`, `logging`, `os`, `sys`, `uuid`, `datetime`, `Path`, `dotenv_values`, `tradingagents.portfolio`. Neu: `subprocess`, `tradingagents.memory.TradingMemoryLog` (der Executor darf `tradingagents` importieren, das Fachmodul nicht), `scripts/state_maintenance` (über `importlib.util` wie `load_broker_module`/`load_contracts_module`, Zeilen 108-144; ein dritter Lader `load_decision_module()` nach demselben Muster: in `sys.modules` registrieren vor `exec_module`, bei Fehler wieder entfernen).
```python
def load_contracts_module():
    if "ibkr_contracts" in sys.modules:
        return sys.modules["ibkr_contracts"]
    spec = importlib.util.spec_from_file_location("ibkr_contracts", _CONTRACTS_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ibkr_contracts"] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop("ibkr_contracts", None)
        raise
    return module
```

**Exit-Konstanten** (Zeilen 60-69): `EXIT_REJECTED = 5` existiert; nur Modul-Docstring (Zeilen 31-41, "5 order rejected (reserved for later phases)") und Handbuch auf "aktiv" umstellen. Nicht mehr als die 10 vorhandenen `EXIT_*` anlegen (`test_handbook_exit_table_matches_executor` erwartet exakt 10).

**Settings** (`read_settings`, Zeilen 168-184, `REQUIRED_ENV` Zeile 73): `wanted = (*REQUIRED_ENV, TRADING_MODE_ENV)` filtert nur diese Schlüssel. Für `IBKR_PAPER_LOG_REMOTE` (Default `fork`) und `IBKR_PAPER_LOG_BRANCH` (Default `paper-log`) einen optionalen Tupel `OPTIONAL_ENV` ergänzen, ohne `missing` zu beeinflussen; Werte per Whitelist validieren (`[A-Za-z0-9._/-]`, kein führendes `-`), Fehler als `ConfigError` (Zeilen 187-207 sind das Validierungsmuster).
```python
wanted = (*REQUIRED_ENV, TRADING_MODE_ENV)
settings = {key: values[key].strip() for key in wanted if isinstance(values.get(key), str)}
missing = [key for key in REQUIRED_ENV if not settings.get(key)]
```

**Default-Pfad unter `%LOCALAPPDATA%`** (Zeilen 147-162): für Kopie `decision-log.copy.md` und Trockenlauf-JSON dasselbe Muster (`LOCALAPPDATA` oder `Path.home()/".tradingenginex"/"ibkr"`), z. B. `default_preview_file(environ=None)`.

**Subkommando-Struktur** (`run_resolve` 406-570, `_resolve` 767-792, `build_parser` 606-626, `main` 629-673): Muster für `preview`:
1. `build_parser`: `sub.add_parser("preview", ...)`, `tickers` als `nargs="*"`, `--out`, `--log-file`, `--env-file`; **kein** `--trade-date` (D-07). Zeile 640 (`needs a subcommand: account, resolve`) um `preview` ergänzen.
2. `main`: wie bei `resolve` Pflichtpositionals prüfen ("needs at least one TICKER (no default list)", Zeilen 645-649), `clock = clock or (lambda: datetime.now(UTC))` (Zeile 636), Dispatch in `try/finally: close_logging()`.
3. `_preview(args, broker_factory, logger, clock)` ist eine Kopie von `_resolve` (Zeilen 767-792): Module laden, Default-`broker_factory`, `progress = {"connecting": False, "connected": False}`, `_guarded(...)` mit `"preview output"`.
4. `run_preview(...)`: wie `run_resolve` zuerst alles Lokale ohne Gateway (Hold muss ohne Gateway laufen, SC1), dann `adapter = broker_factory(host, port, logger)`, `progress["connecting"] = True`, `with adapter as broker:`, `progress["connected"] = True`, `broker.health()`-Check, danach Fachketten.
```python
adapter = broker_factory(host, port, logger)
progress["connecting"] = True
with adapter as broker:
    progress["connected"] = True
    health = broker.health()
    if not health.ok:
        line = f'ibkr-state={health.state} code=- detail="{health.detail}"'
        logger.error(line)
        print(f"error: {line}", file=sys.stderr)
        return EXIT_GATEWAY
    outcome = contracts_mod.resolve_all(args.tickers, broker=broker, **common)
```

**Fehlerabbildung `_guarded`** (Zeilen 689-728): unverändert wiederverwenden; `ReadOnlyViolation` bleibt `WRITE_REFUSED`/Exit 3 und darf von `preview` nie verschluckt werden (Pitfall 7).
```python
except broker_mod.ReadOnlyViolation as exc:
    line = f'ibkr-state=WRITE_REFUSED code=- detail="{exc}"'
    return _fail(logger, EXIT_GATEWAY, line, line)
```

**Frühe Fehler mit `_fail`** (Zeilen 255-258, Nutzung 421-437): `_fail(logger, EXIT_PRECONDITION, "ibkr-state=...", "console text")`. Für `paper-log-unavailable`, `summary-missing`, `state-log-finding`.

**Konsolenzeile je Ticker + Logzeile** (`_result_line` 388-403, Schleife 548-561): `print(f"preview: {ticker} {state} ...")` und `logger.log(level, "ibkr-state=%s ticker=%s state=%s detail=%r ...")`. SHA (D-04) in Logzeile und JSON.
```python
state = "RESOLVED" if not result.rejected else "RESOLVE_REJECTED"
logger.log(
    logging.WARNING if result.rejected else logging.INFO,
    "ibkr-state=%s ticker=%s state=%s detail=%r tradingClass=%s longName=%s",
    state, result.ticker, result.state, result.detail, result.trading_class, result.long_name,
)
```

**Protokoll-JSON atomar** (`_resolve_payload` 577-600, Schreiben 563-569): Payload mit `schema_version`, `as_of`, `rows`; Schreiben über `contracts_mod.write_json_atomic(out, payload)` mit `OSError` -> `OutputError`. Vorher `_discard_previous(out, logger)` (Zeilen 676-686, 416-427). **Kein Ledger.**
```python
if args.out is not None:
    payload = _resolve_payload(outcome, contracts_mod, now_utc)
    try:
        contracts_mod.write_json_atomic(out, payload)
    except OSError as exc:
        raise OutputError(f"{out}: {type(exc).__name__}: {exc}") from exc
```

**Exit-Mapping bei mehreren Tickern** (`return EXIT_PRECONDITION if outcome.rejected else EXIT_OK`, Zeile 570): alle Ticker verarbeiten, dann schwerster Code aus der Tabelle `EXIT_BY_STATE` (5 vor 2, 0 sonst).

**Git-Zugriff (neu, kein exaktes Analog):** `subprocess.run` mit injizierbarem Runner, Listenform, `GIT_TERMINAL_PROMPT=0`, Timeout, Bytes statt Text lesen, UTF-8 strict selbst dekodieren (RESEARCH Muster 6). `git show <sha>:<pfad>` mit `--` bzw. validierten Argumenten; `trade_date` strikt `YYYY-MM-DD` validieren, bevor ein Pfad `runs/<date>/summary.json` gebaut wird.

**Verify mit Kopie** (`scripts/state_maintenance.py:141-205`): `check_decision_log(path)` liest per `Path` und zählt Blöcke gegen `TradingMemoryLog.load_entries()`; `verify(cache_dir, memory_log)` prüft zusätzlich Checkpoint-DBs unter `<cache_dir>/checkpoints` (Pitfall 4). Daher `check_decision_log(kopie)` direkt aufrufen (oder `verify` mit leerem Temp-`cache_dir`) und das Fehlen/Leersein der Datei selbst als Befund werten.
```python
blocks = [block for block in text.split(TradingMemoryLog._SEPARATOR) if block.strip()]
entries = TradingMemoryLog({"memory_log_path": str(path)}).load_entries()
if len(entries) != len(blocks):
    return (f"only {len(entries)}/{len(blocks)} blocks parsed as entries ...")
```

**Log-Parser** (`tradingagents/memory/log.py:76-86, 310-337`): `TradingMemoryLog({"memory_log_path": str(kopie)}).load_entries()` liefert Dicts mit `date`, `ticker`, `rating`, `pending`; "neuester Eintrag je Ticker" ist der letzte Treffer in Dateireihenfolge (Datei ist append-only; `get_past_context` iteriert mit `reversed(entries)`, Zeilen 111-119).

---

### `pyproject.toml` (config) ÄNDERUNG

**Analog:** Extra `ibkr`, Zeilen 42-50. Neue Abhängigkeit in dieselbe Liste, mit Kommentar zum Grund (D-05), Format wie die vorhandenen Einträge:
```toml
ibkr = [
    # Pinned exactly: single maintainer, ... scripts/ibkr_broker.py is the only module that imports it.
    "ib_async==2.1.0",
    "tzdata>=2025.2,<2026.0",
]
```
Der Wächter `test_ibkr_extra_pins_the_client_library_exactly` (`test_ibkr_isolation.py:21-27`) bleibt grün, solange `ib_async==2.1.0` und `tzdata>=2025.2,<2026.0` unverändert bleiben und `ib_async` nicht in den Kerndependencies steht. Neuer Eintrag: `"exchange_calendars>=4.13,<5"`. `test_tzdata_cap_carries_its_reason` (Zeilen 30-35) verlangt den Kommentar zum tzdata-Deckel; nicht entfernen. Vor Install `checkpoint:human-verify` (RESEARCH Package Legitimacy).

---

### `tests/ibkr_fakes.py` (test-helper) ÄNDERUNG

**Analog:** dieselbe Datei.

**Neue gesteuerte Coroutinen** nach dem Muster von `qualifyContractsAsync`/`reqContractDetailsAsync` (Zeilen 234-274): `self.calls.append(...)`, `self._emit_during(name)`, `"hang"`-Zweig über `await _forever()`, Rückgabe einer Liste. Für `whatIfOrderAsync(contract, order)` (Antwort steuerbar: `OrderState`-Namespace, `[]`, `"hang"`, Fehler-Emission 154/10349/321 über `emit_during["whatif"]`) und `reqAllOpenOrdersAsync()`.
```python
async def reqContractDetailsAsync(self, contract):
    ...
    self.calls.append("contract_details")
    self.details_calls = [*getattr(self, "details_calls", []), copy.copy(contract)]
    self._emit_during("contract_details")
    if self.details == "hang":
        await _forever()
    return list(self.details.get(contract.conId, []))
```

**Verbotsliste anpassen** (Zeilen 276-299): `reqAllOpenOrders`, `whatIfOrder`, `placeOrder` sind heute `_forbidden` (zeichnen den Namen auf und werfen `AssertionError`). `placeOrder` und `whatIfOrder` (blockierend) bleiben verboten (G2: `FakeIB.calls` darf nie `placeOrder` enthalten); nur die Async-Varianten werden steuerbar. `FORBIDDEN_CALLS = (*ibkr_fakes.WRITE_CALLS, "whatIfOrder")` in `tests/test_ibkr_broker.py:33` bleibt gültig. Reservierte Marktdaten-Falle für REQ-68: `reqMktData` als `_forbidden` ergänzen.

**Fixtures:** `position(account, symbol, quantity, avg_cost=100.0, **contract)` (Zeilen 115-122) nimmt `conId` bereits über `**contract` an (`FakeContract.conId`); `stk_contract` (Zeilen 70-90) für Aufruferseite. `account_value(tag, value, currency="EUR", account=...)` (Zeilen 125-127) für `AvailableFunds`. Order-Fabrik: `broker.IbHandles(ib=fake, contract=FakeContract, fetch_none=0, order=FakeOrder)` in `make_handles` (Zeilen 302-309); `FakeOrder` als Dataclass mit `action`, `totalQuantity`, `orderType`, `tif`, `account`, `whatIf` analog `FakeContract` (Zeilen 58-67).
Barrier-Erkennung: `self._recorders` und `barrier_armed_at_connect` (Zeilen 170-185) prüfen, ob `client.<name>` ersetzt wurde; wenn `placeOrder` künftig durch einen Wächter statt `refuse` ersetzt wird, bleibt `is not recorder` gültig.

---

### `tests/test_ibkr_broker.py` (test) ÄNDERUNG

**Analog:** dieselbe Datei, Zeilen 69-170.

**Zu ändernde Tests:** `test_write_barrier_is_armed_before_connect` (Zeilen 69-76) ruft `getattr(fake.client, name)()` für alle `WRITE_CALLS` und erwartet `ReadOnlyViolation`: für `placeOrder` ohne `whatIf` bleibt das richtig (Wächter wirft), aber `getattr(...)()` ohne Argumente ist dann ein `TypeError`; Wächter mit `*args` und Prüfung robust bauen oder den Test für `placeOrder` mit einem Order-Objekt ohne `whatIf` aufrufen. `test_write_barrier_on_the_real_client_object` (Zeilen 115-124) auf Order mit `whatIf=False` -> `ReadOnlyViolation`; zusätzlich neuer Test mit `whatIf=True` (geht durch). `WRITE_MESSAGE_IDS`-Parametrisierung (Zeilen 127-141, `(3, 4, 19, 21, 58)`): Id 3 nur noch ohne `whatIf`-Feld parametrisiert; neue Tests mit **echter** `ib_async.client.Client`-Klasse und einer Stub-Verbindung, die `sendMsg`-Bytes mitschreibt (RESEARCH Muster 1, Test).
```python
def test_write_barrier_on_the_real_client_object():
    ib_async = pytest.importorskip("ib_async")
    ib = ib_async.IB()
    broker._arm_write_barrier(ib.client)
    order = ib_async.Order(orderId=1, action="BUY", totalQuantity=1, orderType="MKT")
    with pytest.raises(broker.ReadOnlyViolation):
        ib.placeOrder(ib_async.Contract(conId=265598), order)
```
(Hinweis: diese Zeile enthält `orderId=1` im Testtext; der Wächter `test_adapter_hard_codes_no_order_id` prüft nur `ADAPTER`, nicht die Tests.)

**Neue Tests** im Stil der bestehenden Fabriken: Hilfsfunktionen `_broker(fake, loop, ...)`/`_connected(fake, loop)` (am Dateianfang, Zeilen 33-60) wiederverwenden; Kurz-Timeouts `request_timeout=0.05` wie in `_fake_factory` (`test_ibkr_resolve.py:84-96`).

---

### `tests/test_ibkr_preview.py` (test, E2E gegen `FakeIB`) NEU

**Analog:** `tests/test_ibkr_resolve.py`

**Kopf und Lader** (Zeilen 1-62): Modul-Docstring ("against fakes only"), `pytestmark = pytest.mark.unit`, `_load_executor()` über `spec_from_file_location`, `executor.load_broker_module()`/`load_contracts_module()`, `DEFAULT_ENV`, injizierte Konstanten `OPEN_NOW`/`CLOSED_NOW` (als UTC-`datetime`), `CON_IDS`.
```python
pytestmark = pytest.mark.unit
_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ibkr_executor.py"

def _load_executor():
    spec = importlib.util.spec_from_file_location("ibkr_executor", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
executor = _load_executor()
broker = executor.load_broker_module()
contracts_mod = executor.load_contracts_module()
```

**Fixtures:** `loop` (session-scope, `ibkr_fakes.session_loop()`), `_block_real_connect` (autouse, `ibkr_fakes.block_real_ib_connect`), `_close_logging` (autouse, `executor.close_logging()` nach dem Test) (Zeilen 51-62).

**Fabriken:** `_env_file(tmp_path, **values)`, `_RecordingFactory` ("must never be called", für SC1/Hold ohne Gateway), `_fake_factory(fake, loop)`, `_fixed(moment)`, `_run(...)` (Zeilen 64-125). Für `preview`: `_run` um injizierte Quellen erweitern (Runner für git / Pfad zur eingefrorenen Kopie von `decision-log.md` + `summary.json`, Kalender, Uhr); Kopie liegt als Fixture im Repo (Commit `71df89d`, `runs/2026-10-09/summary.json`).
```python
def _run(tmp_path, factory, tickers, *, extra=(), env_file=None, contracts=None, clock=OPEN_NOW):
    ...
    code = executor.main(argv, broker_factory=factory, clock=_fixed(clock))
    executor.close_logging()
    return code, contracts, log
```
Assertions: Exit-Code, Konsolenzeile (`capsys`), Logtext (`_log_text(log)`), `fake.calls` (nie `placeOrder`/`cancelOrder`/`whatIfOrder`, G2 "nothing_sent"), JSON-Inhalt.

---

### `tests/test_ibkr_decision.py` (test, transform) NEU

**Analog:** `tests/test_ibkr_contracts.py` (reine Funktionen, Parametrisierung, injizierte Uhr); Zeitwerte wie in `test_ibkr_resolve.py:42-48` (`datetime(..., tzinfo=UTC)`). Kalender real (`exchange_calendars.get_calendar("XNYS")`, Pflicht-Install oder `pytest.importorskip`). Vier Gegenproben aus RESEARCH Muster 4 plus Feiertagsmontag `2026-09-07`.

---

### `tests/test_ibkr_paperlog.py` (test, Subprozess-I/O) NEU

**Analog:** `tests/test_ibkr_resolve.py` (tmp_path, Injektion statt echtem Netz). `tests/conftest.py` blockt nur Python-Sockets, nicht Git-Subprozesse; daher ist der injizierbare Runner (`run=subprocess.run`) Pflicht. Tests: fetch scheitert -> `paper-log-unavailable` ohne Rückfall, SHA in Logzeile/JSON und nicht im `decision_key`, `GIT_TERMINAL_PROMPT=0`, Timeout -> `paper-log-unavailable`, Bytes werden strikt UTF-8 dekodiert.

---

### `tests/test_paper_summary_contract.py` (test, Erzeuger-Verbrauchervertrag) NEU

**Analog:** `tests/test_daily_paper_run.py`

**Lader und Helfer** (Zeilen 20-40, 289-300): `_load_runner()` lädt `scripts/daily_paper_run.py` über `spec_from_file_location`; `_run_main(monkeypatch, tmp_path, graph, extra_args=())` patcht `tradingagents.graph.trading_graph.TradingAgentsGraph` und ruft `main(argv)` mit `--tickers AAPL --date 2026-08-20 --max-cost 1.0 --rates ... --out ... --state ...`. Die echte `summary.json` lesen und durch `ibkr_decision.read_summary` schicken; Negativ-Kontrolle: Feld entfernt/umbenannt/Typ geändert -> `SummaryContractError`; Zusatzfeld bleibt grün; `report` wird nicht gelesen.
```python
_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "daily_paper_run.py"

def _load_runner():
    spec = importlib.util.spec_from_file_location("daily_paper_run", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
runner = _load_runner()
```
Rundlauf `TradingMemoryLog.store_decision(...)` in eine Temp-Datei, danach `load_entries()`.

---

### `tests/test_ibkr_isolation.py` (test, statische Wächter) ÄNDERUNG

**Analog:** dieselbe Datei.

Konkrete Anpassungen:
- Zeile 128: `public == {"connect", "positions", "health", "search_contract", "contract_details", "preview_order", "open_orders"}`.
- Zeile 180: `len(codes) == 10` bleibt (keine neue `EXIT_*`-Konstante).
- Neu `test_handbook_exit_five_is_active` nach dem Muster von `test_handbook_exit_two_is_active` (Zeilen 200-208): Zeile `| 5 | \`EXIT_REJECTED\` |` genau einmal, ohne "reserved".
- `test_resolver_is_library_free` (Zeilen 239-243) um `ibkr_decision.py` ergänzen; `test_no_hard_coded_trading_times_in_execution_code` (Zeilen 256-270) globbt `scripts/ibkr_*.py` und deckt das neue Modul automatisch ab; `test_resolver_takes_the_clock_as_a_parameter` (Zeilen 273-277) für `ibkr_decision.py` duplizieren.
- Neu `test_no_market_data_in_execution_path` (REQ-68): AST-/Text-Suche nach `reqMktData`/`reqTickers`/`ticker(` in Executor und Adapter.
- `test_handbook_does_not_name_the_client_library` (Zeilen 166-168): `ib_async` darf im Handbuch weiterhin nicht vorkommen.
- `test_handbook_documents_resolve` (Zeilen 185-197) als Muster für `test_handbook_documents_preview` (Nadeln: `preview`, `skipped-hold`, `stale-decision`, `over-budget`, `halted`, `paper-log-unavailable`, `IBKR_PAPER_LOG_REMOTE`).

---

### `scripts/IBKR_EXECUTION.md` (doc) ÄNDERUNG

**Analog:** bestehendes Handbuch, durch Wächter gepinnt (Exit-Tabelle als `| <code> | \`EXIT_X\` |`-Zeilen; Client-ID 20001 muss vorkommen; `ib_async` darf nicht vorkommen; Paper-Run-Befehl mit `--out`/`--state`). Neue Abschnitte: `preview`-Aufruf, Zustandstabelle der Phase 4 (je Zustand Exit-Code), Settings `IBKR_PAPER_LOG_REMOTE`/`_BRANCH`, Exit 5 aktiv.

---

## Geteilte Muster

### Atomares Schreiben und Pfade unter `%LOCALAPPDATA%`
**Quelle:** `scripts/ibkr_contracts.py:434-457` (`write_json_atomic`, `_temp_for`), `scripts/ibkr_executor.py:147-162` (`default_contracts_file`, `default_log_file`)
**Anwenden auf:** Trockenlauf-JSON, Kopie von `decision-log.md`
Nur `write_json_atomic(path, payload)` verwenden, nie eigene Schreiblogik (RESEARCH "Nicht selbst bauen").

### Benannter Zustand statt Ausnahme, eine Zeile pro Ticker
**Quelle:** `scripts/ibkr_contracts.py:47-65` (Zustandskonstanten, `REJECTED_STATES`), `scripts/ibkr_executor.py:388-403, 548-561` (`_result_line`, Logzeile `ibkr-state=...`)
**Anwenden auf:** alle neuen Ablehnungs- und Überspringgründe; Logformat `ibkr-state=<STATE> ticker=%s state=%s detail=%r`.

### Fehlerabbildung auf Exit-Codes
**Quelle:** `scripts/ibkr_executor.py:255-258` (`_fail`), `689-728` (`_guarded`)
**Anwenden auf:** `_preview`; Exit-Semantik aus D-16: Vorbedingungen 2, Ablehnungen am `whatIf` 5, `schema_version != 1` 1, Gateway/Sperre 3, Guard 8.
```python
def _fail(logger, code, log_line, console):
    logger.error(log_line)
    print(f"error: {console}", file=sys.stderr)
    return code
```

### Injizierte Abhängigkeiten (Uhr, Broker, Runner, Kalender)
**Quelle:** `ibkr_executor.main(argv, *, broker_factory=None, clock=None)` (Zeile 629), `resolve_all(..., broker, now_utc, logger)` (Zeile 643), Tests: `_fixed(moment)`, `_fake_factory(fake, loop)`
**Anwenden auf:** `preview` (zusätzlich `git_runner`, `calendar`); Fachmodul bekommt `now_utc` und Kalender als Parameter, nie eine eigene Uhr.

### Fail-closed Lesefenster mit Link-Ereignissen
**Quelle:** `scripts/ibkr_broker.py:630-665` (`_read`, `_request_error_since`), `667-678` (`_request`), `714-731` (`_on_error`)
**Anwenden auf:** `preview_order`, `open_orders`

### Test-Hygiene für IBKR-Tests
**Quelle:** `tests/test_ibkr_resolve.py:51-62`, `tests/ibkr_fakes.py:321-333` (`block_real_ib_connect`)
**Anwenden auf:** jede neue Testdatei, die `executor.main` oder `IbkrBroker` nutzt: `loop`-Fixture, autouse `block_real_ib_connect`, autouse `close_logging`.

### Kommandos der Umgebung
`.venv/Scripts/python.exe -m pytest ...` und `.venv/Scripts/python.exe -m ruff check scripts tests` (kein `uv run`, SSL-Problem; `python` im PATH ist 3.10 und nicht zu verwenden).

## Kein Analog gefunden

Teilmuster ohne Vorbild im Repo; Planer nutzt RESEARCH.md:

| Teilmuster | Rolle | Datenfluss | Grund / Quelle |
|------------|-------|------------|----------------|
| Wire-Level-Prüfung des `whatIf`-Feldes in `send`/`sendMsg` (`_whatif_in_fields`) | middleware | request-response | Bestehende Sperre prüft nur die Nachrichten-Id; Layout aus `ib_async` 2.1.0 `client.py:472-707` (RESEARCH Muster 1) |
| `git fetch` / `git show` mit injizierbarem Runner | utility | file-I/O (Subprozess) | Kein `subprocess`-Aufruf in `scripts/ibkr_*.py`; nur `tests/test_ibkr_isolation.py:42` nutzt `subprocess` (Test); Skizze RESEARCH Muster 6 |
| XNYS-Kalender / Aktualität (`execution_session`, `freshness`) | service | transform | Neue Abhängigkeit `exchange_calendars`; Skizze RESEARCH Muster 4 |
| Zielrechnung `plan_order`, Toleranzband | service | transform | Neu; Skizze RESEARCH Muster 5 (Tabelle `{Buy:2, Overweight:1, Underweight:0, Sell:0}`, Hold zuerst abfangen) |
| Konsumentenvertrag `read_summary` (`SUMMARY_FIELDS`, `RUN_FIELDS`) | utility | transform | Erzeugerseite `daily_paper_run.py` vorhanden, Konsument neu; RESEARCH "Code-Beispiele" |
| `whatIf`-Ergebnisurteil `judge_preview` (Unset-Sentinel `1.797e308`, `warningText`) | service | transform | RESEARCH Pitfall 1/2 und "Fehlerprüfung am `whatIf`-Ergebnis" |

## Metadaten

**Analog-Suchbereich:** `scripts/ibkr_*.py`, `scripts/state_maintenance.py`, `scripts/daily_paper_run.py`, `tradingagents/memory/log.py`, `tradingagents/agents/rating.py`, `tests/ibkr_fakes.py`, `tests/test_ibkr_{broker,resolve,isolation}.py`, `tests/test_daily_paper_run.py`, `pyproject.toml`
**Gescannte Dateien:** 14 (Hauptdateien vollständig bzw. gezielt gelesen; `test_ibkr_contracts.py` und `test_ibkr_executor.py` nur per Größe und Dateinamen erfasst)
**Extraktionsdatum:** 2026-10-12
