# Quick 261018-kof: Vorhersagelogik und Statistik - Research

**Researched:** 2026-10-18
**Domain:** Bewertungskette Rating → Settlement → Aggregation, Musterauswertung, Statistik bei kleinem N, Codex-Review
**Confidence:** HIGH (Code und Daten lokal geprüft), MEDIUM bei den Statistik-Schwellen (Ermessen)

<user_constraints>
## User Constraints (aus CONTEXT.md, gekürzt; verbindlich)

- **Methodik:** Erst auswerten, dann eine Muster-Schicht bauen. Schritt 1: 4-6 explizite Muster je Entscheidung und je Muster Trefferquote, mittleres Alpha und N. Schritt 2 (Muster-Schicht, Veto) **nur für Muster, die sich belegen lassen**. Damit fällt Schritt 2 aus dieser Aufgabe heraus (siehe Datenlage).
- **Muster nur aus Kursen bis einschließlich Entscheidungsdatum**, nie danach. Codex prüft das.
- **Validierung:** Codex-Code-Review der ganzen Kette (Rechenfehler, Look-ahead, Benchmark, Haltedauer, REVIEW/Hold, Survivorship, Mehrfachzählung, Alpha-Rundung). Formvorlage `04-CODEX-REVIEW.md`. Dazu die echte Historie aus `fork/paper-log` lesen, ohne Checkout.
- **Kein neuer Backtest, keine LLM-Kosten.**
- **Strang-Module:** eigene Dateien, keine Edits in `rating.py`, `settlement.py`, `backtest.py`. Ausnahme: ein von Codex belegter echter Fehler wird mit dem kleinstmöglichen Patch und einem Test behoben und als Upstream-Kandidat notiert.
- **Nicht anfassen:** `scripts/ibkr_*`, IBKR-Tests, `scripts/IBKR_EXECUTION.md`.
- **Ermessen:** Auswahl der Muster, Fenster und Schwellen als Code-Konstanten. Format der Auswertung frei, solange sie auf dem Memory-Log-Format arbeitet.
- **Datenlage:** 16 Einträge, nur 1 abgerechnet (Hold). Die Auswertung muss „zu wenig Daten" als eigenes Ergebnis ausgeben.
</user_constraints>

## Project Constraints (aus CLAUDE.md / Memory)
- Tests: `.venv/Scripts/python.exe -m pytest`, Lint: `.venv/Scripts/python.exe -m ruff check` (`uv run` scheitert lokal an TLS). Ruff: line-length 100, py311.
- Code, Commits und Docstrings auf Englisch, `.planning/` auf Deutsch.
- Graphify und Serena sind nur Navigationshilfen, kein Gate.
- Veröffentlichen nur über das Remote `fork`. `origin` dient nur zum Pullen.

## 1. Die Kette mit Belegstellen

**Rating.** `tradingagents/agents/rating.py:55-93` `extract_rating` liest nur ein ausdrückliches Label („Rating: X"). Widersprechen sich mehrere Labels, kommt `None` zurück. `parse_rating` (:96) macht daraus `REVIEW`, nie Hold. `run_rating` (:106) nimmt zuerst das strukturierte `final_rating`.

**Log-Format** (`tradingagents/memory/log.py`)
- Offener Eintrag (:57): `[YYYY-MM-DD | TICKER | Rating | pending]`, dann `DECISION:`. Blöcke werden mit `<!-- ENTRY_END -->` getrennt (:15).
- Abgerechneter Eintrag (`_resolved_tag` :268): `[date | ticker | rating | +2.0% | +4.0% | 5d | resolved:YYYY-MM-DD]`. Raw und Alpha werden mit **`{:+.1%}`** formatiert (:161-162), also auf 0,1 Prozentpunkte gerundet.
- Der Parser (`_parse_entry` :310-341) liefert `date, ticker, rating, pending, raw, alpha, holding, resolved, decision, reflection`. `raw`, `alpha` und `holding` sind **Strings**.
- Ein Eintrag je (date, ticker): Die Sperre in `store_decision` (:51-55) verhindert Doppelzählung.

**Settlement** (`tradingagents/memory/settlement.py`)
- `resolve_benchmark` :14-35. `benchmark_ticker` überschreibt alles, sonst gilt die Suffix-Map, US-Default ist SPY. Der verwendete Benchmark steht **nicht** im Log-Tag.
- `fetch_returns` :52-103 holt Kurse über `get_closes` (`dataflows/vendors/yahoo/market.py:268`, `yf.Ticker.history`, Ende exklusiv). Einstieg ist der **erste Schlusskurs nach** `trade_date` (:78, `index > start`), Ausstieg `stock.index[holding_days]` (:88). Für den Benchmark gilt `asof(entry)/asof(exit)` (:97). Alpha ist die einfache Differenz `raw - bench_ret` (:99), ohne Beta-Bereinigung. Solange das Fenster nicht vollständig gehandelt ist, bleibt der Eintrag pending (:86, :93).
- `settle_pending` :114-160 ruft vor dem Schreiben den LLM-Reflector auf (:144). Unser Auswertungsmodul darf diesen Pfad **nie** aufrufen, sonst entstehen LLM-Kosten.

**Aggregation** (`tradingagents/backtest.py`)
- `_alpha` :65-75 parst den gerundeten String zurück.
- `_DIRECTION` :90: Buy und Overweight = +1, Hold = 0, Underweight und Sell = -1.
- `summarize` :184-214: `hit_rate = Anteil(alpha*direction > 0)` (:204). Für Hold ist `hit_rate=None`, `mean_alpha` wird trotzdem berechnet. REVIEW zählt als `unscored` (:207).

### Verdachtsstellen als Prompts für Codex (nicht selbst beheben)
1. **Gleichstand durch Rundung:** Ein Alpha unter 0,05 % wird zu „+0.0%" oder „-0.0%", `_alpha` liefert 0,0, und `0*direction > 0` ist False. Gleichstände zählen damit als **Fehltreffer** (`backtest.py:204`, `log.py:162`). Die Trefferquote ist dadurch nach unten verzerrt.
2. **„called the direction" heißt hier relativ zum Benchmark.** Die Trefferquote misst das Vorzeichen des Alphas, nicht das des Raw-Returns (`backtest.py:112, 204`). Ein Overweight bei steigender Aktie und noch stärker steigendem SPY gilt als falsch. Das kann so gewollt sein, die Beschriftung ist aber missverständlich.
3. **Verschiedene Einstiegskonventionen im selben Log (belegt).** Der einzige abgerechnete Eintrag `[2026-10-09 | AAPL | Hold | +2.0% | +4.0% | 5d | resolved:2026-10-16]` wurde am 2026-10-17 um 06:59 UTC abgerechnet. Der Fix #1518 (f5e3eae) kam erst um 14:56 per Rebase nach `fork/main`. Unter der neuen Regel wäre der Ausstieg der 2026-10-19 (Einstieg 10-12 + 5 Handelstage), unter der alten der 10-16 (Einstieg 10-09). Der Eintrag folgt also der **alten** Konvention. Der Tag kennzeichnet die Konvention nicht, und `render()` behauptet „from the first close after" für alle Einträge (`backtest.py:122`).
4. **Gemischte Fenster und Benchmarks:** `summarize` mittelt über verschiedene `holding`-Werte (:209-210 listet sie nur auf). Ein Wechsel des Benchmarks lässt sich im Log nicht erkennen.
5. **Zählung von pending:** Abgerechnete Einträge mit unlesbarem Alpha fallen still aus `resolved` heraus und landen im `pending`-Zähler (:197, :212).
6. **Rotation:** Mit `memory_log_max_entries` (Default `None`, `default_config.py:93`) fallen die ältesten abgerechneten Einträge weg (`log.py:273-308`). Die Aggregate stimmen dann nicht mehr. Im Paper-Lauf ist die Rotation aus; das muss geprüft bleiben.
7. **Survivorship und Auswahlverzerrung:** Der Ticker-Pool AAPL, MSFT und NVDA ist fest und im Nachhinein gewählt. Das ist kein Code-Fehler, gehört aber als Einschränkung in jede Aussage.
8. **Überlappende Fenster:** Tägliche Entscheidungen bei 5 Tagen Haltedauer überlappen sich. Die Ergebnisse sind autokorreliert, das effektive N ist ungefähr N/5 je Ticker. `summarize` behandelt jede Zelle als unabhängig.
9. **Beta:** Alpha ist eine einfache Differenz zu SPY. Bei NVDA (hohes Beta) steckt im Alpha deshalb Marktbewegung.
10. **Look-ahead im Analysten:** `load_ohlcv` filtert auf `Date <= as_of` (`ohlcv.py:229`), Einstieg ist der nächste Schlusskurs. Konsistent. Aber `_fill_price_gaps` macht `ffill().bfill()` (`ohlcv.py:88`): Ein `bfill` an einer Lücke mitten in der Reihe übernimmt einen späteren Wert, der aber noch ≤ as_of liegt. Codex soll bestätigen, dass dabei nichts über `as_of` hinaus gelangt.

## 2. Musterauswertung ohne Look-ahead

**Kursquelle:** yfinance über `dataflows/vendors/yahoo`. `load_ohlcv(symbol, as_of_date, fill_gaps=True)` (`ohlcv.py:161`) lädt 5 Jahre bis heute, cacht je Symbol in `config["data_cache_dir"]` und schneidet bei `<= as_of` ab. Es wird mit `auto_adjust=True` adjustiert. `get_closes` (Settlement) nutzt ebenfalls `history()` mit dem adjustierten Default. [VERIFIED: Codebase]

**Empfohlener Aufbau (rein und offline testbar):**
- `compute_patterns(ohlcv: pd.DataFrame, as_of: str) -> dict[str, PatternState]`. Die Funktion schneidet **selbst** auf `Date <= as_of` ab und rechnet erst danach. Das Abschneiden gehört in die Funktion, nicht zum Aufrufer, damit der Test „ändere die Kurse nach as_of → das Ergebnis bleibt gleich" die Look-ahead-Freiheit direkt beweist.
- Die Kursquelle wird injiziert: `evaluate(entries, price_loader: Callable[[str, str], pd.DataFrame])`. Der Default-Adapter ruft einmal je Ticker `load_ohlcv(ticker, max_date, fill_gaps=False)` auf und schneidet je Eintrag ab. Tests übergeben einen synthetischen Frame, also kein Netz und kein Monkeypatch nötig. Das Monkeypatch-Muster für `settlement.get_closes` gibt es schon (`tests/test_graph_end_to_end.py:317`).
- Indikatoren mit pandas selbst rechnen (ewm/rolling, wenige Zeilen) statt mit stockstats. stockstats `wrap()` verändert den Frame und berechnet über die ganze Reihe. Nach dem Abschneiden wäre das kausal, aber schlecht nachvollziehbar. Optional sichert ein Paritätstest gegen `stockstats` die Übereinstimmung mit dem, was der Analyst gesehen hat.
- Warm-up: Ein Muster, für das zu wenige Bars vorliegen (z. B. < 200 für SMA200), liefert `None` („nicht berechenbar"), nicht False.

**Startmenge (Code-Konstanten, Ermessen):**

| Muster | Definition (Close ≤ as_of) | Konstante | Begründung |
|---|---|---|---|
| `rsi_extreme` | RSI(14, Wilder: `ewm(alpha=1/14, adjust=False)`) ≤ 30 → oversold, ≥ 70 → overbought | 14 / 30 / 70 | Wilder-Standard, gleich dem `rsi` im Analysten-Prompt |
| `macd_cross` | MACD(12,26,9): Vorzeichenwechsel von MACD minus Signal in den letzten 3 Sitzungen | 12/26/9, 3 | Standardparameter. 3 Sitzungen, damit ein Kreuz vom Vortag nicht verloren geht |
| `breakout_20` | Close > max(Close der vorherigen 20 Sitzungen) bzw. < min | 20 | Donchian-20, etwa ein Handelsmonat. Der heutige Bar ist aus dem Max ausgeschlossen |
| `trend_sma200` | Close über / unter SMA200 | 200 | Klassischer langfristiger Trendfilter, braucht ≥ 200 Bars |
| `sma50_200` | SMA50 über / unter SMA200 (Regime) | 50/200 | Golden/Death-Cross-Regime |
| `bollinger_out` (optional) | Close außerhalb der Bänder BB(20, 2σ) | 20 / 2 | Standard, steht in der Indikatorliste des Analysten |

Jedes Muster bekommt eine implizite Richtung (+1/-1). Bei RSI ist sie konträr: oversold → +1. Das ist eine Setzung und wird im Code dokumentiert. Zwei Auswertungen je Muster:
- **(a) Engine bedingt:** Trefferquote und mittleres Alpha der Engine-Ratings in Einträgen, bei denen das Muster aktiv ist. Gilt nur für Richtungsratings.
- **(b) Muster allein:** Die Richtung des Musters wird gegen das Vorzeichen des Alphas geprüft. Das nutzt **alle** abgerechneten Einträge, **auch Hold**, und ist damit die Grundlage für das spätere Veto aus Schritt 2.

## 3. Statistik bei kleinem N (ohne neue Abhängigkeiten)

Verfügbare Bibliotheken: `pandas>=3.0.6` (bringt numpy mit) und stdlib `math`. **scipy ist nicht installiert**, der Wilson-Score wird deshalb von Hand gerechnet. [VERIFIED: pyproject.toml]

```python
import math
Z95 = 1.959963984540054  # two-sided 95 %
def wilson(hits: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)
```

- **`MIN_N = 20` unabhängige Fälle je Muster.** Bei n=20 und p=0,6 reicht das Intervall ungefähr von 0,39 bis 0,78; erst ab dieser Größe kann man ein Intervall sinnvoll lesen. Darunter lautet das Ergebnis `status="insufficient"`, N wird trotzdem gemeldet, eine Trefferquote nicht. [ASSUMED: Ermessen]
- **Unabhängigkeit:** Je Ticker werden nicht überlappende Einträge gierig ausgewählt (Abstand ≥ `holding` Handelstage, ersatzweise ≥ 7 Kalendertage bei `5d`). Gegen `MIN_N` zählt `n_independent`, `n_all` steht nur zur Information daneben.
- **Gleichstände** (Alpha-String „±0.0%") kommen nicht in den Nenner und werden als `ties` ausgewiesen. Das korrigiert die Verzerrung aus Verdachtsstelle 1 im Strang-Modul, ohne `backtest.py` zu ändern.
- REVIEW-Einträge und solche mit unlesbarem Alpha werden ausgeschlossen und gezählt. Pending-Einträge zählen nur in N_pending.
- Das Ergebnis enthält immer `holding` und `conventions`; gemischte Fenster werden als Warnung ausgegeben.

## 4. Codex-CLI (lokal geprüft)

`codex --version` → `codex-cli 0.137.0`. `codex exec --help` bestätigt diese Flags: `-s read-only`, `-m`, `-C <DIR>`, `--ephemeral`, `-o/--output-last-message <FILE>`, den Prompt über stdin mit `-`, sowie `--output-schema` und `--json`. In `~/.codex/config.toml` steht nur `sandbox = "unelevated"` (Windows) und kein Modell, deshalb wird `-m gpt-5.5` explizit gesetzt. [VERIFIED: lokal]

```bash
codex exec -s read-only -m gpt-5.5 -C "C:/Users/admin/PycharmProjects/TradingEngineX" \
  --ephemeral -o "<scratchpad>/codex-review.md" - < "<scratchpad>/codex-prompt.md"
```

- **Phase 4 als Vorbild:** Das Frontmatter lautet `source: codex exec (codex-cli 0.137.0, sandbox read-only)`, `scope: committed HEAD <sha>`, `note: static analysis only; the Codex sandbox blocked pytest`. Den Testlauf hat der Orchestrator auf demselben HEAD gemacht. Das wird hier genauso gehandhabt: Der Prompt verlangt eine statische Prüfung mit `file:line` und Befundtabellen, pytest läuft danach separat. Den Bericht nach `.planning/quick/261018-kof-.../261018-kof-CODEX-REVIEW.md` übernehmen.
- Der Prompt enthält die 10 Verdachtsstellen oben als Prüfliste und, sobald es sie gibt, die neuen Muster-Module (Look-ahead-Prüfung). Den HEAD-SHA vorher committen und im Prompt nennen.
- **TLS:** Codex hat in Phase 4 hinter AVG funktioniert. Die drei Variablen `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE` und `SSL_CERT_FILE` (im lokalen `.env` vorhanden, Rezept in `scripts/PAPER_RUN.md:156-181`) braucht vor allem **yfinance**, also den einmaligen Lauf auf echten Kursen. Ohne Bundle liefert yfinance Fehler oder Ersatzdaten. Deshalb muss das Auswertungsskript `load_dotenv()` aufrufen oder die Variablen voraussetzen und fehlende Kurse laut melden. [CITED: scripts/PAPER_RUN.md]

## 5. Echte Historie (verifiziert)

- `git fetch fork paper-log` funktioniert. `git show fork/paper-log:decision-log.md` auf 5541cd9 (2026-10-17) liefert 16 Tags. **`TradingMemoryLog.load_entries()` parst alle 16**, und `summarize()` gibt aus: „Resolved 1 · pending 15, Hold n=1, mean alpha +4.00 %". [VERIFIED: lokal ausgeführt, Kopie im Scratchpad]
- Lesen ohne Checkout: Den Blob in eine temporäre Datei schreiben und den Pfad an `TradingMemoryLog({"memory_log_path": tmp})` übergeben. Das Skript nimmt `--log <pfad>` oder `--git-ref fork/paper-log`, im zweiten Fall über `subprocess` mit `git show`. **Nicht** `scripts/ibkr_paperlog.py` verwenden (IBKR-Sperre).
- `daily_paper_run.py:112-129`: `trade_date` ist der vorige Wochentag, Feiertage werden nicht berücksichtigt. Ein Muster an einem Feiertag nimmt daher den letzten Bar ≤ trade_date. Der Einstieg ist der Schlusskurs des Laufdatums. Kein Look-ahead.

## 6. Ablage und Grenzen

- Vorbild für Strang-Module ist `tradingagents/jev/` mit dem Docstring „(fork-only)" und den Tests `tests/test_jev_*.py`. Empfohlen:
  - `tradingagents/patterns/__init__.py` mit Docstring „(fork-only)"
  - `patterns/signals.py` (reine Indikatoren und `compute_patterns`)
  - `patterns/evaluate.py` (Log-Join, Wilson, Mindest-N, Unabhängigkeit)
  - CLI `scripts/pattern_eval.py` (Vorbild `scripts/state_maintenance.py`, kein `ibkr_`-Präfix)
  - Tests `tests/test_patterns_signals.py`, `tests/test_patterns_evaluate.py`
- Upstream-Dateien nur bei einem von Codex belegten Fehler anfassen. Wahrscheinlichster Kandidat ist der Gleichstand durch Rundung (Verdachtsstelle 1): ein Einzeiler in `summarize`, der Ties aus dem Nenner nimmt, plus Test. Ob das gewollt ist, entscheidet der Operator; vorher nichts ändern.
- Keine Imports aus `graph/`, keinen Reflector und kein `settle_pending` in den neuen Modulen. Damit ist ein LLM-Aufruf schon durch die Importe ausgeschlossen. Ein Test kann prüfen, dass `tradingagents.patterns` weder `langchain` noch `TradingAgentsGraph` importiert.

## Validation Architecture

| Property | Value |
|---|---|
| Framework | pytest ≥ 8 (vorhanden, 115 Testdateien) |
| Quick run | `.venv/Scripts/python.exe -m pytest tests/test_patterns_signals.py tests/test_patterns_evaluate.py -q` |
| Full suite | `.venv/Scripts/python.exe -m pytest -q` und `.venv/Scripts/python.exe -m ruff check` |

Pflichttests (Wave 0, neu):
- **Kein Look-ahead:** Kurse nach `as_of` verändern (z. B. ×10) → `compute_patterns` liefert dasselbe Ergebnis.
- Warm-up: Bei < 200 Bars ist `trend_sma200` gleich `None`.
- Bekannte Werte: RSI auf einer monoton steigenden Reihe → 100 bzw. overbought; ein konstruierter Ausbruch löst `breakout_20` aus.
- Wilson-Werte: (0,0) → None, (10,20) → etwa (0,299; 0,701), (20,20) → Obergrenze 1,0.
- Unter `MIN_N` → `insufficient`, ohne Trefferquote. Ties werden aus dem Nenner genommen.
- Überlappung: Tägliche Einträge eines Tickers ergeben `n_independent` < `n_all`.
- Parser-Rundlauf mit einer Fixture im echten Tag-Format (Kopie der 16 Tags oder synthetisch). Kein Netz.
- Importsperre: Das Modul importiert weder `langchain` noch `graph`.

## Security Domain
Keine Authentifizierung, keine Sessions, keine Zugriffssteuerung. V5 (Eingabeprüfung) ist relevant: Log-Tags und Git-Ref sind Eingaben. Die Ref wird nur als Argumentliste an `subprocess` übergeben (kein `shell=True`), Ticker werden mit dem vorhandenen `safe_ticker_component` geprüft. Keine Secrets in Ausgaben; die CA-Variablen enthalten nur Pfade.

## Assumptions Log
| # | Annahme | Risiko |
|---|---|---|
| A1 | `MIN_N=20` unabhängige Fälle und Z=1,96 | Gering, es ist eine Konstante. Ein anderer Wert ändert nur, wann „insufficient" ausgegeben wird |
| A2 | RSI-Richtung konträr (oversold → +1) | Mittel. Die Momentum-Lesart wäre umgekehrt, deshalb im Code und im Bericht offenlegen |
| A3 | Codex' read-only-Sandbox blockiert Python wieder wie in Phase 4 | Gering, die Tests laufen ohnehin separat |
| A4 | Die Einordnung von 10-09 AAPL in die alte Konvention ist aus den Daten und Zeitstempeln abgeleitet, nicht aus einem Log-Feld | Gering. Codex soll das bestätigen |

## Open Questions
1. Soll die Trefferquote am Alpha (relativ) oder am Raw-Return (absolut) gemessen werden? Empfehlung: im Strang-Modul beide ausgeben und den Upstream-Code nicht ändern.
2. Soll der Eintrag nach alter Konvention (10-09 AAPL) aus der Auswertung fallen? Empfehlung: drin lassen und markieren (Abrechnung vor 2026-10-17 14:56 UTC). Bei N=1 ist das ohne Wirkung.
