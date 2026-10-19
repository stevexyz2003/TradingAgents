# Codex-Gegenprüfung: Vorhersage-/Statistik-/News-Methoden in TradingEngineX

Antworte auf Deutsch (Code-Bezeichner im Original).

## 1. Rolle und Regeln

**1a Rolle.** Du bist unabhängiger Prüfer. Du liest den Code selbst und übernimmst keine Behauptung ungeprüft. Du führst keinen Code aus und rufst keine Netzwerk-APIs auf.

**1b Lesestand.** Geprüft wird ausschließlich der Commit `4a55d2c93f6e70f2f48e50be0fef271b4544b233`. Lies über `git show 4a55d2c93f6e70f2f48e50be0fef271b4544b233:<pfad>` und suche über `git grep -n <muster> 4a55d2c93f6e70f2f48e50be0fef271b4544b233 -- <pfade>`. Alle Zeilenangaben beziehen sich auf diesen SHA. Der Working Tree (uncommittete Änderungen, u. a. parallele Phase-6-Arbeit an `scripts/ibkr_executor.py`, `tests/test_ibkr_execute.py`, `scripts/IBKR_EXECUTION.md`, `.planning/STATE.md`, `.planning/debug/`) liegt außerhalb des Umfangs.

**1c Belege.** Positive Aussagen (etwas existiert) brauchen `Datei:Zeile`. Negative Aussagen (etwas existiert nicht) brauchen einen **Abwesenheitsbeleg** mit vier Teilen: (i) die verwendeten Suchbegriffe, (ii) die durchsuchten Verzeichnisse, (iii) die exakten `git grep`-Muster samt Trefferzahl, (iv) positive Anker als `Datei:Zeile`, also den Dependency-Block in `pyproject.toml` und die nächstliegende tatsächlich vorhandene Implementierung (z. B. die Stelle, an der stattdessen das LLM entscheidet). Dazu eine Aussage zur Vollständigkeit (z. B. "alle .py unter tradingagents/, cli/, scripts/ durchsucht; Notebooks/Docs nicht"). Ohne diese Teile lautet das Urteil "nicht prüfbar"; geraten wird nicht.

**1d Widerlegungspflicht und Unabhängigkeit.** Versuche **jede** Hypothese aktiv zu widerlegen, auch über Synonyme und indirekte Implementierungen. Suche mindestens diese Begriffe: `numpy.random`, `np.random`, `statistics.`, `np.percentile`, `quantile`, `textblob`, `vader`, `transformers`, `sentence-transformers`, `sklearn`, `arch`, `statsmodels`, `scipy.stats`, `embedding`, `cosine`, `tfidf`, Keyword-/Wortlisten (z. B. Listen mit "bullish"/"bearish"), `sentiment`. **Einige Hypothesen können falsch sein.** Beispiel: Unsere eigene Liste nennt M1-P1-2 "Security-Scan fehlt", dabei existiert seit `cf6ab73` `.github/workflows/security-audit.yml`. Die Dateien `.planning/quick/261019-o31-*` darfst du für H-01..H-10 **erst nach** deinem eigenen Urteil öffnen. Danach gelten sie nur als zu widerlegende Behauptungen, nicht als Beleg.

**1e Geheimnisse.** `.env`, `.env.*`, `*.pem`, `*.key` und Zertifikats-Bundles werden **nicht geöffnet**. Kein Secret, Token oder API-Key wird zitiert. Enthält ein Suchtreffer einen Wert, nenne nur Datei und Variablennamen.

## 2. Hypothesen (aus Quick 261019-o31; bestätigen oder widerlegen)

Startfundstelle jeweils: `.planning/quick/261019-o31-architekturschaubild-tradingenginex-mit-/261019-o31-RESEARCH-architecture.md` §3 (3a/3b/3c) und §4. Suche auch daneben.

- H-01: Kein stochastisches Prognosemodell (Monte Carlo, GARCH/ARCH, Bayes, Random Walk, Verteilungsprognose) in `tradingagents/`, `scripts/`, `cli/`.
- H-02: Keine statistischen/ML-Bibliotheken (scipy, sklearn, statsmodels) und keine NLP-/Embedding-Pakete in `pyproject.toml` und keine entsprechenden Importe.
- H-03: Das einzige Zufallselement im Entscheidungspfad ist ungesteuertes LLM-Sampling (`default_config.py` temperature None, `llm_clients/factory.py`); `random.uniform` nur als Retry-Jitter.
- H-04: Technische Indikatoren (stockstats) sind nur LLM-Eingabe, kein regelbasiertes Signal im Entscheidungspfad.
- H-05: Die Musterschicht `tradingagents/patterns/` wird vom Graph nicht importiert und ist nur Nachauswertung.
- H-06: Keine eigene semantische News-Auswertung: kein Sentiment-Scoring, keine Embeddings, keine Deduplizierung/Relevanzgewichtung. Der `SentimentReport`-Score (0-10) wird vom LLM erzeugt (`schemas.py`). Alpha-Vantage NEWS_SENTIMENT ist im Paper-Lauf nicht aktiv.
- H-07: Memory-Retrieval ist rein zeitbasiert (`memory/log.py`), keine Ähnlichkeitssuche.
- H-08: Statistik nur in der Nachauswertung (Settlement raw/alpha ohne Beta, `backtest.summarize`, Wilson/MIN_N). Rückwirkung auf Entscheidungen nur über LLM-Reflexionstexte.
- H-09: Positionsgröße ist eine feste Leiter (Buy=2, Overweight=1, sonst 0 Blöcke, `scripts/ibkr_decision.py`) und hängt nicht von Konfidenz, Volatilität oder Kursziel ab. Stop-Loss/Take-Profit aus `TraderProposal` gehen nicht an IBKR.
- H-10: Jev-Konfidenzen wirken nur als REVIEW-Fallback (>= 0,9). Schattenergebnisse werden nicht aggregiert, die Kalibrierung ist nicht geprüft.
- H-11: Lückenliste M1/M2/Upstream. Behauptete Zählung aus o31: M1 11 Einträge = 6 umgesetzt / 2 teilweise / 2 offen / 1 verworfen; M2 70 = 52 / 9 / 9; Upstream 35 = 34 / 0 / 1. Quellen: `.planning/MILESTONE.md` (M1 P1/P2), `.planning/REQUIREMENTS.md` (REQ-IBKR-01..70), `.planning/ROADMAP.md` (Coverage-/Statustabelle), `.planning/phases/*/*-VERIFICATION.md` (Phasen 2-5 `passed`), für Upstream die README und der Code. Behaupteter Status pro ID, den du gegen Quellen und Code prüfst: M1-P1-2 teilweise (kein Security-Scan; möglicherweise durch `security-audit.yml` seit cf6ab73 überholt), M1-P2-6 offen, M1-P2-8 offen, REQ-IBKR-49 offen, -50 offen, -51 offen, -52 offen, -53 offen, -54 offen, -56 offen, -57 teilweise, -58 offen, -59 offen, -60 teilweise, -65 teilweise (Phase 6 läuft), U-35 offen (README verspricht simulierte Börse, Code führt nicht aus).
- H-12: Die Datenbasis für eine statistische Aussage zur Trefferquote fehlt (wenige abgerechnete Einträge, fester Ticker-Pool, überlappende Fenster, Feeds nicht point-in-time).

## 3. Offene Suche

Was hat o31 übersehen? Suche Vorhersage-, Statistik- oder NLP-Logik sowie Risiko- oder Datenqualitätsmechanismen, die o31 nicht nennt. Nummeriere sie N-01...

## 4. Lückenbewertung für belastbares Trading

Beantworte konkret und auf dieses Repo bezogen, was für stabiles, messbar profitables Trading fehlt. Dimensionen: Vorhersagemodelle (Wahrscheinlichkeit/Verteilung, Kalibrierung), Validierung (Out-of-Sample, Walk-Forward, Baselines Buy-and-Hold und Zufall, Signifikanz/Mehrfachtests, Look-ahead/Survivorship), Kosten/Slippage, Risiko (Positionsgröße, Stop, Drawdown-Limit, Exposure), Datenqualität (point-in-time, Vollständigkeit, Vendor-Ausfall), Monitoring/Betrieb, Go/No-Go. Sage auch, was kein Plan garantieren kann (Profitabilität) und welche Nachweise eine evidenzbasierte Freigabe bräuchte.

## 5. Ausgabeformat (verbindlich)

- Kopfzeile mit HEAD-SHA.
- Tabelle `| Nr | Hypothese/Befund | Datei:Zeile | Grad (B/W/I) | Urteil (bestätigt/widerlegt/teils/nicht prüfbar/neu) | Begründung |`. Nummern H-01.. für Hypothesen, N-01.. für neue Befunde.
- Abschnitt "Lückenbewertung" je Dimension, mit Priorität.
- Abschnitt "Go/No-Go-Kriterien" mit messbaren Schwellen als Vorschlag (z. B. Mindest-N, Zeitraum, Baseline-Vergleich, max. Drawdown).
- Abschnitt "Verdikt", 3-6 Sätze.
