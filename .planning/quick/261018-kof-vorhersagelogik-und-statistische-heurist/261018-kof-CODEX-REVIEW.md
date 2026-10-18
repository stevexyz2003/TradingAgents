---
source: codex exec (codex-cli 0.163.0, sandbox read-only), Modell gpt-6.1-sol, Reasoning Effort high
scope: committed HEAD e1a2bc0 (Zeilenangaben beziehen sich darauf; Codex las den Stand ueber Git, der Checkout lag da schon auf d5c68db)
date: 2026-10-18
note: static analysis only; Codex fuehrte weder Tests noch Code aus. Der Executor hat die Suite danach auf HEAD 33767b3 gemessen - 2662 passed, 4 skipped, 5 failed (bekannte Windows-Umgebungsfehler, keine Regression); ruff check . sauber.
---

# Quick 261018-kof, Codex-Validierung

**Hinweis zum Lauf:** Der erste Versuch scheiterte (HTTP 400, `gpt-5.5` wird vom ChatGPT-Konto nicht mehr angeboten; `codex-cli 0.137.0` konnte die Modellliste ausserdem nicht dekodieren). Der Orchestrator hat die CLI von **0.137.0 auf 0.163.0** aktualisiert. Das Modell des Kontos ist jetzt **`gpt-6.1-sol`**, nicht `gpt-5.5`. Der Lauf nutzte den unveraenderten Prompt `codex-prompt.md`. Codex hat keine Tests ausgefuehrt.

**Ergebnis laut Codex:** Die grundlegende Renditearithmetik (`raw = P_exit/P_entry - 1`, `alpha = raw - bench`) stimmt, kein BLOCKER. Nachweisbare Fehler gibt es bei Zaehlung, Datenauswahl und statistischer Freigabe im neuen Modul sowie eine Zaehlschwaeche im Upstream (`summarize`).

## Befunde

Schweregrad WARNING, wenn nicht anders angegeben; "bew." = bewiesen.

| Nr | Datei:Zeile (e1a2bc0) | Grad | Status | Befund |
|---|---|---|---|---|
| 1 | `memory/log.py:161`, `backtest.py:204` | W | bew. | Rundung auf 0,1 pp vernichtet das Vorzeichen; Nullen zaehlen in `summarize` als Fehltreffer. Das Strangmodul nimmt Ties aus dem Nenner, ist daher mit `summarize` nicht direkt vergleichbar. |
| 2 | `backtest.py:112`, `:204` | W | bew. | "called the direction" meint Benchmark-relativ (Alpha-Vorzeichen), nicht Raw-Richtung. |
| 3 | `patterns/evaluate.py:138`, `settlement.py:78/:88` | W | teils bew. | Konventionsableitung stimmt (10-09 -> 10-16 ist `decision_close`). Dass der Eintrag wirklich vor Fix #1518 abgerechnet wurde, folgt nicht aus dem Tag (`resolved` ist ein Kursdatum, kein Abrechnungszeitpunkt). |
| 4 | `backtest.py:200`, `:209`, `settlement.py:131/:135` | W | bew. | `summarize` mischt Haltedauern; Benchmark und Konvention stehen nicht im Tag; Haltedauer/Benchmark werden erst beim Settlement aus der dann aktuellen Config gewaehlt. |
| 5 | `backtest.py:197`, `:212` | W | bew. | Abgerechneter Eintrag mit unlesbarem Alpha erscheint als pending. |
| 6 | `memory/log.py:273`, `backtest.py:151/:156` | W | bew. wenn aktiv | Rotation kuerzt die Historie und das Doppelzaehl-Gedaechtnis. Default aus (`default_config.py:93`). |
| 7 | `daily-paper-run.yml:75`, `patterns/evaluate.py:50` | W | Verdacht | Fester Ticker-Pool; "chosen in hindsight" behauptet mehr Herkunftswissen, als das Modul hat. |
| 8 | `backtest.py:195`, `patterns/evaluate.py:152` | W | bew. | Ueberlappende Fenster, keine Bereinigung in `summarize`; `N/holding` ist nur eine Groessenordnung, Ticker sind ueber den Markt abhaengig. |
| 9 | `settlement.py:96` | I | bew. | Alpha ist die einfache Differenz (implizites Beta 1). |
| 10 | `ohlcv.py:230`, `:251` | I | bew. | Look-ahead-Verdacht ueber `bfill` widerlegt: der Datumsfilter laeuft vor `_fill_price_gaps`; das Strangmodul nutzt `fill_gaps=False`. |
| 11 | `patterns/evaluate.py:182` | W | bew. | `MIN_N` prueft `n_independent` statt des Metrik-Nenners: 20 Faelle mit 19 Alpha-Ties ergaben `ok` und 100 % bei Nenner 1. |
| 12 | `patterns/evaluate.py:263` | W | bew. | Unlesbares Alpha verwarf auch gueltiges Raw (und umgekehrt asymmetrisch). |
| 13 | `patterns/evaluate.py:158` | W | bew. | Unabhaengigkeit ueber Wochentage statt Handelssitzungen: bei einem Feiertag ueberlappen Fenster trotzdem; gleiches Problem bei `entry_convention`. |
| 14 | `patterns/signals.py:48` | W | bew./Verdacht | Doppelte Tagesbars zaehlen mehrfach (200 Zeilen eines Tages erfuellen SMA200); tz-aware `as_of` nicht normalisiert; gemischte Offsets fragil (Verdacht). |
| 15 | `patterns/signals.py:61` | W | bew. | RSI ohne Wilder-Startwert (SMA der ersten 14): Beispiel 1x +1, 13x -1 ergibt 38,16 statt 7,14. |
| 16 | `patterns/signals.py:89` | W | bew. | MACD-Kreuz -0,1 -> 0 -> +0,1 wird uebersehen. |
| 17 | `yahoo/market.py:271`, `settlement.py:86` | W | bew. | Settlement prueft nicht, ob der Ausstiegsbar final ist; ein vorlaeufiger Tagesbar kann ein Fenster vortaeuschen und dauerhaft abgerechnet werden. |
| 18 | `patterns/signals.py:99` | I | bew. | Ausbruch ist die Close-basierte Donchian-Variante; SMA, Bollinger (ddof=0) korrekt. |
| 19 | `patterns/evaluate.py:56` | I | bew. | Wilson-Formel korrekt; Mehrfachvergleich ueber viele Zellen nicht korrigiert. |
| 20 | `patterns/evaluate.py:173` | I | bew. | Trefferdefinitionen beider Modi und getrennte Ties korrekt. |
| 21 | `patterns/evaluate.py:348` | W | bew. | Markdown zeigt die Nenner nicht; Bezugsgruppen (alle Faelle vs. unabhaengige) verschieden; `mean_alpha` ungerichtet. |
| 22 | `memory/log.py:46` | I | bew. | Doppelzaehl-Sperre korrekt; nach Rotation nicht mehr geschuetzt. |
| 23 | `rating.py:96`, `patterns/evaluate.py:304` | I | bew. | REVIEW-Fallback korrekt; kein LLM-/Settlement-/Reflector-Pfad im neuen Modul. |
| 24 | `scripts/pattern_eval.py:44` | I | bew. | `--git-ref` gegen Option-/Shell-Injection gesichert. |
| 25 | `tests/test_patterns_*.py` | W | bew. | Grenzfaelle fehlten (Feiertag, Duplikate, RSI-Seed, MACD-Null, MIN_N nach Ties). |

**Verdikt (Codex):** Kein BLOCKER. Fuer explorative Beschreibungen brauchbar; belastbare Aussagen ueber unabhaengige Trefferquoten brauchen zuerst echte Fenstertrennung, Mindestzahlen je Metrik, nachvollziehbare Nenner und dauerhaft gespeicherte Settlement-Konventionen. Die letzten vier Punkte sind mit den Fixes unten umgesetzt (ausser dem Speichern der Konventionen im Log, siehe #3/#4).

## Disposition (was mit jedem Befund geschieht)

Querpruefung: Ich habe die Behauptungen gegen den Code gelesen und fuer die Fixes jeweils zuerst einen fehlschlagenden Test geschrieben (RED bestaetigt fuer die Signalfixes) bzw. den Fehler per Test belegt.

| Nr | Disposition | Detail |
|---|---|---|
| 1 | Designfrage Operator | Rundung/Tie-als-Fehltreffer in `summarize` ist Interpretationssache und liegt im Upstream. Das Strangmodul behandelt Ties bereits explizit (aus dem Nenner). Wunsch von Codex: praezisere Werte im Log speichern - Upstream-Aenderung, nicht minimal. |
| 2 | Designfrage Operator | Beschriftung "called the direction" in `render()`; Strangmodul meldet beide Metriken. Unveraendert. |
| 3 | Keine Aktion / Designfrage | Ableitung bestaetigt. Die Herkunft des Eintrags ergibt sich aus den Zeitstempeln (Abrechnung 2026-10-17 06:59 UTC, Fix 14:56 UTC), nicht aus dem Tag; der Eintrag bleibt markiert. Konvention im Log zu speichern waere eine Upstream-Aenderung (Operator). |
| 4 | Designfrage Operator | Benchmark/Konvention/Fenster nicht im Tag; Config-Drift beim Settlement. Strangmodul warnt bei gemischten Fenstern/Konventionen. Unveraendert. |
| 5 | **Behoben** (`33767b3`), **Upstream-Kandidat** | `summarize` zaehlt nur echte offene Eintraege als pending; settled-unlesbare gehen nach `unscored`. Kleinster Patch (5 Zeilen) plus Test `test_a_settled_entry_with_unreadable_alpha_is_not_counted_as_pending`. |
| 6 | Keine Aktion | Rotation ist per Default aus und im Paper-Lauf nie gesetzt (`default_config.py:93`). Bleibt zu beobachten; `state_maintenance.py` kennt bewusst kein `rotate`. |
| 7 | **Behoben** (`c757adf`) | Warnung abgeschwaecht: "small and fixed pool ... selection effects cannot be ruled out". |
| 8 | Keine Aktion | `summarize` unveraendert (Upstream, deskriptiv korrekt). Das Strangmodul rechnet Hit-Raten nur auf unabhaengigen Faellen. Restabhaengigkeit zwischen Tickern bleibt eine Einschraenkung. |
| 9 | Keine Aktion | Beta-Warnung steht im Bericht. |
| 10 | Keine Aktion | Widerlegt, bleibt so. |
| 11 | **Behoben** (`c757adf`) | `status_alpha` / `status_raw` je Metrik, `ok` erst ab `den_* >= MIN_N`; nur Ties ergibt `insufficient`. Tests `test_min_n_gate_applies_per_metric_denominator`, `test_only_ties_is_insufficient_not_ok`. |
| 12 | **Behoben** (`c757adf`) | Alpha und Raw unabhaengig; "unparseable" nur wenn beide unlesbar oder Haltedauer fehlt. Test `test_metrics_are_evaluated_independently_and_symmetrically`. |
| 13 | **Behoben** (`c757adf`) | Unabhaengigkeit und Konvention aus den Handelssitzungen des geladenen Kursindex; ohne abdeckende Sitzungsdaten Fallback auf Wochentage, als `approximate` (`~`) und per Warnung markiert. Tests mit Feiertag (`test_independence_uses_real_sessions_around_a_holiday`, `test_convention_uses_sessions_when_available`). |
| 14 | **Behoben** (`c757adf`) | Tagesbars nach Normalisierung dedupliziert (letzte Zeile gewinnt); tz-aware `as_of` wird auf das lokale Datum normalisiert. Tests: 200 Duplikate erfuellen SMA200 nicht. Gemischte Offset-Strings bleiben ein Verdacht ohne reales Vorkommen (Yahoo-Index ist einheitlich). |
| 15 | **Behoben** (`c757adf`) | RSI mit Wilder-SMA-Startwert; Test mit Codex-Beispiel (7,14). |
| 16 | **Behoben** (`c757adf`) | MACD-Kreuz ueber das letzte von null verschiedene Vorzeichen (`_cross_state`); Test -0,1 -> 0 -> +0,1. |
| 17 | **Upstream-Kandidat, nicht gepatcht** | `settlement.fetch_returns` (`settlement.py:86-93`) nimmt `get_closes` (`yahoo/market.py:271`, `yf.Ticker.history`) unbesehen: Der letzte Bar kann waehrend der laufenden Sitzung ein vorlaeufiger Tagesclose sein, den Yahoo mit positivem Preis liefert. Dann wirkt das Fenster vollstaendig, der Ausstieg wird mit einem Zwischenkurs berechnet und dauerhaft ins Log geschrieben. `ohlcv.py:151` kennt das Problem (#1150) und behandelt es fuer Indikatoren. Vorschlag: vor dem Abrechnen pruefen, dass der Ausstiegsbar vor dem heutigen Datum liegt oder der Markt geschlossen ist. Der morgendliche UTC-Lauf mindert das Risiko fuer US-Aktien; allgemein ist es nicht ausgeschlossen. Nicht minimal (Marktkalender/Zeitzone), daher nicht in dieser Aufgabe. |
| 18 | **Behoben** (`c757adf`) | Docstring nennt die Close-basierte Donchian-Variante. |
| 19 | Keine Aktion | Mehrfachvergleich ueber 24 Zellen ist bei `insufficient` ohne Wirkung; bei spaeterer Belegung beachten. |
| 20 | Keine Aktion | Bestaetigt. |
| 21 | **Behoben** (`c757adf`) | Markdown zeigt `n_all`, `n_indep`, `den a/r`, Ties je Metrik, Status je Metrik und eine Legende der Bezugsgruppen; `mean_alpha` als ungerichtet dokumentiert. Test `test_markdown_shows_denominators_and_reference_groups`. |
| 22 | Keine Aktion | Bestaetigt. |
| 23 | Keine Aktion | Bestaetigt (Importtests AST + Subprozess vorhanden). |
| 24 | Keine Aktion | Bestaetigt. |
| 25 | **Behoben** (`c757adf`) | Neue Regressionstests fuer alle genannten Grenzfaelle (siehe oben). |

## Zusammenfassung der Aenderungen

- `c757adf` `fix(patterns): apply codex review findings` (nur `tradingagents/patterns/` und seine Tests; CLI unveraendert).
- `33767b3` `fix(backtest): do not count settled entries with unreadable alpha as pending` (Upstream-Kandidat, 5 Zeilen plus Test).
- Nicht angefasst: `rating.py`, `settlement.py`, `log.py`, `ohlcv.py`, `market.py`, alle IBKR-Dateien.
