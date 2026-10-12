# Phase 3: Symbol-Auflösung, Handelbarkeit und Handelszeiten - Pattern Map

**Mapped:** 2026-10-12
**Files analyzed:** 13 (3 neu im Code, 4 neu in Tests, 6 geändert)
**Analogs found:** 12 / 13 (1 Teil-Analog ohne Code-Vorbild: Sitzungs-Parser)

## File Classification

| Neue/geänderte Datei | Rolle | Data Flow | Nächster Analog | Match |
|----------------------|-------|-----------|-----------------|-------|
| `scripts/ibkr_contracts.py` (NEU: Tabelle, Allow-List, Parser, Zustände, Persistenz) | utility/model (bibliotheksfrei) | transform + file-I/O | `scripts/ibkr_broker.py` (Konstanten/Dataclasses/Named States), `ibkr_executor.py::write_portfolio_atomic` (Persistenz) | role-match |
| `scripts/ibkr_broker.py` (+`search_contract`, +`contract_details`, +`reqMarketDataType(3)`, +Codes) | service/adapter | request-response | `IbkrBroker.health()` und `positions()` im selben File | exact |
| `scripts/ibkr_executor.py` (+`resolve`-Subkommando) | controller (CLI) | request-response | `run_account` / `_account` / `build_parser` / `main` im selben File | exact |
| `scripts/IBKR_EXECUTION.md` (+`resolve`, +neuer Ticker, Exit 2 aktiv, +10167) | doc | — | eigene Abschnitte "Commands", "Exit codes", "States and log format" | exact |
| `tests/ibkr_fakes.py` (FakeContract/FakeIB erweitern) | test-fixture | request-response | `FakeIB.reqContractDetailsAsync`, `FakeIB.accountSummaryAsync` | exact |
| `tests/test_ibkr_contracts.py` (NEU) | test | transform + file-I/O | `tests/test_ibkr_executor.py::TestAccount` (tmp_path, Logging) + `tests/test_ibkr_broker.py` (parametrisiert) | role-match |
| `tests/test_ibkr_resolve.py` (NEU) | test | request-response | `tests/test_ibkr_executor.py` (`_run`, `_fake_factory`, `_log_text`) | exact |
| `tests/test_ibkr_broker.py` (Erweiterung) | test | request-response | eigene `test_state_map`, `test_farm_ok_codes_log_at_info` | exact |
| `tests/test_ibkr_isolation.py` (Methodenmenge, AST `symbols`, SC7-Grep, Handbuch) | test (Guard) | static analysis | eigene `_imports`, `test_adapter_has_at_most_ten_public_methods`, `test_handbook_exit_table_matches_executor` | exact |
| `tests/test_ibkr_executor.py` (Exit-Docstring-Test, `EXIT_NAMES` bleiben) | test | — | eigene `TestExitCodes` | exact |
| `.planning/REQUIREMENTS.md` (REQ-IBKR-31 umformulieren) | doc | — | REQ-67-Override in `02-VERIFICATION.md` | role-match |
| `tests/test_ibkr_contracts.py` Gegentest gegen `liquidSessions()` | test | transform | kein Vorbild (`pytest.importorskip`) | none |

Hinweis: `.planning/ibkr-marktdaten-befund.md` hat unbestätigte Operator-Änderungen. In keinem Plan anfassen oder stagen, nur `git add <expliziter Pfad>`.

## Pattern Assignments

### `scripts/ibkr_broker.py` (adapter, request-response)

**Analog:** derselbe File, `IbkrBroker.health()` (Z. 388-432) für "eine Anfrage per `conId` unter Timeout"; `positions()` (Z. 434-510) für Link-Event-Fenster; `_request` (Z. 512-523) für Timeout-Mapping.

**Konstanten- und Codes-Muster** (Z. 68-97) - neue Einträge hier anhängen (10167 neu, INFO_CODES erweitern, 10089/10090-Labels NICHT ändern, weil `test_state_map` sie pinnt; 154 NICHT aufnehmen):
```python
STATE_BY_CODE: dict[int, str] = {
    ...
    10089: "MARKET_DATA_NOT_SUBSCRIBED",
    10090: "MARKET_DATA_NOT_SUBSCRIBED",
    2172: "GATEWAY_VERSION_EXPIRING",
}
#: Farm-OK notices: logged at INFO, never as a warning.
INFO_CODES = frozenset({2104, 2106, 2158})
```
Ziel: `STATE_BY_CODE[10167] = "MARKET_DATA_DELAYED"` (optional `200: "CONTRACT_NOT_FOUND"`), `INFO_CODES` um `10089, 10090, 10167` erweitern. Die Log-Zeile entsteht unverändert in `_on_error` (Z. 559-562):
```python
state = state_for_code(errorCode)
level = logging.INFO if errorCode in INFO_CODES else logging.WARNING
self._log.log(level, 'ibkr-state=%s code=%s detail="%s"', state, errorCode, errorString)
```

**Frozen-Dataclass-Muster für broker-neutrale Rückgabe** (Z. 152-181) - `ContractInfo` genauso, nie ib_async-Objekte nach außen:
```python
@dataclass(frozen=True)
class BrokerPosition:
    """One held position of the paper account, broker-neutral."""
    symbol: str
    sec_type: str
    local_symbol: str
    currency: str
    ...
```

**Lesemethode mit Timeout** (Muster `health()` Z. 414-423 plus `_request` Z. 512-523). Jede neue Anfrage über `self._request(name, lambda: ...)`; frisches `handles.contract(...)` pro Aufruf (Pitfall 2: `qualifyContracts` mutiert die Anfrage):
```python
details = self._call(
    lambda: ib.reqContractDetailsAsync(handles.contract(conId=PROBE_CON_ID)),
    self._probe_timeout,
)
...
def _request(self, name: str, make_awaitable):
    try:
        return self._call(make_awaitable, self._request_timeout)
    except TimeoutError as exc:
        raise GatewayUnavailable(
            REQUEST_TIMEOUT, None, f"{name} did not answer within {self._request_timeout}s"
        ) from exc
    except ConnectionError as exc:
        raise GatewayUnavailable("NOT_CONNECTED", 504, f"{name} not sent ({type(exc).__name__})") from exc
```
Vorgehen für `search_contract`: `self._request("qualifyContracts", lambda: ib.qualifyContractsAsync(handles.contract(symbol=..., secType=..., exchange=..., currency=..., primaryExchange=...), returnAll=True))`; Slot `None` -> `()`, `Contract` -> 1 Element, `list` -> alle. `contract_details(con_id, exchange)`: `reqContractDetailsAsync(handles.contract(conId=con_id, exchange=exchange))`, `len != 1` -> benannter Fehlerzustand (Muster `PROBE_FAILED`, Z. 428-431).

**Link-Event-Fenster wie in `positions()`** (Z. 455-478), falls Lesemethoden Link-Verlust erkennen sollen: `opened = self._open_link()` vor der Anfrage, `mark = len(self._link_codes)`, danach `self._link_event_since(mark)`.

**`reqMarketDataType(3)` in `connect()`:** nach dem Paper-Guard, direkt nach dem `CONNECTED`-Log (Z. 377-386). Nicht vor dem Guard, nicht bei Guard-Verletzung:
```python
if accounts != [EXPECTED_ACCOUNT]:
    self._log.error("ibkr-state=ACCOUNT_GUARD_VIOLATED accounts_seen=%s", accounts)
    self._disconnect()
    raise AccountGuardViolation(accounts)
self._log.info("ibkr-state=CONNECTED account=%s clientId=%s readonly=True ...", ...)
# hier: ib.reqMarketDataType(3)  (synchron, ohne Antwort)
```
**Öffentliche Methoden:** heute `{connect, positions, health}`; mit zwei neuen = 5 (Grenze 10). Schreibsperre `_WRITE_MESSAGE_IDS = {3,4,19,21,58}` (Z. 66) unverändert.

---

### `scripts/ibkr_executor.py` (CLI-Subkommando `resolve`)

**Analog:** derselbe File, `run_account` (Z. 304-345), `_account` (Z. 404-464), `build_parser` (Z. 351-361), `main` (Z. 364-388).

**Parser-Muster** (Z. 356-361) - `resolve` als zweiter Subparser mit positionalem `tickers` (`nargs="*"`, Pflicht per Handprüfung wie `--out`, damit Exit 1 statt argparse-Exit), `--contracts`, `--init`/`--rebaseline` (gegenseitig ausschließend), `--out`, `--log-file`, `--env-file`:
```python
sub = parser.add_subparsers(dest="command")
account = sub.add_parser("account", help="read positions and cash into a portfolio JSON")
account.add_argument("--out", type=Path, default=None, help="portfolio JSON (required)")
account.add_argument("--log-file", type=Path, default=default_log_file())
account.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
```
**Pflichtargument-Muster in `main`** (Z. 372-378; die Fehlermeldung "needs a subcommand: account" muss um `resolve` ergänzt werden):
```python
if not args.command:
    parser.print_usage(sys.stderr)
    print("error: ibkr_executor.py needs a subcommand: account", file=sys.stderr)
    return EXIT_CONFIG
if args.out is None:
    print("error: account needs --out PATH", file=sys.stderr)
    return EXIT_CONFIG
```
Achtung: `if args.out is None` gilt heute für alle Befehle; für `resolve` ist `--out` optional, die Prüfung muss auf `account` begrenzt werden. Danach `main` verzweigt zu `_account` bzw. neu `_resolve`, beides in `try/finally: close_logging()`.

**Modul-Ladung per importlib** (Z. 99-116, `load_broker_module`) - für `ibkr_contracts` exakt kopieren (Eintrag in `sys.modules` VOR `exec_module`, bei Fehler wieder entfernen), damit Executor und Tests dieselben Klassen sehen:
```python
if "ibkr_broker" in sys.modules:
    return sys.modules["ibkr_broker"]
spec = importlib.util.spec_from_file_location("ibkr_broker", _BROKER_PATH)
module = importlib.util.module_from_spec(spec)
sys.modules["ibkr_broker"] = module
try:
    spec.loader.exec_module(module)
except BaseException:
    sys.modules.pop("ibkr_broker", None)
    raise
return module
```

**Fehlerbehandlung / Exit-Mapping** (Z. 416-464) - denselben `except`-Block für `resolve` wiederverwenden (am besten in eine gemeinsame Hilfsfunktion ziehen, nicht duplizieren): `MissingSettings` -> `EXIT_NO_CREDENTIALS`, `ConfigError` -> `EXIT_CONFIG`, `AccountGuardViolation` -> `EXIT_ACCOUNT_GUARD`, `ReadOnlyViolation` -> `WRITE_REFUSED`/`EXIT_GATEWAY`, `GatewayUnavailable` -> `EXIT_GATEWAY`, `ImportError` -> `LIBRARY_MISSING`, `Exception` -> `logger.exception` + `EXIT_GATEWAY if progress["connecting"] else EXIT_CONFIG`. `_fail` (Z. 218-221):
```python
def _fail(logger, code, log_line, console):
    logger.error(log_line)
    print(f"error: {console}", file=sys.stderr)
    return code
```
`resolve` neu: `EXIT_PRECONDITION` (2) wenn mindestens ein Ticker abgewiesen; `contracts.json` fehlt/kaputt/falsche Schema-Version -> Stopp des ganzen Laufs (Wahl des Exit-Codes: Planner; naheliegend `EXIT_PRECONDITION` fuer fehlend ("resolve --init"), `EXIT_CONFIG` fuer unlesbar - als Entscheidung dokumentieren).

**Konsolenzeile** (Z. 344): eine Zeile pro Ticker im Stil
```python
print(f"account: {len(ctx.positions)} position(s), cash {ctx.cash} {ctx.currency} -> {out}")
```
-> `print(f"resolve: {ticker} {state} ...")`; Details (alle Kandidaten) nur ins Log.

**Atomares Schreiben** (`write_portfolio_atomic`, Z. 280-301) - Muster fuer `contracts.json` und `--out resolve.json` (temp mit uuid-Suffix im selben Verzeichnis, `check` vor `os.replace`, `BaseException` -> `temp.unlink(missing_ok=True)`, nichts schlucken):
```python
out = Path(out)
out.parent.mkdir(parents=True, exist_ok=True)
temp = out.with_name(f"{out.name}.{uuid.uuid4().hex}.tmp")
try:
    temp.write_text(portfolio_json(ctx, as_of), encoding="utf-8")
    if check is not None:
        check(temp)
    os.replace(temp, out)
except BaseException:
    temp.unlink(missing_ok=True)
    raise
```
Eine generische `write_json_atomic(path, payload, check=None)` in `ibkr_contracts.py` (bibliotheksfrei, kein `tradingagents`-Import) ist der Schnitt; `write_portfolio_atomic` bleibt unverändert, da es `PortfolioContext` serialisiert.

**Default-Pfad unter LOCALAPPDATA** (Z. 119-125, `default_log_file`) - gleiches Muster fuer `default_contracts_file()`:
```python
base = environ.get("LOCALAPPDATA")
if base:
    return Path(base) / "TradingEngineX" / "ibkr" / "logs" / "ibkr_executor.log"
return Path.home() / ".tradingenginex" / "ibkr" / "logs" / "ibkr_executor.log"
```
Docstring-Update Pflicht: Exit-Tabelle im Modul-Docstring (Z. 23-33) - Zeile 2 nicht mehr "reserved"; `test_exit_codes_match_the_docstring_table` liest sie per Regex `^\s{4}(\d+)\s{2,}`. Kommando-Zeile `resolve ...` ebenfalls in den Docstring.

**Uhr:** `datetime.now(UTC)` nur an der Aufrufstelle im Executor, als Argument an reine Funktionen (kein `--now`-Schalter, Security).

---

### `scripts/ibkr_contracts.py` (NEU, bibliotheksfrei)

**Analog (Konstanten + benannte Zustände):** `scripts/ibkr_broker.py` Z. 25-50 (kommentierte Code-Konstanten), Z. 99-106 (benannte Zustände als Strings), Z. 143-181 (frozen Dataclasses), Z. 109-111 (`state_for_code`-Stil: kleine reine Funktion mit Default).
```python
#: The one paper account this adapter may talk to (ibkr-konto-befund.md). A code
#: constant, never read from .env ...
EXPECTED_ACCOUNT = "DUQ634065"
...
CONNECT_TIMEOUT = "CONNECT_TIMEOUT"
HEALTHY = "HEALTHY"
UNKNOWN = "UNKNOWN"
```
Übertragen: `ALLOWED_SEC_TYPES = frozenset({"STK"})`, `SESSION_BUFFER_MINUTES = 15`, `SCHEMA_VERSION = 1`, Zustandsstrings `ok`, `not-mapped`, `not-allowed`, `ambiguous`, `not-found`, `drift`, `not-tradable`, `closed`, `session-unknown`, `halted` (letzterer wird in Phase 3 nie gesetzt). Mapping-Tabelle als Code-Konstante mit nur Suchschlüsseln (`symbol`, `secType`, `exchange`, `currency`, `primaryExchange`), Einträge: `AAPL`, `MSFT`, `NVDA` (STK/SMART/USD/NASDAQ), `^GSPC` (IND/CBOE/SPX), `XAUUSD+` (CMDTY/SMART/XAUUSD/USD).

**Analog (Persistenz):** `write_portfolio_atomic` (s. o.). Zusätzlich history-Zeile `open("a", encoding="utf-8", newline="\n")` + `flush` + `os.fsync` VOR dem `os.replace` (Research Pattern 3, Pitfall 5). `PermissionError` nicht schlucken.

**Isolations-Regeln (hart):** kein `import ib_async`, kein `tradingagents.*` (insbesondere nicht `tradingagents.dataflows.symbols`), keine Uhrzeit-Literale `13:30|14:30|09:30|16:00` auch nicht in Kommentaren/Docstrings. Beispielstrings gehören in `tests/`.

**Kein Code-Analog:** Sitzungs-Parser (`parse_liquid_hours`, `evaluate_session`) - Spezifikation steht in RESEARCH.md "Unser Parser: Spezifikation". Reine Funktionen mit injiziertem `now_utc` (aware, sonst `ValueError`, Muster `portfolio_json` Z. 273-274: `if as_of.tzinfo is None: raise ValueError("as_of must carry a time zone")`).

---

### `tests/ibkr_fakes.py` (Fake-Erweiterung)

**Analog:** `FakeIB.reqContractDetailsAsync` (Z. 173-180) und `accountSummaryAsync` (Z. 160-171), `FakeContract` (Z. 57-63), `FakeIB.__init__` (Z. 88-113).

**Ist-Stand, der erweitert werden muss** (liefert heute immer die Probe-Antwort):
```python
async def reqContractDetailsAsync(self, contract):
    self.calls.append("probe")
    self._emit_during("probe")
    if self.probe == "hang":
        await _forever()
    if self.probe == "empty":
        return []
    return [SimpleNamespace(contract=FakeContract(conId=contract.conId))]
```
Anforderungen: `FakeContract` +`primaryExchange`, `exchange`, `tradingClass` (Defaults, Konstruktor ist `FakeContract(**kwargs)` mit Dataclass-Defaults); `reqContractDetailsAsync` je `conId` konfigurierbar (Details mit `orderTypes`, `validExchanges`, `timeZoneId`, `liquidHours`, `tradingHours`, `longName`), `probe`-Verhalten fuer `PROBE_CON_ID` und `health()` unverändert lassen; neues `qualifyContractsAsync(self, *contracts, returnAll=False)` mit 0/1/n-Slots (`None` / `Contract` / `list`), aufgezeichnet in `calls` und mit `_emit_during`; `reqMarketDataType(self, t)` zeichnet `calls.append(f"reqMarketDataType({t})")` auf (Reihenfolgetest: nach `connect`, nicht bei Guard-Verletzung). Die Fake-Methode `qualifyContractsAsync` soll das übergebene Contract-Objekt wie die Bibliothek mutieren (Pitfall 2 testbar).

**Verbotene Aufrufe** (Z. 185-205): `whatIfOrder`, `placeOrder` etc. bleiben `_forbidden`; Phase 3 ruft sie nicht auf. Der Kommentar "Phase 2 reads fresh..." ist anzupassen.

---

### `tests/test_ibkr_resolve.py` (NEU, request-response)

**Analog:** `tests/test_ibkr_executor.py` - Helfer `_env_file` (Z. 73-79), `_fake_factory` (Z. 93-108), `_run` (Z. 111-127), `_log_text` (Z. 130-131), Fixtures `loop`/`_block_real_connect`/`_close_logging` (Z. 57-70), `_RecordingFactory` (Z. 82-90) als Beweis "kein Broker-Aufruf" (`not-mapped`, `not-allowed`, leere Tickerliste).

**Fixture-Kopf zum Kopieren** (Z. 57-70):
```python
@pytest.fixture(scope="session")
def loop():
    yield from ibkr_fakes.session_loop()

@pytest.fixture(autouse=True)
def _block_real_connect(monkeypatch):
    ibkr_fakes.block_real_ib_connect(monkeypatch)

@pytest.fixture(autouse=True)
def _close_logging():
    yield
    executor.close_logging()
```
**Factory gegen echten Adapter + FakeIB** (Z. 93-108): `broker.IbkrBroker(host, port, logger=logger, ib_factory=ibkr_fakes.make_handles(fake), loop=loop, connect_timeout=0.05, request_timeout=0.05, probe_timeout=0.05)`.
**Aufrufmuster** (`_run`): `executor.main(argv, broker_factory=factory)` gefolgt von `executor.close_logging()`; `argv` mit `--env-file`, `--log-file`, `--contracts` aus `tmp_path`. Konsolenzeilen per `capsys.readouterr().out.strip().splitlines()`. Kandidatenliste (SC3): `caplog`/Logdatei muss EINE Zeile mit allen `conId=`/`primaryExchange=`/`localSymbol=` enthalten. Alle Pfade aus `tmp_path`, nie das echte `%LOCALAPPDATA%`; "kein Sitzungswert auf Platte" = `contracts.json`-Text enthält weder `liquidHours` noch `tradingHours`.

---

### `tests/test_ibkr_contracts.py` (NEU, transform + file-I/O)

**Analog:** `tests/test_ibkr_broker.py` fuer Parametrisierung und Pinning (`@pytest.mark.parametrize(("code","state"), [...])`, Z. 283-308) und `pytestmark = pytest.mark.unit` (Z. 15 in executor/broker-Tests). Modul laden per `importlib.util.spec_from_file_location` mit `sys.modules`-Eintrag (Muster `ibkr_fakes.load_broker`, Z. 23-35) -> `load_contracts()` im Fakes-Modul ergänzen.
**Gegentest SC6:** `ib_async = pytest.importorskip("ib_async")`; Neu-Format-Strings gegen `ContractDetails.liquidSessions()` vergleichen (Tupel `(start, end)`), Alt-Format `20090507:0700-1830`: ib_async wirft `ValueError` (als erwartetes Verhalten festhalten), unser Parser liefert 07:00-18:30. Kein Analog im Repo.
**Tabellentest (D-06):** `PAPER_RUN_TICKERS`-Default `AAPL,MSFT,NVDA` steht in `.github/workflows/daily-paper-run.yml:72` und `scripts/PAPER_RUN.md:40`; Test liest die Workflow-Zeile per Regex (Muster `_handbook_paper_run_dirs`, test_ibkr_isolation.py Z. 48-57).
**Grenzfälle Puffer:** `start+15min` ok, `start+15min-1s` closed, `end-15min` ok, `end-15min+1s` closed.

---

### `tests/test_ibkr_isolation.py` (Guards)

**Analog:** derselbe File.

**AST-Importtest** (`_imports`, Z. 97-104) für D-07 wiederverwenden:
```python
def _imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return names
```
Achtung: `_imports` liefert nur Top-Level-Namen. Für "importiert `tradingagents.dataflows.symbols` nicht" eine zweite Variante mit vollem Modulnamen (`node.module`, `a.name`) bauen; zusätzlich asserten, dass `ibkr_contracts.py` weder `ib_async` noch `tradingagents` importiert. Bestehender `test_only_the_adapter_imports_the_client_library` (Z. 108-115) deckt das neue Modul automatisch ab, weil er `scripts/**` rglob't.

**Methodenmenge** (Z. 118-128) - die Zeile `assert public == {"connect", "positions", "health"}` muss auf die neue Menge `{"connect", "positions", "health", "search_contract", "contract_details"}` gezogen werden; `len(public) <= 10` bleibt.

**SC7-Test (neu):** Muster `test_adapter_hard_codes_no_order_id` (Z. 131-135) - Quelltext lesen, `assert` auf Abwesenheit; über `scripts/ibkr_*.py` glob'en (nicht über `tests/`), Muster als zusammengesetzte Zeichenkette halten, damit der Test sich nicht selbst findet:
```python
source = ADAPTER.read_text(encoding="utf-8")
assert "orderId=" not in source
```
**Handbuch-Test** (`test_handbook_exit_table_matches_executor`, Z. 171-182) prüft per Regex `^\| {value} \| `{name}` \|` - bleibt grün, solange die Tabellenzeilen im Format bleiben; neue Tests: Handbuch enthält `resolve`-Abschnitt und die Zeile für Exit 2 trägt nicht mehr "reserved". `test_handbook_does_not_name_the_client_library` (Z. 166-168): im Handbuch KEIN "ib_async" schreiben.

---

### `tests/test_ibkr_broker.py` (Erweiterung)

**Analog:** `test_state_map` (Z. 283-308) um `(10167, "MARKET_DATA_DELAYED")` ergänzen, 10089/10090 unverändert lassen; `test_farm_ok_codes_log_at_info` (Z. 312-320) als Vorlage für neuen parametrisierten Test "10089, 10090, 10167 loggen auf INFO":
```python
@pytest.mark.parametrize("code", [2104, 2106, 2158])
def test_farm_ok_codes_log_at_info(loop, caplog, code):
    adapter = _broker(FakeIB(), loop)
    with caplog.at_level(logging.INFO, logger="ibkr_broker"):
        adapter._on_error(-1, code, "data farm connection is OK", None)
    assert code in broker.INFO_CODES
    (record,) = caplog.records
    assert record.levelno == logging.INFO
    assert f"ibkr-state=FARM_OK code={code}" in record.getMessage()
```
`test_other_codes_log_at_warning` (Z. 323-332) benutzt 321 und bleibt gültig. Weitere neue Tests nach Muster `test_positions_request_timeout` (Z. 521) für Timeout der neuen Lesemethoden; Schreibsperre-Test nach Muster `test_write_barrier_lets_read_messages_through` (Z. 143) für die Kopfwörter der neuen Requests (nur `reqMktData`-Kopf `1` verifiziert; Msg-Id 9/59 sind Annahme A1).

---

### `scripts/IBKR_EXECUTION.md` (Handbuch)

**Analog:** eigene Abschnitte. Zu ändern: Exit-Tabelle Zeile 112 (`| 2 | `EXIT_PRECONDITION` | precondition not met (reserved for later phases) |` -> aktivieren, Format `| 2 | `EXIT_PRECONDITION` |` beibehalten wegen Regex-Test); State-Tabelle (Z. 149-163) um `10167 | MARKET_DATA_DELAYED (logged at INFO)` ergänzen, Zeile 158 und 162 anpassen (10089/10090 ebenfalls INFO); Abschnitt "Commands" (Z. 243-) um `resolve`-Beispiele in Windows-cmd-Stil (`:: ...`-Kommentare, `%LOCALAPPDATA%`) erweitern; neuer Abschnitt "New ticker" (Commit + einmaliger `resolve <TICKER>`-Probelauf, Ausgabe in Commit-Message/PR; D-08); `resolve --init`/`--rebaseline`-Ablauf. Das Handbuch darf den Bibliotheksnamen nicht nennen.

---

### `.planning/REQUIREMENTS.md` (REQ-IBKR-31 ändern)

**Analog:** REQ-67-Override der Phase 2 (`02-VERIFICATION.md`, Frontmatter `overrides:` mit `must_have`, `reason`, `accepted_by`, `accepted_at`). Für REQ-31 Textänderung (Wortlaut in RESEARCH.md "REQ-31-Änderung"); `accepted_by: Operator` nicht vom Agenten vergeben. Vorher `grep REQ-IBKR-31 .planning` ausführen.

## Shared Patterns

### Benannte Zustände im Log
**Quelle:** `scripts/ibkr_broker.py` Z. 140, 547-548, 559-562; `scripts/ibkr_executor.py` Z. 412, 419, 424, 439, 447
**Gilt für:** alle neuen Logzeilen in `ibkr_contracts.py`/`resolve`
```python
return f'ibkr-state={self.state} code={code} detail="{self.detail}"'
self._log.warning('ibkr-state=%s code=- detail="%s"', state, detail)
```
Neue Zeilen im selben Format, z. B. `ibkr-state=AMBIGUOUS_CONTRACT code=- detail="symbol=ES candidates=[conId=…/primaryExchange=…/localSymbol=…, …]"` (alle Kandidaten, nicht kürzen). Zusätzlich INFO `learned conId=…`. Roh-Ticker vor dem Tabellentreffer nur mit `repr()` loggen (Log-Injection).

### Fail-closed / Fehler laut
**Quelle:** `write_portfolio_atomic` (Z. 280-301, "nothing is swallowed"), `positions()` (Z. 455-478, Snapshot verwerfen), `validate_settings` (Z. 150-170, `ConfigError` mit konkreter Meldung)
**Gilt für:** `contracts.json`-Laden (fehlt, kaputt, falsche Schema-Version, `conId` nicht int > 0), Handelbarkeit (leere Felder = `not-tradable`), Sitzung (Parse-Fehler = `session-unknown`).

### Logging-Setup und Konsole
**Quelle:** `scripts/ibkr_executor.py` Z. 176-198 (`setup_logging`), Z. 218-221 (`_fail`)
**Gilt für:** `resolve` - Logger `logging.getLogger("ibkr_executor")` bzw. ein Kindlogger; alle Logger propagieren auf die Root-Datei. Konsole: eine Zeile pro Ticker (stdout), Fehler als `error: ...` (stderr).

### Bibliotheksfreiheit und Modul-Laden
**Quelle:** `scripts/ibkr_executor.py` Z. 99-116, `tests/ibkr_fakes.py` Z. 23-35
**Gilt für:** `ibkr_contracts.py`, Executor, Tests (ein Modulobjekt pro Prozess, `sys.modules`-Eintrag vor `exec_module`).

### Tests: kein Gateway, keine echten Pfade
**Quelle:** `tests/ibkr_fakes.py::block_real_ib_connect` (Z. 227-238), `tests/test_ibkr_executor.py` Fixtures (Z. 57-70)
**Gilt für:** jedes neue Testmodul; `pytestmark = pytest.mark.unit`, alle Pfade aus `tmp_path`.

### Windows-Atomizität
**Quelle:** `write_portfolio_atomic` (temp + `os.replace`, temp im `finally`/`except BaseException` entfernen)
**Gilt für:** `contracts.json`, `--out resolve.json`; History-Zeile vor dem Ersetzen mit `fsync` (Research Pitfall 5).

## No Analog Found

| Datei/Teil | Rolle | Data Flow | Grund |
|------------|-------|-----------|-------|
| `liquidHours`-Parser + `evaluate_session` in `scripts/ibkr_contracts.py` | utility | transform | Kein Zeit-/Sitzungscode im Repo; Spezifikation aus RESEARCH.md (beide Formate, `CLOSED`, über Mitternacht, führendes `;`, `zoneinfo`, 15-min-Puffer, `session-unknown`) |
| Gegentest gegen `liquidSessions()` | test | transform | Kein `importorskip`-Muster im Bestand; `pytest.importorskip("ib_async")` verwenden, Alt-Format erwartet `ValueError` |
| `contracts-history.jsonl` append-only | utility | file-I/O | Kein Append-Log im Repo; Muster aus RESEARCH.md Pattern 3 |

## Metadata

**Analog-Suchbereich:** `scripts/`, `tests/ibkr_*`, `tests/test_ibkr_*`, `.github/workflows/daily-paper-run.yml`, `scripts/PAPER_RUN.md`, `scripts/IBKR_EXECUTION.md`
**Gelesene Dateien:** 7 (ibkr_broker.py, ibkr_executor.py, ibkr_fakes.py, test_ibkr_isolation.py, Auszüge test_ibkr_broker.py / test_ibkr_executor.py / IBKR_EXECUTION.md)
**Extraktionsdatum:** 2026-10-12
