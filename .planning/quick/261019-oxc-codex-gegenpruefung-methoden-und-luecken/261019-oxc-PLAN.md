---
phase: quick-261019-oxc
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/codex-prompt.md
  - .planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/codex-output.md
  - .planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/261019-oxc-CODEX-REVIEW.md
  - .planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/261019-oxc-MILESTONE-DRAFT.md
autonomous: true
requirements: [QUICK-261019-oxc]

must_haves:
  truths:
    - "Codex (gpt-6.1-sol, read-only, ChatGPT-Konto) hat die Methoden-Behauptungen aus 261019-o31 unabhängig am Code geprüft. Seine Rohantwort liegt unverändert in codex-output.md, oder der Lauf ist als BLOCKED mit exaktem Fehlertext dokumentiert, ohne eigene Ersatz-Review."
    - "Negative Hypothesen (etwas existiert nicht) sind über Abwesenheitsbelege prüfbar: Suchbegriffe, Verzeichnisse und git-grep-Muster am fixierten SHA, positive Anker und eine Aussage zur Vollständigkeit; Codex hat jede Hypothese aktiv zu widerlegen versucht."
    - "Codex hat den per Template-Variable fixierten HEAD-SHA gelesen (git show/git grep <SHA>); alle Zeilenangaben beziehen sich auf diesen SHA."
    - "Jede geprüfte Hypothese (H-xx) hat im Review ein Urteil von Codex (bestätigt/widerlegt/teils/nicht prüfbar) mit Datei:Zeile-Beleg und dazu unsere Disposition (bestätigt/widerlegt/neu)."
    - "Das Review nennt ausdrücklich, wo Codex von der o31-Research abweicht oder etwas Neues findet."
    - "Das Review enthält ein nüchternes Go/No-Go-Urteil für echtes Trading. Es sagt, was kein Plan garantieren kann (Profitabilität), und benennt die Nachweise, die für eine belastbare Freigabe nötig sind."
    - "Der Meilenstein-Entwurf ist klar als Entwurf zur Entscheidung durch den Operator markiert. Er enthält Ziele, Anforderungskandidaten mit IDs (PRED/VAL/RISK/DATA/OPS) und messbaren Kriterien, eine Phasenskizze, Nicht-Ziele und offene Fragen."
    - "Es gibt keine Code-Änderung, keine Git-Schreibaktion, keinen Backtest und keinen LLM-API-Call. Geschrieben wurde nur im Quick-Verzeichnis und im Scratchpad; der Baseline-Vergleich (git status + git hash-object vor/nach) zeigt das, Änderungen anderer Sessions ausgenommen."
  artifacts:
    - path: ".planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/codex-prompt.md"
      provides: "Codex-Prompt mit Hypothesen H-01..H-xx, Belegpflicht, Lückenbewertung, Go/No-Go-Kriterien"
      contains: "H-01"
    - path: ".planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/codex-output.md"
      provides: "Unveränderte Codex-Rohantwort (oder BLOCKED-Protokoll)"
    - path: ".planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/261019-oxc-CODEX-REVIEW.md"
      provides: "Review im 04-/kof-Format: Frontmatter, Befunde, Verdikt, Disposition, Abgleich mit o31"
      contains: "## Disposition"
    - path: ".planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/261019-oxc-MILESTONE-DRAFT.md"
      provides: "Deutscher Entwurf für /gsd:new-milestone 'Vorhersage-Engine'"
      contains: "ENTWURF"
  key_links:
    - from: "codex-prompt.md"
      to: "codex exec"
      via: "stdin-Umleitung, -o codex-output.md"
      pattern: "codex exec -s read-only -m gpt-6.1-sol"
    - from: "261019-oxc-CODEX-REVIEW.md"
      to: "codex-output.md"
      via: "Befundtabelle übernimmt Codex-Nummern 1:1"
      pattern: "\\| H-0"
    - from: "261019-oxc-MILESTONE-DRAFT.md"
      to: "261019-oxc-CODEX-REVIEW.md"
      via: "jede Anforderung verweist auf den Befund oder die Lücke, aus der sie stammt"
      pattern: "(PRED|VAL|RISK|DATA|OPS)-[0-9]{2}"
---

<objective>
Codex prüft als unabhängige zweite Sicht die Methoden-Bestandsaufnahme aus Quick 261019-o31 am Code: Gibt es wirklich keine statistischen oder stochastischen Vorhersagemodelle und keine eigene semantische News-Auswertung? Dazu bewertet Codex die Umsetzungslücken (M1/M2/Upstream) und nennt, was für stabiles, messbar profitables Trading fehlt. Danach entstehen zwei Dokumente: ein Review im 04-/kof-Format mit unserer Disposition und ein deutscher Meilenstein-Entwurf „Vorhersage-Engine“, der `/gsd:new-milestone` als Grundlage dient.

Purpose: Der Operator hält den heutigen Stand für echtes Trading nicht für ausreichend. Der neue Meilenstein wird ohne Altspezifikation neu formuliert. Deshalb braucht er eine belegte, nicht von unserer eigenen Research abgeschriebene Ausgangslage und messbare Go/No-Go-Kriterien.

Output: `codex-prompt.md`, `codex-output.md`, `261019-oxc-CODEX-REVIEW.md` und `261019-oxc-MILESTONE-DRAFT.md`, alle im Quick-Verzeichnis.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/quick/261019-o31-architekturschaubild-tradingenginex-mit-/261019-o31-RESEARCH-architecture.md
@.planning/quick/261019-o31-architekturschaubild-tradingenginex-mit-/261019-o31-RESEARCH-requirements.md
@.planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-CODEX-REVIEW.md

Quick-Verzeichnis (QDIR): `C:/Users/admin/PycharmProjects/TradingEngineX/.planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken`
Scratchpad: `C:\Users\admin\AppData\Local\Temp\claude\C--Users-admin-PycharmProjects-TradingEngineX\92d8ebad-eff8-46ce-bcee-2437ca37eb39\scratchpad`
**HEAD-SHA ist Pflicht-Template-Variable `{{HEAD_SHA}}`.** Der Prompt enthält sie als Platzhalter. Der Executor füllt sie unmittelbar vor dem Codex-Lauf mit dem vollen 40-stelligen Ergebnis von `git rev-parse HEAD` (nur lesen). Zum Zeitpunkt der Planprüfung war das `e0336b2…`; `cf6ab73` ist veraltet und darf nicht hart eingetragen werden. Nach dem Füllen darf im Prompt kein `{{HEAD_SHA}}` mehr stehen.

**Baseline vor T1 (Punkt Nachweis „nichts angefasst“):** Vor dem ersten Schritt von T1 schreibt der Executor in den Scratchpad:
- `baseline-status.txt` = `git status --porcelain`
- `baseline-hash.txt` = exakt die Ausgabe von `git ls-files tradingagents cli pyproject.toml | while read f; do echo "$(git hash-object "$f") $f"; done` (dasselbe Format nutzt der Vergleich im T1-Verify)
Nach jedem Task wird gegen diese Baseline verglichen. Ausgenommen sind Änderungen anderer Sessions an `scripts/ibkr_*`, `tests/test_ibkr_*`, `.planning/STATE.md`, `.planning/debug/`, `.planning/phases/06-*`. Eine Abweichung in `tradingagents/`, `cli/` oder `pyproject.toml` ist eine **WARNUNG** (ins SUMMARY), kein Fehlschlag, denn eine parallele Session kann sie verursacht haben. Der Executor selbst schreibt dort nie.

**Harte Grenzen (gesperrt, Operator):**
- Kein Code ändern. Kein Backtest. Keine LLM-API-Kosten. Codex läuft nur über das ChatGPT-Konto.
- Keine Git-Schreibaktion (kein add/commit/stash/checkout).
- NICHT anfassen: `scripts/ibkr_executor.py`, `tests/test_ibkr_execute.py`, `scripts/IBKR_EXECUTION.md`, `.planning/STATE.md`, `.planning/debug/`. Dort arbeitet gerade eine parallele Phase-6-Session (uncommitted). Der Codex-Prompt muss Codex anweisen, den committed HEAD zu prüfen und uncommittete Änderungen an diesen Dateien als außerhalb des Umfangs zu behandeln.
- `.planning`-Dokumente sind deutsch. Codex soll deutsch antworten.

**Codex auf dieser Maschine (codex-cli 0.163.0):**
Aufruf (Git-Bash, aus QDIR heraus oder mit absoluten Pfaden):
`codex exec -s read-only -m gpt-6.1-sol -c model_reasoning_effort=high -C "C:/Users/admin/PycharmProjects/TradingEngineX" --ephemeral -o "<QDIR>/codex-output.md" - < "<QDIR>/codex-prompt.md"`
Codex prüft nur statisch. `gpt-5.5` lehnt das ChatGPT-Konto ab.
**Laufregeln (verbindlich):**
- Der Lauf startet **immer mit `run_in_background: true`**. stderr jedes Versuchs geht in eine eigene Datei im Scratchpad: `C:\Users\admin\AppData\Local\Temp\claude\C--Users-admin-PycharmProjects-TradingEngineX\92d8ebad-eff8-46ce-bcee-2437ca37eb39\scratchpad\codex-stderr-try1.txt` bzw. `-try2.txt`, Exit-Code in `codex-exit-tryN.txt`.
- Warten bis etwa **25 Minuten** (Monitor/until-Schleife auf Prozessende bzw. Exit-Code-Datei). Der letzte Lauf dauerte etwa 5 Minuten.
- Ein Abbruch durch eigenes Timeout/Kill zählt **nicht** als Versuch. Dann einmal mit gleicher Wartezeit neu starten und das im SUMMARY vermerken.
- Als Versuch zählt nur ein Lauf, den Codex selbst mit Fehler beendet (Exit ≠ 0 mit Codex-Fehlertext) oder der eine leere Ausgabedatei hinterlässt. Nach einem gescheiterten Versuch einmal unverändert wiederholen.
- **BLOCKED** nur, wenn zwei echte Versuche scheitern **und** ein realer Codex-Fehlertext aus stderr vorliegt, der dann wörtlich zitiert wird. Ein reines Timeout ohne Codex-Fehler ist nicht BLOCKED, sondern wird als „Lauf nicht abgeschlossen“ mit Wartezeit gemeldet.
- In keinem Fall eine eigene Review als Codex-Ergebnis ausgeben.

**Bekannte Abweichung, die als Hypothese in den Prompt gehört:** Die o31-Matrix führt M1-P1-2 als „teilweise, kein Security-Scan“. Seit `cf6ab73` gibt es aber `.github/workflows/security-audit.yml` (pip-audit, blockierend, wöchentlich). Codex soll das bestätigen. Es ist ein Beispiel dafür, dass die Lückenliste veraltet sein kann.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Codex-Prompt schreiben und Codex ausführen</name>
  <files>QDIR/codex-prompt.md, QDIR/codex-output.md</files>
  <read_first>261019-o31-RESEARCH-architecture.md §3 (3a/3b/3c) und §4; 261019-o31-RESEARCH-requirements.md (Zählung je Quelle, alle Zeilen mit Status offen/teilweise, Unklare Punkte); 261018-kof-CODEX-REVIEW.md (Format der Befundtabelle)</read_first>
  <action>
Schritt 0: Baseline nach `<context>` in den Scratchpad schreiben.

Schreibe `codex-prompt.md` auf Deutsch mit dem Write-Tool. Der Prompt muss allein verständlich sein. Codex kann die o31-Dateien im Repo grundsätzlich lesen. Deshalb regelt der Prompt ausdrücklich, wie er mit ihnen umgehen darf (siehe Regel 1d). Er enthält diese Abschnitte:

(1) Rolle und Regeln.
(1a) Codex ist unabhängiger Prüfer. Er liest den Code selbst und übernimmt keine Behauptung ungeprüft. Codex führt keinen Code aus und ruft keine Netzwerk-APIs auf. Antwortsprache Deutsch, Code-Bezeichner im Original.
(1b) Lesestand: Geprüft wird ausschließlich der SHA `{{HEAD_SHA}}`. Codex liest über `git show {{HEAD_SHA}}:<pfad>` und sucht über `git grep -n <muster> {{HEAD_SHA}} -- <pfade>`. Alle Zeilenangaben beziehen sich auf diesen SHA. Der Working Tree (uncommittete Änderungen, u. a. parallele Phase-6-Arbeit) ist außerhalb des Umfangs.
(1c) Belege: Positive Aussagen (etwas existiert) brauchen `Datei:Zeile`. Negative Aussagen (etwas existiert nicht) brauchen einen **Abwesenheitsbeleg** mit vier Teilen: (i) die verwendeten Suchbegriffe, (ii) die durchsuchten Verzeichnisse, (iii) die exakten `git grep`-Muster samt Trefferzahl, (iv) positive Anker als `Datei:Zeile`, also den Dependency-Block in `pyproject.toml` und die nächstliegende tatsächlich vorhandene Implementierung (z. B. die Stelle, an der stattdessen das LLM entscheidet). Dazu eine Aussage zur Vollständigkeit (z. B. „alle .py unter tradingagents/, cli/, scripts/ durchsucht; Notebooks/Docs nicht“). Ohne diese Teile lautet das Urteil „nicht prüfbar“, geraten wird nicht.
(1d) Widerlegungspflicht und Unabhängigkeit: Codex versucht **jede** Hypothese aktiv zu widerlegen, auch über Synonyme und indirekte Implementierungen. Mindestens diese Begriffe sind zu suchen: `numpy.random`, `np.random`, `statistics.`, `np.percentile`, `quantile`, `textblob`, `vader`, `transformers`, `sentence-transformers`, `sklearn`, `arch`, `statsmodels`, `scipy.stats`, `embedding`, `cosine`, `tfidf`, Keyword-/Wortlisten (z. B. Listen mit „bullish“/„bearish“), `sentiment`. Der Prompt sagt ausdrücklich: **Einige Hypothesen können falsch sein.** Beispiel: Unsere eigene Liste nennt M1-P1-2 „Security-Scan fehlt“, dabei existiert seit `cf6ab73` `.github/workflows/security-audit.yml`. Die Dateien `.planning/quick/261019-o31-*` darf Codex für H-01..H-10 **erst nach** seinem eigenen Urteil öffnen. Danach gelten sie nur als zu widerlegende Behauptungen, nicht als Beleg.
(1e) Geheimnisse: `.env`, `.env.*`, `*.pem`, `*.key` und Zertifikats-Bundles werden **nicht geöffnet**. Kein Secret, Token oder API-Key wird zitiert. Wenn ein Suchtreffer einen Wert enthält, nennt Codex nur Datei und Variablennamen.

(2) Hypothesen H-01 bis mindestens H-12. Sie stammen aus o31 und sind als Behauptungen formuliert, die Codex bestätigen oder widerlegen soll. Pflichtinhalte:
- H-01: kein stochastisches Prognosemodell (Monte Carlo, GARCH/ARCH, Bayes, Random Walk, Verteilungsprognose) in `tradingagents/`, `scripts/`, `cli/`.
- H-02: keine statistischen/ML-Bibliotheken (scipy, sklearn, statsmodels) und keine NLP-/Embedding-Pakete in `pyproject.toml` und keine entsprechenden Importe.
- H-03: das einzige Zufallselement im Entscheidungspfad ist ungesteuertes LLM-Sampling (`default_config.py` temperature None, `llm_clients/factory.py`); `random.uniform` nur als Retry-Jitter.
- H-04: technische Indikatoren (stockstats) sind nur LLM-Eingabe, kein regelbasiertes Signal im Entscheidungspfad.
- H-05: die Musterschicht `tradingagents/patterns/` wird vom Graph nicht importiert und ist nur Nachauswertung.
- H-06: keine eigene semantische News-Auswertung: kein Sentiment-Scoring, keine Embeddings, keine Deduplizierung/Relevanzgewichtung. Der `SentimentReport`-Score (0–10) wird vom LLM erzeugt (`schemas.py`). Alpha-Vantage NEWS_SENTIMENT ist im Paper-Lauf nicht aktiv.
- H-07: Memory-Retrieval rein zeitbasiert (`memory/log.py`), keine Ähnlichkeitssuche.
- H-08: Statistik nur in der Nachauswertung (Settlement raw/alpha ohne Beta, `backtest.summarize`, Wilson/MIN_N). Rückwirkung auf Entscheidungen nur über LLM-Reflexionstexte.
- H-09: Positionsgröße ist eine feste Leiter (Buy=2, Overweight=1, sonst 0 Blöcke, `scripts/ibkr_decision.py`) und hängt nicht von Konfidenz, Volatilität oder Kursziel ab. Stop-Loss/Take-Profit aus `TraderProposal` gehen nicht an IBKR.
- H-10: Jev-Konfidenzen wirken nur als REVIEW-Fallback (≥ 0,9). Schattenergebnisse werden nicht aggregiert, die Kalibrierung ist nicht geprüft.
- H-11: Lückenliste M1/M2/Upstream (behauptete Zählung aus o31: M1 11 Einträge = 6 umgesetzt/2 teilweise/2 offen/1 verworfen; M2 70 = 52/9/9; Upstream 35 = 34/0/1). Quellen der Anforderungen nennt der Prompt ausdrücklich: `.planning/MILESTONE.md` (M1 P1/P2), `.planning/REQUIREMENTS.md` (REQ-IBKR-01..70), `.planning/ROADMAP.md` (Coverage-/Statustabelle), `.planning/phases/*/*-VERIFICATION.md` (Phasen 2–5 `passed`), für Upstream die README und den Code. Der Prompt führt pro ID den behaupteten Status auf, den Codex gegen Quellen und Code prüft: M1-P1-2 teilweise (kein Security-Scan; möglicherweise durch `security-audit.yml` seit cf6ab73 überholt), M1-P2-6 offen, M1-P2-8 offen, REQ-IBKR-49 offen, -50 offen, -51 offen, -52 offen, -53 offen, -54 offen, -56 offen, -57 teilweise, -58 offen, -59 offen, -60 teilweise, -65 teilweise (Phase 6 läuft), U-35 offen (README verspricht simulierte Börse, Code führt nicht aus).
- H-12: Die Datenbasis für eine statistische Aussage zur Trefferquote fehlt (wenige abgerechnete Einträge, fester Ticker-Pool, überlappende Fenster, Feeds nicht point-in-time).
Pro Hypothese nennt der Prompt die o31-Fundstelle als Startpunkt und sagt dazu, dass Codex auch daneben suchen soll.

(3) Offene Suche: Was hat o31 übersehen? Gesucht sind Vorhersage-, Statistik- oder NLP-Logik und Risiko- oder Datenqualitätsmechanismen, die o31 nicht nennt.

(4) Lückenbewertung für belastbares Trading. Codex soll konkret und auf dieses Repo bezogen beantworten, was für stabiles, messbar profitables Trading fehlt. Dimensionen: Vorhersagemodelle (Wahrscheinlichkeit/Verteilung, Kalibrierung), Validierung (Out-of-Sample, Walk-Forward, Baselines Buy-and-Hold und Zufall, Signifikanz/Mehrfachtests, Look-ahead/Survivorship), Kosten/Slippage, Risiko (Positionsgröße, Stop, Drawdown-Limit, Exposure), Datenqualität (point-in-time, Vollständigkeit, Vendor-Ausfall), Monitoring/Betrieb, Go/No-Go. Codex soll auch sagen, was kein Plan garantieren kann (Profitabilität) und welche Nachweise eine evidenzbasierte Freigabe bräuchte.

(5) Ausgabeformat, verbindlich:
- Kopfzeile mit HEAD-SHA.
- Tabelle `| Nr | Hypothese/Befund | Datei:Zeile | Grad (B/W/I) | Urteil (bestätigt/widerlegt/teils/nicht prüfbar/neu) | Begründung |`. Nummern H-01.. für Hypothesen, N-01.. für neue Befunde.
- Abschnitt „Lückenbewertung“ je Dimension, mit Priorität.
- Abschnitt „Go/No-Go-Kriterien“ mit messbaren Schwellen als Vorschlag (z. B. Mindest-N, Zeitraum, Baseline-Vergleich, max. Drawdown).
- Abschnitt „Verdikt“, 3–6 Sätze.

Danach Codex ausführen. Unmittelbar vorher `git rev-parse HEAD` (nur lesen) ausführen und alle Vorkommen von `{{HEAD_SHA}}` im Prompt durch den vollen SHA ersetzen. `codex --version` prüfen. Dann den Aufruf aus `<context>` nach den dortigen Laufregeln starten: Hintergrund, bis etwa 25 Minuten Wartezeit, stderr und Exit-Code je Versuch im Scratchpad, Timeout-Kill zählt nicht als Versuch. Erst wenn zwei echte Versuche mit realem Codex-Fehlertext scheitern, schreibe in `codex-output.md` nur `STATUS: BLOCKED`, beide Exit-Codes und den wörtlichen stderr-Text. Schreibe keine eigene Review. `codex-output.md` wird nach dem Lauf nicht editiert, denn sie ist der Rohbeleg. Zum Schluss Baseline-Vergleich nach `<context>`; Abweichungen in `tradingagents/`, `cli/` oder `pyproject.toml` als WARNUNG notieren.
  </action>
  <verify>
    <automated>Q="C:/Users/admin/PycharmProjects/TradingEngineX/.planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken"; test "$(grep -cE '^\W*H-(0[1-9]|1[0-2])' "$Q/codex-prompt.md")" -ge 12 && grep -q "Datei:Zeile" "$Q/codex-prompt.md" && grep -q "Go/No-Go" "$Q/codex-prompt.md" && for t in "Abwesenheitsbeleg" "sentence-transformers" "numpy.random" "scipy.stats" "tfidf" "git grep" ".env" "*.pem" "security-audit.yml"; do grep -qF "$t" "$Q/codex-prompt.md" || { echo "FEHLT: $t"; exit 1; }; done && ! grep -qF '{{HEAD_SHA}}' "$Q/codex-prompt.md" && grep -qE 'git show [0-9a-f]{40}:' "$Q/codex-prompt.md" && test -s "$Q/codex-output.md" && (grep -q "STATUS: BLOCKED" "$Q/codex-output.md" || grep -qE 'H-0[1-9]' "$Q/codex-output.md") && SP='C:/Users/admin/AppData/Local/Temp/claude/C--Users-admin-PycharmProjects-TradingEngineX/92d8ebad-eff8-46ce-bcee-2437ca37eb39/scratchpad' && R=C:/Users/admin/PycharmProjects/TradingEngineX && test -s "$SP/baseline-hash.txt" && { (cd $R && git ls-files tradingagents cli pyproject.toml | while read f; do echo "$(git hash-object "$f") $f"; done) | diff -q - "$SP/baseline-hash.txt" >/dev/null || echo "WARNUNG: tradingagents/cli/pyproject.toml weicht von der Baseline ab (andere Session?) - ins SUMMARY"; } && echo OK</automated>
  </verify>
  <done>Der Prompt enthält H-01..H-12 mit Startfundstellen, Belegpflicht, offene Suche, Lückendimensionen, Go/No-Go und das Ausgabeformat. `codex-output.md` enthält entweder die unveränderte Codex-Antwort mit H-Nummern oder ein BLOCKED-Protokoll mit exaktem Fehler. Weder Code noch Git noch die gesperrten Dateien wurden berührt.</done>
</task>

<task type="auto">
  <name>Task 2: 261019-oxc-CODEX-REVIEW.md im 04-/kof-Format mit Disposition und o31-Abgleich</name>
  <files>QDIR/261019-oxc-CODEX-REVIEW.md</files>
  <read_first>QDIR/codex-output.md (vollständig); 261018-kof-CODEX-REVIEW.md als Formatvorlage</read_first>
  <action>
Ist `codex-output.md` BLOCKED: Schreibe das Review nur mit Frontmatter (`status: BLOCKED`), Laufhinweis, exaktem Fehler und dem Satz „Keine Codex-Befunde; keine Ersatz-Review“. Lass Task 3 aus und melde BLOCKED.

Sonst übernimmst du die kof-Struktur:
(a) YAML-Frontmatter mit `source` (codex exec, codex-cli-Version, sandbox read-only, Modell gpt-6.1-sol, Reasoning high), `scope` (committed HEAD-SHA, Hinweis auf parallele uncommittete Phase-6-Dateien außerhalb des Umfangs), `date: 2026-10-19` und `note` (nur statische Analyse, kein Test, kein Backtest, keine LLM-API-Kosten).
(b) Titel, „Hinweis zum Lauf“ (Versuche, Dauer, Besonderheiten) und „Ergebnis laut Codex“ in 2–3 Sätzen.
(c) `## Befunde`: Tabelle `| Nr | Datei:Zeile | Grad | Status | Befund |`. Nummern und Belege übernimmst du 1:1 von Codex (H-xx, N-xx), ohne Umdeutung.
(d) `**Verdikt (Codex):**` sinngemäß aus dem Codex-Verdikt.
(e) `## Lückenbewertung und Go/No-Go (Codex)`: die Dimensionen und die vorgeschlagenen Schwellen kompakt übernehmen. Die Aussage, dass Profitabilität nicht garantierbar ist, bleibt sichtbar stehen.
(f) `## Disposition`: Tabelle `| Nr | Disposition | Prüfung | Detail |`. Die Spalte Prüfung enthält je Zeile genau einen der Werte **geprüft** (Beleg selbst an der SHA-Zeile bzw. Abwesenheit selbst per `git grep <SHA>` nachvollzogen) oder **nur übernommen**. Disposition ist eine von **bestätigt** / **widerlegt** / **neu**, optional mit Zusatz „Designfrage Operator“ oder „Meilenstein-Kandidat“. Prüfe dafür jeden Codex-Beleg selbst stichprobenartig mit Read/Grep an der genannten Zeile. Die Querprüfung erfolgt wie in kof, weil Agent-Selbstaussagen falsch sein können. Wo Codex' Beleg nicht stimmt, steht das im Detail.
(g) `## Abgleich mit o31`: Tabelle `| o31-Aussage (Fundstelle) | Codex | Abweichung | Folge |`, mindestens für alle Hypothesen mit Urteil widerlegt/teils und alle N-Befunde. Dazu der explizite Abgleich der Lückenzählung, z. B. M1-P1-2 durch cf6ab73. Zum Schluss ein Absatz, welche Teile der o31-Seite bzw. des Schaubilds dadurch veraltet sind. Die Seite selbst wird NICHT geändert, sie wird nur benannt.
Keine Code- oder Git-Änderung. Sprache Deutsch.
  </action>
  <verify>
    <automated>F="C:/Users/admin/PycharmProjects/TradingEngineX/.planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/261019-oxc-CODEX-REVIEW.md"; head -1 "$F" | grep -q '^---$' && grep -q '^source:' "$F" && (grep -q 'status: BLOCKED' "$F" || (grep -q '^## Befunde' "$F" && grep -q '^## Disposition' "$F" && grep -q '^## Abgleich mit o31' "$F" && grep -q 'Go/No-Go' "$F" && grep -cE '^\| (H|N)-[0-9]{2}' "$F" | awk '$1>=24{ok=1} END{exit !ok}' && awk '/^## Disposition/{d=1;next} /^## /{d=0} d && /^\| (H|N)-[0-9]{2}/ {n++; if ($0 !~ /geprüft|nur übernommen/) bad++} END{exit !(n>=12 && bad==0)}' "$F")) && echo OK</automated>
  </verify>
  <done>Das Review hat Frontmatter und Befundtabelle mit den Codex-Nummern 1:1, das Codex-Verdikt, Lückenbewertung und Go/No-Go, eine Disposition je Nummer (bestätigt/widerlegt/neu) mit eigener Stichprobe sowie den Abgleich mit o31 inklusive Zählungsabweichungen. Bei BLOCKED steht nur das Protokoll da, ohne Ersatz-Review.</done>
</task>

<task type="auto">
  <name>Task 3: 261019-oxc-MILESTONE-DRAFT.md (Entwurf „Vorhersage-Engine“ für /gsd:new-milestone)</name>
  <files>QDIR/261019-oxc-MILESTONE-DRAFT.md</files>
  <read_first>QDIR/261019-oxc-CODEX-REVIEW.md (Abschnitte Lückenbewertung, Disposition, Abgleich)</read_first>
  <action>
Schreibe den deutschen Entwurf. Die erste Zeile nach dem Titel ist ein Kasten: „**ENTWURF — nicht beschlossen.** Grundlage für `/gsd:new-milestone`; Ziele, Umfang und Schwellen entscheidet der Operator.“ Abschnitte:
1. `## Ausgangslage`: 5–8 Sätze aus dem Review, mit Verweisen auf H-/N-Nummern. Die Entscheidung ist heute ein LLM-Urteil ohne eigenes Prognosemodell und ohne Validierung. Der Operator hält das für echtes Trading nicht ausreichend.
2. `## Ziele`: 3–6 ergebnisförmige Ziele, z. B. eine messbare Prognose mit Unsicherheit, eine Validierung vor jeder Freigabe, Risiko und Kosten im Entscheidungspfad, eine point-in-time-Datenbasis und ein Go/No-Go-Gate.
3. `## Was kein Plan garantieren kann`: Profitabilität ist nicht planbar. Planbar sind die Nachweisführung und ein Abbruch bei Nichterfüllung (No-Go ist ein gültiges Ergebnis).
4. `## Anforderungskandidaten`: Tabellen je Gruppe PRED-xx, VAL-xx, RISK-xx, DATA-xx, OPS-xx mit je mindestens 3 Einträgen. Spalten `| ID | Anforderung | Messbares Akzeptanzkriterium | Herkunft (H-/N-Nr. oder Codex-Lückendimension) |`. Jedes Kriterium ist prüfbar formuliert, mit Zahl, Zeitraum, Baseline oder Artefakt. Beispiele: VAL Walk-Forward mit festen Out-of-Sample-Fenstern, Vergleich gegen Buy-and-Hold und Zufallsstrategie, Kosten/Slippage-Annahme in bp, Mindest-N unabhängiger Fälle, Korrektur für Mehrfachtests. RISK mit Positionsgröße aus Volatilität/Konfidenz, Max-Drawdown-Stopp und Exposure-Limit. DATA point-in-time für News/Social/Kurse. PRED mit kalibrierter Wahrscheinlichkeit/Verteilung (z. B. Brier/Reliability) und LLM-Sampling-Streuung gemessen. OPS mit Monitoring/Heartbeat und Go/No-Go-Protokoll. Konkrete Schwellwerte stehen als „Vorschlag“ in eckigen Klammern, damit klar ist, dass der Operator entscheidet. Keine Anforderung sagt eine Rendite oder Trefferquote als Ziel zu. Kriterien sind als Nachweis formuliert („wird gemessen/berichtet“, „Gate entscheidet Go/No-Go anhand Schwelle X“), nie als Zusage. Die Wörter „garantiert“, „sichert zu“, „erzielt“ und „erreicht eine Rendite/Trefferquote“ kommen in ID-Zeilen nicht vor.
5. `## Phasenskizze`: 4–7 Phasen in sinnvoller Abhängigkeitsfolge (z. B. Datenbasis/point-in-time → Baselines + Validierungsrahmen → Prognosemodell(e) → Risiko/Sizing → Paper-Bewährung → Go/No-Go-Gate). Je Phase eine Überschrift `### Phase N: <Name>`, Ziel, genau eine Zeile `**Anforderungen:** <ID>, <ID>, …` und ein Exit-Kriterium. Jede Anforderungs-ID taucht in genau einer `**Anforderungen:**`-Zeile auf.
6. `## Nicht-Ziele`: z. B. keine Echtgeld-Freigabe ohne bestandenes Gate, kein Ersatz von M2-Phase 6–8 in diesem Meilenstein, kein Hochfrequenzhandel, kein Renditeversprechen. Abhängigkeit zu offenen M2-Punkten (REQ-IBKR-49..60) benennen.
7. `## Offene Fragen an den Operator`: mindestens 6 nummerierte Fragen (`1. …`), z. B. Universum/Ticker-Pool, Haltedauer, Budget für LLM-Kosten bei Mehrfachläufen, Datenkauf ja/nein, Rolle des LLM (Merkmalslieferant vs. Entscheider), Schwellenwerte des Gates, Verhältnis zu M2.
Keine Code- oder Git-Änderung. Sprache Deutsch.
  </action>
  <verify>
    <automated>F="C:/Users/admin/PycharmProjects/TradingEngineX/.planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/261019-oxc-MILESTONE-DRAFT.md"; grep -q 'ENTWURF' "$F" && for g in PRED VAL RISK DATA OPS; do test "$(grep -oE "^\| $g-[0-9]{2}" "$F" | sort -u | wc -l)" -ge 3 || exit 1; done && for s in 'Ziele' 'Anforderungskandidaten' 'Phasenskizze' 'Nicht-Ziele' 'Offene Fragen' 'garantieren'; do grep -q "^## .*$s" "$F" || exit 1; done && T=$(grep -oE '^\| (PRED|VAL|RISK|DATA|OPS)-[0-9]{2}' "$F" | tr -d '| ' | sort -u) && A=$(awk '/^## .*Phasenskizze/{p=1;next} /^## /{p=0} p && /^\*\*Anforderungen:\*\*/' "$F" | grep -oE '(PRED|VAL|RISK|DATA|OPS)-[0-9]{2}' | sort) && test -z "$(echo "$A" | uniq -d)" && test "$T" = "$(echo "$A" | sort -u)" && test "$(awk '/^## .*Offene Fragen/{p=1;next} /^## /{p=0} p && /^[0-9]+\. /' "$F" | wc -l)" -ge 6 && ! grep -E '^\| (PRED|VAL|RISK|DATA|OPS)-[0-9]{2}' "$F" | grep -qiE 'garantier|sichert zu|zusicher|erzielt|erreicht (eine|mindestens) (Rendite|Trefferquote)' && echo OK</automated>
  </verify>
  <done>Der Entwurf ist klar als nicht beschlossen markiert. PRED/VAL/RISK/DATA/OPS haben je mindestens 3 Kandidaten mit messbaren Kriterien und Herkunftsverweis; keine ID sagt Rendite oder Trefferquote zu. Die Phasenskizze ordnet jede ID genau einer Phase zu (maschinell geprüft). Nicht-Ziele, die Aussage zur Nicht-Garantierbarkeit und mindestens 6 offene Operatorfragen sind vorhanden.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Repo → Codex (OpenAI/ChatGPT-Konto) | Codex liest den Repo-Inhalt im read-only-Sandbox und überträgt ihn zur Modellausführung |
| Codex-Ausgabe → Planungsdokumente | Die Modellausgabe ist nicht vertrauenswürdig (Halluzinationsgefahr bei Belegen) |
| Parallele Phase-6-Session → gemeinsamer Working Tree | Uncommittete fremde Änderungen |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-oxc-01 | Information Disclosure | `.env`, Keys im Working Tree | mitigate | Regel 1e im Prompt verbietet Codex, `.env`, `.env.*`, `*.pem`, `*.key` und Zertifikats-Bundles zu öffnen und Secrets zu zitieren (T1-Verify prüft, dass die Regel im Prompt steht). Vor dem Abschluss prüft ein Grep auf `sk-`/`API_KEY=` in den QDIR-Dateien, dass kein Secret übernommen wurde. |
| T-oxc-02 | Tampering | gesperrte Phase-6-Dateien, STATE.md | mitigate | `-s read-only`, keine Git-Schreibaktion. Der Executor schreibt nur in QDIR und Scratchpad. Baseline (`git status --porcelain` + `git hash-object` für tradingagents/, cli/, pyproject.toml) vor T1 und Vergleich danach; Abweichung dort = WARNUNG (parallele Session möglich), fremde Phase-6-Pfade ausgenommen. |
| T-oxc-03 | Repudiation / Integrität | codex-output.md | mitigate | Die Rohausgabe bleibt unverändert. Das Review übernimmt die Nummern 1:1. Die Disposition beruht auf einer eigenen Stichprobe der Belege, wie bei kof. |
| T-oxc-04 | Spoofing | Ersatz-Review bei Codex-Ausfall | mitigate | Bei zwei Fehlschlägen ist der Status BLOCKED mit exaktem Fehler. Es wird keine eigene Analyse als Codex ausgegeben. |
| T-oxc-05 | Denial of Service | Kosten | accept | Der Lauf geht über das ChatGPT-Konto, nicht über die API. Es gibt keine LLM-API-Calls und keinen Backtest. |
</threat_model>

<verification>
- Alle vier Dateien liegen in QDIR. Außerhalb von QDIR und Scratchpad wurde nichts geschrieben: `git status --porcelain` wird gegen `baseline-status.txt` verglichen. Neu sein darf nur das Quick-Verzeichnis. Ausgenommen sind Änderungen anderer Sessions an `scripts/ibkr_*`, `tests/test_ibkr_*`, `.planning/STATE.md`, `.planning/debug/`, `.planning/phases/06-*`. Der Hash-Vergleich für tradingagents/, cli/ und pyproject.toml gibt bei Abweichung eine WARNUNG im SUMMARY aus, keinen Fehlschlag.
- Kein Secret-Muster in QDIR: `grep -rE 'sk-[A-Za-z0-9]{10,}|API_KEY=\S+' QDIR` liefert nichts.
- Bei BLOCKED: Review und Summary melden BLOCKED, und es gibt keinen MILESTONE-DRAFT.
</verification>

<success_criteria>
- Codex-Gegenprüfung durchgeführt (oder sauber BLOCKED), mit Belegen als Datei:Zeile.
- Das Review zeigt Bestätigungen, Widerlegungen und neue Befunde gegenüber o31 und enthält ein nüchternes Go/No-Go-Urteil.
- Der Meilenstein-Entwurf ist als Entwurf markiert und hat messbare Anforderungskandidaten in 5 Gruppen, Phasenskizze, Nicht-Ziele und offene Fragen. Er ist direkt als Eingabe für `/gsd:new-milestone` nutzbar.
- Kein Code, kein Git-Write, keine API-Kosten.
</success_criteria>

<output>
`.planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/261019-oxc-SUMMARY.md` anlegen. Kein Commit durch den Executor; der Orchestrator entscheidet über den Commit.
</output>
