# IBKR-Anbindung — Ausführungs-Architektur im Bestand

**Erhoben:** 2026-10-11 · `main` @ `f3fc77e` · `fork/paper-log` @ `71df89d`
**Thema:** Was die Entscheidungsseite heute liefert, wie daraus eine Order wird, Idempotenz, Rückkanal, Windows-Betrieb, Fehlermodi.
**Nicht hier:** Wahl der IBKR-Bibliothek, Gateway-Login/2FA, Contract-Auflösung, Handelszeiten-Abfrage, Marktdaten-Abo — das ist der Schwesteragent („IBKR-Schnittstelle"). Wo diese Arbeit eine Schnittstelle *voraussetzt*, steht das als Annahme markiert.
**Konfidenz gesamt:** HOCH für den Bestand (jede Aussage mit `Datei:Zeile` am Arbeitsbaum geprüft), MITTEL für die IBKR-Protokollsemantik (offizielle IBKR-Doku, teils nur über Suchindex erreichbar — `interactivebrokers.com/docs/tws-api/...` antwortet auf direkten Abruf mit HTTP 403), MITTEL für die Mapping-Muster (keine normative Quelle; Branchenpraxis + zwei Open-Source-Referenzimplementierungen).

---

## 0. Kernaussagen in zehn Zeilen

1. Es existiert **kein Zeile Ausführungscode** im Repo. Suche über `*.py/*.yml/*.toml/*.md` (ohne `build/`, `.venv/`, `CHANGELOG.md`) nach `ib_insync|ibapi|place_order|order_id|orderRef|broker` findet ausschließlich Symbol-Normalisierung (`tradingagents/dataflows/symbols.py`) und Testfixtures. `scripts/PAPER_RUN.md:9-11` sagt es explizit: *„It is paper only. Nothing here places, routes, or simulates orders."*
2. Die Entscheidungsseite liefert **ein Rating-Wort pro (Ticker, trade_date)** — fünfstufig, plus zwei Nicht-Werte (`null`, `"REVIEW"`). Keine Stückzahl, keine Richtung im Order-Sinn, kein Limit, keine Ziel-Allokation.
3. Das einzige numerische Feld in der Entscheidung ist `price_target` (`tradingagents/agents/schemas.py:253`) — ein Kursziel, **kein** Limitpreis und keine Größe.
4. Die drei Artefakte auf `paper-log` **divergieren nach einem Wiederholungslauf**: `summary.json` wird überschrieben (letzter Lauf gewinnt), `index.md` wird angehängt (alle Läufe, inkl. Duplikate), `decision-log.md` behält den **ersten** Eintrag (Idempotenz-Guard `tradingagents/memory/log.py:47-55`). Das ist am 2026-10-09 real passiert und im Branch nachweisbar.
5. Die eigentliche Designlücke ist das Mapping. Empfehlung: **Zielpositions-Leiter in „Blöcken" + Differenz-Order + Toleranzband**, nicht „Signal → Kauforder".
6. IBKR bietet **keinen Idempotenz-Schlüssel**. `orderId` ist nur monoton pro Client, `orderRef` ist ein freier, nicht erzwungen eindeutiger Mitläufer-String. Idempotenz muss **lokal** gebaut werden; IBKR liefert nur den Abfrage-/Abgleichpfad (`reqOpenOrders`, `reqAllOpenOrders`, `reqCompletedOrders`, `reqExecutions`).
7. `tradingagents/dataflows/files.py:36-49` (`locked`) taugt als Mutex **zwischen Prozessen auf einer Maschine** und ist auf Windows implementiert (`msvcrt.locking`, `files.py:67-88`). Es taugt **nicht** als Schutz gegen „Order platziert, Prozess gestorben, nichts protokolliert" — dafür braucht es ein Write-Ahead-Ledger.
8. Fills **nicht** auf `paper-log` zurückschreiben. Der CI-Commit-Schritt (`.github/workflows/daily-paper-run.yml:194-211`) macht `reset --hard FETCH_HEAD` → `commit` → `push HEAD:paper-log` ohne Rebase/Retry. Ein zweiter Schreiber kostet im Konfliktfall **einen ganzen Entscheidungstag** (so auch dokumentiert in `scripts/STATE_OPERATIONS.md:233-236`). Empfehlung: eigener Branch, ein Schreiber pro Branch.
9. Windows: **Task Scheduler**, nicht Dienst, nicht Dauerläufer. Die drei entscheidenden Einstellungen sind „Run task as soon as possible after a scheduled start is missed", „Do not start a new instance" und „Run whether user is logged on or not".
10. Der Zeitversatz ist der Kern des Entwurfs: CI entscheidet 06:30 UTC, die US-Sitzung öffnet 13:30 UTC (EDT) / 14:30 UTC (EST). Ein Samstagslauf ist erst Montag ausführbar. Die prüfbare Regel lautet nicht „Entscheidung ist jünger als X Stunden", sondern **„zwischen `trade_date` und dem Ausführungsfenster hat keine reguläre Sitzung geschlossen"**.

---

## 1. Was die Entscheidungsseite heute genau liefert

### 1.1 `runs/<trade_date>/summary.json` — Schema `schema_version: 1`

Erzeugt in `scripts/daily_paper_run.py:420-434` (Kopf) und `:470-479` (`totals`), geschrieben `:487`, auf den Branch kopiert `:323-331`. Die Versionsnummer steht in `:43` („Bumped when the shape of summary.json changes in a non-additive way").

Wörtlich, am Beispiel `git show fork/paper-log:runs/2026-10-09/summary.json`:

| Feld | Typ / Wert im Original | Quelle | Für die Ausführung brauchbar? |
|---|---|---|---|
| `schema_version` | `1` | `daily_paper_run.py:43,421` | ja — Vertragsprüfung |
| `started_at` | `"2026-10-11T12:22:46.050904+00:00"` | `:419,422` | ja — **Laufzeit**, nicht Handelszeit |
| `finished_at` | `"2026-10-11T12:24:58.587229+00:00"` | `:484` | ja |
| `trade_date` | `"2026-10-09"` | `:424` ← `resolve_trade_date` `:114-122` | ja — **der Zeitbezug der Analyse** |
| `provider` | `"anthropic"` | `:425` | nein (Provenienz) |
| `deep_think_llm` / `quick_think_llm` | `"claude-sonnet-5-5"` / `"claude-haiku-5-5"` | `:426-427` | nein |
| `max_cost_per_run_usd` / `max_total_cost_usd` | `1.5` / `1.5` | `:428-429` | nein |
| `commit` | `"07f4e67bf65d8751ad212c1c35da5e8b74e06115"` | `:430` ← `os.environ["GITHUB_SHA"]` | **Achtung:** das ist der **Code**-SHA auf `main` (`git cat-file -t 07f4e67` → `commit`, enthalten in `main`), **nicht** der `paper-log`-Commit. Der ist `71df89d` und steht nirgends in der Datei. |
| `status` | `"ok"` \| `"partial"` \| `"failed"` | `:431`, gesetzt `:480-483` | ja — Vorbedingung |
| `totals` | `{tickers, cost_usd, tokens_in, tokens_out, ok, failed, budget_aborted, skipped}` | `:470-479` | nein |
| `runs[]` | Liste, ein Objekt je Ticker | `:433` | ja |

Pro `runs[]`-Element (`run_ticker`, `daily_paper_run.py:292-320`; Skip-Variante `:448-458`):

| Feld | Werte | Quelle |
|---|---|---|
| `ticker` | `"AAPL"` | `:296` |
| `status` | `"ok"` \| `"failed"` \| `"budget_aborted"` \| `"skipped"` | `:297,311,314,450` |
| `signal` | **`null`** oder `"Buy"`/`"Overweight"`/`"Hold"`/`"Underweight"`/`"Sell"` oder **`"REVIEW"`** | `:298,308` ← `graph.propagate` → `run_rating` |
| `cost_usd`, `tokens_in`, `tokens_out`, `duration_s` | Zahlen | `:299-302,319` |
| `report` | `"/home/runner/work/TradingAgents/TradingAgents/paper-run-out/reports/AAPL/complete_report.md"` | `:309` — **Runner-Pfad, lokal unbrauchbar.** Der gleiche Report liegt auf dem Branch als `runs/<date>/<TICKER>.md` (`:328-331`). |
| `error` | `null` oder `"<Typ>: <Text>"` | `:303,312,315` |

### 1.2 Die Signal-Werte — 5-stufig, nicht 3-stufig

Die Frage aus dem Auftrag ist eindeutig beantwortbar: **im Summary landet die 5-stufige Portfolio-Manager-Skala**, nicht die 3-stufige Trader-Skala.

* `propagate` gibt `(final_state, run_rating(final_state))` zurück — `tradingagents/graph/trading_graph.py:440`, Docstring `:193-197`.
* `run_rating` liest `final_state["final_rating"]`, sonst parst es die PM-Entscheidung — `tradingagents/agents/rating.py:106-112`.
* `final_rating` entsteht aus `PortfolioDecision.rating`, Typ `PortfolioRating` = `Buy|Overweight|Hold|Underweight|Sell` — `tradingagents/agents/schemas.py:66-74,230-239`.
* Die 3-stufige `TraderAction` (`Buy|Hold|Sell`, `schemas.py:76-87`) ist eine **Zwischenstufe**: sie landet in `trader_investment_plan` (`tradingagents/agents/trader/trader.py:93-96`), wird in den vollen Zustandslog geschrieben (`trading_graph.py:512`) und in den Report gerendert (`schemas.py:191-213`, inkl. der Altlast-Zeile `FINAL TRANSACTION PROPOSAL: **BUY**`) — aber **nie** in `summary.json["runs"][*]["signal"]`.
* Zusätzlich existiert `"REVIEW"` (`rating.py:26-30`) als Sentinel für „kein lesbares Rating". Der Kommentar ist für die Ausführung bindend: *„It is not a tradeable position"*, und `is_review` (`rating.py:115-117`) ist der vorgesehene Guard.

Beobachteter Wert im Bestand: genau **ein** erfolgreicher Lauf, Signal `"Hold"` (`runs/2026-10-09/summary.json`, `index.md` letzte Zeile). Alle 37 vorherigen Zeilen in `index.md` sind `failed` mit Signal `-` (kein API-Guthaben, dokumentiert in `scripts/PAPER_RUN.md:30-34`).

### 1.3 `decision-log.md` — der eigentliche Entscheidungsdatensatz

Format: Tag-Zeile + `DECISION:`-Block, Blöcke getrennt durch `<!-- ENTRY_END -->` (`tradingagents/memory/log.py:15,57-58`).

Wörtlich auf dem Branch:

```
[2026-10-09 | AAPL | Hold | pending]

DECISION:
**Rating**: Hold

**Executive Summary**: Hold AAPL at your existing standard allocation. ...

**Investment Thesis**: ...

**Price Target**: 342.0

**Time Horizon**: 2-6 weeks, ...

<!-- ENTRY_END -->
```

Tag-Felder: `[trade_date | ticker | rating | pending]`, nach Settlement `[trade_date | ticker | rating | +x.x% | +y.y% | Nd | resolved:YYYY-MM-DD]` (`log.py:57` bzw. `:258-271`). Der Parser ist öffentlich und wiederverwendbar: `TradingMemoryLog.load_entries()` → `[{date, ticker, rating, pending, raw, alpha, holding, resolved, decision, reflection}]` (`log.py:76-87,310-341`).

**Das ist die maschinenlesbarste und gleichzeitig idempotenz-sicherste Quelle**, weil `store_decision` bereits einen Guard auf genau dem Schlüssel hat, den die Ausführung braucht (`log.py:47-55`):

```python
if line.startswith(f"[{trade_date} | {ticker} |") and line.endswith("]"):
    return
```

Kommentar dort: *„Any entry for this ticker and date blocks another, pending or settled."*

### 1.4 `index.md` — Append-only, mit Duplikaten

Kopf `daily_paper_run.py:53-58`, Zeilen `:264-277`. Eine Zeile je `runs[]`-Element je Lauf, **ohne** Dedup. Sichtbar im Branch: `2026-10-09 | AAPL` steht **dreimal** (zweimal `failed`, einmal `ok | Hold`). Für die Ausführung nur als Audit-Spur brauchbar, nicht als Eingang.

### 1.5 Der Divergenzfall — belegt, nicht hypothetisch

Nach einem Wiederholungslauf auf dasselbe `trade_date`:

| Artefakt | Verhalten | Code |
|---|---|---|
| `runs/<date>/summary.json` | **überschrieben** — letzter Lauf gewinnt | `shutil.copyfile(...)`, `daily_paper_run.py:327` |
| `runs/<date>/<TICKER>.md` | überschrieben | `:328-331` |
| `index.md` | **angehängt** — alle Läufe stehen da | `:275-276` |
| `decision-log.md` | **erster** Eintrag bleibt, zweiter wird verworfen | `log.py:47-55` |

Der 2026-10-09 ist genau dieser Fall: `summary.json` zeigt `ok/Hold`, `index.md` zeigt zusätzlich die zwei gescheiterten Vorläufe, `decision-log.md` hat einen Eintrag. Die Ausführung muss **eine** Quelle zur Wahrheit erklären, sonst entscheidet der Zufall des Lesezeitpunkts.

### 1.6 Zeitbezug

* `trade_date` = voriger **Wochentag** (`previous_weekday`, `daily_paper_run.py:100-111`). Börsenfeiertage sind **nicht** modelliert — der Docstring sagt es (`:105-107`), `PAPER_RUN.md:157-159` wiederholt es. An einem Feiertag ist `trade_date` ein Tag ohne Sitzung, und die Analyse nutzt die Daten der letzten echten Sitzung.
* `started_at`/`finished_at` sind **Laufzeit** in UTC, nicht Handelszeit.
* Es gibt **kein** Feld, das die Gültigkeit/Verfallszeit der Entscheidung ausdrückt. `time_horizon` ist Freitext (`schemas.py:257-259`, Beispielwert `"2-6 weeks, reassess after the next one or two sessions ..."`) und nicht parsbar.

### 1.7 Was fehlt, um daraus eine Order zu machen

| Fehlend | Status im Bestand | Konsequenz |
|---|---|---|
| **Stückzahl / Notional** | existiert nirgends als Zahl. `TraderProposal.position_sizing` ist `str \| None` mit Beispiel `'5% of portfolio'` (`schemas.py:180-183`) und landet nicht im Summary. | muss die Ausführungsseite erfinden → Abschnitt 2 |
| **Richtung im Order-Sinn** | nur implizit über die Rating-Stufe. Die einzige Richtungs-Abbildung im Repo ist `_DIRECTION = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}` (`tradingagents/backtest.py:88-90`) — und die ist explizit als *Bewertungs*-, nicht Ausführungsabbildung deklariert (`backtest.py:9-14`: *„Turning a rating into a filled order needs a quantity, a fill price and a cash ledger, none of which the system has"*). | darf nicht als Order-Richtung missbraucht werden: sie wirft Buy/Overweight und Underweight/Sell zusammen |
| **Limitpreis** | `PortfolioDecision.price_target` ist ein Kursziel (`schemas.py:253-256`), `TraderProposal.entry_price`/`stop_loss` existieren (`:164-179`), landen aber nicht im Summary und sind beide `Optional` mit dokumentiert unzuverlässiger Füllung (`_coerce_optional_float`, `:33-58`, verwirft Prozentangaben und Bereiche). | Limitpreis muss aus Marktdaten kommen (Schwesteragent) oder man nimmt Markt-Orders |
| **Ziel-Allokation** | nirgends. `PortfolioContext` (`tradingagents/portfolio.py:29-55`) ist der **Eingang** (was gehalten wird), nicht das Ziel. | Ziel-Leiter ist eine neue Entscheidung des Operators |
| **Ist-Position** | `PortfolioContext` existiert als Datentyp mit `Position(ticker, quantity, average_price)` und `cash`/`currency` (`portfolio.py:23-32`) und wird per `load_portfolio(path)` aus JSON gelesen (`:58-64`). Der Paper-Lauf übergibt heute **kein** `portfolio` (`daily_paper_run.py:307` ruft `graph.propagate(ticker, trade_date)` ohne das Argument). | **Das ist der Wiederverwendungspunkt.** Ein IBKR-Kontolesen, das `PortfolioContext` füllt und als JSON ablegt, schließt den Kreis: die Analyse sieht ab dann die echte Position (`portfolio.py:5-8`: *„Without it the agents cannot tell adding to a full position from opening a new one"*). |
| **Stop-Loss-Order** | nicht vorgesehen. Die Leitplanke „nur Markt-/Limit-Orders" schließt Stop-Orders ohnehin aus. | Stop bleibt Freitext im Report; die Ausführung setzt keinen |

---

## 2. Signal → Order: das Mapping-Muster

### 2.1 Die drei Kandidaten

| | **A — Fixbetrag pro Signalstufe** | **B — Zielposition („Target") pro Signalstufe + Differenz-Order** | **C — Alles-oder-Nichts** |
|---|---|---|---|
| Regel | `Buy → kaufe N`, `Overweight → kaufe N/2`, `Sell → verkaufe alles`, ... | Jede Stufe definiert eine **Zielmenge**; Order = `Ziel − Ist` | `Buy/Overweight → volle Position`, `Hold → nichts`, `Underweight/Sell → flat` |
| Zustand nötig? | nein | ja (Ist-Position) | ja (nur „habe ich oder nicht") |
| Verhalten bei Wiederholung | **akkumuliert** — fünf Buy-Tage = fünffache Position | **konvergiert** — fünf Buy-Tage = Zielposition, Tag 2-5 erzeugen keine Order | binär, aber stabil |
| Idempotenz | nur über einen externen Schlüssel erzwingbar; ein Fehler im Ledger = echte Doppelposition | **selbstheilend**: ein verlorener Ledger-Eintrag führt beim nächsten Lauf zur gleichen Zielposition, nicht zur doppelten | selbstheilend, aber sehr grob |
| Verhalten bei Teil-Fill | der Rest ist still verloren; der nächste Lauf addiert auf die unvollständige Position | **der Rest wird am nächsten Lauf automatisch nachgeholt**, weil `Ziel − Ist` noch eine Lücke zeigt | Teil-Fill = Zustand „halb drin", den das Modell nicht kennt |
| Informationsverlust | gering | mittel (diskrete Leiter) | hoch — 5 Stufen → 2 Zustände |
| Overweight vs. Buy unterscheidbar | ja | ja | nein |
| Fremder Eingriff (Operator handelt manuell im Paper-Konto) | wird ignoriert, Position läuft weg | wird **eingerechnet** — das Ziel gilt, egal wer die Position verändert hat | wird eingerechnet |

### 2.2 Empfehlung: Muster B, Zielpositions-Leiter in „Blöcken", long-only

**Begründung in vier Punkten:**

1. **Teil-Fill und Idempotenz fallen zusammen.** Bei B sind „Order ging verloren", „Order wurde nur teilweise gefüllt" und „Ledger-Eintrag fehlt" *derselbe* Zustand: die Ist-Position weicht vom Ziel ab, und der nächste Lauf korrigiert. Bei A sind es drei verschiedene Fehler mit drei verschiedenen Gegenmaßnahmen. Für einen unbeaufsichtigten Prozess auf einem Arbeitsplatzrechner, der nachts aus ist, ist das der entscheidende Unterschied. Das ist auch die Konvergenz, die etablierte Ausführungs-Frameworks verwenden: NautilusTrader gleicht beim Start den lokalen Zustand gegen Venue-Reports ab, bevor Strategien laufen; StockSharps `PositionTargetManager` rechnet die Differenz und handelt **nicht**, wenn die Abweichung innerhalb einer Toleranz liegt.
2. **Der Ledger wird vom Wahrheitsträger zum Beschleuniger.** Er verhindert die *Doppelorder innerhalb eines Tages* (wichtig, weil `Ziel − Ist` sofort nach einer offenen, noch nicht gefüllten Order weiterhin eine Lücke zeigt), aber ein Datenverlust im Ledger ist kein Kapitalrisiko mehr. Das ist die richtige Risikoverteilung für ein Dateisystem-basiertes Zustandsmodell, wie dieses Projekt es überall sonst hat.
3. **Es passt zur vorhandenen Semantik.** `PortfolioContext` (`portfolio.py:29-55`) beschreibt bereits *Zustand*, nicht *Transaktion*. Die PM-Entscheidung ist sprachlich eine Zielaussage, nicht eine Transaktionsaussage — die echte AAPL-Entscheidung lautet wörtlich *„Hold AAPL at your existing standard allocation. Do not add at 336–337 and do not trim now."* Ein Rating ist ein Soll-Zustand.
4. **Fremde Eingriffe werden eingerechnet.** Ein Paper-Konto, in dem der Operator zwischendurch per TWS handelt, zerstört Muster A sofort.

### 2.3 Die konkrete Leiter für Phase 1

Definition: ein **Block** ist eine vom Operator je Ticker konfigurierte **feste Stückzahl** (z. B. `AAPL: 3`). Nicht ein Notional-Betrag — Begründung unten.

| Signal | Zielposition | Anmerkung |
|---|---|---|
| `Buy` | 2 Blöcke | |
| `Overweight` | 1 Block | |
| `Hold` | **kein Ziel — Order wird unterdrückt** | nicht „1 Block": sonst eröffnet das häufigste Rating aus dem Flat eine Position. Die eine reale Entscheidung im Bestand ist ein `Hold` — das darf am Tag 1 nichts kaufen. Deckungsgleich mit `_DIRECTION["Hold"] == 0` („claims no direction", `backtest.py:88-90`). |
| `Underweight` | 0 Blöcke | |
| `Sell` | 0 Blöcke | |
| `"REVIEW"` | **keine Order, Lauf als „needs review" protokollieren** | `rating.py:26-30`, Guard `is_review` `:115-117` |
| `null` (Lauf `failed`/`skipped`/`budget_aborted`) | **keine Order** | `daily_paper_run.py:298,451` |

Order = `clamp(Ziel − Ist)`, Toleranzband: `|Ziel − Ist| < 1 Block` → keine Order. Long-only: ein negatives Ziel gibt es nicht, ein `Sell` ohne Position ist eine Nulloperation (**kein** Short).

**Bekannte, bewusste Vereinfachung:** mit einer 2-Block-Leiter und long-only fallen `Underweight` und `Sell` auf dasselbe Ziel (0) zusammen — die 5-stufige Skala verliert eine Stufe. Erweiterungspfad, sobald der Mechanismus trägt: Leiter auf 4 Blöcke (`Buy 4 / Overweight 3 / Hold – / Underweight 1 / Sell 0`), dann sind alle fünf Stufen unterscheidbar. Das sollte **nicht** in Phase 1 passieren, weil eine größere Leiter die Obergrenze pro Order erhöht und damit die erste Leitplanke aufweicht.

**Warum Stückzahl und nicht Notional:** ein Notional-Block (z. B. 1.000 USD) braucht zur Umrechnung in Stückzahl einen Referenzpreis. Der käme entweder aus einem IBKR-Marktdaten-Abo (Paper-Konten liefern ohne Abo verzögerte Daten — Thema des Schwesteragenten) oder aus dem eigenen yfinance-Pfad des Projekts, und beide bringen eine zusätzliche Fehlerquelle *in den Pfad, der Orders auslöst*. Eine konfigurierte Stückzahl macht die Leitplanke „harte Positionsgröße pro Order" trivial prüfbar (`abs(qty) <= MAX_QTY_PER_ORDER`) und braucht keinen Kurs. Der Preis fehlt dann nur noch für den Limitpreis — siehe nächster Punkt. Die Branchenpraxis würde hier Volatilitäts-Normalisierung empfehlen (fester Dollarbetrag heißt in einem Low-Vol- und einem High-Vol-Namen sehr unterschiedliches Risiko); das ist richtig, aber eine Verfeinerung für später, nicht für den ersten Durchstich mit drei Mega-Cap-Tickern.

### 2.4 Markt- oder Limit-Order?

Die Leitplanke erlaubt beides. Empfehlung für Phase 1: **Markt-Order in einem definierten Fenster innerhalb der Sitzung** (nicht in der Eröffnungsauktion, nicht in den letzten Minuten), weil:

* kein Referenzpreis nötig → eine Abhängigkeit weniger im Order-Pfad;
* eine Markt-Order hinterlässt **keine ruhende Order**. Eine nicht gefüllte Limit-Order, die über Nacht oder bis zum nächsten Entscheidungszyklus liegt, ist genau der Zustand, der die Fehlermodi „Teil-Fill unbemerkt" und „Order gegen veraltete Entscheidung" erzeugt, und sie verkompliziert `Ziel − Ist` um eine dritte Größe (Ist + offen + Ziel).

Wenn Limit-Orders gewollt sind: **Time-in-Force muss `DAY` sein**, damit keine Order den Entscheidungszyklus überlebt, und offene Orders aus dem laufenden Tag müssen vor jeder neuen Order in die Differenzrechnung eingehen (`Ziel − Ist − offen`).

---

## 3. Idempotenz pro Entscheidung — konkret

### 3.1 Der Schlüssel

**Empfehlung: `decision_key = f"{trade_date}|{ticker}"`.**

Begründung:

* Er ist **identisch** mit dem Schlüssel, den das Projekt für genau dieses Problem schon verwendet (`log.py:47-55`). Zwei verschiedene Idempotenzschlüssel für „dieselbe Entscheidung" sind eine Fehlerquelle für sich.
* Er ist **stabil** gegen Wiederholungsläufe. Der `paper-log`-Commit-SHA ist es **nicht**: ein Wiederholungslauf schreibt einen neuen Commit mit einem neuen SHA und überschreibt `runs/<date>/summary.json` (`daily_paper_run.py:327`). Mit dem SHA im Schlüssel wäre derselbe Handelstag zweimal ausführbar — das wäre eine Doppelorder per Konstruktion.
* `summary.json["commit"]` ist als Schlüsselteil **untauglich**: es ist der Code-SHA auf `main` (`:430`, verifiziert: `07f4e67` ist ein Commit auf `main`), konstant über alle Ticker eines Laufs und über mehrere Tage, wenn `main` sich nicht bewegt.
* Der `paper-log`-Commit-SHA gehört trotzdem in den Ledger — als **Provenienz**, nicht als Identität: `git rev-parse <branch>` nach dem Fetch, damit man später rekonstruieren kann, *welche Fassung* der Entscheidung gelesen wurde.

Daraus folgt eine Regel, die explizit entschieden werden muss: **die erste Entscheidung, die der Ausführer für einen `decision_key` sieht, gewinnt.** Eine spätere, abweichende Fassung derselben `(trade_date, ticker)`-Entscheidung wird protokolliert und **nicht** ausgeführt. Das ist genau die Semantik von `store_decision` (`log.py:47-55`) und macht `decision-log.md` zur konsistenten Quelle: wenn der Ausführer `decision-log.md` liest statt `summary.json`, kann der Divergenzfall aus 1.5 ihn gar nicht treffen.

**Empfohlene Lesequelle:** `decision-log.md` über `TradingMemoryLog({"memory_log_path": <lokale Kopie>}).load_entries()` (`log.py:76-87`), gefiltert auf `entry["date"] == trade_date`. Das liefert `rating` direkt und ist der einzige Eingang, der „erster Eintrag gewinnt" schon eingebaut hat. `summary.json` dient dann als **Vorbedingungsprüfung** (`status`, `runs[*].status == "ok"`) und als Querprobe: weicht das Rating im Log vom `signal` im Summary ab, ist das ein Wiederholungslauf — protokollieren, nicht ausführen.
Einschränkung, die man kennen muss: `_parse_entry` verwirft Blöcke mit weniger als vier Tag-Feldern **lautlos** (`log.py:315-319`). Deshalb muss die Integritätsprüfung aus `scripts/state_maintenance.py:141-174` (`check_decision_log`, vergleicht Blockzahl gegen Eintragszahl) **vor** dem Ableiten von Orders laufen — sie ist dafür bereits auf einen beliebigen Pfad parametrisierbar (`--memory-log`).

### 3.2 Was IBKR dafür anbietet — und was nicht

| Mechanismus | Semantik | Für Idempotenz brauchbar? | Konfidenz |
|---|---|---|---|
| `orderId` | ganzzahlig, monoton **pro Client**. Startwert kommt per `nextValidId` beim Connect; „The next valid identifier is persistent between TWS sessions"; mit mehreren Clients auf einem Konto muss die ID größer als **alle** vorherigen sein. Zurücksetzen nur in den API-Einstellungen und nur, wenn keine aktiven API-Orders existieren. Fehler **103** = „order ID is less than or equal to the order ID of a previous order from this client". | **Nein.** Verhindert nur die *technische* Wiederverwendung einer ID, nicht die *semantische* Doppelorder: zwei Orders mit verschiedenen `orderId` für dieselbe Entscheidung werden beide angenommen. | HOCH (IBKR-Doku) |
| `clientId` | Trennt API-Clients. `reqOpenOrders` liefert nur Orders **desselben** `clientId`; Statusmeldungen gehen an den Client mit derselben ID. `clientId 0` ist ein Sonderfall (bindet manuelle TWS-Orders). | Als **Zuständigkeitsgrenze** ja: ein fester `clientId` für den Ausführer macht „meine Orders" abfragbar. Als Lock **nein** — IBKR verweigert einen zweiten Connect mit derselben `clientId`, was faktisch wie ein Mutex wirkt, aber darauf darf man die Sicherheit nicht aufbauen. | HOCH |
| `orderRef` | *„user-customizable string that can be set from the API or TWS and will be associated with an order for its lifetime"*; erscheint auch im `Execution`-Objekt. | **Ja, als Korrelationsschlüssel** — dort gehört der `decision_key` hinein. **Nicht** als Eindeutigkeitsgarantie: IBKR erzwingt keine Unität. | HOCH für Existenz/Durchreichung, MITTEL für „erscheint auf *jeder* Execution" (am Paper-Konto zu verifizieren) |
| `permId` | permanente TWS-Order-ID; stabil über Sessions; 0 für Trades von außerhalb IB | **Ja, als Rückschlüssel** nach dem Platzieren: `decision_key → permId` im Ledger | MITTEL |
| `execId` | je Teil-Fill eigener Wert. Eine **Korrektur** erkennt man daran, dass eine `execId` bis auf die Ziffern nach dem letzten Punkt mit einer früheren identisch ist (`.02` korrigiert `.01`). | **Ja** — der Dedup-Schlüssel des Fill-Ledgers; die Korrektur-Regel muss implementiert sein, sonst zählt man korrigierte Fills doppelt | MITTEL |
| `reqOpenOrders` | aktive Orders **dieses** `clientId`; keine Subscription, einmalige Antwort | ja, für „liegt noch etwas offen?" | HOCH |
| `reqAllOpenOrders` | alle offenen Orders aller Clients **und** manuell in TWS platzierte; einmalige Antwort, kein Abo. Fremde Orders sind sichtbar, aber nicht änderbar. | **Ja — die richtige Abfrage für den Startup-Abgleich**, weil nur sie fremde/manuelle Orders sieht | HOCH |
| `reqCompletedOrders` | Orders **des Tages**, die nicht mehr änderbar sind (gefüllt, abgelehnt, storniert). IBKR: *„clients can use it to keep a record of submissions that can no longer be traced through reqOpenOrders"* | **Ja — unverzichtbar.** Eine gefüllte Order ist über `reqOpenOrders` unsichtbar; ohne diese Abfrage sieht der Startup-Abgleich eine platzierte Order als „nie passiert". | HOCH |
| `reqExecutions` + `ExecutionFilter` | Filter: `ClientId`, `AcctCode`, `Time` (`yyyymmdd hh:mm:ss`, nur Executions **danach**), `Symbol`, `SecType`, `Exchange`, `Side`. Standardfenster: nur Executions **seit Mitternacht** des Kontos; IB Gateway ist auf den aktuellen Handelstag begrenzt; ein leerer Filter liefert alle. | **Ja, für Fills und Teil-Fills.** Die Mitternachtsgrenze ist eine harte Designvorgabe: Fills eines Vortages sind nicht nachträglich holbar → sie **müssen** am Tag selbst persistiert werden. | HOCH für die Filterfelder (Klassenreferenz), MITTEL für die exakte Fenstersemantik (IBKR-Seiten widersprechen sich zwischen „24 Stunden" und „seit Mitternacht"; neuere Referenz nennt zusätzlich `LastNDays`, max. 7) |
| `reqGlobalCancel` | storniert **alle** offenen Orders, auch direkt in TWS platzierte | **Ja — das ist der scharfe Arm des Kill-Switch** | HOCH |

**Fazit: IBKR hat keinen Idempotenz-Schlüssel.** Es gibt keinen „Idempotency-Key"-Header wie bei modernen REST-Brokern. Was es gibt, ist ein vollständiger **Abfragepfad**, mit dem man „habe ich für diesen `decision_key` heute schon etwas platziert?" **nachträglich feststellen** kann — vorausgesetzt, der `decision_key` steht in `orderRef`, und man fragt alle drei Quellen ab (offen + abgeschlossen + Executions).

### 3.3 Was lokal persistiert werden muss: Write-Ahead-Ledger

Die Lücke, die kein Lock schließt: zwischen „`placeOrder` ist über die Leitung" und „ich habe das aufgeschrieben" kann der Prozess sterben. Deshalb **vor** dem Platzieren schreiben:

```
status: intent   → decision_key, ticker, rating, target_qty, current_qty, order_qty,
                   order_ref, client_id, paper_log_sha, written_at
status: placed   → + order_id, perm_id, placed_at
status: filled   → + exec_ids[], filled_qty, avg_price, filled_at
status: partial  → + filled_qty < order_qty, offene Restmenge
status: rejected → + Fehlercode/Text
status: skipped  → + Grund (Hold / REVIEW / Toleranzband / Kill-Switch / stale)
```

Daraus folgt die **Startup-Regel**, die vor jeder neuen Order laufen muss:

> Jeder Ledger-Eintrag im Zustand `intent` oder `placed` wird gegen IBKR aufgelöst — `reqAllOpenOrders` + `reqCompletedOrders` + `reqExecutions(ClientId=…)`, gefiltert auf `orderRef == decision_key` —, **bevor** irgendeine neue Order entsteht. Bleibt ein `intent` unauflösbar, bricht der Lauf ab und meldet, statt zu raten.

Das ist dieselbe Startup-Reconciliation, die NautilusTrader als Pflichtschritt vor dem Start der Strategien fährt („aligns cached order and position state with venue reports before trader components start"; ein Fehlschlag der Reconciliation bricht den Start ab).

**Format: JSONL oder Markdown, nicht SQLite.** Zwei Gründe aus dem Bestand: (a) `scripts/state_maintenance.py:68` schließt `.db` per `BACKUP_EXCLUDED_SUFFIXES` aus der Sicherung aus — ein SQLite-Ledger wäre nicht gesichert, selbst wenn man ihn auf die Allow-Liste nimmt (`_backup_included`, `:350-351`); (b) `STATE_OPERATIONS.md:200-205` dokumentiert, dass eine korrupte SQLite-Datei auf Abfragen weiter plausibel antwortet — eine Zeile-pro-Ereignis-Textdatei hat diesen Fehlermodus nicht und ist diffbar.

### 3.4 Taugen `files.py:locked` und `state_maintenance.py`?

**`locked` (`tradingagents/dataflows/files.py:36-49`) — ja, mit klar benannten Grenzen.**

| Prüfung | Befund |
|---|---|
| Windows-tauglich? | ja — `_hold_windows` über `msvcrt.locking`, `files.py:67-88` |
| Prozessübergreifend? | ja — Docstring `:38` („across threads and processes"), OS-Dateisperre |
| Wird beim Prozesstod freigegeben? | ja, das Betriebssystem gibt Dateisperren beim Prozessende frei → kein verklemmter Lock nach einem Absturz |
| Nicht-blockierende Variante? | ja, `wait=False` → `yield False` (`:44-48,58-60,77-79`). **Das ist die richtige Variante für den Ausführer:** ein zweiter Prozess soll nicht warten und dann doppelt handeln, er soll sich sauber beenden. |
| Grenze 1 | Rein **advisory** — nur Prozesse, die `locked()` aufrufen, respektieren ihn |
| Grenze 2 | Nur **eine Maschine**. Gegen „CI und lokaler Prozess gleichzeitig" hilft er nicht |
| Grenze 3 | `_hold_windows` sperrt ein Byte an Offset 0 der `.lock`-Datei und schleift auf `EDEADLOCK` (`:76-83`); jeder andere `OSError` wird **geworfen**. Ein Sperrversuch auf einem Netzlaufwerk o. ä. kann damit eine Ausnahme statt eines `False` ergeben — der Ausführer muss das fangen und als „nicht ausführen" behandeln, nicht als Absturz. |
| Grenze 4 | Schützt **Dateien**, nicht Netzaufrufe. Die Lücke „Order platziert, nichts geschrieben" bleibt → Ledger aus 3.3 |
| Grenze 5 | `.lock`-Dateien werden nie gelöscht (`STATE_OPERATIONS.md:240`) und `decision-log.md.lock` liegt bereits **committed** auf `paper-log` (im Tree nachweisbar), weil der CI-Commit `git add -A .` ohne Exclude macht (`daily-paper-run.yml:203`). Ein Ledger-Lock im selben Verzeichnis würde denselben Weg gehen → Ledger-Verzeichnis außerhalb jedes Git-Checkouts halten oder `.gitignore` im State-Verzeichnis anlegen. |

**`scripts/state_maintenance.py` — teilweise, und das Fehlende ist benennbar.**

| Taugt | Begründung |
|---|---|
| `verify` / `check_decision_log` (`:141-174`) | **Ja, direkt.** Prüft den Entscheidungs-Log an einem beliebigen Pfad (`--memory-log`) und erkennt genau den gefährlichen Fall: lautlos verworfene Einträge. Gehört als Vorbedingung in den Ausführer. Exit 0 = clean, 2 = Befund, 1 = Usage (`:45-47`). |
| `backup` (`:354-411`) | **Nein, nicht ohne Erweiterung.** Explizite Allow-Liste `decision-log.md`, `index.md`, `runs/**`, CLI-Log (`:382-393`). Ein Fill-Ledger ist **nicht** enthalten und würde beim ersten Backup fehlen; `.db` ist zusätzlich ausgeschlossen (`:68`). → Allow-Liste erweitern ist eine echte, kleine Aufgabe. |
| `prune` | nicht relevant — fasst nur Checkpoints und Report-Verzeichnisse an, und der Entscheidungs-Log wird bewusst nie getrimmt (`:340-341`) |

---

## 4. Rückkanal: wohin die Fills

### 4.1 Was zusammengeführt werden muss

| Soll (heute vorhanden) | Ist (neu) |
|---|---|
| `decision-log.md` Tag: `[trade_date \| ticker \| rating \| pending]` → nach Settlement `… \| +x.x% \| +y.y% \| Nd \| resolved:…]` (`log.py:258-271`) | ausgeführte Stückzahl, Durchschnittspreis, Zeitpunkt, `permId`/`execId`, Abweichung Ziel↔Ist |
| `index.md`: `trade_date, ticker, signal, status, cost, tokens, run` (`daily_paper_run.py:53-58`) | zusätzliche Spalten oder eine eigene Tabelle `trade_date, ticker, rating, target_qty, order_qty, filled_qty, avg_price, status` |
| `runs/<date>/summary.json` | — |

Wichtig: der Track-Record des Projekts misst heute **Entscheidungsqualität** (realisierter Return + Alpha gegen Benchmark, `tradingagents/memory/settlement.py`, beschrieben in `PAPER_RUN.md:140-156`), **nicht** Ausführungsqualität. Das sind zwei Größen, und sie dürfen nicht in dieselbe Spalte. Der Ausführungs-Rückkanal liefert eine **zweite** Messreihe: Slippage, Fill-Quote, Abweichung Ziel↔Ist. Die Zusammenführung ist ein Join über `(trade_date, ticker)` — derselbe Schlüssel wie der `decision_key`. Das ist genau der Grund, diesen Schlüssel nicht mit einem SHA zu verzieren.

### 4.2 Fills auf `paper-log` zurückschreiben — dafür / dagegen

**Dafür:** ein Ort, ein Join, überlebt den Rechner, ist von überall lesbar, braucht keine neue Infrastruktur.

**Dagegen — und das wiegt mehr:** der CI-Commit-Schritt verträgt keinen zweiten Schreiber. `.github/workflows/daily-paper-run.yml:144-161` holt den Branch mit `git fetch -q --depth=1 origin paper-log` und macht `git reset -q --hard FETCH_HEAD`; `:194-211` macht danach `git add -A .`, `git commit`, `git push -q origin "HEAD:$STATE_BRANCH"` — **ohne** Rebase, ohne Retry, ohne `--force-with-lease`. Pusht der lokale Ausführer zwischen dem Fetch (Minute 0) und dem Push (Minute ~7) des CI-Laufs, ist der CI-Push ein Non-Fast-Forward und schlägt fehl. Der State liegt in `$RUNNER_TEMP` (`:101`) und ist danach weg: **der ganze Entscheidungstag ist verloren**, inklusive der `pending`-Einträge, deren realisierter Return später auflösen sollte — genau was `:195-197` zu verhindern versucht. `STATE_OPERATIONS.md:233-236` benennt dieselbe Lücke bereits: *„There is no lock on `paper-log` itself. A second writer from another workflow would fail at the non-fast-forward `push`, so the failure mode is a *lost* run, not a corrupted log."* Und `PAPER_RUN.md:161-162`: *„One writer only."*

Das Zeitfenster ist klein (CI 06:30 UTC, Ausführung ab 13:30 UTC), aber nicht leer: `workflow_dispatch` ist jederzeit möglich (`daily-paper-run.yml:30-53`), der 2026-10-09-Lauf im Branch ist selbst ein manueller um 12:22 UTC, und die `concurrency`-Gruppe (`:58-62`) serialisiert nur GitHub-Läufe gegeneinander, nicht gegen einen lokalen Prozess.

### 4.3 Empfehlung

1. **Wahrheit ist der lokale Ledger.** Append-only JSONL im State-Verzeichnis des Ausführers, außerhalb jedes Git-Arbeitsbaums.
2. **Veröffentlichung auf einem eigenen Branch**, z. B. `paper-fills`, geschrieben **ausschließlich** vom lokalen Ausführer. Invariante: *ein Schreiber pro Branch*. Damit ist der Konflikt strukturell ausgeschlossen statt durch Timing gehofft.
3. **Der Join passiert beim Lesen**, nicht beim Schreiben: ein kleines Auswertungsskript liest `paper-log:decision-log.md` und `paper-fills:fills.jsonl` und erzeugt den Soll/Ist-Bericht. Niemand muss dafür in den Branch des anderen schreiben.
4. **Wenn `paper-log` trotzdem einen Fill-Verweis bekommen soll**, dann erst nachdem der CI-Schritt auf `git pull --rebase` + Retry umgestellt ist. Das ist eine Änderung am Produktionspfad und widerspricht der Projektlinie („The production path gets no new moving parts by operator decision", `STATE_OPERATIONS.md:244-245`) — also nicht in Phase 1.
5. **Nebeneffekt, der die Alarmierung gratis löst:** weil der Ausführer ohnehin auf `paper-fills` pusht, kann derselbe Commit einen Heartbeat tragen (Zeitstempel, Gateway-Status, Zahl offener Positionen). Ein CI-Cron-Job, der **nur** diesen Branch liest, wird rot, wenn der Heartbeat zu alt ist — Alarmierung über den Kanal, den das Projekt schon benutzt und liest (`PAPER_RUN.md:3-7`: ein tägliches grünes Häkchen, das bei Ausfall rot wird), **ohne** IBKR-Credentials in der CI. Siehe 5.4.

---

## 5. Betrieb auf Windows

### 5.1 Task Scheduler vs. Dienst vs. Dauerläufer

| | Task Scheduler | Windows-Dienst (z. B. via NSSM) | Dauerläufer im Nutzerkontext |
|---|---|---|---|
| Startet nach Reboot | ja | ja | nein (ohne Autostart) |
| Holt verpassten Lauf nach | **ja, eingebaut** | nein (muss die App selbst) | nein |
| Verhindert zweite Instanz | **ja, eingebaut** | implizit | nein |
| Zeitfenster eingebaut | ja | nein (App-Logik) | nein |
| Zustand zwischen Läufen | keiner → zwingt zu persistiertem Zustand, was hier **richtig** ist | im Speicher → verführt dazu, Zustand im RAM zu halten | wie Dienst, nur unzuverlässiger |
| Fehlersichtbarkeit ohne Konsole | Task-History + Exit-Code + eigene Logdatei | Event-Log + eigene Logdatei | nichts |
| Rechte/Installation | keine Installation | Admin, zusätzliche Software | keine |

**Empfehlung: Task Scheduler.** Die Zustandslosigkeit ist hier ein Vorteil, kein Mangel: ein Prozess, der jeden Tag neu startet, **muss** seinen Zustand im Ledger haben, und genau dieses Design braucht der Idempotenz-Entwurf aus Abschnitt 3. Ein Dauerläufer, der den Zustand im Speicher hält, sieht länger robust aus und ist nach dem ersten unbemerkten Absturz schlechter.

Ein **Dienst** wäre erst gerechtfertigt, wenn Intraday-Nachführung gewünscht ist (Order-Status in Echtzeit verfolgen, Teil-Fills sofort nachordern). Für einen Lauf pro Handelstag ist er Mehraufwand ohne Gegenwert.

### 5.2 Die Einstellungen, die zählen

Aus der Microsoft-Dokumentation zu Task Settings (Registerkarte *Settings*, sofern nicht anders vermerkt):

| Einstellung | Wert | Warum |
|---|---|---|
| *Run task as soon as possible after a scheduled start is missed* | **an** | Doku: *„the Task Scheduler service will start the task if the task was scheduled to run at a certain time, but for some reason (for example, the computer was turned off …) the task was not activated."* Achtung: *„By default the service waits ten minutes before starting the missed task."* Ein Dritthersteller-Hinweis warnt, dass „as soon as possible" deutlich später liegen kann als erwartet → **der Ausführer darf sich nicht auf die Startzeit verlassen, er muss seine Vorbedingungen selbst prüfen** (Handelszeit, Entscheidungsalter). |
| *If the task is already running, then the following rule applies* | **Do not start a new instance** | Doku: *„The Task Scheduler service will not run the new instance of the task and will not stop the instance that is already running."* Erste Verteidigungslinie gegen zwei parallele Ausführer. Zweite Linie bleibt `locked(..., wait=False)` (3.4). |
| *Stop the task if it runs longer than* | z. B. 30 min | begrenzt einen hängenden Gateway-Connect |
| *If task fails, restart every* | z. B. 10 min, 3 Versuche | nur sinnvoll, **weil** der Lauf idempotent ist — sonst ist Auto-Retry eine Doppelorder-Maschine |
| *Run whether user is logged on or not* (Register *General*) | an | sonst läuft nichts auf einem gesperrten Rechner. **Annahme/Risiko:** das IB-Gateway ist eine GUI-Anwendung und braucht i. d. R. eine interaktive Sitzung — die Verträglichkeit beider Einstellungen ist am konkreten Setup zu prüfen und gehört zum Thema des Schwesteragenten. |
| *Wake the computer to run this task* (Register *Conditions*) | an, wenn der Rechner schlafen darf | nicht Standard. Scheitert der Weckzeitgeber, protokolliert der Scheduler **Event-ID 410** („Task Scheduler service failed to set a wakeup timer"). |
| *Start the task only if the computer is on AC power* (Register *Conditions*) | **aus** erwägen | sonst läuft auf einem Notebook im Akkubetrieb nichts, und zwar lautlos |

### 5.3 Verpasster Lauf (Rechner aus)

Drei Fälle, drei Antworten:

1. **Rechner aus zur Startzeit, an während der Sitzung** → Catch-up greift (plus mindestens 10 min Verzug). Der Ausführer prüft dann selbst: Handelszeit? Entscheidung noch aktuell (5.5)? Wenn ja → ausführen, wenn nein → `status: skipped` mit Grund.
2. **Rechner den ganzen Tag aus** → kein Lauf. Der nächste Lauf findet eine Entscheidung mit einem dazwischenliegenden Sitzungsschluss und **überspringt** sie (Fehlermodus „Order gegen veraltete Entscheidung"). Entscheidend: das Überspringen muss **protokolliert und sichtbar** sein, nicht still.
3. **Mehrere Tage aus** → der Ledger zeigt eine Lücke. Weil das Mapping zielbasiert ist (Abschnitt 2), gibt es nichts nachzuholen: der erste Lauf danach stellt die Zielposition der **aktuellen** Entscheidung her. Das ist der zweite große Vorteil von Muster B.

### 5.4 Fehler sehen, ohne Konsole

Vier Ebenen, alle nötig:

1. **Exit-Code**, nach dem Vorbild des Repos (`daily_paper_run.py:13-19,36-40`; `state_maintenance.py:45-47`). Vorschlag: `0` ok · `1` Konfigurationsfehler, nichts getan · `2` Vorbedingung nicht erfüllt (kein Handelstag / keine neue Entscheidung) · `3` Gateway nicht erreichbar · `4` Kill-Switch aktiv · `5` Order abgelehnt · `20` Reconciliation ungelöst, Lauf abgebrochen. Der Code landet in der Task-History als „Last Run Result".
2. **Task-History** — auf Windows 10/11 **standardmäßig aus**. Einschalten über *Enable All Tasks History* im Kontextmenü der Task Scheduler Library, oder per `wevtutil set-log Microsoft-Windows-TaskScheduler/Operational /enabled:true` (erhöhte Rechte). Ohne das sieht man hinterher nicht, ob der Task überhaupt lief.
3. **Eigene Logdatei** mit absolutem Pfad, UTF-8, rotierend. UTF-8 ist im Projekt Konvention (`MILESTONE.md:36`: durchgängig explizites `encoding="utf-8"`, #543/#550/#576) und auf Windows nicht optional.
4. **Externer Heartbeat** — der wichtigste Punkt, weil 1-3 nur sichtbar sind, wenn jemand nachschaut. Der Push auf `paper-fills` (4.3) trägt den Zeitstempel; ein CI-Cron liest den Branch, vergleicht gegen die erwartete Kadenz und wird rot, wenn er zu alt ist. Damit erbt die Ausführung dieselbe Ausfallmeldung, die der Paper-Lauf schon hat, und die CI braucht **keine** IBKR-Credentials — sie liest nur einen Branch. Das ist konform mit der gesetzten Entkopplung.

### 5.5 Der Zeitversatz — Entwurfspunkt, nicht Detail

| Ereignis | Zeit (UTC) | Quelle |
|---|---|---|
| CI-Analyse startet | **06:30**, Di–Sa | `cron: '30 6 * * 2-6'`, `daily-paper-run.yml:26-29` |
| Laufdauer | ~2 min je Ticker (2026-10-09: 12:22:46 → 12:24:58 für einen Ticker), Timeout 60 min | `summary.json`, `daily-paper-run.yml:68` |
| `trade_date` der Analyse | voriger **Wochentag** | `previous_weekday`, `daily_paper_run.py:100-111` |
| US-Regelsitzung | 09:30–16:00 America/New_York = **13:30–20:00 UTC (EDT)** / **14:30–21:00 UTC (EST)** | Sitzungszeiten; EDT/EST-Umstellung nicht im Repo modelliert |
| Frühestes Ausführungsfenster | **+7:00 h (EDT)** bzw. **+8:00 h (EST)** nach dem CI-Start | |

Daraus:

* **Di–Fr:** Entscheidung über den Schluss von Tag *n−1*, ausgeführt bei Eröffnung Tag *n* → eine Übernachtslücke (ca. 17,5 h zwischen Datenstand und Ausführung). Das ist der Normalfall und akzeptabel.
* **Samstag:** `trade_date` = Freitag, frühestes Ausführungsfenster Montag 13:30 UTC → ca. **65,5 h** zwischen Freitagsschluss und Ausführung. In Sitzungen gezählt liegt **keine** Sitzung dazwischen — die Entscheidung ist also formal nicht veraltet, die Welt aber zwei Tage weiter. **Das muss der Operator explizit entscheiden:** Samstagsentscheidung am Montag ausführen oder verwerfen. Empfehlung: ausführen, aber als `weekend_gap` markieren, damit die Auswertung später beide Fälle trennen kann.
* **Montag:** kein CI-Lauf (Cron ist Di–Sa). Der Montagslauf des Ausführers verarbeitet die Samstagsentscheidung.
* Die Cron-Zeit ist **fix in UTC**, die deutsche Ortszeit wandert also (08:30 MESZ / 07:30 MEZ) und die US-Eröffnung wandert in UTC (13:30/14:30). Der Ausführer darf keine UTC-Uhrzeit hart kodieren, sondern muss gegen die Sitzung rechnen (Zeitzonen-Auflösung: `pytz` ist bereits Abhängigkeit, `pyproject.toml:21`; die Handelszeiten-Abfrage selbst ist Thema des Schwesteragenten).

**Die prüfbare Aktualitätsregel** (robust gegen Wochenende und Feiertag, weil in Sitzungen gezählt, nicht in Stunden):

> Eine Entscheidung ist ausführbar, wenn zwischen ihrem `trade_date` und dem aktuellen Ausführungsfenster **keine** reguläre Sitzung geschlossen hat.

Gegenprobe an den Fällen: Di-Lauf, `trade_date`=Mo → keine Sitzung dazwischen → ja. Sa-Lauf am Mo ausgeführt, `trade_date`=Fr → dazwischen Sa/So, keine Sitzung → ja. Lauf am Mi verpasst, Do nachgeholt, `trade_date`=Di → die Mittwochssitzung hat dazwischen geschlossen → **nein**. Feiertag am Montag, Di-Lauf mit `trade_date`=Mo (kein Sitzungstag), Ausführung Di → keine Sitzung dazwischen → ja.

---

## 6. Fehlermodi, die echten Schaden anrichten

### 6.1 Doppel-Order — Schwere: hoch

**Wie es passiert:** Catch-up-Lauf plus regulärer Lauf; Auto-Retry nach Timeout, bei dem `placeOrder` tatsächlich durchkam; zwei parallele Prozesse; manueller Start neben dem geplanten.

**Warum es hier besonders leicht passiert:** `orderId` monoton zu halten verhindert es **nicht** — zwei verschiedene IDs für dieselbe Entscheidung sind beide gültig (3.2). Und bei Muster A (Fixbetrag) wäre das Ergebnis eine echte Doppelposition.

**Gegenmaßnahme (gestaffelt, alle vier):**
1. Zielpositions-Mapping (Abschnitt 2) — der zweite Lauf rechnet `Ziel − Ist` und findet keine Lücke.
2. Ledger-Guard auf `decision_key`, Write-Ahead (3.3).
3. `locked(<ledger>, wait=False)` → bei nicht erhaltenem Lock sauber beenden, nicht warten (3.4).
4. Task Scheduler *Do not start a new instance* (5.2).
5. Startup-Reconciliation über `orderRef` gegen `reqAllOpenOrders` + `reqCompletedOrders` + `reqExecutions` (3.3) — die einzige Maßnahme, die auch den Fall „platziert, aber nicht protokolliert" fängt.

**Erkennung:** Zahl der Orders pro `decision_key` > 1 im Ledger; Ist-Position > Ziel nach einem Lauf.

### 6.2 Order gegen veraltete Entscheidung — Schwere: hoch

**Wie es passiert:** Rechner war zwei Tage aus, Catch-up feuert; Entscheidung vom Samstag wird Mittwoch ausgeführt; ein Wiederholungslauf überschreibt `summary.json` mit einem anderen Signal (1.5), während der Ausführer die alte Fassung gelesen hat.

**Gegenmaßnahme:**
1. Die Aktualitätsregel aus 5.5 als harte Vorbedingung, Verstoß → Exit 2 mit protokolliertem Grund, niemals still.
2. **`decision-log.md` als Lesequelle**, nicht `summary.json` — der Divergenzfall kann dann nicht auftreten (3.1).
3. Querprobe Rating (Log) gegen `signal` (Summary); Abweichung → nicht ausführen, meldepflichtig.
4. Der gelesene `paper-log`-SHA im Ledger, damit nachträglich rekonstruierbar ist, welche Fassung gehandelt wurde.

**Erkennung:** Differenz zwischen `trade_date` und Ausführungszeitpunkt in Sitzungen > 0; Rating-Abweichung zwischen den Quellen.

### 6.3 Teil-Fill unbemerkt — Schwere: mittel bis hoch

**Wie es passiert:** eine Limit-Order füllt teilweise und bleibt liegen; `reqExecutions` liefert pro Teil-Fill eine eigene `execId`; eine nachträgliche **Korrektur** ändert nur die Ziffern nach dem letzten Punkt der `execId` (`.01` → `.02`) und wird ohne diese Regel doppelt gezählt. Verschärfend: das Executions-Fenster ist auf den **aktuellen Handelstag seit Mitternacht** begrenzt (IB Gateway) — ein Teil-Fill, der am Tag nicht persistiert wurde, ist am nächsten Tag nicht mehr abfragbar.

**Gegenmaßnahme:**
1. Markt-Orders in Phase 1 (2.4) — keine ruhenden Orders, kein Teil-Fill-Zustand über den Lauf hinaus. Wenn Limit, dann TIF `DAY`.
2. Fill-Ledger pro `execId` mit Dedup **und** Korrekturregel (gleiche `execId` bis auf die Ziffern nach dem letzten Punkt → ersetzen, nicht addieren).
3. Vor jeder Order `reqExecutions(ClientId=…)` + `reqCompletedOrders` **noch am selben Tag** abfragen und persistieren — nicht auf morgen verschieben.
4. Zielbasiertes Mapping holt den Rest ohnehin am nächsten Lauf nach — das ist die Auffangschicht, nicht die Lösung.
5. Nicht vergessen: Paper-Fills sind nur eine Annäherung. IBKR sagt zu seinem Simulator, es gebe *„no way to exactly replicate live markets"*. Fill-Quoten und Teil-Fill-Verhalten aus dem Paper-Konto sind kein Beweis für den Livefall.

**Erkennung:** `filled_qty != order_qty` am Laufende; Summe der Fills aus dem Ledger weicht von der IBKR-Position ab.

### 6.4 Gateway tot ohne Alarm — Schwere: hoch (stiller Totalausfall)

**Wie es passiert:** Gateway abgestürzt, 2FA abgelaufen, täglicher Neustart, Rechner aus, Task-History nie eingeschaltet. Der Ausführer bricht korrekt ab, protokolliert korrekt in eine Datei, die niemand liest — und wochenlang passiert nichts. Für die Analyse hat das Projekt dieses Problem bewusst gelöst (der tägliche CI-Lauf als Heartbeat, `PAPER_RUN.md:3-7`); die Ausführung hat **keinen** solchen Kanal.

**Gegenmaßnahme:**
1. Heartbeat-Push auf `paper-fills` bei **jedem** Lauf, auch bei „nichts zu tun" und bei „Gateway tot" (mit Grund). Ein Lauf, der nichts pusht, ist selbst ein Signal.
2. CI-Cron, der nur diesen Branch liest und bei zu altem Heartbeat rot wird → nutzt GitHubs bestehende Benachrichtigung, keine Credentials in der CI.
3. Explizite Vorbedingungsprüfung (Gateway erreichbar, Konto lesbar, Position lesbar) mit eigenem Exit-Code (`3`), bevor irgendetwas anderes passiert.
4. Task-History/Operational-Log einschalten (5.4) — sonst fehlt sogar die Information, ob der Task lief.

**Erkennung:** Heartbeat-Alter > erwartete Kadenz; Lücke in der `trade_date`-Folge des Ledgers.

### 6.5 Kill-Switch unwirksam — Schwere: hoch (die Maßnahme, auf die man sich verlässt)

**Wie es passiert:** vier klassische Varianten.
*(a)* Der Schalter wird einmal beim Start geprüft; ein Lauf, der 20 Minuten arbeitet, platziert danach weiter.
*(b)* Fail-open: die Datei fehlt / die Variable ist nicht gesetzt / das Lesen schlägt fehl → „also handeln".
*(c)* Der Schalter hält neue Orders an, lässt aber **bestehende offene Orders** liegen, die danach noch füllen.
*(d)* Der Schalter wirkt nur im geplanten Lauf, nicht im Catch-up oder im manuellen Start.

**Gegenmaßnahme:**
1. **Fail-closed:** Ausführung erfordert ein **explizites** Einschalten (z. B. `TEX_EXEC_ENABLED=1` **und** Abwesenheit einer Kill-Datei). Fehlt eines von beiden oder ist der Zustand nicht lesbar → nicht handeln. Für den Env-Teil gibt es die Projektkonvention `_ENV_OVERRIDES` (`tradingagents/default_config.py:10-34`) samt strikter Boolean-Koerzion, die einen vertippten Wert **wirft** statt still auf den Default zu fallen (`:41-45`) — genau das richtige Verhalten für einen Sicherheitsschalter.
2. **Vor jeder einzelnen Order neu prüfen**, nicht einmal pro Lauf. Billig (ein `Path.exists()`) und der einzige Weg, (a) zu schließen.
3. **Scharfer Arm:** bei aktivem Kill-Switch zusätzlich `reqGlobalCancel` — storniert *alle* offenen Orders, „including those placed directly from TWS". Das schließt (c).
4. Der Zustand muss in **jedem** Lauf protokolliert werden (`status: skipped`, Grund `kill_switch`), sonst ist ein aktiver Kill-Switch von einem toten Prozess nicht zu unterscheiden.
5. Ein Test, der genau das prüft: gesetzter Kill-Switch → kein `placeOrder`-Aufruf, Exit 4. Das ist ohne Gateway testbar (Fake/Stub), analog zu `scripts/smoke/stub_llm.py`.

**Erkennung:** jeder Lauf meldet den Schalterzustand; ein Lauf, der handelt, obwohl der Schalter an ist, ist per Testfall ausgeschlossen.

---

## 7. Offene Punkte / Grenzen dieser Erhebung

| Punkt | Status |
|---|---|
| Exaktes Lookback-Fenster von `reqExecutions` | IBKR-Seiten widersprechen sich („24 h ab Fill" vs. „seit Mitternacht"; neuere Referenz nennt `LastNDays`, max. 7). Für den Entwurf wurde die **konservative** Lesart genommen (nur aktueller Handelstag). Am Paper-Konto zu verifizieren. |
| Trägt **jede** Execution den `orderRef`? | Doku sagt, das Feld ist Teil des `Execution`-Objekts und bleibt der Order „for its lifetime"; „auf jeder Execution" ist damit nicht formal belegt. Am Paper-Konto zu verifizieren, **bevor** die Reconciliation darauf aufbaut. |
| Maximale Länge / erlaubte Zeichen in `orderRef` | nicht gefunden. `decision_key` ist mit `2026-10-09|AAPL` kurz und ASCII; falls IBKR `|` nicht mag, `_` nehmen. Zu verifizieren. |
| `Run whether user is logged on or not` + GUI-Gateway | Verträglichkeit nicht geprüft — Thema des Schwesteragenten (Gateway-Betrieb). |
| Marktdaten für einen Limitpreis | nicht geprüft (Abo-Frage am Paper-Konto) — Thema des Schwesteragenten. Die Empfehlung Markt-Order in Phase 1 umgeht die Frage bewusst. |
| Keine Vertragsprüfung für `schema_version` | `grep "schema_version" tests/test_daily_paper_run.py` → kein Treffer. Der Konsumentenvertrag ist heute unbewacht; eine Änderung an `summary.json` würde den Ausführer brechen, ohne dass ein Test rot wird. |
| `index.md` wächst mit Duplikaten | kein Mechanismus dagegen; für die Ausführung irrelevant, für die späteren Soll/Ist-Auswertungen relevant (Dedup beim Lesen nötig). |
| Backup deckt den Ledger nicht | `state_maintenance.py:382-393` Allow-Liste; Erweiterung ist eine benannte, kleine Aufgabe. |

---

## 8. Anforderungs-Kandidaten

Nummeriert, einzeln prüfbar, direkt nach `REQUIREMENTS.md` übernehmbar.

**Quelle & Vertrag**

1. Der Ausführer liest Entscheidungen **ausschließlich** aus `decision-log.md` auf dem Branch `paper-log`, geparst über `tradingagents.memory.TradingMemoryLog.load_entries()`; `runs/<trade_date>/summary.json` dient nur der Vorbedingungsprüfung. Prüfbar: der Ausführer öffnet keinen anderen Entscheidungseingang.
2. Der Ausführer verweigert den Lauf, wenn `summary.json["schema_version"] != 1`, mit Exit 1 und benannter Abweichung.
3. Der Ausführer verweigert den Lauf, wenn `scripts/state_maintenance.py verify --memory-log <lokale Kopie>` einen Befund meldet (Exit 2).
4. Eine Entscheidung ist nur ausführbar, wenn der zugehörige `runs[]`-Eintrag `status == "ok"` hat **und** `signal` einer der fünf Stufen `Buy|Overweight|Hold|Underweight|Sell` ist. `null` und `"REVIEW"` führen nie zu einer Order (`tradingagents.agents.rating.is_review` als Guard).
5. Weicht das Rating in `decision-log.md` vom `signal` in `summary.json` für dasselbe `(trade_date, ticker)` ab, wird nicht ausgeführt; der Lauf protokolliert die Abweichung und endet mit Exit 2.
6. Der Ausführer greift **nicht** auf `runs[*].report` zu (Runner-Pfad); bei Bedarf nutzt er `runs/<trade_date>/<TICKER>.md`.
7. Eine Vertragsprüfung in der Testsuite hält die Felder fest, die der Ausführer aus `summary.json` liest; eine nicht-additive Änderung an `daily_paper_run.py` lässt diesen Test fehlschlagen.

**Mapping und Größe**

8. Das Signal wird auf eine **Zielposition** abgebildet, nicht auf eine Transaktion: `Buy → 2 Blöcke`, `Overweight → 1 Block`, `Underweight → 0`, `Sell → 0`; `Hold` erzeugt **nie** eine Order.
9. Ein Block ist eine je Ticker konfigurierte **feste Stückzahl**. Es existiert keine Ableitung einer Stückzahl aus einem Kurs im Order-Pfad.
10. Die Ordermenge ist `Ziel − Ist − offen`; ist `|Ziel − Ist| < 1 Block`, wird keine Order erzeugt (Toleranzband).
11. Jede Order unterliegt einer harten Obergrenze `abs(order_qty) <= MAX_QTY_PER_ORDER`; eine Order, die sie überschreitet, wird **nicht** gekürzt, sondern abgelehnt und gemeldet.
12. Phase 1 ist **long-only**: ein negatives Ziel ist nicht darstellbar, und ein `Sell`/`Underweight` ohne Bestand ist eine protokollierte Nulloperation.
13. Phase 1 platziert **Markt-Orders** innerhalb eines konfigurierten Fensters der regulären Sitzung (nicht Eröffnungsauktion, nicht Schlussminuten). Limit-Orders, falls später zugelassen, haben zwingend Time-in-Force `DAY`.
14. Die Ist-Position stammt bei **jedem** Lauf frisch vom Broker; eine zwischengespeicherte Position wird nie zur Mengenberechnung verwendet.
15. Das Kontolesen füllt `tradingagents.portfolio.PortfolioContext` und legt es als JSON ab, sodass `load_portfolio()` es lesen kann — damit die Analyse ab Phase 1 die echte Position sieht.

**Idempotenz**

16. Der Idempotenzschlüssel ist `decision_key = "<trade_date>|<ticker>"`. Kein Commit-SHA ist Teil des Schlüssels.
17. Pro `decision_key` existiert höchstens **ein** Ausführungsversuch. Eine spätere, abweichende Fassung derselben Entscheidung wird protokolliert und nicht ausgeführt („erste Fassung gewinnt", analog `tradingagents/memory/log.py:47-55`).
18. Der `decision_key` wird als `orderRef` an die Order gehängt; der gelesene `paper-log`-Commit-SHA wird im Ledger als Provenienz geführt.
19. Der Ledger-Eintrag im Zustand `intent` wird **vor** dem Platzieren geschrieben und erst danach auf `placed`/`filled`/`partial`/`rejected` fortgeschrieben (Write-Ahead).
20. Beim Start löst der Ausführer jeden Ledger-Eintrag im Zustand `intent` oder `placed` gegen den Broker auf — `reqAllOpenOrders` **und** `reqCompletedOrders` **und** `reqExecutions(ClientId=…)`, gefiltert auf `orderRef` —, **bevor** eine neue Order entsteht. Bleibt ein Eintrag unauflösbar, bricht der Lauf mit Exit 20 ab.
21. Der Ausführer hält während des gesamten Laufs einen nicht-blockierenden Dateilock über `tradingagents.dataflows.files.locked(<ledger>, wait=False)`; erhält er ihn nicht, beendet er sich ohne jede Order.
22. Der geplante Task ist mit *Do not start a new instance* konfiguriert.
23. Der Ausführer verbindet sich mit einem festen, dokumentierten `clientId`, der kein anderer Prozess benutzt, und beginnt seine Order-IDs beim `nextValidId` der aktuellen Verbindung (nie hart kodiert).
24. Der Ledger liegt außerhalb jedes Git-Arbeitsbaums oder das State-Verzeichnis enthält eine `.gitignore` für `*.lock`/`*.tmp` — damit kein Sperr-Sidecar committet wird (wie es `decision-log.md.lock` auf `paper-log` heute passiert ist).
25. Der Ledger ist eine Append-only-Textdatei (JSONL), keine SQLite-Datei.
26. `scripts/state_maintenance.py backup` nimmt den Ledger in die Allow-Liste auf.

**Aktualität und Zeit**

27. Eine Entscheidung ist nur ausführbar, wenn zwischen ihrem `trade_date` und dem aktuellen Ausführungsfenster **keine** reguläre Sitzung geschlossen hat. Verstoß → keine Order, Exit 2, protokollierter Grund.
28. Eine Entscheidung, deren `trade_date` ein Freitag ist und die am folgenden Montag ausgeführt wird, wird als `weekend_gap` markiert, damit die Auswertung sie trennen kann.
29. Der Ausführer kodiert keine UTC-Uhrzeit für Marktöffnung/-schluss hart, sondern rechnet gegen die Sitzung in `America/New_York`.
30. Der Ausführer prüft seine Vorbedingungen selbst und verlässt sich nicht auf die Startzeit des Schedulers (Catch-up startet mit mindestens zehn Minuten Verzug und laut Fremdberichten gelegentlich deutlich später).

**Kill-Switch**

31. Ausführung ist **fail-closed**: sie erfordert eine explizit gesetzte Freigabe-Variable **und** die Abwesenheit der Kill-Datei. Fehlt eine Bedingung oder ist der Zustand nicht lesbar, wird nicht gehandelt (Exit 4).
32. Der Kill-Switch wird **unmittelbar vor jeder einzelnen Order** neu geprüft, nicht einmal pro Lauf.
33. Wird ein aktiver Kill-Switch festgestellt, storniert der Ausführer zusätzlich alle offenen Orders (`reqGlobalCancel`) und beendet sich mit Exit 4.
34. Jeder Lauf protokolliert den Zustand des Kill-Switch, auch wenn er inaktiv ist.
35. Ein Test ohne Gateway weist nach: bei aktivem Kill-Switch erfolgt kein Platzierungsaufruf und der Exit-Code ist 4.

**Rückkanal und Beobachtbarkeit**

36. Fills werden pro `execId` protokolliert; eine Korrektur (gleiche `execId` bis auf die Ziffern nach dem letzten Punkt) **ersetzt** den vorherigen Eintrag und wird nicht addiert.
37. Alle Executions und abgeschlossenen Orders eines Handelstags werden **am selben Tag** persistiert, weil das Broker-Fenster auf den aktuellen Handelstag begrenzt ist.
38. Der Ausführer schreibt **nicht** auf den Branch `paper-log`. Er veröffentlicht auf einem eigenen Branch, den ausschließlich er schreibt (Invariante: ein Schreiber pro Branch).
39. Jeder Lauf pusht einen Heartbeat (Zeitstempel, Gateway-Status, Zahl offener Orders, Schalterzustand) auf diesen Branch — auch bei „nichts zu tun" und bei „Gateway nicht erreichbar".
40. Ein CI-Job liest ausschließlich diesen Branch und wird rot, wenn der Heartbeat älter als die erwartete Kadenz ist. Er erhält **keine** IBKR-Credentials.
41. Der Soll/Ist-Bericht entsteht beim **Lesen** per Join über `(trade_date, ticker)` aus `paper-log:decision-log.md` und dem Fill-Ledger; kein Prozess schreibt dafür in den Branch eines anderen.
42. Der Ausführer verwendet dokumentierte, disjunkte Exit-Codes nach dem Vorbild von `scripts/daily_paper_run.py:13-19` und schreibt zusätzlich eine UTF-8-Logdatei mit absolutem Pfad.
43. Die Task-History bzw. das Operational-Log des Schedulers ist aktiviert (auf Windows 10/11 nicht Standard), und die Aktivierung ist im Betriebshandbuch festgehalten.
44. Die Ausführungsmetriken (Slippage, Fill-Quote, Abweichung Ziel↔Ist) werden getrennt von den Entscheidungsmetriken (realisierter Return, Alpha) geführt und nie in dieselbe Spalte geschrieben.

---

## 9. Quellen

**Bestand (HOCH — am Arbeitsbaum geprüft, `main` @ `f3fc77e`, `fork/paper-log` @ `71df89d`)**
`scripts/daily_paper_run.py` · `scripts/PAPER_RUN.md` · `scripts/STATE_OPERATIONS.md` · `scripts/state_maintenance.py` · `.github/workflows/daily-paper-run.yml` · `tradingagents/agents/rating.py` · `tradingagents/agents/schemas.py` · `tradingagents/agents/trader/trader.py` · `tradingagents/memory/log.py` · `tradingagents/dataflows/files.py` · `tradingagents/portfolio.py` · `tradingagents/backtest.py` · `tradingagents/graph/trading_graph.py` · `tradingagents/default_config.py` · `pyproject.toml` · `git show fork/paper-log:{index.md,decision-log.md,runs/2026-10-09/summary.json}`

**IBKR TWS API (HOCH/MITTEL — offizielle Doku; `interactivebrokers.com/docs/tws-api/...` liefert auf direkten Abruf HTTP 403, Inhalte daher über Suchindex und den GitHub-Pages-Spiegel bezogen, der sich selbst als „deprecated" kennzeichnet)**
- [Execution Object](https://www.interactivebrokers.com/docs/tws-api/doc/order-management/execution-details/the-execution-object) · [Execution-Klassenreferenz](https://www.interactivebrokers.com/docs/tws-api/ref/execution)
- [API client's orders (`reqOpenOrders`)](https://www.interactivebrokers.com/docs/tws-api/doc/order-management/requesting-currently-active-orders/api-clients-orders) · [All submitted orders (`reqAllOpenOrders`)](https://www.interactivebrokers.com/docs/tws-api/doc/order-management/requesting-currently-active-orders/all-submitted-orders) · [Manually Submitted TWS Orders](https://www.interactivebrokers.com/docs/tws-api/doc/order-management/requesting-currently-active-orders/manually-submitted-tws-orders)
- [Retrieving Completed Orders](https://www.interactivebrokers.com/docs/tws-api/doc/order-management/retrieving-completed-orders/introduction)
- [Cancel All Open Orders (`reqGlobalCancel`)](https://www.interactivebrokers.com/docs/tws-api/doc/orders/cancelling-an-order/cancel-all-open-orders)
- [Executions / `reqExecutions`](https://www.interactivebrokers.com/docs/tws-api/sync-doc/executions) · [ExecutionFilter-Klassenreferenz](https://interactivebrokers.github.io/tws-api/classIBApi_1_1ExecutionFilter.html)
- [Order Submission / `nextValidId`](https://interactivebrokers.github.io/tws-api/order_submission.html) · [Orders (C#-Leitfaden, `clientId`-Sequenzen)](https://www.interactivebrokers.co.jp/en/software/csharp/topics/orders.htm) · [Error Codes (103)](https://www.interactivebrokers.com/docs/tws-api/doc/error-handling/error-codes) · [message codes](https://interactivebrokers.github.io/tws-api/message_codes.html)
- [Paper-Trader-Ausführungen entsprechen nicht dem Markt (IBKR KB 252)](https://ibkb.interactivebrokers.com/article/252)

**Windows Task Scheduler (HOCH für die Settings-Semantik, MITTEL für das Catch-up-Verhalten in der Praxis)**
- [Task Settings (Microsoft Learn, archiviert)](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-server-2008-r2-and-2008/cc722178(v=ws.11))
- [Event ID 410 — Wake Computer Task Registration](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-server-2008-r2-and-2008/cc727230(v=ws.10))
- [Task Scheduler History aktivieren (pureinfotech)](https://pureinfotech.com/enable-task-scheduler-history-windows-11/) — Dritthersteller, NIEDRIG/MITTEL
- [Hinweis „as soon as possible kann deutlich später sein" (2BrightSparks)](https://help.2brightsparks.com/support/solutions/articles/43000336003) — Dritthersteller, NIEDRIG

**Muster für Zielposition / Reconciliation / Idempotenz (MITTEL — keine normative Quelle, zwei Referenzimplementierungen plus Branchenpraxis)**
- [NautilusTrader — Live trading / Execution reconciliation](https://nautilustrader.io/docs/latest/concepts/live/)
- [StockSharp — Target Position Management](https://doc.stocksharp.com/en/topics/api/strategies/target_position_management)
- [US-Patent 8712896 — Target trading system and method](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8712896) (Differenz-Order, Round-Lot-Falle)
- [NexusTrader — Reliable WS Order Flow (Idempotenzschlüssel)](https://nexustrader.readthedocs.io/en/latest/quickstart/reliable_orders.html) — NIEDRIG/MITTEL
- [Idempotente Order-Pipeline, Abgleich vor Retry (DEV Community)](https://dev.to/cvchelles/building-an-idempotent-crypto-order-pipeline-in-nodejs-9ip) — NIEDRIG
- [Signal→Notional-Mapping und Volatilitäts-Normalisierung (quantvault)](https://quantvault.org/problem-1967-from-ml-signals-to-live-trades.html) — NIEDRIG
- [fynance — Signal-Mapper mit Dead-Band](https://fynance.readthedocs.io/en/stable/_modules/fynance/signal/mappers.html) · [wraquant — Rebalance-Threshold](https://wraquant.readthedocs.io/en/stable/_modules/wraquant/backtest/position.html) — NIEDRIG/MITTEL
