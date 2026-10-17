# Anforderungen — Meilenstein M2: IBKR Paper Execution

**Stand:** 2026-10-11 · Branch `main`, HEAD `f3fc77e` · Zielkonto IBKR Paper `DUQ634065`
**Vorgänger:** Meilenstein „Produktionsreife v0.2.x → v0.2.5" ist abgeschlossen ([MILESTONE.md](./MILESTONE.md)); bewusst offen geblieben sind dort nur P2 #6 (Observability/Alerting) und P2 #8 (Provider-Ausfall-Policy).
**Kein Versionsname:** `pyproject.toml` trägt die Upstream-Version (aktuell 0.6.0), eigene Tags gibt es seit 2026-08-18 nicht mehr. Ein „v0.3" würde mit Upstream kollidieren, deshalb heißt dieser Meilenstein `M2 — IBKR Paper Execution` und nicht nach einer Versionsnummer.

**Ziel in einem Satz:** Die Entscheidungen, die der tägliche Paper-Lauf heute protokolliert, werden gegen das IBKR-Paper-Konto `DUQ634065` tatsächlich ausgeführt, mit nachvollziehbarer Soll-Ist-Zusammenführung.

**Quellen:** `.planning/research/ibkr-execution-architecture.md` (Bestand, Mapping, Idempotenz, Rückkanal, Windows-Betrieb — 44 Anforderungs-Kandidaten) und `.planning/research/ibkr-interface.md` (Schnittstellenwahl, Bibliothekslage, 2FA, Symbol-Auflösung, Handelszeiten). Beide vom 2026-10-11. Wo eine Anforderung auf einer Stelle im Bestand sitzt, steht die Stelle als `Datei:Zeile` dabei; diese Zitate sind in den Recherchen am Arbeitsbaum geprüft.

---

## Gesetzte Entscheidungen (Operator, nicht erneut aufzurollen)

1. **Orders werden direkt platziert.** Es gibt kein vorgeschaltetes Lese-Projekt. Konto-/Positionslesen und Symbol-Auflösung sind technische Voraussetzungen *innerhalb* der ersten Phasen dieses Meilensteins, kein eigener Meilenstein.
2. **Entkoppelte Architektur.** Die Analyse bleibt in GitHub Actions (`.github/workflows/daily-paper-run.yml`) und schreibt wie heute auf `paper-log`. Ein **lokaler** Prozess liest von dort und führt gegen das Gateway aus. Die CI erhält **keine** IBKR-Credentials.
3. **Vier Leitplanken sind Pflicht, keine davon ist optional:** harte Positionsgröße pro Order · Kill-Switch per Datei/Variable · nur Markt-/Limit-Orders zu Handelszeiten · Idempotenz pro Entscheidung. Sie stehen in Abschnitt 4 und sind dort als `[L1]`…`[L4]` markiert.
4. **Credentials liegen lokal** in der gitignorierten `.env`: `IBKR_USERNAME`, `IBKR_PASSWORD`, `IBKR_ACCOUNT_ID=DUQ634065`, `IBKR_TRADING_MODE=paper`, `IBKR_HOST=127.0.0.1`, `IBKR_PORT=4002` (`.gitignore:151`).

**Stack, mit benannten Risiken:** IB Gateway im Paper-Modus (Port 4002) + `ib_async` 2.1.0 gepinnt (BSD-2-Clause, implementiert das Binärprotokoll selbst und braucht kein `ibapi` → kein GPL-Kontakt). Die Client Portal Web API ist ausgeschlossen: für Individual-Konten nur über das Client Portal Gateway authentifizierbar, und IBKR schreibt dazu wörtlich *„does not support an automated authentication process"* plus täglichen Browser-Login. Die Risiken der `ib_async`-Wahl sind Bus-Faktor 1, `main` ohne Commit seit 2025-12-06 (Arbeit liegt unreleased auf `next`), und der Dependency-Deckel `tzdata<2026.0` bei aktuellem `tzdata` 2026.5 — das geht hier nur auf, weil die `.venv` noch 2025.2 hält. `ib_async.Watchdog` ist **nicht** nutzbar, weil es einen IBC-Controller als Pflichtargument verlangt und IBC seit 2026-09-01 archiviert ist; die Reconnect-Logik wird selbst geschrieben.

---

## Lesehilfe

Jede Anforderung ist **ein prüfbarer Satz**. Wo der Satz allein nicht sagt, wie man ihn testet, folgt eine Zeile „**Nachweis:**". IDs sind stabil und werden nicht neu vergeben, auch wenn eine Anforderung später entfällt. Die Zuordnung zu Phasen steht in [ROADMAP.md](./ROADMAP.md), inklusive einer Coverage-Tabelle über alle 68 IDs.

---

## 1. Verbindung & Sicherheit

**REQ-IBKR-01** — Der Meilenstein beginnt mit einer **Messung am Konto**, nicht mit Code: gemessen und schriftlich festgehalten werden (a) ob der Login mit dem separaten Paper-Username von `DUQ634065` einen Zweitfaktor verlangt, (b) was `managedAccounts` direkt nach `connect()` liefert, (c) was `reqContractDetails` für `AAPL` und für je ein Exemplar der exotischen Klassen (`SPX`/`IND`, `GC`/`FUT`, `XAUUSD`/`CMDTY`, `EUR.USD`/`CASH`, `BTC`/`CRYPTO`) liefert — inklusive `ineligibilityReasonList` und `validExchanges` —, (d) welche Zeichen und welche Länge `orderRef` akzeptiert (insbesondere ob `|` durchgeht), (e) wie weit `reqExecutions` am Gateway tatsächlich zurückblickt (die IBKR-Seiten widersprechen sich zwischen „24 Stunden", „seit Mitternacht" und `LastNDays` ≤ 7).
> **Nachweis:** `.planning/ibkr-konto-befund.md` existiert, ist committet und enthält zu jeder der fünf Fragen eine datierte Antwort mit dem rohen Beobachtungstext, nicht nur eine Zusammenfassung.

**REQ-IBKR-02** — Der Ausgang der 2FA-Messung ist dokumentiert **entscheidend** für die Betriebsform: kein Zweitfaktor → der Wochenlogin ist automatisierbar und unbeaufsichtigter Wochenbetrieb ist möglich; Zweitfaktor → ein manueller Quittierungsvorgang pro Woche ist eine benannte, terminierte Betriebsaufgabe im Handbuch. Ein nicht dokumentierter Ausgang blockiert den unbeaufsichtigten Betrieb.
> Begründung: Die Quellenlage ist offiziell widersprüchlich — IBKR sagt „2FA is required for all users" auf *Kontoebene*, sagt aber nichts über den Prompt beim Login mit dem separaten Paper-Username; Community-Berichte widersprechen sich direkt. Das ist eine Fünf-Minuten-Messung und keine Recherchefrage.

**REQ-IBKR-03** — Der Ausführer verbindet sich ausschließlich gegen **IB Gateway im Paper-Modus** auf dem in `.env` konfigurierten Host/Port, nutzt den **separaten Paper-Username** (damit es den Live/Paper-Umschalter des Login-Fensters gar nicht gibt) und verbindet bis zur ersten echten Order mit `readonly=True`.

**REQ-IBKR-04** — **Paper-Guard:** Unmittelbar nach `connect()` prüft der Ausführer, dass die Menge der verwalteten Konten **genau** `{"DUQ634065"}` ist, und trennt bei jeder Abweichung sofort, ohne eine einzige Order gesendet zu haben; geprüft wird die exakte Kontonummer, nicht das `DU`-Präfix.
> Begründung: Der Port ist nur ein Default und in der Gateway-GUI umkonfigurierbar — „Port 4002 ⇒ es ist Paper" ist **kein** Beweis. Die `DU`/`U`-Präfixkonvention ist in keiner offiziellen IBKR-Doku belegt und taugt höchstens als zweiter Gürtel.
> **Nachweis:** Test mit einem Stub, der eine abweichende Kontomenge liefert → kein Platzierungsaufruf, Exit 8.

**REQ-IBKR-05** — Alle IBKR-Zugangsdaten kommen aus der lokal gehaltenen, gitignorierten `.env`; kein IBKR-Secret liegt in GitHub Actions, und kein CI-Job benötigt eines.
> **Nachweis:** `git ls-files .env` ist leer; eine Suche nach `IBKR` in `.github/workflows/` findet keine Secret-Referenz.

**REQ-IBKR-06** — `ib_async` ist auf **2.1.0** exakt gepinnt, `tzdata` auf `<2026.0` mitgepinnt, und die Deklaration trägt einen Kommentar, der den Grund benennt (`ib_async` 2.1.0 verlangt `tzdata<2026.0,>=2025.2`, aktuell ist `tzdata` 2026.5 — es geht nur auf, weil die `.venv` 2025.2 hält).
> **Nachweis:** Eine Auflösung in einer frischen Umgebung läuft durch; mit `tzdata>=2026.1` bricht sie (`ResolutionImpossible`) — korrigiert 2026-10-11, siehe ROADMAP Phase 2 Kriterium 6.

**REQ-IBKR-07** — Die gesamte IBKR-Nutzung liegt hinter **einem** eigenen Adapter mit höchstens zehn Methoden (`connect`, `resolve`, `is_tradable_now`, `preview`, `place`, `positions`, `open_orders`, `executions`, `cancel_all`, `health`); kein anderer Modulpfad importiert `ib_async`.
> Begründung: Bus-Faktor 1 bei `ib_async` und IBKRs laufende Protobuf-Migration. Ein Austausch gegen den offiziellen `TWSSyncWrapper` soll eine Datei kosten und nicht eine Umschreibung — mit dem Wissen, dass dieser Fallback ab TWS API 10.49 GPL-belastet ist und für einen öffentlichen Fork vorher lizenzrechtlich geklärt werden müsste.
> **Nachweis:** Eine Suche nach `ib_async` in `tradingagents/` und `scripts/` nennt genau die Adapter-Datei.

**REQ-IBKR-08** — Der Ausführer verbindet sich mit einem festen, im Handbuch dokumentierten `clientId`, den kein anderer Prozess benutzt, und beginnt seine Order-IDs beim `nextValidId` der aktuellen Verbindung; keine Order-ID ist hart kodiert.
> Zu erwartende Fehlerbilder: **326** („client id is already in use"), **103** („order ID is less than or equal to …"). `orderId`-Monotonie allein ist **kein** Idempotenzschutz — siehe REQ-IBKR-39.

**REQ-IBKR-09** — Der Ausführer behandelt die IBKR-Betriebszustände als benannte Zustände statt als Abstürze — mindestens **1100** (Verbindung verloren), **1101**/**1102** (wieder da, mit/ohne Abos), **1300** (Port geändert), **2103**/**2105** vs. **2104**/**2106**/**2158** (Farm-Status), **2110**, **326**, **502**, **504**, **507**, **321** (schreibgeschützt), **10089**/**10090** — und sendet zwischen einem `1100` und dem folgenden `1101`/`1102` keine Order; Liveness wird über eine **echte Antwort** auf einen harmlosen Probe-Request festgestellt, nicht über den Socket-Status.
> Begründung: Eine TCP-Verbindung kann „oben" aussehen, während die Gateway-Session tot ist — genau das Muster, das `ib_async.Watchdog` über seinen `probeContract` fährt. Der Watchdog selbst ist nicht nutzbar (IBC-Controller als Pflichtargument, IBC archiviert).

**REQ-IBKR-10** — Das API-Schreibrecht (Gateway-Einstellung „Read-Only" aus) wird als **dokumentierte Einmalhandlung** unmittelbar vor der ersten echten Order freigegeben; vorher scheitert jeder Platzierungsversuch nachweislich an Fehler **321** („Die API befindet sich im schreibgeschützten Modus", Order-Status `ValidationError`) — **gemessen 2026-10-11 an Gateway 10.50.1**; der in der Recherche erwartete Code **10015** trat nicht auf.
> Begründung: Read-Only macht die Lesephasen strukturell ungefährlich, und 321 ist der Laufzeitmarker dafür.
> **Korrektur aus der Messung (2026-10-11):** Read-Only ist **nicht** standardmäßig an — am laufenden Gateway war es aus, und eine Probe-Order wurde angenommen (sofort storniert, nichts gefüllt). Die Einstellung ist also eine aktive Handlung, keine Voreinstellung, auf die man sich verlassen kann. Nach dem Nachweis hat der Operator den Schreibschutz wieder deaktiviert; in den Phasen 2–4 trägt damit allein der clientseitige `readonly=True`-Parameter, was schwächer ist als die Gateway-Einstellung und in REQ-IBKR-03 entsprechend zu behandeln ist.

**REQ-IBKR-11** — Das Kontolesen liefert Bestand und freies Kapital in einen `tradingagents.portfolio.PortfolioContext` (`tradingagents/portfolio.py:29-55`) und legt ihn als JSON ab, das `load_portfolio()` (`portfolio.py:58-64`) lesen kann, sodass die Analyse die echte Position sieht.
> Begründung und Eigenwert: `scripts/daily_paper_run.py:307` ruft heute `graph.propagate(ticker, trade_date)` **ohne** `portfolio` — die Agenten entscheiden also ohne Kenntnis der eigenen Positionen, obwohl der Zieltyp fertig im Repo liegt (`portfolio.py:5-8`: *„Without it the agents cannot tell adding to a full position from opening a new one"*). Das Kontolesen verbessert damit auch die Analysequalität und ist nicht nur Zulieferer der Mengenrechnung.

**REQ-IBKR-12** — Die Ist-Position stammt bei **jedem** Lauf frisch vom Broker; ein zwischengespeicherter Positionsstand wird nie zur Mengenberechnung verwendet.

---

## 2. Entscheidungsübernahme

**REQ-IBKR-13** — Der Ausführer liest Entscheidungen **ausschließlich** aus `decision-log.md` auf dem Branch `paper-log`, geparst über `tradingagents.memory.TradingMemoryLog.load_entries()` (`tradingagents/memory/log.py:76-87`) und gefiltert auf `entry["date"] == trade_date`; `runs/<trade_date>/summary.json` dient nur der Vorbedingungsprüfung.
> Begründung: Nach einem Wiederholungslauf **divergieren** die drei Artefakte auf `paper-log` — `summary.json` wird überschrieben (`daily_paper_run.py:327`), `index.md` wird angehängt (alle Läufe inkl. Duplikate, `:275-276`), `decision-log.md` behält den **ersten** Eintrag (`log.py:47-55`). Das ist am 2026-10-09 real passiert. Nur `decision-log.md` hat „erster Eintrag gewinnt" schon eingebaut, auf genau dem Schlüssel, den die Ausführung braucht.
> **Nachweis:** Der Ausführer öffnet keinen anderen Entscheidungseingang; ein Test mit divergierenden Artefakten liefert die Fassung aus dem Log.

**REQ-IBKR-14** — Der Ausführer verweigert den Lauf mit Exit 1 und benannter Abweichung, wenn `summary.json["schema_version"] != 1`.
> **Nachweis:** Ein Vertragstest in der Testsuite hält die Felder fest, die der Ausführer aus `summary.json` liest; eine nicht-additive Änderung an `scripts/daily_paper_run.py` lässt diesen Test fehlschlagen. Heute ist dieser Konsumentenvertrag unbewacht — `schema_version` kommt in `tests/test_daily_paper_run.py` nicht vor.

**REQ-IBKR-15** — Der Ausführer verweigert den Lauf mit Exit 2, wenn `scripts/state_maintenance.py verify --memory-log <lokale Kopie>` einen Befund meldet.
> Begründung: `_parse_entry` verwirft Blöcke mit weniger als vier Tag-Feldern **lautlos** (`log.py:315-319`). `check_decision_log` (`scripts/state_maintenance.py:141-174`) vergleicht Blockzahl gegen Eintragszahl und erkennt genau diesen Fall; es ist bereits auf einen beliebigen Pfad parametrisierbar.

**REQ-IBKR-16** — Eine Entscheidung ist nur ausführbar, wenn ihr `runs[]`-Eintrag `status == "ok"` hat **und** ihr Rating eine der fünf Stufen `Buy|Overweight|Hold|Underweight|Sell` ist; `null` (Lauf `failed`/`skipped`/`budget_aborted`) und `"REVIEW"` führen **nie** zu einer Order.
> Begründung: `"REVIEW"` ist der Sentinel für „kein lesbares Rating", und der Kommentar an der Quelle ist für die Ausführung bindend: *„It is not a tradeable position"* (`tradingagents/agents/rating.py:26-30`). Guard ist `rating.is_review` (`:115-117`).

**REQ-IBKR-17** — Weicht das Rating in `decision-log.md` vom `signal` in `summary.json` für dasselbe `(trade_date, ticker)` ab, wird **nicht** ausgeführt; der Lauf protokolliert die Abweichung und endet mit Exit 2.
> Begründung: Diese Abweichung *ist* der Marker für einen Wiederholungslauf. Sie zu handeln heißt, eine Entscheidung auszuführen, die der Entscheider schon ersetzt hat.

**REQ-IBKR-18** — Der Ausführer greift **nicht** auf `runs[*].report` zu; braucht er den Report, nimmt er `runs/<trade_date>/<TICKER>.md` vom Branch.
> Begründung: Das Feld enthält den Runner-Pfad (`/home/runner/work/...`, `daily_paper_run.py:309`) und ist lokal grundsätzlich unbrauchbar.

**REQ-IBKR-19** — **Aktualitätsregel:** Eine Entscheidung ist nur ausführbar, wenn zwischen ihrem `trade_date` und dem aktuellen Ausführungsfenster **keine reguläre Sitzung geschlossen** hat; ein Verstoß führt zu keiner Order, Exit 2 und einem protokollierten Grund — niemals zu stillem Überspringen.
> Begründung: In Sitzungen gezählt, nicht in Stunden — dann ist die Regel robust gegen Wochenende und Feiertag. Gegenprobe: Di-Lauf mit `trade_date`=Mo → ja. Sa-Entscheidung am Mo ausgeführt (`trade_date`=Fr) → ja. Mi verpasst, Do nachgeholt (`trade_date`=Di) → **nein**, die Mittwochssitzung hat dazwischen geschlossen. Der Zeitversatz ist strukturell: die Analyse läuft Di–Sa 06:30 UTC (`daily-paper-run.yml:26-29`), die US-Regelsitzung öffnet 13:30 UTC (EDT) bzw. 14:30 UTC (EST).

**REQ-IBKR-20** — Eine Entscheidung mit `trade_date` Freitag, die am folgenden Montag ausgeführt wird, wird im Ledger als `weekend_gap` markiert.
> Begründung: Formal liegt keine Sitzung dazwischen, die Welt ist aber zwei Tage weiter (ca. 65,5 h). Operator-Entscheidung: ausführen, aber trennbar halten, damit die Auswertung beide Fälle später unterscheiden kann.

---

## 3. Order-Erzeugung

**REQ-IBKR-21** — Das Signal wird auf eine **Zielposition** abgebildet, nicht auf eine Transaktion: `Buy → 2 Blöcke`, `Overweight → 1 Block`, `Underweight → 0`, `Sell → 0`; `Hold` erzeugt **nie** eine Order.
> Begründung: Ein Rating ist sprachlich ein Soll-Zustand — die eine reale Entscheidung im Bestand lautet wörtlich *„Hold AAPL at your existing standard allocation. Do not add at 336–337 and do not trim now."* Zielbasiertes Mapping fasst „Order verloren", „Teil-Fill" und „fehlender Ledger-Eintrag" in **einen** selbstheilenden Zustand zusammen: die Ist-Position weicht vom Ziel ab, und der nächste Lauf korrigiert. `Hold` darf bewusst kein Ziel setzen, sonst eröffnet das häufigste Rating aus dem Flat eine Position; deckungsgleich mit `_DIRECTION["Hold"] == 0` (`tradingagents/backtest.py:88-90`).
> Bewusste Vereinfachung: Mit einer 2-Block-Leiter und long-only fallen `Underweight` und `Sell` auf dasselbe Ziel (0) zusammen — die 5-stufige Skala verliert eine Stufe. Die 4-Block-Leiter ist Erweiterungspfad, nicht M2 (siehe „Nicht in diesem Meilenstein").

**REQ-IBKR-22** — Ein **Block** ist eine je Ticker vom Operator konfigurierte **feste Stückzahl**; es existiert keine Ableitung einer Stückzahl aus einem Kurs im Order-Pfad.
> Begründung: Ein Notional-Block bräuchte einen Referenzpreis und damit eine zusätzliche Fehlerquelle *in dem Pfad, der Orders auslöst*. Eine konfigurierte Stückzahl macht die Leitplanke „harte Positionsgröße" trivial prüfbar (`abs(qty) <= MAX_QTY_PER_ORDER`) und braucht keinen Kurs.

**REQ-IBKR-23** — Die Ordermenge ist `Ziel − Ist − offen`; ist `|Ziel − Ist| < 1 Block`, wird **keine** Order erzeugt (Toleranzband).

**REQ-IBKR-24** — M2 ist **long-only**: ein negatives Ziel ist nicht darstellbar, und ein `Sell`/`Underweight` ohne Bestand ist eine protokollierte Nulloperation, kein Short.

**REQ-IBKR-25** — M2 platziert **Markt-Orders** innerhalb eines konfigurierten Fensters der regulären Sitzung (nicht Eröffnungsauktion, nicht Schlussminuten); eine später zugelassene Limit-Order hat zwingend Time-in-Force `DAY`, und offene Orders des laufenden Tages gehen in die Differenzrechnung ein.

*Geändert 2026-10-17 (Phase 5, D-10): Das Sitzungsfenster ist in Phase 5 umgesetzt (aus Phase 4 verschoben am 2026-10-16) und entspricht dem Puffer der Phase 3: Beginn +15 min, Ende −15 min über `SESSION_BUFFER_MINUTES`, Halbtage ergeben sich über `liquidHours`. Außerhalb: `skipped` mit Grund `outside_session`. Bestätigung durch den Operator im Verifikationsbericht der Phase 5.*
> Begründung: Eine Markt-Order hinterlässt keine ruhende Order. Eine nicht gefüllte Limit-Order, die bis zum nächsten Entscheidungszyklus liegt, erzeugt genau die Zustände „Teil-Fill unbemerkt" und „Order gegen veraltete Entscheidung" und verkompliziert `Ziel − Ist` um eine dritte Größe.

**REQ-IBKR-26** — Marktdaten sind **nicht** Teil des Order-Pfads: `reqMarketDataType(3)` (delayed) ist Default, und die Fehler **10089**/**10090** („API data requires subscription" / Teilabdeckung) gelten als erwartete Zustände, nicht als Fehlschlag.
> Begründung: Ob ein Paper-Konto Marktdaten-Abos erbt, ist offiziell widersprüchlich dokumentiert (Client-Portal-Guide: „market data subscriptions … are the same as specified for your regular account" vs. Marktdaten-Doku: Sharing muss eingerichtet werden, ein Live-User teilt mit genau einem Paper-Konto, laut KB 1719 zusätzlich an „gleiches Gerät" gebunden). Für ein tägliches Gate sind 15 Minuten Verzögerung irrelevant; die Abhängigkeit im Order-Pfad wäre es nicht.

**REQ-IBKR-27** — Die IBKR-Symbol-Auflösung ist ein **unabhängiger zweiter Pfad vom Roh-Ticker** und setzt nicht auf `normalize_symbol()` auf.
> Begründung: `tradingagents/dataflows/symbols.py` normalisiert verlustbehaftet auf Yahoo-Schreibweise — `XAUUSD`, `XAU` und `GOLD` werden alle zu `GC=F`, einem COMEX-Future mit Verfall, Multiplikator 100 und Margin, während IBKR für genau diesen Fall `XAUUSD` als `secType="CMDTY"` auf `SMART` führt. Wer über den Yahoo-Normalizer geht, kauft etwas Handelbares mit falschem Nominal — und das wirft keine Exception, sondern füllt das Decision-Log mit Returns, die zu einer anderen Position gehören als die Entscheidung. `normalize_symbol()` bleibt, was es ist: die Vendor-Normalisierung für Datenabfragen.

**REQ-IBKR-28** — In M2 ist die `secType`-Allow-List **`{STK}`**; jeder andere `secType` und jeder nicht explizit gemappte Roh-Ticker wird mit benannter Meldung abgewiesen, nicht „durchprobiert".
> Begründung: Die Ticker-Liste des Paper-Laufs ist `AAPL,MSFT,NVDA` (`scripts/PAPER_RUN.md`), also ausschließlich `STK`. Dass `secType="IND"` nicht orderbar ist, lässt sich **nicht** mit einem offiziellen Zitat belegen — man muss das aber auch nicht wissen, wenn man es selbst vorher ablehnt. Die breitere Allow-List `{STK, CASH, FUT, CMDTY, CRYPTO, CFD}` aus der Recherche ist dokumentierter Erweiterungspfad, nicht M2-Umfang.

**REQ-IBKR-29** — Die Auflösung besteht auf **Eindeutigkeit**: `qualifyContracts(..., returnAll=True)` muss **genau einen** Treffer liefern; null Treffer („not known") und mehrere Treffer („ambiguous") führen zum Abbruch, und die Kandidatenliste landet im Log.
> Begründung: `returnAll=True` existiert genau deshalb — ohne den Parameter gehen Konflikte nur in den Bibliotheks-Log, *„which isn't useful if you are logging to a file and not watching immediately"*. Erwartete Fehlerbilder: **200** („No security definition has been found" / „is ambiguous"), **203** („you must specify the currency").

**REQ-IBKR-30** — Der `conId` des aufgelösten Contracts wird **persistiert** und bei jedem Lauf gegen die Erwartung geprüft (`conId`, `primaryExchange`, `currency`, `localSymbol`); ab dem zweiten Lauf wird über `conId` + `exchange` geordert, und ein geänderter `conId` bei gleichem Symbol führt zu keiner Order, sondern zu einer Meldung.
> Begründung: `conId` + `exchange` ist die offiziell minimale, eindeutige Contract-Form, und IBKR empfiehlt das Persistieren selbst. Ein geänderter `conId` bei gleichem Symbol ist das Alarmsignal für eine Corporate Action. Nebeneffekt: die Pacing-Grenzen der Symbolsuche (`reqMatchingSymbols` ≥ 1 s, max. 16 Treffer, nur Aktien) entfallen nach dem ersten Lauf.

**REQ-IBKR-31** — Die **Handelbarkeit** wird abgefragt, nicht angenommen: `validExchanges` besteht nicht nur aus der Pseudo-Börse `VALUE` und enthält `SMART`, und `orderTypes` enthält `MKT` und `LMT`; leere Felder gelten als nicht handelbar. Letzte Schicht ist das `whatIf`-Preview (Phase 4).
> Begründung: `ineligibilityReasonList` ist „List of details why the account cannot trade the given security" — genau das gesuchte Signal; seine offizielle Felddokumentation ist allerdings erkennbar ein Copy-Paste-Fehler, der Inhalt ist deshalb am Konto empirisch anzusehen (REQ-IBKR-01c). `VALUE` ist „a holding exchange used for clients to close positions on a contract that is no longer listed" — man kann schließen, aber nicht eröffnen.

*Geändert 2026-10-12 (Phase 3, D-19): `ineligibilityReasonList` existiert in ib_async 2.1.0 nicht (`.planning/ibkr-konto-befund.md` §4); der frühere Wortlaut war so nicht prüfbar. Bestätigung durch den Operator im Verifikationsbericht der Phase 3.*

---

## 4. Leitplanken

Die vier Pflicht-Leitplanken sind markiert: `[L1]` Positionsgröße · `[L2]` Kill-Switch · `[L3]` Handelszeiten · `[L4]` Idempotenz. Keine ist optional, keine darf in einer Phase „nachgezogen" werden, die nach der ersten echten Order liegt.

**REQ-IBKR-32** `[L1]` — Jede Order unterliegt einer harten Obergrenze `abs(order_qty) <= MAX_QTY_PER_ORDER`; eine Order, die sie überschreitet, wird **nicht gekürzt**, sondern abgelehnt und gemeldet.
> Begründung: Eine stillschweigende Kürzung verwandelt einen Konfigurationsfehler in eine halb ausgeführte Absicht und verwischt die Spur. Deshalb ablehnen.

**REQ-IBKR-33** `[L2]` — Die Ausführung ist **fail-closed**: sie erfordert eine explizit vorhandene Freigabe-Datei (`RELEASE` im State-Ordner, mit Konto und Ablaufdatum) **und** die Abwesenheit der Kill-Datei. Fehlt eines von beiden oder ist der Zustand nicht lesbar, wird nicht gehandelt (Exit 4).

*Geändert 2026-10-17 (Phase 5, D-01/D-02/D-20): Freigabe als Datei mit Konto und „gültig bis“ (höchstens 90 Tage im Voraus, einschließlich des Tages in UTC) statt Env-Variable; unbeaufsichtigter Betrieb folgt in Phase 8. Bestätigung durch den Operator im Verifikationsbericht der Phase 5.*
> Begründung: Für den Env-Teil gibt es die Projektkonvention `_ENV_OVERRIDES` (`tradingagents/default_config.py:10-34`) samt strikter Boolean-Koerzion, die einen vertippten Wert **wirft** statt still auf den Default zu fallen (`:41-45`) — genau das richtige Verhalten für einen Sicherheitsschalter.

**REQ-IBKR-34** `[L2]` — Der Kill-Switch wird **unmittelbar vor jeder einzelnen Order** neu geprüft, nicht einmal pro Lauf.
> Begründung: Der klassische Fehlermodus ist „einmal beim Start geprüft, danach 20 Minuten weiter platziert". Die Prüfung ist ein `Path.exists()` und damit billig genug, um sie in die innere Schleife zu legen.

**REQ-IBKR-35** `[L2]` — Wird ein aktiver Kill-Switch festgestellt, storniert der Ausführer zusätzlich **alle** offenen Orders über `reqGlobalCancel` und beendet sich mit Exit 4.
> Begründung: Ein Schalter, der nur neue Orders anhält, lässt bestehende offene Orders weiter füllen. `reqGlobalCancel` storniert auch direkt in TWS platzierte Orders und ist damit der scharfe Arm.

**REQ-IBKR-36** `[L2]` — **Jeder** Lauf protokolliert den Zustand des Kill-Switch, auch wenn er inaktiv ist.
> Begründung: Sonst ist ein aktiver Kill-Switch nicht von einem toten Prozess zu unterscheiden.
> **Nachweis:** Ein Test **ohne** Gateway (Stub nach dem Muster von `scripts/smoke/stub_llm.py`) weist nach: gesetzter Kill-Switch → kein Platzierungsaufruf, Exit 4, Schalterzustand im Ledger.

**REQ-IBKR-37** `[L3]` — Eine Order entsteht nur, wenn der Ausführungszeitpunkt in einem `liquidSessions()`-Intervall des **aufgelösten** Contracts liegt; `outsideRth` bleibt in M2 aus, Handelszeiten werden aus `ContractDetails` (`tradingHours`/`liquidHours`/`timeZoneId`) gelesen und nie als Uhrzeit hart kodiert, der Cache dafür lebt höchstens einen Handelstag, und ein `HALTED`-Tick bzw. Fehler **154** verhindert die Order.
> Begründung: IBKR liefert pro Kalendertag entweder ein konkretes Fenster oder `CLOSED` — Feiertage und Halbtage kommen damit ohne eigenen Kalender mit. `ib_async` parst das bereits zeitzonenbewusst. Der tägliche Gateway-Restart existiert laut IBKR genau zum Neuladen der Contract-Definitionen, deshalb darf der Cache den Restart nicht überleben. Und: Handelszeit ist nicht Handelbarkeit — ein Contract kann mitten in den `liquidHours` angehalten sein.

*Geändert 2026-10-12 (Phase 3, D-20): Verzögerte Marktdaten liefern am Paper-Konto keinen Halted-Tick (Messung bei offener US-Sitzung, `03-RESEARCH.md` §D-20). Phase 3 liefert Sitzungsfenster, Puffer und `session-unknown` und sieht den Zustand `halted` nur in der Ergebnisschnittstelle vor; die Halt-Erkennung über Fehler **154** am `whatIf` übernimmt Phase 4. Bestätigung durch den Operator im Verifikationsbericht der Phase 3.*

**REQ-IBKR-38** — Vor **jeder** echten Order läuft ein `whatIf`-Preview (`IB.whatIfOrder()`); Margin-Impact, Kommission und ein eventuelles `rejectReason` werden protokolliert, und ein gesetztes `rejectReason` verhindert die Order. Das Preview ist nur dann aussagekräftig, wenn **REQ-IBKR-69** eingehalten ist — ohne explizites `tif` kommt es wortlos leer zurück.
> Begründung: Das ist der stärkste Einzel-Check der Kette — *„the order will undergo a credit check for the expected post-trade margin requirement without executing an order"*. Eine Order auf den falschen Contract fällt hier über Margin, Kommission oder Reject-Grund auf, **bevor** sie gesendet wird.

**REQ-IBKR-69** — Jede Order — auch eine `whatIf`-Vorschau — setzt ihre Gültigkeitsdauer (`order.tif`) **explizit**; der tatsächlich wirksame Wert wird aus dem Ergebnis zurückgelesen und protokolliert, statt dem gesetzten Wunsch zu vertrauen.
> **Begründung (gemessen 2026-10-12, siehe [ibkr-marktdaten-befund.md](./ibkr-marktdaten-befund.md) Befund 4):** `ib_async`s `LimitOrder(...)` setzt kein `tif`. Das Gateway schreibt es dann gemäß seiner **Order-Voreinstellung** um, meldet das als **10349** — und verwirft dabei die `whatIf`-Anfrage: zurück kommt eine leere Liste statt eines `OrderState`, **ohne Fehler**. Mit explizitem `tif` (`DAY` wie `GTC` geprüft) liefert dieselbe Anfrage vollständige Margin- und Kommissionswerte. Der 10349 lag bei jeder Fehlmessung vor und sah wie eine Randnotiz aus.
> **Nachweis:** Ein Test ohne gesetztes `tif` zeigt die leere Vorschau, derselbe Test mit gesetztem `tif` einen `OrderState` mit `initMarginChange`. **10349** steht in der Liste der behandelten Codes (REQ-IBKR-09).

**REQ-IBKR-70** — Die Budgetprüfung einer Order läuft über `initMarginChange` aus dem `whatIf`-Preview, das in **Kontowährung** zurückkommt; der Ausführer rechnet keinen eigenen Wechselkurs.
> **Begründung (gemessen 2026-10-12):** Auf AAPL (USD-Papier, EUR-Konto) liefert die Vorschau `initMarginChange=997.14` in **EUR** und `commission=1.00003` mit `commissionCurrency=USD` — Margin in Kontowährung, Kommission in Instrumentwährung. Damit ist die Umrechnung im Preview enthalten. Ein EUR/USD-Kurs ist über Marktdaten ohnehin nicht zu bekommen (10089, Abo nötig) und steht vor der ersten USD-Position auch nicht im Kontobericht. Ergänzt REQ-IBKR-68, das ohne Kurs in Stückzahlen rechnet.
> **Nachweis:** Der Budget-Test vergleicht gegen den EUR-Wert aus dem Preview, nicht gegen ein selbst gerechnetes Produkt aus Stückzahl und USD-Kurs.

**REQ-IBKR-39** `[L4]` — Der Idempotenzschlüssel ist `decision_key = "<trade_date>|<ticker>"`; **kein** Commit-SHA ist Teil des Schlüssels.
> Begründung: Der Schlüssel ist identisch mit dem, den das Projekt für genau dieses Problem schon benutzt (`log.py:47-55`). Zwei verschiedene Idempotenzschlüssel für „dieselbe Entscheidung" sind eine Fehlerquelle für sich. Ein `paper-log`-SHA im Schlüssel wäre eine Doppelorder per Konstruktion, weil ein Wiederholungslauf einen neuen Commit schreibt; und `summary.json["commit"]` ist ohnehin untauglich — es ist der **Code**-SHA auf `main` (`daily_paper_run.py:430`), konstant über alle Ticker eines Laufs. Derselbe Schlüssel ist später der Join-Schlüssel des Soll-Ist-Berichts (REQ-IBKR-49) — ein weiterer Grund, ihn nicht mit einem SHA zu verzieren. Falls die Messung aus REQ-IBKR-01d zeigt, dass IBKR `|` in `orderRef` nicht mag, wird `_` genommen.

**REQ-IBKR-40** `[L4]` — Pro `decision_key` existiert höchstens **ein** Ausführungsversuch; eine spätere, abweichende Fassung derselben `(trade_date, ticker)`-Entscheidung wird protokolliert und **nicht** ausgeführt („erste Fassung gewinnt", analog `log.py:47-55`).

**REQ-IBKR-41** `[L4]` — Der `decision_key` wird als `orderRef` an die Order gehängt, und der gelesene `paper-log`-Commit-SHA wird im Ledger als **Provenienz** geführt (nicht als Identität).
> Begründung: IBKR bietet keinen Idempotenz-Schlüssel; `orderRef` ist ein freier, von IBKR *nicht* auf Eindeutigkeit geprüfter Mitläufer-String und taugt nur als Korrelationsschlüssel. Dass er auf **jeder** Execution erscheint, ist offiziell nicht formal belegt und gehört zu den Messpunkten aus REQ-IBKR-01.

**REQ-IBKR-42** `[L4]` — **Write-Ahead:** Der Ledger-Eintrag im Zustand `intent` wird **vor** dem Platzieren geschrieben und erst danach auf `placed` / `filled` / `partial` / `rejected` / `skipped` fortgeschrieben; `skipped` trägt immer einen Grund (`hold`, `review`, `tolerance`, `kill_switch`, `stale`, `weekend_gap`, `size_cap`, `not_tradable`, `outside_session`).

*Geändert 2026-10-17 (Phase 5, D-11/D-18): Die Gründe sind um `source_conflict` (REQ-63), `already_attempted` und `decision_changed` (REQ-40) sowie `foreign_open_order` (D-12 aus Phase 4) ergänzt; `weekend_gap` ist eine Markierung am Eintrag (REQ-20), kein Grund. Die Liste im Satz bleibt, dieser Vermerk ergänzt sie. Bestätigung durch den Operator im Verifikationsbericht der Phase 5.*
> Begründung: Zwischen „`placeOrder` ist über die Leitung" und „ich habe das aufgeschrieben" kann der Prozess sterben. Kein Dateilock schließt diese Lücke.

**REQ-IBKR-43** `[L4]` — **Startup-Reconciliation:** Jeder Ledger-Eintrag im Zustand `intent` oder `placed` wird gegen den Broker aufgelöst — `reqAllOpenOrders` **und** `reqCompletedOrders` **und** `reqExecutions(ClientId=…)`, gefiltert auf `orderRef` —, **bevor** irgendeine neue Order entsteht; bleibt ein Eintrag unauflösbar, bricht der Lauf mit Exit 6 ab und meldet, statt zu raten.
> Begründung: Alle drei Quellen sind nötig. Eine gefüllte Order ist über `reqOpenOrders` unsichtbar; `reqAllOpenOrders` ist die einzige Abfrage, die auch fremde und manuell in TWS platzierte Orders sieht; `reqCompletedOrders` liefert die Orders des Tages, die nicht mehr änderbar sind. Das ist dieselbe Startup-Reconciliation, die NautilusTrader als Pflichtschritt vor dem Start der Strategien fährt — und ein Fehlschlag bricht dort den Start ab.

**REQ-IBKR-44** `[L4]` — Der Ausführer hält während des gesamten Laufs einen **nicht-blockierenden** Dateilock über `tradingagents.dataflows.files.locked(<ledger>, wait=False)` (`tradingagents/dataflows/files.py:36-49`); erhält er ihn nicht, beendet er sich ohne jede Order (Exit 7), und ein `OSError` beim Sperrversuch gilt als „nicht ausführen", nicht als Absturz.
> Begründung: Der Lock ist prozessübergreifend, auf Windows über `msvcrt.locking` implementiert (`files.py:67-88`) und wird beim Prozesstod vom Betriebssystem freigegeben. Seine Grenzen sind benannt: rein advisory, nur eine Maschine, schützt Dateien statt Netzaufrufe — und `_hold_windows` wirft jeden `OSError` außer `EDEADLOCK` (`:76-83`), was auf einem Netzlaufwerk eine Ausnahme statt eines `False` ergeben kann. `wait=False` ist die richtige Variante: ein zweiter Prozess soll nicht warten und dann doppelt handeln.

**REQ-IBKR-45** — Die Prüfkette läuft an **genau einer** Stelle im Code in dieser Reihenfolge und ist in dieser Reihenfolge getestet: Lock → Reconciliation → Quellen-/Integritätsprüfung → Aktualität → Auflösung + Handelbarkeit → Mengenrechnung → Größen-Obergrenze → Handelszeit → Kill-Switch → `whatIf` → `intent` schreiben → platzieren.
> Begründung: Eine über mehrere Funktionen verstreute Kette ist genau der Zustand, in dem später ein Pfad die Leitplanke umgeht — insbesondere im Catch-up- und im manuell gestarteten Lauf.
> **Nachweis:** Ein Test fährt die Kette mit einem Stub-Broker und prüft die Aufrufreihenfolge, nicht nur das Ergebnis.

---

## 5. Nachvollziehbarkeit

**REQ-IBKR-46** — Der Ledger ist eine **append-only JSONL-Textdatei** außerhalb jedes Git-Arbeitsbaums (alternativ: das State-Verzeichnis trägt eine `.gitignore` für `*.lock`/`*.tmp`); er ist **keine** SQLite-Datei, und kein Sperr-Sidecar landet in einem Commit.
> Begründung, zwei Punkte aus dem Bestand: (a) `scripts/state_maintenance.py:68` schließt `.db` per `BACKUP_EXCLUDED_SUFFIXES` aus der Sicherung aus, und `scripts/STATE_OPERATIONS.md:200-205` dokumentiert, dass eine korrupte SQLite-Datei auf Abfragen weiter plausibel antwortet — eine Zeile-pro-Ereignis-Textdatei hat diesen Fehlermodus nicht und ist diffbar. (b) `decision-log.md.lock` liegt heute **committet** auf `paper-log`, weil der CI-Commit `git add -A .` ohne Exclude macht (`daily-paper-run.yml:203`); ein Ledger-Lock im selben Verzeichnis würde denselben Weg gehen.

**REQ-IBKR-47** — Fills werden pro `execId` protokolliert, mit Dedup und **Korrekturregel**: eine `execId`, die bis auf die Ziffern nach dem letzten Punkt mit einer früheren identisch ist (`.02` korrigiert `.01`), **ersetzt** den vorherigen Eintrag und wird nicht addiert.

**REQ-IBKR-48** — Alle Executions und abgeschlossenen Orders eines Handelstags werden **am selben Tag** persistiert.
> Begründung: Das Broker-Fenster ist auf den aktuellen Handelstag begrenzt (Standardfilter „seit Mitternacht", IB Gateway auf den aktuellen Handelstag). Ein Teil-Fill, der am Tag nicht persistiert wurde, ist am nächsten Tag nicht mehr abfragbar. Die exakte Fenstersemantik ist offiziell widersprüchlich und ist ein Messpunkt (REQ-IBKR-01e); bis zur Messung gilt die konservative Lesart.

**REQ-IBKR-49** — Der Soll-Ist-Bericht entsteht beim **Lesen**, per Join über `(trade_date, ticker)` aus `paper-log:decision-log.md` und dem Fill-Ledger; kein Prozess schreibt dafür in den Branch eines anderen.

**REQ-IBKR-50** — **Ausführungsmetriken** (Slippage, Fill-Quote, Abweichung Ziel↔Ist) werden getrennt von den **Entscheidungsmetriken** (realisierter Return, Alpha vs. Benchmark, `tradingagents/memory/settlement.py`) geführt und nie in dieselbe Spalte geschrieben; der Bericht benennt, dass Paper-Fills ein Test der Mechanik und keine Messung der Ausführungsqualität sind.
> Begründung: Paper-Fills werden „from the top of the book" simuliert, der Rest einer teilausgeführten exchange-directed Market-Order wird abgelehnt, und IBKR sagt zu seinem Simulator *„no way to exactly replicate live markets"*. Fill-Quoten aus dem Paper-Konto sind damit systematisch nach oben verzerrt.

**REQ-IBKR-51** — `scripts/state_maintenance.py backup` nimmt den Ledger **und** den persistierten Contract-Cache in seine Allow-Liste auf.
> Begründung: Die Allow-Liste ist heute explizit auf `decision-log.md`, `index.md`, `runs/**` und das CLI-Log begrenzt (`state_maintenance.py:382-393`) — ein neuer Zustand fehlt beim ersten Backup, ohne dass es jemandem auffällt.

---

## 6. Betrieb

**REQ-IBKR-52** — Der Ausführer schreibt **nicht** auf den Branch `paper-log`; er veröffentlicht auf einem eigenen Branch, den ausschließlich er schreibt (Invariante: **ein Schreiber pro Branch**).
> Begründung, und sie wiegt mehr als die Bequemlichkeit eines gemeinsamen Branches: Der CI-Commit-Schritt verträgt keinen zweiten Schreiber. `daily-paper-run.yml:144-161` holt den Branch mit `fetch --depth=1` und macht `reset --hard FETCH_HEAD`; `:194-211` macht danach `add -A .`, `commit`, `push HEAD:$STATE_BRANCH` — **ohne** Rebase, ohne Retry, ohne `--force-with-lease`. Pusht der lokale Ausführer zwischen Fetch und Push des CI-Laufs, ist der CI-Push ein Non-Fast-Forward, und weil der State in `$RUNNER_TEMP` liegt (`:101`), ist **der ganze Entscheidungstag verloren** — inklusive der `pending`-Einträge. `STATE_OPERATIONS.md:233-236` und `PAPER_RUN.md` („One writer only.") benennen dieselbe Lücke. Das Zeitfenster ist klein (CI 06:30 UTC, Ausführung ab 13:30 UTC), aber nicht leer: `workflow_dispatch` ist jederzeit möglich, und die `concurrency`-Gruppe serialisiert nur GitHub-Läufe gegeneinander, nicht gegen einen lokalen Prozess.

**REQ-IBKR-53** — **Jeder** Lauf pusht einen Heartbeat auf diesen Branch — Zeitstempel, Gateway-/Session-Zustand, Zahl offener Orders, Kill-Switch-Zustand, Exit-Code —, auch bei „nichts zu tun" und bei „Gateway nicht erreichbar".
> Begründung: Ein Lauf, der nichts pusht, ist selbst ein Signal. Der stille Totalausfall ist der gefährlichste Fehlermodus: Gateway abgestürzt oder Wochen-Login vergessen, der Ausführer bricht korrekt ab, protokolliert korrekt in eine Datei, die niemand liest — und wochenlang passiert nichts.

**REQ-IBKR-54** — Ein CI-Job liest **ausschließlich** diesen Branch, wird rot, wenn der Heartbeat älter als die erwartete Kadenz ist, und erhält **keine** IBKR-Credentials.
> Begründung und Verhältnis zum Vorgänger: Damit erbt die Ausführung dieselbe Ausfallmeldung, die der Paper-Lauf schon hat („ein tägliches grünes Häkchen, das bei Ausfall rot wird", `PAPER_RUN.md`), ohne die gesetzte Entkopplung zu verletzen. Das bedient **P2 #6 des Vorgänger-Meilensteins teilweise mit** — siehe Abschnitt „Verhältnis zum Vorgänger-Meilenstein".

**REQ-IBKR-55** — Der Ausführer verwendet dokumentierte, disjunkte Exit-Codes nach dem Vorbild von `scripts/daily_paper_run.py:36-40` und schreibt zusätzlich eine UTF-8-Logdatei mit absolutem Pfad:

| Exit | Bedeutung |
|---|---|
| 0 | ok, einschließlich „nichts zu tun" |
| 1 | Konfigurationsfehler, nichts getan |
| 2 | Vorbedingung nicht erfüllt (kein Handelstag · Entscheidung veraltet · Quellen divergieren · Integritätsbefund) |
| 3 | Gateway/Session nicht erreichbar |
| 4 | Kill-Switch aktiv oder Freigabe fehlt |
| 5 | Order abgelehnt |
| 6 | Reconciliation ungelöst, Lauf abgebrochen |
| 7 | Lock nicht erhalten (zweite Instanz), sauber beendet |
| 8 | Konto-Guard verletzt (`managedAccounts` ≠ `{"DUQ634065"}`) |
| 20 | Zugangsdaten fehlen oder sind unlesbar — gleiche Bedeutung wie `EXIT_NO_CREDENTIALS` (`daily_paper_run.py:40`) |

> UTF-8 ist im Projekt Konvention und auf Windows nicht optional (#543/#550/#576).

**REQ-IBKR-56** — Der geplante Task läuft im **Windows Task Scheduler** mit „Run **only** when user is logged on", „Do not start a new instance", einem Zeitlimit gegen hängende Gateway-Connects, „Run task as soon as possible after a scheduled start is missed" und einem Auto-Retry; „Run whether user is logged on or not" ist ausdrücklich **ausgeschlossen**.
> Begründung: Hier widersprechen sich die beiden Recherchen, und die spezifischere gewinnt. Der IBC User Guide sagt wörtlich *„the task is always started in a separate user session which you cannot see and interact with … you are strongly advised NOT to use the option for 'Run whether user is logged on or not'"* — und das IB Gateway ist eine GUI-gebundene Java-Anwendung („For security reasons, a headless session of TWS or IBGW without a GUI is not supported"). Der Auto-Retry ist nur deshalb vertretbar, **weil** der Lauf idempotent ist; ohne Abschnitt 4 wäre er eine Doppelorder-Maschine. Ein echter Windows-Dienst ist kein gangbarer Weg.

**REQ-IBKR-57** — Der Ausführer prüft seine Vorbedingungen **selbst** und verlässt sich nicht auf die Startzeit des Schedulers.
> Begründung: Der Catch-up startet laut Microsoft-Doku „by default … ten minutes" nach dem verpassten Termin und laut Fremdberichten gelegentlich deutlich später. Für die drei Fälle gilt: Rechner zur Startzeit aus / während der Sitzung an → Catch-up greift, dann entscheiden Handelszeit und Aktualität; Rechner den ganzen Tag aus → die Entscheidung wird am nächsten Lauf übersprungen, **protokolliert und sichtbar**; mehrere Tage aus → es gibt nichts nachzuholen, weil das Mapping zielbasiert ist (REQ-IBKR-21).

**REQ-IBKR-58** — Die Task-History bzw. das Operational-Log des Schedulers ist aktiviert, und die Aktivierung ist im Betriebshandbuch festgehalten.
> Begründung: Auf Windows 10/11 ist die Task-History **standardmäßig aus**. Ohne sie fehlt hinterher sogar die Information, ob der Task überhaupt lief.

**REQ-IBKR-59** — Der Gateway-Betrieb ist reproduzierbar dokumentiert und so eingestellt: „Never lock Trader Workstation", nativer **Auto-Restart** täglich, Order-Precautions bewusst konfiguriert (sonst hängt eine Order an einem Bestätigungsdialog, den niemand wegklickt), `ClosedownAt` Freitagabend, und **ein manueller Login pro Woche** als benannte Betriebsaufgabe; IBC ist kein Fundament.
> Begründung: IBKR legt die Obergrenze der Unbeaufsichtigtheit auf **eine Woche** fest — Auto-Restart trägt „from Sunday to Sunday without re-authenticating", aber *„After the nightly server reset on Saturday night it will be necessary to again enter security credentials"*, und der Wochenzyklus beginnt montags. Das Fehlerbild eines vergessenen Logins ist `Soft token=0 received instead of expected permanent`, Fehler 1100 oder 502 — nicht „nicht eingeloggt". IBC ist seit 2026-09-01 archiviert (letztes Release 3.24.2); der Maintainer begründet es selbst mit dem nativen Auto-Restart. IBC 3.24.2 wird nur dann nachgerüstet, wenn die Messung aus REQ-IBKR-01a zeigt, dass der Paper-Login ohne Zweitfaktor geht.

**REQ-IBKR-60** — Es existiert ein Betriebshandbuch `scripts/IBKR_EXECUTION.md` nach dem Muster von `scripts/PAPER_RUN.md`: Einrichtung, Gateway- und Scheduler-Einstellungen, Exit-Code-Tabelle, Bedienung des Kill-Switch, Wochenlogin-Ritual, die typischen Fehlerbilder mit ihrer üblichen Behebung, und wie man den Soll-Ist-Bericht erzeugt und liest.

---

## 7. Redundante Absicherung (Fail-closed)

> **Grundregel:** Eine Freigabe braucht einen positiven Beweis. Das Ausbleiben eines Fehlers ist kein Beweis.
> Übernommen am 2026-10-12 aus `.planning/quick/261012-ap2-*/261012-ap2-SICHERUNGSPRINZIP.md` (Kandidaten S-01 … S-08); die Begründungen und die vier Messungen, aus denen die Regel stammt, stehen dort.

**REQ-IBKR-61** (S-01) — Liefert `whatIfOrder()` keine Margin- und Kommissionswerte — leere Liste, `None`, fehlende Felder —, gilt das als **abgelehnte** Vorschau: keine Order, benannter Zustand, eigener Exit-Code.
> **Nachweis:** Test mit gestubbtem Leer-Rückgabewert; es erfolgt kein `placeOrder`.

**REQ-IBKR-62** (S-02) — Jeder API-Aufruf hat ein Timeout, und ein Timeout ist ein benannter Fehlerzustand, kein stilles Weiterlaufen.
> **Nachweis:** Test mit nicht antwortender Gegenstelle endet im Fehlerpfad, nicht im Hänger. Gilt ab Phase 2 für jeden späteren Aufruf weiter.

**REQ-IBKR-63** (S-03) — Kein sicherheitskritischer Fakt stützt sich auf nur eine Quelle: Paper-Konto (`managedAccounts` **und** Kontofeld der Order), aktuelle Position (Ledger **und** `reqPositions()`), „schon ausgeführt?" (Ledger-Eintrag **und** `orderRef`-Suche über offene/erledigte Orders), Handelbarkeit (`tradingSessions()` **und** Order-Status nach Platzierung, 399 = geparkt). Widersprechen sich die Quellen, gilt der vorsichtigere Wert, und der Lauf meldet den Widerspruch.

*Geändert 2026-10-17 (Phase 5, D-11/D-18/D-22): Übergangsquellen bis Phase 6/7: Position nach der engen Regel D-18 (Widerspruch nur bei eigenen Fills im Ledger), Handelbarkeit = Börsenkalender + `liquidHours` bis zum Order-Status 399 im Placer von Phase 6, Konto = `managedAccounts` + `RELEASE.account` (das Echo auf der Order ist optional). Reichweite nach D-11: Konto-Widerspruch stoppt den Lauf (Exit 8), die übrigen stoppen nur den Ticker. Bestätigung durch den Operator im Verifikationsbericht der Phase 5.*
> **Nachweis:** je ein Test, der beide Quellen auseinanderlaufen lässt und zeigt, dass keine Order entsteht.

**REQ-IBKR-64** (S-04) — Der Kill-Switch ist fail-closed: Gehandelt wird nur, wenn eine ausdrückliche Freigabe **vorhanden und lesbar** ist **und** die Kill-Datei fehlt; geprüft wird unmittelbar vor **jeder** Order, nicht einmal beim Start. `reqGlobalCancel` bleibt der scharfe Arm für bereits liegende Orders.
> **Nachweis:** Test mit unlesbarer Freigabedatei → keine Order.

**REQ-IBKR-65** (S-05) — Nach jeder Order wird der tatsächliche Zustand bei IBKR gelesen (Status, Stückzahl, `orderRef`) und mit der Absicht verglichen; eine Abweichung ist ein Alarm, kein stilles Fortfahren.

**REQ-IBKR-66** (S-06) — Zu jeder Schutzmaßnahme gehört eine **Negativ-Kontrolle**: ein Test, in dem sie auslösen muss und der Durchlauf scheitert. Eine Sicherung ohne Negativ-Kontrolle gilt als nicht erbracht.

**REQ-IBKR-67** (S-07) — Fehlercodes, auf die ein Test oder eine Sicherung baut, sind am realen Gateway gemessen, bevor der Test auf sie baut; die Messung ist mit Datum belegt (Vorbild: 321 statt 10015, `ibkr-konto-befund.md`).

**REQ-IBKR-68** (S-08) — Ohne verfügbaren Wechselkurs wird in Stückzahlen gerechnet; fehlt ein Kurs oder Preis, wird die Größe **nicht geschätzt** — der Lauf meldet und hält an. `bid`/`ask` = `-1` (verzögerte Daten) sind keine Zahl für ein Limitverfahren.

---

## Nicht in diesem Meilenstein

| Ausgeschlossen | Begründung |
|---|---|
| **Live-Konto / echtes Geld** | LLM-Entscheidungen sind nicht deterministisch; der Produktiveinsatz bleibt hinter einem Paper-Gate (MILESTONE.md, „Produktionsrisiken"). Zusätzlich ist die Autologon-Empfehlung für den Windows-Betrieb bei einem Paper-Konto tragbar und bei einem Live-Konto nicht ohne weiteres. |
| **Short-Positionen** | M2 ist long-only (REQ-IBKR-24): kein negatives Ziel, keine Leihe, keine Margin-Modellierung. |
| **Optionen, Futures, Forex, Krypto, CFDs, Indizes** | Allow-List `{STK}` (REQ-IBKR-28). Jede weitere Klasse bringt ein eigenes Thema mit: Expiry-Rollover und Multiplikator bei `FUT`, Permission-Matrix des **Live**-Kontos bei allen, `conId`-Unterschiede je Listing-Exchange bei `CRYPTO` (BTC@PAXOS ≠ BTC@Zerohash), regulatorischer Ausschluss bei `CFD`. `IND` und `CONTFUT` sind strukturell nicht orderbar. |
| **Mehrere Konten / Multi-Account** | Der Paper-Guard verlangt genau ein Konto (REQ-IBKR-04). Ein Advisor-/Multi-Account-Setup würde ihn aufweichen. |
| **Stop-Loss, Bracket, komplexe Order-Typen** | Leitplanke `[L3]` erlaubt nur Markt-/Limit-Orders. Im Paper-Konto sind Stops ohnehin „always simulated", das Verhalten wäre also nicht einmal aussagekräftig. Der Stop bleibt Freitext im Report. |
| **Limit-Orders mit Preisfindung aus Marktdaten** | Marktdaten bleiben außerhalb des Order-Pfads (REQ-IBKR-26). Limit-Orders kommen erst in Frage, wenn der Mechanismus trägt — dann mit TIF `DAY` (REQ-IBKR-25). |
| **4-Block-Leiter / `Underweight` ≠ `Sell`** | Eine größere Leiter erhöht die Obergrenze pro Order und weicht damit Leitplanke `[L1]` auf. Erweiterungspfad, sobald der Mechanismus trägt. |
| **Volatilitäts-normalisierte Positionsgröße** | Fachlich richtig (ein fester Betrag heißt in einem Low-Vol- und einem High-Vol-Namen sehr Unterschiedliches), braucht aber einen Referenzpreis im Order-Pfad. Verfeinerung für später. |
| **Intraday-Nachführung, Dauerläufer, Windows-Dienst** | Ein Lauf pro Handelstag. Ein Dienst wäre erst gerechtfertigt, wenn Order-Status in Echtzeit verfolgt und Teil-Fills sofort nachgeordert werden sollen — und er verführt dazu, Zustand im RAM zu halten, was dem Idempotenz-Entwurf widerspricht. |
| **Fill-Verweise auf `paper-log`** | Erst nachdem der CI-Commit-Schritt auf `pull --rebase` + Retry umgestellt ist. Das ist eine Änderung am Produktionspfad und widerspricht der Projektlinie („The production path gets no new moving parts by operator decision", `STATE_OPERATIONS.md:244-245`). |
| **Alpha-/Backtest-Auswertung aus Paper-Fills** | Top-of-Book-Simulation und die Ablehnung des Restes teilausgeführter Market-Orders verzerren Fill-Quoten systematisch nach oben (REQ-IBKR-50). |
| **Client Portal Web API / OAuth** | Für Individual-Konten nur über das Client Portal Gateway, und IBKR: „does not support an automated authentication process" + täglicher Browser-Login + Ortsbindung an eine Maschine. Die programmatischen OAuth-Pfade sind Advisor-/Broker-/Prop-/Fund-/Third-Party-Konten vorbehalten. |
| **`IBeam`/`ibind` als Login-Automatisierung** | Funktioniert nachweislich, steht aber im direkten Widerspruch zur Hersteller-Aussage. Für einen geplanten Produktionspfad ein schlechter Tausch. |
| **Offizieller `ibapi`-Sync-Wrapper als Fallback** | Inhaltlich attraktiv (`TWSSyncWrapper` ab TWS API 10.40), aber TWS API 10.49+ steht seit 2026-08-03 unter GPL; die genaue Variante ist nicht verifiziert. Für einen **öffentlichen** Fork vor dem ersten Commit zu klären, nicht hier. |

---

## Verhältnis zum Vorgänger-Meilenstein

Offen geblieben sind im Meilenstein „Produktionsreife" bewusst genau zwei Punkte (Operator-Entscheidung 2026-10-11, MILESTONE.md):

- **P2 #6 — Observability/Alerting:** **teilweise von M2 mitbedient, aber nicht erledigt.** REQ-IBKR-53/54 liefern einen Heartbeat-Kanal samt Alarm für die **Ausführungsseite**, über denselben Mechanismus, den das Projekt schon benutzt und liest (ein Branch, ein CI-Cron, GitHubs eigene Benachrichtigung) und **ohne** Credentials in der CI. Was damit *nicht* erledigt ist: Metriken und Alerting für die **Analyseseite** — Vendor-Ausfälle, Fehlerraten, Latenz und Kosten je Run. Dieser Rest bleibt sichtbar offen.
- **P2 #8 — Provider-Ausfall-/Quota-Policy:** von M2 **nicht** berührt. Der Ausführer konsumiert nur das Ergebnis der Analyse; was passiert, wenn ein LLM-Provider ausfällt, entscheidet sich weiter auf der Analyseseite. Für den Ausführer ist ein ausgefallener Analyselauf einfach „keine Entscheidung für heute" (`status != "ok"`, REQ-IBKR-16) und damit ein normaler, protokollierter Zustand.

Der Produktivpfad der Analyse (`daily-paper-run.yml`, `scripts/daily_paper_run.py`) bekommt in M2 **keine neuen beweglichen Teile**. Die einzige Berührung ist additiv und optional: das Portfolio-JSON aus REQ-IBKR-11, das `graph.propagate` als `portfolio` mitgegeben wird.

---

## Offene Messpunkte — entscheidet Phase 1

Diese Punkte sind heute offen, in fünf Minuten am Konto messbar und beeinflussen den Zuschnitt mehr als jede weitere Recherche. Sie sind in REQ-IBKR-01 gebündelt und in [ROADMAP.md](./ROADMAP.md) als Gate vor Phase 2 verdrahtet.

| Messpunkt | Was davon abhängt |
|---|---|
| Verlangt der Paper-Login einen Zweitfaktor? | Ob unbeaufsichtigter Wochenbetrieb möglich ist (REQ-IBKR-02, -59) und ob IBC 3.24.2 nachgerüstet wird |
| Was liefert `managedAccounts`? | Formulierung des Paper-Guards (REQ-IBKR-04) |
| Was liefert `reqContractDetails` für `AAPL` — und für die exotischen Klassen, inkl. `ineligibilityReasonList`? | Erwartungswerte des Identitätsvergleichs (REQ-IBKR-30), Inhalt der Handelbarkeitsprüfung (REQ-IBKR-31) |
| Akzeptiert `orderRef` ein `\|`, und wie lang darf es sein? | Schreibweise des `decision_key` in der Order (REQ-IBKR-41) |
| Wie weit blickt `reqExecutions` am Gateway zurück? | Ob die tagesgleiche Persistenz (REQ-IBKR-48) ausreicht oder verschärft werden muss |
| Trägt **jede** Execution den `orderRef`? | Ob die Reconciliation (REQ-IBKR-43) darauf aufbauen darf oder einen zweiten Rückschlüssel (`permId`) braucht |
