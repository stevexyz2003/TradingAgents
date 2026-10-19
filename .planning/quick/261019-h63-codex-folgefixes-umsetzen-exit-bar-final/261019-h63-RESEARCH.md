# Quick 261019-h63: Codex-Folgefixes - Research

**Erstellt:** 2026-10-19 · **Basis:** HEAD `47d2ac2` (enthält upstream v0.7.0, `origin/main` e8f5503) · **Konfidenz:** HIGH (alles am Code verifiziert, Baseline 172 Tests grün)

<user_constraints>
Gesperrt laut `261019-h63-CONTEXT.md` / `261018-kof-DECISIONS.md`: #17 → #1/#2 → #4, je ein kleiner Commit mit Test und „Upstream candidate“ im Body. Nicht anfassen: `scripts/ibkr_*`, IBKR-Tests, `scripts/IBKR_EXECUTION.md`. Keine neuen Abhängigkeiten, kein Backtest, keine LLM-Kosten. Ermessen: Bestimmung der Börsenzeit je Ticker und das konkrete Feldformat.
</user_constraints>

## Gemessener Ausgangszustand

- Der Upstream-Diff des Forks ist auf diesen Dateien sehr klein: nur `backtest.py` +5/-2 (Fix #5). Die Rebase-Fläche ist also praktisch alles, was dieser Task neu hinzufügt.
- Baseline: `.venv/Scripts/python.exe -m pytest tests/test_memory_log.py tests/test_backtest.py tests/test_cli_memory_log.py tests/test_patterns_evaluate.py tests/test_graph_end_to_end.py -q` ergibt **172 passed (17 s)**. Alle Kursfixtures liegen in 2026-01 bzw. 2026-06/07, also vor „heute“. Ein Finalitätsfilter mit der echten Uhr bricht keinen bestehenden Test.

## #17 Exit-Bar-Finalität

**Wo der Exit-Bar übernommen wird:** `settlement.py:77` (`stock = _by_day(get_closes(...))`), `:81` (Benchmark), `:86` (`len(stock) <= holding_days` → pending), `:88` (`exit_ = stock.index[holding_days]`), `:93` (Benchmark muss bis `exit_` gehandelt haben), `:97` (`bench.asof(exit_)`). `get_closes` (`yahoo/market.py:268-272`) liefert `yf.Ticker.history()["Close"]` ungeprüft weiter.

**Woher die Börsenzeitzone kommt (ohne neue Abhängigkeit, ohne Zusatz-Call):** yfinance 1.7.0 lokalisiert den Index der Tagesbars auf `exchangeTimezoneName` (`.venv/.../yfinance/scrapers/history.py:380, :423, :497`) [VERIFIED: installierter Quelltext]. Den Live-Bar der laufenden Sitzung führt es in die heutige Zeile zusammen (`utils.fix_Yahoo_returning_live_separate`, `utils.py:687`). Die Serie trägt ihre Börsenzeitzone also selbst, und `_by_day` (`settlement.py:38-49`) wirft sie erst in `:47-48` weg. `symbols.py`, `benchmark_map` oder eine Regionstabelle braucht man dafür nicht. Eine Uhrzeit für den Sitzungsschluss kennt das Repo nirgends. `ohlcv.py:146-158` (`_cache_is_fresh`, #1150) löst das Problem nur über eine TTL und den lokalen `pd.Timestamp.today()`, also ohne Börsenzeit. Für das Settlement ist das kein Vorbild.

**Kleinste Prüfung (Empfehlung):** In `_by_day` vor dem `tz_localize(None)` alle Bars verwerfen, deren Datum in der Zeitzone der Serie **nicht vor dem heutigen Börsentag** liegt:
```python
def _by_day(closes, now):            # now: tz-aware datetime (UTC)
    closes = closes[closes > 0]
    tz = getattr(closes.index, "tz", None)
    today = now.astimezone(tz or UTC).date()       # naive index (tests/other vendors): UTC
    closes = closes[closes.index.date < today]     # today's bar may still be live (#1150)
    if tz is not None:
        closes = closes.tz_localize(None)
    return closes
```
`fetch_returns(..., now: datetime | None = None)` mit `now = now or datetime.now(UTC)`. Den Wert an **beide** `_by_day`-Aufrufe (`:77`, `:81`) geben. Danach greifen die vorhandenen Prüfungen `:86` und `:93` von selbst: Ist der Aktien- oder Benchmark-Exit-Bar vorläufig, fehlt er, und der Eintrag bleibt ohne Fehler pending. `settle_pending` braucht dafür keine Signaturänderung. Tests übergeben `now=` direkt an `fetch_returns`.

- **Abdeckung:** Wochenende und Feiertag: Der letzte Bar (Freitag) liegt vor heute, gilt also als final. Krypto (Index UTC, 24/7): Der heutige UTC-Bar wird ausgeschlossen, das ist korrekt. Nicht-US-Börse (`.T`, `.DE`): eigene tz aus dem Index. Benchmark in anderer Zeitzone (z. B. BTC-USD gegen SPY, oder ein expliziter `benchmark_ticker`) wird in seiner eigenen tz geprüft.
- **Zweite Klausel der Entscheidung** („oder die Sitzung ist laut Börsenzeit geschlossen“): Sie würde nur *früher* abrechnen, und dafür bräuchte man `history_metadata["currentTradingPeriod"]`. Das hieße, die Signatur von `get_closes` zu ändern oder eine Schlusszeit-Tabelle zu pflegen. Die reine Datumsregel ist strenger und nie falsch. Sie verzögert höchstens um einen Tag (Paper-Lauf 06:59 UTC = 02:59 NY: US-Bars sind dann schon „gestern“, also keine Verzögerung). **Empfehlung:** nur die Datumsregel umsetzen und die Abweichung im Commit/SUMMARY nennen (siehe Offene Frage 1).
- **Neue Tests** (`tests/test_memory_log.py`, Klasse `TestSettlementWindow` bei `:1090`, Helfer `_closes` bei `:1082`): (a) Ein Exit-Bar mit Datum = heute (NY-tz, `now` = 20:00 UTC) ergibt `(None,)*4`. (b) Am Folgetag mit demselben Fixture wird abgerechnet. (c) Benchmark-Bar = heute in seiner eigenen tz, die Aktie ist schon final: Ergebnis pending. (d) Coin mit UTC-Index, `now` am Samstag: Der Samstagsbar ist ausgeschlossen. Bestehende Tests bleiben unverändert.

## #1 Gleichstände / #2 beide Trefferquoten (`backtest.py`)

**Struktur:** `_alpha` `:65-75`, `RatingScore(count, hit_rate, mean_alpha)` `:93-97`, `render` `:108-126` (Label „called the direction“ `:112`), `summarize` `:184-217`. Die Trefferzählung steht in `:204`: `a * direction > 0` über `len(alphas)`, daher zählt 0 als Fehltreffer.

**Konsumenten (grep):** `cli/main.py:154` und `README.md:403` (`summarize(result).render()`), `tests/test_backtest.py:134-319` (prüft `count`, `hit_rate`, `mean_alpha` und Textfragmente: „not archived“, „Pending“, „5 … day“, „no direction“). `build/lib/` ist ein veraltetes Build-Artefakt und wird nicht angefasst. `patterns/evaluate.py` hat eigene Felder (`hit_rate_alpha/raw`, `ties_*`, `:85-88`, `:207-208`) und ist nicht betroffen.

**Kleinste Änderung:**
- `RatingScore` bekommt Felder mit Default **am Ende**, damit der positionale Konstruktor kompatibel bleibt: `ties: int = 0`, `raw_hit_rate: float | None = None`, `raw_ties: int = 0`. `hit_rate` bleibt die Alpha-Quote, jetzt aber `hits / (hits + misses)`, wobei ein Tie ist, was `a == 0` erfüllt (`-0.0 == 0` ist True, „-0.0%“ wird also abgedeckt). Gibt es nur Ties, ist das Ergebnis `None`.
- Ein `_raw(entry)` analog zu `_alpha`, aber auf `entry["raw"]` (am besten ein gemeinsamer `_pct(text)`). Ist Raw unlesbar, fällt der Eintrag nur aus dem Raw-Nenner. `count` und `mean_alpha` bleiben unverändert.
- `render`: z. B. `- Buy: n=2, beat the benchmark 50% (1 tie), price direction 100%, mean alpha +1.00% vs the benchmark`. Hold behält „no direction claimed“ (der Test `:234-236` verlangt „no direction“). Bei „nur Ties“ einen eigenen Text verwenden, etwa „no decisive outcome“, damit `None` nicht mit Hold verwechselt wird.
- Die alten Tests bleiben ohne Ties gültig (`:138`, `:206-228`). Neue Tests: Alpha `0.0` und `-0.0004` (wird auf „-0.0%“ gerundet) zählen als Tie, nicht im Nenner. Raw-Quote und Raw-Ties werden getrennt geführt. Labels erscheinen im Render-Text.

## #4 Parameter bei Entscheidung fixieren

**Writer/Parser des Tags (vollständig):** Writer `log.py:57` (pending), `:259-271` (`_resolved_tag`). Matcher `log.py:54` (Idempotenz), `:175-178` und `:230` (`endswith("| pending]")`), `:290-293` (Rotation). Parser `log.py:310-341` (`fields[3] == "pending"`, `fields[6:]` nach `resolved:`). Externe Leser: `patterns/evaluate.py:119-121, 382-387` (über `load_entries`), `scripts/state_maintenance.py:166-169` (Blockzahl gegen Entry-Zahl), `scripts/ibkr_executor.py:2309` (nur `load_entries`, **nicht anfassen**) und **`scripts/smoke/docker_smoke.sh:209`** (grept die exakte Zeile `[DATE | T | Overweight | pending]`).

**Folgerung:** Den Tag **nicht** verändern. Ein Feld hinter `pending` würde in alten Binärständen `endswith("| pending]")` brechen, also Settlement und Rotation, außerdem den Smoke-Test. Ein Feld vor `pending` verschiebt `fields[3]`, und alte Parser hielten den Eintrag dann für abgerechnet. **Empfehlung:** eine eigene Zeile im Body zwischen Tag und `DECISION:`:
```
[2026-10-20 | NVDA | Buy | pending]

SETTLEMENT: holding=5d | benchmark=SPY | entry=next_close

DECISION:
...
```
- Alte Parser ignorieren die Zeile: `_DECISION_RE` sucht `DECISION:\n` per `search`, `_REFLECTION_RE` ebenso. Das Settlement übernimmt sie über `rest.lstrip()` (`:185-187`, `:239-241`) unverändert in den abgerechneten Block. Die Blockzahl bleibt gleich (state_maintenance), Idempotenz-Scan `:53-55` greift nicht (beginnt nicht mit `[`). `_format_full`/Prompt-Injektion zeigen sie nicht.
- Parser: nur den Text **vor** dem `DECISION:`-Match nach `^SETTLEMENT: ` durchsuchen, damit LLM-Prosa das Feld nicht fälschen kann. Ergebnis: `entry["settlement"] = {"holding": "5d", "benchmark": "SPY", "entry": "next_close"}`, für Alt-Einträge `{}`. Unbekannte Keys tolerieren.
- `store_decision(..., settlement: dict | None = None)` (`log.py:32`) schreibt die Zeile nur, wenn das Argument gesetzt ist. log.py bleibt dadurch frei von Config-Wissen.
- **Zeitpunkt der Entscheidung, Konfiguration bekannt:** `trading_graph.py:388-401` (`record_decision`, `self.config`, `settlement` ist dort schon importiert). Alle Pfade laufen hier durch: propagate `:439`, CLI `cli/run.py:372`, backtest über propagate. Werte: `config.get("holding_period_days", 5)`, `settlement.resolve_benchmark(company_name, self.config)`, Konvention als Konstante `"next_close"` (Name wie `patterns/evaluate.py:163`; Settlement implementiert nur `>` start, `settlement.py:78`). `tests/test_cli_memory_log.py:22` nutzt eine Config ohne diese Keys. Deshalb immer `.get` mit Default verwenden.
- **Settlement:** `settle_pending` (`settlement.py:131`, `:135`) berechnet Benchmark und Haltedauer bisher einmal je Ticker aus der aktuellen Config. Das gehört **in die Schleife je Eintrag**: Gespeicherte Werte gewinnen, sonst gilt die Config (Rückwärtskompatibilität). Eine unbekannte `entry` wird in `result.failed` gemeldet und bleibt pending, statt still falsch abgerechnet zu werden. `reflect_on_final_decision(benchmark_name=..., holding_days=...)` erhält die Werte des Eintrags.
- **Echte Alt-Fixtures** (`fork/paper-log` @ `5541cd9`, 2026-10-17, `decision-log.md`, 16 Einträge, gelesen per `git show`): `[2026-10-09 | AAPL | Hold | +2.0% | +4.0% | 5d | resolved:2026-10-16]` (abgerechnet, Legacy-Konvention `decision_close`) und `[2026-10-12 | AAPL | Hold | pending]`. Test: beide Blöcke (gekürzt, wörtlich mit `DECISION:`/`REFLECTION:` und `<!-- ENTRY_END -->`) parsen, ergeben `settlement == {}`, und das Settlement nutzt für den Pending-Eintrag die Config. Dazu: `patterns.evaluate.log_text_to_entries` liest einen Mix aus Alt- und Neuformat, und `state_maintenance.check_decision_log` liefert `None`.

## Fallstricke

1. **Smoke-Grep** `docker_smoke.sh:209`: Der Tag muss byte-gleich bleiben. Das spricht für die Body-Zeile.
2. **Uhr in Tests:** Das neue `now` immer explizit setzen. Die Fixtures in 2026-01 bleiben nur zufällig grün.
3. **Naiver Index:** Fallback UTC, im Docstring erwähnen. yfinance liefert immer tz-aware.
4. **`hit_rate is None`** hat jetzt zwei Bedeutungen (Hold oder nur Ties). Im Render-Text unterscheiden.
5. **Rebase:** Neue Felder und Parameter nur additiv mit Defaults ergänzen. Keine Umbenennung, keine Umformatierung bestehender Zeilen. Ein Commit je Befund.
6. **Parallele Phase-6-Session:** Kein `git add -A`, nur die eigenen Dateien stagen (`.planning/debug/` ist untracked und fremd). Vor jedem Edit neu lesen.
7. **Prüfbefehle:** `.venv/Scripts/python.exe -m pytest <files> -q` und `.venv/Scripts/python.exe -m ruff check tradingagents tests` (kein `uv run`, kein Makefile).

## Offene Fragen

1. #17, zweite Klausel („Sitzung laut Börsenzeit geschlossen“): **Empfehlung: weglassen.** Das ist strenger, kostet höchstens einen Tag und braucht keine Signaturänderung an `get_closes`. Falls doch gewünscht: `history_metadata["currentTradingPeriod"]["regular"]["end"]` über einen neuen optionalen Rückgabeweg. Größer und netzabhängig. Nach KD-19 autonom entscheidbar, im SUMMARY dokumentieren.
2. #4: Sollen auch die Tags abgerechneter Einträge `bench:`/`entry:` als zusätzliche Trailing-Felder tragen (`fields[6:]` wird vom Parser schon toleriert)? **Empfehlung: nein**, die Body-Zeile bleibt ja erhalten. Weniger Diff.
