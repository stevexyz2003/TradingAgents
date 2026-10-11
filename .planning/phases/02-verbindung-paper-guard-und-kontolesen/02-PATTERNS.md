# Phase 2: Verbindung, Paper-Guard und Kontolesen — Pattern Map

**Erstellt:** 2026-10-11 (HEAD `5876373`)
**Analysierte Dateien (neu/geändert):** 12
**Analoga gefunden:** 11 / 12 (eine Datei ohne echtes Analogon: der Adapter selbst)

Alle Zeilenangaben gegen den Arbeitsbaum vom 2026-10-11 gemessen. Der Operator arbeitet parallel in denselben Dateien: Die Zeilennummern sind deshalb Lesehilfe und kein Patch-Anker. Vor jedem Edit neu lesen.

## File Classification

| Neue/geänderte Datei | Rolle | Datenfluss | Nächstes Analogon | Qualität |
|---|---|---|---|---|
| `scripts/ibkr_executor.py` (neu) | Kommando/CLI | request-response, file-I/O | `scripts/state_maintenance.py` (Unterkommandos, `main` → int) + `scripts/daily_paper_run.py` (Exit-Codes, `ConfigError`, Credentials-Check) | exact |
| `scripts/ibkr_broker.py` (neu) | Service/Adapter | event-driven, request-response (async) | keins für `ib_async`; Lazy-Import-Muster aus `scripts/daily_paper_run.py:159-178`, 437 | partial |
| `tests/test_ibkr_executor.py` (neu) | Test | — | `tests/test_daily_paper_run.py` + `tests/test_state_maintenance.py` | exact |
| `tests/test_ibkr_broker.py` (neu) | Test | — | `tests/test_daily_paper_run.py` (`_FakeGraph`) | role-match |
| `tests/test_ibkr_isolation.py` (neu) | Test (Struktur-Wächter) | — | `tests/test_layering.py`, `tests/test_daily_paper_run.py:150-166` (Workflow lesen), `tests/test_version.py` (pyproject lesen) | exact |
| `tests/ibkr_fakes.py` (neu, Helfer) | Test-Fixture/Fake | — | `tests/test_daily_paper_run.py:49-69` (`_FakeGraph`), `tests/conftest.py:59-75` (Sperr-Fixture) | role-match |
| `pyproject.toml` (Extra `ibkr`) | Konfig | — | `pyproject.toml:37-41` (Extra `bedrock`) | exact |
| `scripts/daily_paper_run.py` (`--portfolio`) | Kommando/CLI | file-I/O | sich selbst (`parse_args` 334-367, `main` 370-394, `run_ticker` 292-320) | exact |
| `tradingagents/reporting.py` (`_header`) | Utility (Rendering) | transform | sich selbst (`_header` 20-46, Zeile 44-45 `memory_note`) | exact |
| `tests/test_reporting.py` / `tests/test_daily_paper_run.py` (Portfolio-Tests ergänzen) | Test | — | `tests/test_reporting.py:31-42`, `tests/test_daily_paper_run.py:285-318` | exact |
| `scripts/IBKR_EXECUTION.md` (neu) | Handbuch | — | `scripts/STATE_OPERATIONS.md:1-25` + `scripts/PAPER_RUN.md:1-22` | exact |
| `.env.example` (IBKR-Block, auskommentiert) | Konfig | — | `.env.example:33-36` (Bedrock-Block) | exact |

## Pattern Assignments

### `scripts/ibkr_executor.py` (Kommando, request-response + file-I/O)

**Analoga:** `scripts/state_maintenance.py` (Gerüst mit Unterkommandos), `scripts/daily_paper_run.py` (Exit-Code-Namen, `ConfigError`, injizierbares `environ`).

**Kopf: Shebang + Modul-Docstring mit Handbuch-Verweis und Exit-Code-Tabelle** (`state_maintenance.py:1-29`):
```python
#!/usr/bin/env python3
"""State maintenance for the TradingEngineX strand: prune, backup, verify.

Operational tooling, not part of the ``tradingagents`` library: ...

Operating manual: ``scripts/STATE_OPERATIONS.md``.

    state_maintenance.py verify [--cache-dir P] [--memory-log P]
    ...
Exit codes:
    0   ok
    1   usage/configuration error - nothing was done
    2   verify found something
"""
```
Für den Executor: dieselbe Form, Handbuch `scripts/IBKR_EXECUTION.md`, alle zehn Codes (Skizze in `02-RESEARCH.md` Zeile 375-399). Der Docstring darf das Wort `ib_async` **nicht** enthalten (Kriterium 4; `ast`-Test erfasst nur Importe, der `git grep` aber auch Text).

**Exit-Code-Konstanten** (`daily_paper_run.py:36-40`) — eine Konstante pro Zeile, Namen wiederverwenden:
```python
EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_RUN_FAILED = 3
EXIT_BUDGET = 4
EXIT_NO_CREDENTIALS = 20
```
`EXIT_OK`, `EXIT_CONFIG` und `EXIT_NO_CREDENTIALS` behalten Namen und Wert aus `daily_paper_run.py` bei. Neu: `EXIT_GATEWAY = 3` (dieselbe Zahl wie `EXIT_RUN_FAILED`, andere Bedeutung → im Docstring klarstellen), `EXIT_ACCOUNT_GUARD = 8` usw.

**Benannte Konfig-Ausnahme** (`daily_paper_run.py:61-62`):
```python
class ConfigError(Exception):
    """Invalid input or configuration - nothing is run."""
```

**Pflichtfeld-Check mit injizierbarem `environ`, leer = fehlend** (`daily_paper_run.py:196-207`):
```python
def missing_credentials(provider: str, environ: dict | None = None) -> list[str]:
    """Names of the env vars this provider needs that are absent or empty."""
    env = os.environ if environ is None else environ
    ...
    return [name for name in required if not str(env.get(name, "")).strip()]
```
Direkt übertragbar auf `REQUIRED_ENV = ("IBKR_HOST", "IBKR_PORT", "IBKR_ACCOUNT_ID")` → Exit 20. Die Werte kommen aus `dotenv_values(path)` (Pfad fest, Pitfall 6), nicht aus `os.environ`. Bestehende Tupel-Konstante als Vorbild: `AZURE_REQUIRED_ENV` (`daily_paper_run.py:46-51`).

**Unterkommando-Parser** (`state_maintenance.py:417-444`):
```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="state_maintenance.py",
        description="Prune, back up and verify the state a run leaves behind.",
    )
    sub = parser.add_subparsers(dest="command")

    backup_parser = sub.add_parser("backup", help="archive the track record")
    backup_parser.add_argument("--out", default=None, help="directory for the archive (required)")
```
Für `account`: `--out` (Pflicht, absolut auflösen wie `daily_paper_run.py:382` `args.out.resolve()`), `--log-file`, `--env-file`.

**`main` übersetzt `SystemExit` in einen Rückgabewert** (`state_maintenance.py:447-473`):
```python
def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse exits on a usage error and on --help. Callers (and the tests)
        # want a return code from main(), so translate instead of propagating.
        return EXIT_CONFIG if exc.code else EXIT_OK

    if not args.command:
        parser.print_usage()
        print("state_maintenance.py needs a subcommand: verify, prune or backup")
        return EXIT_CONFIG
    ...
    print(f"unknown subcommand: {args.command}")
    return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
```
Erweiterung laut Research: `main(argv=None, *, environ=None, broker_factory=None) -> int` — die Keyword-Argumente sind Test-Nähte.

**Fehlerpfad: eine Zeile auf stderr, Rückgabe des Codes** (`daily_paper_run.py:392-394`):
```python
    except (ConfigError, BudgetConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
```
**Abweichung, die der Planer festhalten muss:** `daily_paper_run.py:316` und `:442` rufen `traceback.print_exc()` auf. Genau das verbietet Kriterium 3 für den Executor. Der Executor übernimmt die Struktur, nicht das `print_exc`: `logger.exception(...)` nur in den `FileHandler`, auf der Konsole eine Zeile ohne Traceback.

**Lazy-Import einer optionalen Abhängigkeit mit Rückfall** (`daily_paper_run.py:159-168`):
```python
    try:
        from tradingagents.llm_clients.openai_client import OPENAI_COMPATIBLE_PROVIDERS
    except ImportError:  # pragma: no cover - SDK missing
        return False
```
Vorbild für „Adapter laden → `ImportError` → Exit 1 mit Hinweis `pip install -e ".[ibkr]"`". Der Executor importiert `scripts/ibkr_broker.py` per `importlib.util.spec_from_file_location` oder per Pfad im selben Verzeichnis (scripts/ ist kein Paket — siehe Shared Patterns).

**Atomares Schreiben** (`tradingagents/dataflows/files.py:14-33`):
```python
    path = Path(path)
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        write(str(temp))
        os.replace(temp, path)
    except PermissionError as exc:
        temp.unlink(missing_ok=True)
        logger.warning("Kept the cached %s; it is in use (%s)", path.name, exc)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
```
**Muster kopieren, Funktion nicht wiederverwenden:** `replace_file` schluckt `PermissionError` (Cache-Semantik). Für das Portfolio-JSON wäre „alte Datei bleibt stehen, Exit 0" falsch. Der Executor schreibt den `tmp`-Namen genauso (`<name>.<uuid>.tmp` im selben Verzeichnis), lässt `PermissionError` aber zu einem Fehler-Exit werden. JSON-Text mit `encoding="utf-8"` wie `daily_paper_run.py:487`:
```python
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
```
Danach Gegenprobe mit `load_portfolio(out)` (`tradingagents/portfolio.py:58-64`), die jede Schemaverletzung als `ValueError` meldet.

**Logging:** Ein `logging.FileHandler(..., encoding="utf-8")` gibt es im Repo noch nicht (`grep FileHandler` in `tradingagents/ cli/ scripts/`: kein Treffer). Nur `logger = logging.getLogger(__name__)` als Konvention (`files.py:11`). Siehe „No Analog Found".

---

### `scripts/ibkr_broker.py` (Adapter, event-driven + async request-response)

**Analogon:** keins im Repo für eine Socket-Bibliothek mit Events. Übertragbare Teilmuster:

**Import erst im Funktionskörper** (`daily_paper_run.py:171-178` und `:437-439`):
```python
def providers_in_use(config: dict) -> list[str]:
    """Every provider this config calls: ``llm_provider`` plus any tier's own (#1440)."""
    from tradingagents.llm_clients.factory import tier_provider
    ...
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        graph = TradingAgentsGraph(config=config)
```
Genau so `_default_ib_factory()` mit `from ib_async import IB` im Körper (`02-RESEARCH.md` Muster 1). `tests/test_layering.py:18` nutzt `ast.walk`, findet diesen Import also trotzdem — gewollt.

**Modul-Konstanten mit `#:`-Doc-Kommentar und Begründung** (`state_maintenance.py:49-50`, `:67-68`):
```python
#: Tables a healthy LangGraph SQLite checkpoint carries (checkpointer.py:93).
CHECKPOINT_TABLES = ("checkpoints", "writes")

#: Sidecars and scratch files never belong in a backup.
BACKUP_EXCLUDED_SUFFIXES = (".lock", ".tmp", ".db")
```
Für `EXPECTED_ACCOUNT`, `EXECUTOR_CLIENT_ID`, `PROBE_CON_ID`, `*_TIMEOUT_S`, `_WRITE_CALLS` und die Code→Zustand-Tabelle. Der Kommentar nennt die Herkunft (`ibkr-konto-befund.md`, Pitfall 8), analog zu den `file:line`-Begründungen in `state_maintenance.py:52-65`.

**Benannte Ausnahmen mit einzeiligem Docstring** (Stil `daily_paper_run.py:61-62`): `AccountGuardViolation`, `ReadOnlyViolation`, `GatewayUnavailable(state, code, detail)`. Kern-Skizzen (Schreibsperre, `_call` mit `wait_for`, Guard) stehen in `02-RESEARCH.md` Muster 2-4 — dort übernehmen, nicht neu erfinden.

**Datenabbildung auf das Schema** (`tradingagents/portfolio.py:23-32`):
```python
class Position(BaseModel):
    ticker: str = Field(description="Instrument symbol, e.g. AAPL")
    quantity: float = Field(description="Signed units held; negative is short")
    average_price: float | None = Field(default=None, description="Average entry price per unit")


class PortfolioContext(BaseModel):
    cash: float | None = Field(default=None, description="Free cash available")
    currency: str | None = Field(default=None, description="Currency label for cash and prices")
    positions: list[Position] = Field(default_factory=list)
```
Kein `model_config` → Zusatzfelder werden still verworfen. Der Adapter liefert einen eigenen, broker-neutralen Snapshot (dataclass); die Umwandlung in `PortfolioContext` gehört laut Responsibility Map ins Kommando. `tradingagents/portfolio.py` bleibt unverändert (Broker-Neutralität, Zeile 9-11).

---

### `tests/test_ibkr_executor.py` (Test)

**Analoga:** `tests/test_daily_paper_run.py`, `tests/test_state_maintenance.py`.

**Modul-Docstring, der sagt, was abgedeckt ist und warum** (`test_state_maintenance.py:1-12`), inklusive des Satzes:
```python
Every path is passed in explicitly from ``tmp_path``; nothing here reads ``~``
or the operator's own files.
```
Für IBKR erweitern: „… und nichts liest die echte `.env` oder erreicht das Gateway".

**Skript per Pfad laden** (`test_daily_paper_run.py:22-32`):
```python
_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "daily_paper_run.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("daily_paper_run", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_runner()
```

**`main` mit argv-Liste aufrufen, Rückgabewert gegen benannte Konstante prüfen** (`test_daily_paper_run.py:390-402`):
```python
    def test_preflight_reports_missing_credentials_distinctly(self, monkeypatch, tmp_path):
        # Exit 20 is what lets the workflow skip green instead of going red
        # every morning until the operator adds the secret.
        monkeypatch.setenv("OPENAI_API_KEY", "")
        exit_code = runner.main([ ... "--preflight", ])
        assert exit_code == runner.EXIT_NO_CREDENTIALS
```
Für den Executor statt `monkeypatch.setenv` das explizite `environ=`-Dict bzw. eine `tmp_path/.env` über `--env-file` übergeben (Pitfall 6: die echten `IBKR_*` stehen sonst im Prozess).

**Konsolenausgabe prüfen** (`test_state_maintenance.py:603-608`):
```python
def test_backup_without_out_returns_one(tmp_path, capsys):
    rc = tool.main(["backup", "--state-dir", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "--out" in captured.out + captured.err
```
Kriterium 3 daraus: `assert "Traceback" not in captured.out + captured.err`, und in der Logdatei (`read_text(encoding="utf-8")`) `GATEWAY_UNREACHABLE` und `502`.

**Usage-Fehler als Rückgabewert** (`test_state_maintenance.py:593-600`):
```python
def test_unknown_subcommand_returns_one(capsys):
    assert tool.main(["frobnicate"]) == 1
    capsys.readouterr()
```

**Klassengruppierung nach Thema** (`test_daily_paper_run.py:72, 169, 302`: `TestParseTickers`, `TestCredentials`, `TestMain`) für `TestConfig`, `TestExitCodes`, `TestLogFile`, `TestAccount`.

---

### `tests/test_ibkr_broker.py` (Test)

**Analogon:** `tests/test_daily_paper_run.py:49-69` (`_FakeGraph`, steuerbares Ergebnis + Aufrufliste):
```python
class _FakeGraph:
    """Stand-in for TradingAgentsGraph with a controllable outcome."""

    def __init__(self, *, signal="Buy", error=None, cost=0.25):
        self.signal = signal
        self.error = error
        self.spend_tracker = SimpleNamespace(tokens_in=1000, tokens_out=200, cost=cost)
        self.calls = []

    def propagate(self, ticker, trade_date, asset_type="stock"):
        self.calls.append((ticker, trade_date))
        if self.error is not None:
            raise self.error
        return {"final_trade_decision": f"**Rating**: {self.signal}"}, self.signal
```
Genau diese Form hat das `FakeIB` aus `02-RESEARCH.md` Zeile 402-418 (`calls`-Liste, `refuse=`-Fehler, `SimpleNamespace` für `client`). Assertions über `calls` belegen „getrennt" und „kein Platzierungsaufruf" (Kriterium 2) sowie zwei `reqPositionsAsync` bei zwei `positions()` (REQ-12).

**Parametrisierte Tabellen-Tests** (`test_daily_paper_run.py:90-102`):
```python
    @pytest.mark.parametrize(
        ("today", "expected"),
        [
            ("2026-08-19", "2026-08-18"),  # Wednesday -> Tuesday
            ...
        ],
    )
```
Für die Code→Zustand-Tabelle (`state_map`), je Zeile mit Kommentar.

**Marker:** `@pytest.mark.unit` an jedem Test wie in `tests/test_layering.py:26` und `tests/test_reporting.py:31`. Echte Gateway-Läufe nur `@pytest.mark.integration` (`tests/test_deepseek_reasoning.py:192`); `conftest.py:62-63` hebt dafür die Netzsperre auf, und `pyproject.toml` schließt `integration` per Default aus.

---

### `tests/ibkr_fakes.py` (Test-Helfer)

**Analoga:** `_FakeGraph` (oben) und die Sperr-Fixture `tests/conftest.py:59-75`:
```python
@pytest.fixture(autouse=True)
def _no_network(request, monkeypatch):
    """Tests do not reach the network; one that must is marked integration."""
    if request.node.get_closest_marker("integration"):
        return

    def refuse(*args, **kwargs):
        raise OSError(f"test tried to reach the network: {args[1:] or kwargs}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
```
Danach die IBKR-Sperre bauen: dieselbe `refuse`-Form, gesetzt auf `ib_async.IB.connectAsync` und `ib_async.client.Client.connectAsync`, nur wenn `ib_async` importierbar ist (`pytest.importorskip` bzw. `try/except ImportError`). Sie gehört **nicht** in die globale `conftest.py` — sonst importiert jeder Testlauf `ib_async` und die CI-Matrix ohne das Extra bräuchte die Abfrage dort. Ort: Helfermodul + Modul-Fixture in den drei IBKR-Testdateien.

`tests/__init__.py` existiert, also ist `from tests.ibkr_fakes import FakeIB` möglich. Ein bestehender geteilter Test-Helfer außerhalb von `conftest.py` existiert im Repo nicht; die Datei wäre der erste.

**Session-skopierte Loop-Fixture** (Pitfall 5): kein Vorbild im Repo (bisher nur funktionsskopierte autouse-Fixtures in `conftest.py`). Siehe „No Analog Found".

**Nachweis, dass die Sperre greift** — Muster `tests/test_suite_isolation.py:8-20`:
```python
@pytest.mark.unit
@pytest.mark.parametrize("connect", [
    lambda: socket.create_connection(("192.0.2.1", 80), timeout=1),
    ...
], ids=["connect", "connect_ex", "dns", "curl_cffi"])
def test_a_test_cannot_reach_the_network(connect):
    with pytest.raises(OSError, match="reach the network"):
        connect()
```
Analog einen Test, dass ein echtes `IB().connectAsync(...)` im Testlauf sofort scheitert (mit `importorskip`).

---

### `tests/test_ibkr_isolation.py` (Struktur-Wächter)

**Analogon:** `tests/test_layering.py` (ganze Datei, 35 Zeilen):
```python
ROOT = Path(__file__).resolve().parents[1]
VENDOR_LIBRARIES = {"yfinance"}


def _imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.unit
def test_vendor_libraries_are_imported_only_by_the_data_layer():
    data_layer = ROOT / "tradingagents" / "dataflows"
    offenders = sorted(
        str(path.relative_to(ROOT))
        for package in ("tradingagents", "cli")
        for path in (ROOT / package).rglob("*.py")
        if data_layer not in path.parents and _imports(path) & VENDOR_LIBRARIES
    )
    assert offenders == []
```
Übernehmen: `_imports` 1:1 (oder aus `test_layering` importieren), Pakete `("tradingagents", "cli", "scripts")`, Erwartung `importers == ["scripts/ibkr_broker.py"]` (Pfad mit `.as_posix()` normalisieren — `str(relative_to)` liefert unter Windows Backslashes). `ast.walk` erfasst auch den Import im Funktionskörper. ≤10 öffentliche Methoden: `ast.ClassDef` `IbkrBroker`, `FunctionDef`-Namen ohne `_`-Präfix zählen (Dunder zählen nicht).

**Workflow-Dateien als Text lesen** (`test_daily_paper_run.py:154-159`):
```python
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "daily-paper-run.yml"
        ).read_text(encoding="utf-8")
```
Für Kriterium 8: über `(ROOT / ".github" / "workflows").glob("*.yml")` und `assert "IBKR" not in text`.

**`pyproject.toml` lesen** (`tests/test_version.py:10`, Regex-Prüfung 13-18):
```python
PYPROJECT = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
```
Für den Pin `"ib_async==2.1.0"` und `"tzdata>=2025.2,<2026.0"`: `tomllib.loads(PYPROJECT)["project"]["optional-dependencies"]["ibkr"]` (Py ≥3.11 = `target-version`), die Kommentarzeile per Regex auf dem Rohtext.

**`git ls-files .env`:** `subprocess` nutzt bisher nur `tests/test_cli_commands.py`. Muster: `subprocess.run(["git", "ls-files", ".env"], cwd=ROOT, capture_output=True, text=True)`; überspringen mit `pytest.skip`, wenn `ROOT / ".git"` fehlt.

**`clientId` im Handbuch:** Handbuch lesen wie oben (`read_text(encoding="utf-8")`) und `str(broker.EXECUTOR_CLIENT_ID) in text` prüfen.

---

### `pyproject.toml` (Extra `ibkr`)

**Analogon:** `pyproject.toml:31-41`:
```toml
[project.optional-dependencies]
dev = [
    "ruff>=0.16",
    "pytest>=8.0",
    "pytest-subtests>=0.13",
]
# Amazon Bedrock support (AWS SigV4 auth + boto3). Optional so the core install
# stays lean: pip install "tradingagents[bedrock]".
bedrock = [
    "langchain-aws>=1.7.9",
]
```
Das neue Extra direkt nach `bedrock`, Kommentarform identisch („Optional so … : pip install …"). Inhalt: Vorschlag in `02-RESEARCH.md` Zeile 118-131. **Achtung Rebase:** `pyproject.toml` ist eine Upstream-Datei; der Block steht am Ende der Liste, damit Konflikte klein bleiben.

---

### `scripts/daily_paper_run.py` (`--portfolio`, additiv)

**Analogon:** die Datei selbst.

**Optionales Pfad-Argument** (`daily_paper_run.py:351-356`):
```python
    parser.add_argument(
        "--rates",
        type=Path,
        default=Path(__file__).with_name("paper_run_rates.json"),
        help="JSON rate table {model: {input, output}} in USD per 1M tokens.",
    )
```
Für `--portfolio`: `type=Path, default=None`.

**Laden vor dem Graph-Bau im Konfig-`try`** (`daily_paper_run.py:372-394`) — `load_rates` steht dort; `load_portfolio` daneben, `ValueError` → `ConfigError` → `EXIT_CONFIG`. Muster der Fehlerumwandlung (`daily_paper_run.py:132-137`):
```python
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Rate file not found: {path}") from exc
```

**Durchreichen** (`daily_paper_run.py:292`, `:307`, `:461`):
```python
def run_ticker(graph, ticker: str, trade_date: str, out_dir: Path) -> dict:
    ...
        final_state, signal = graph.propagate(ticker, trade_date)
    ...
        record = run_ticker(graph, ticker, trade_date, out_dir)
```
Ziel: `run_ticker(..., portfolio=None)` und `graph.propagate(ticker, trade_date, portfolio=portfolio)` — Signatur existiert (`tradingagents/graph/trading_graph.py:183`).

**Wichtiger Fallstrick für Bestands-Tests:** `_FakeGraph.propagate(self, ticker, trade_date, asset_type="stock")` (`test_daily_paper_run.py:58`) kennt kein `portfolio=`. Wird `portfolio=` **immer** übergeben, brechen alle `TestRunTicker`/`TestMain`-Fälle mit `TypeError` (in `run_ticker` als Status `failed` geschluckt → Exit 3). Zwei Wege: (a) `portfolio=` nur übergeben, wenn nicht `None` (dann bleibt der Lauf ohne Option byte-gleich — das verlangt der Research ohnehin), oder (b) `_FakeGraph.propagate` um `portfolio=None` erweitern und die Aufrufliste um den Wert. Empfehlung: (a) im Code **und** (b) im Fake, damit der neue Test das Durchreichen prüfen kann.

**Test-Muster für den neuen Fall** (`test_daily_paper_run.py:285-299`): `_run_main(monkeypatch, tmp_path, graph, extra_args=("--portfolio", str(p)))` — `extra_args` existiert schon genau dafür.

---

### `tradingagents/reporting.py` (`_header`, transform)

**Analogon:** `_header` selbst, letzte bedingte Zeile (`reporting.py:44-46`):
```python
    if final_state.get("memory_note"):
        lines.append(f"- Memory log: {final_state['memory_note']}")
    return "\n".join(lines) + "\n\n"
```
`final_state["portfolio_context"]` ist bereits ein **gerenderter String** (`tradingagents/graph/propagation.py:20` `portfolio_context: str = ""`, gefüllt in `trading_graph.py:327` mit `portfolio.render(company_name)`), leer ohne Portfolio. Also derselbe `if final_state.get(...)`-Test; der Block beginnt mit `"Portfolio at the analysis date:"` (`portfolio.py:51`) und wird als eigener Absatz nach den Kopfzeilen angehängt (Leerzeile davor, damit die `- `-Liste des Headers nicht mit der des Blocks verschmilzt). Ohne Portfolio: Ausgabe unverändert. `report_html.render_report` bekommt denselben `final_state` (`reporting.py:117-119`) — ob der Block dort auch erscheinen soll, ist offen (Research sagt „weder in `complete_report.md` noch im HTML").

**Test-Muster** (`tests/test_reporting.py:13-42`):
```python
def _state():
    return {
        "market_report": "MKT",
        ...
        "final_trade_decision": "PM DECISION",
    }


@pytest.mark.unit
def test_write_report_tree_creates_files(tmp_path):
    out = write_report_tree(_state(), "AAPL", tmp_path)
    ...
    complete = out.read_text()
    assert "Trading Analysis Report: AAPL" in complete
```
Neuer Test: `{**_state(), "portfolio_context": PortfolioContext(...).render("AAPL")}` → `"Portfolio at the analysis date" in complete`; Gegenfall ohne Schlüssel → nicht enthalten.

---

### `scripts/IBKR_EXECUTION.md` (Handbuch)

**Analoga:** `scripts/STATE_OPERATIONS.md:1-15`, `scripts/PAPER_RUN.md:1-22`.

**Kopf: Titel „— operating manual", Abgrenzung, Messstand, Schlüsseltabelle ohne Spaltenköpfe** (`STATE_OPERATIONS.md:1-14`):
```markdown
# State: retention, backup and recovery — operating manual

Companion to `scripts/PAPER_RUN.md`. That one covers the daily run; this one
covers what the run leaves on disk: ...

Every claim here carries a `file:line` reference, measured against `main` on
2026-10-11, so a later reader can check it instead of trusting it.

| | |
|---|---|
| Tool | `scripts/state_maintenance.py` (`verify` / `prune` / `backup`) |
| Tests | `tests/test_state_maintenance.py` |
```
**Sicherheitsaussage früh und fett** (`PAPER_RUN.md:9-11`): „It is **paper only**. Nothing here places, routes, or simulates orders" — für Phase 2 entsprechend „read-only, kein Schreib-API, Sperre in der Client-Schicht, Gateway-Schalter Stand <Datum>".

**Befehlsblock mit Kommentar pro Aufruf** (`STATE_OPERATIONS.md:248-266`, Abschnitt `## Commands`) und `## See also` am Ende (`:268`). Abschnitte für Phase 2: clientId (Konstante + Begründung Pitfall 8), Exit-Codes (Tabelle = Docstring), Zustände/Logformat, Read-Only-Zustand mit Datum, Bedienung `account`.

Sprache: Die bestehenden Handbücher sind **englisch** (Code-nahe Doku, Memory: Code/Commits englisch). Das Wort `ib_async` vermeiden („the IBKR client library"), Pitfall 7.

---

### `.env.example` (auskommentierter IBKR-Block)

**Analogon:** `.env.example:33-36`:
```bash
# AWS Bedrock (pip install ".[bedrock]"). Bearer token, or the AWS credential chain; set the region either way.
#AWS_BEARER_TOKEN_BEDROCK=
#AWS_DEFAULT_REGION=us-west-2
#AWS_PROFILE=
```
Analog: `# IBKR paper execution (pip install ".[ibkr]"), local only - never a CI secret.` + `#IBKR_HOST=127.0.0.1`, `#IBKR_PORT=7497`, `#IBKR_ACCOUNT_ID=DUQ634065`, `#IBKR_TRADING_MODE=paper`. Keine Werte für Username/Passwort (A1: das Kommando liest sie nicht). Upstream-Datei → Block ans Ende stellen. Optional: die Datei ist nicht im Research gefordert; Planer entscheidet.

## Shared Patterns

### Skripte sind kein Paket
**Quelle:** `tests/test_daily_paper_run.py:22-29`, `tests/test_state_maintenance.py:27-37`
**Gilt für:** alle drei IBKR-Testdateien und den Import des Adapters durch den Executor.
`scripts/` hat kein `__init__.py`; Tests laden Skripte per `spec_from_file_location`. Wenn `ibkr_executor.py` den Adapter lädt, entweder ebenso per Pfad (`Path(__file__).with_name("ibkr_broker.py")`, Muster `daily_paper_run.py:354`) oder über `sys.path`, das bei `python scripts/ibkr_executor.py` ohnehin `scripts/` enthält — im Test aber **nicht**. Der Pfad-Import ist in beiden Fällen gleich und daher robuster.

### Exit-Codes und Fehlerausgabe
**Quelle:** `scripts/daily_paper_run.py:13-19, 36-40, 392-394`; `scripts/state_maintenance.py:25-29, 447-473`
**Gilt für:** `ibkr_executor.py`, `daily_paper_run.py --portfolio`
Docstring-Tabelle und Konstanten stehen beide im Modul; ein Test hält sie gleich. `main()` gibt immer `int` zurück, `sys.exit(main())` nur unter `__main__`. Fehlermeldung `print(f"error: {exc}", file=sys.stderr)`.

### UTF-8 explizit
**Quelle:** `daily_paper_run.py:133, 268, 275, 487`; `test_layering.py:18`; `portfolio.py:61`
**Gilt für:** jedes `read_text`/`write_text`/`open`/`FileHandler` in allen neuen Dateien — auch in Tests (`test_reporting.py:36` liest ohne `encoding`; das nicht kopieren).

### Injizierbare Nähte statt Monkeypatching des Prozesszustands
**Quelle:** `missing_credentials(provider, environ=None)` (`daily_paper_run.py:196-198`), `build_config(..., base_config=None)` (`:210-219`), `TradingAgentsGraph`-Ersatz per `monkeypatch.setattr` (`test_daily_paper_run.py:286-289`)
**Gilt für:** `IbkrBroker(ib_factory=, loop=)`, `main(environ=, broker_factory=)`.

### Test-Marker und Netzsperre
**Quelle:** `tests/conftest.py:47-75`, `tests/test_layering.py:26`
**Gilt für:** alle neuen Tests — `@pytest.mark.unit`; echte Verbindungen nur `@pytest.mark.integration`. Die globale `_no_network`-Sperre reicht für asyncio-Loopback unter Windows **nicht** (Research Pitfall 4) → zusätzliche IBKR-Sperre in den IBKR-Testmodulen.

### Ruff
`line-length = 100`, `select = ["E","W","F","I","B","UP","C4","SIM"]`, `target-version = "py311"` (→ `datetime.UTC`, `X | None`, wie `daily_paper_run.py:28` und `:114`). Importblöcke isort-sortiert: stdlib, Leerzeile, `tradingagents.*` (`daily_paper_run.py:21-34`).

## No Analog Found

| Datei / Teil | Rolle | Datenfluss | Grund |
|---|---|---|---|
| `scripts/ibkr_broker.py` (Kern: `connectAsync`, `errorEvent`, `wait_for`, Schreibsperre) | Adapter | event-driven/async | Im Repo gibt es keine asyncio- oder Socket-Bibliothek mit Event-Abos. Muster 1-7 aus `02-RESEARCH.md` sind die Vorlage |
| Logdatei (`logging.FileHandler(encoding="utf-8")`, erste Zeile = eigener Pfad) | Utility | file-I/O | Kein `FileHandler` in `tradingagents/`, `cli/`, `scripts/`; bestehende Skripte schreiben nur auf stdout/stderr. Research-Vorgabe (REQ-55) direkt umsetzen |
| Session-skopierte Event-Loop-Fixture | Test-Fixture | — | Alle Fixtures in `conftest.py` sind funktionsskopiert; kein asyncio-Test im Repo mit eigener Loop. Pitfall 5 + Annahme A6 |
| Geteilter Test-Helfer `tests/ibkr_fakes.py` | Test-Fake | — | Bisher liegen Fakes jeweils in der Testdatei (`_FakeGraph`). Der Helfer wäre neu; Inhalt nach `_FakeGraph`-Form |

## Metadata

**Suchbereich:** `scripts/`, `tests/` (conftest, layering, daily_paper_run, state_maintenance, reporting, portfolio_context, suite_isolation, version), `tradingagents/{reporting,portfolio}.py`, `tradingagents/graph/{propagation,trading_graph}.py` (grep), `tradingagents/dataflows/files.py`, `pyproject.toml`, `.env.example`, `.gitignore`, `.github/workflows/ci.yml`
**Gescannte Dateien:** ~16
**Stand:** 2026-10-11
