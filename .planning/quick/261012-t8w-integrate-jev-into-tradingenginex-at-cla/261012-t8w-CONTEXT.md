# Quick Task 261012-t8w: Jev an Klassifizierungs-/Bewertungsstellen der Engine - Context

**Gathered:** 2026-10-12
**Status:** Ready for planning

<domain>
## Task Boundary

Operator-Auftrag: "Baue JEV überall da in die Trading Engine ein, wo es um Klassifizierungen und Bewertungen nach True/False, Options oder Scales geht. Suche diese Stellen mit Serena/Graphify und baue diese Erweiterung um."

Jev (TypeSafe jev-1.13) schreibt nichts; es beantwortet zu einem Text (`state`) Fragen in 3 Formen: `choice` (Option aus Liste), `score` (Stufe auf Skala, 2-10 Stufen, niedrigste zuerst), `noul` (Wahrscheinlichkeit wahr). choice/score liefern `confidence`, noul -> Konfidenz abs(2p-1).
Referenz-Implementierung (stdlib-Client, getestet live): `C:/Users/admin/.claude/skills/jev/jev.py` + `SKILL.md`; Vor-Task: `.planning/quick/261012-sg6-*/` (RESEARCH.md enthält API-Schema).
Direkte API: `POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer <JEV_API_KEY>`, model `jev-latest`; Antwort `{model, answers{id:{type, choice|score|noul, confidence?, probabilities?, legend?}}, usage{input_tokens, output_tokens}}`; Kosten = input_tokens x USD 0.042/M.

Scope: Engine-Code unter `tradingagents/` (und ggf. `cli/`, `scripts/daily_paper_run.py`), nur Stellen, an denen bereits ein Text in eine Klasse/Skala/ja-nein überführt wird (z.B. `tradingagents/agents/rating.py::extract_rating` -> heute `REVIEW`, wenn Heuristik nichts findet). Jev ersetzt KEINE textgenerierenden Agents.

</domain>

<decisions>
## Implementation Decisions

### Rolle: Fallback + Schatten
- Bestehende Logik bleibt primär.
- **Fallback:** Wo die bestehende Logik heute scheitert (z.B. kein Rating -> `REVIEW`), darf Jev einspringen — nur bei Konfidenz >= 0.9 (konfigurierbar). Darunter bleibt das heutige Verhalten (z.B. `REVIEW`). Ein von Jev gelieferter Wert muss als solcher erkennbar sein (Log/State-Feld, Quelle "jev").
- **Schatten:** An allen anderen gefundenen Stellen läuft Jev nur mit; Ergebnis + Konfidenz + Übereinstimmung mit der bestehenden Logik werden protokolliert (Log und, wo sinnvoll, ein State-/Summary-Feld). Kein Einfluss auf Entscheidungen.
- Jeder Jev-Fehler (Netz, 4xx/5xx, Timeout, Schema) ist nicht-fatal: Log-Warnung, heutiges Verhalten. Jev darf einen Run nie abbrechen oder blockieren (kurzer Timeout).

### Aktivierung: Opt-in, Default aus
- Config-Key (z.B. `jev_enabled`, plus `jev_min_confidence`, `jev_timeout`) in `default_config.py` + Env-Override nach bestehendem Muster (`TRADINGAGENTS_JEV_ENABLED` ...).
- Ohne Flag ODER ohne Key: Engine verhält sich bit-identisch wie heute; keine Netzwerkcalls. Bestehende Tests bleiben unverändert grün.
- Key nur aus Env `JEV_API_KEY` (die Engine lädt `.env` bereits, falls so implementiert — prüfen). Key nie loggen; Fehlertexte redigieren.

### Datenschutz
- Operator-Freigabe: Analyse-Reports, Marktdaten, Entscheidungstexte dürfen an TypeSafe.
- Ausgeschlossen: IBKR-/Konto-Daten (Account-ID, Positionen, Credentials), API-Keys. Nur die für die jeweilige Frage nötigen Texte senden.

### Client
- Eigenes Modul im Repo, z.B. `tradingagents/jev/` (stdlib `urllib`, keine neue Dependency), Logik aus `jev.py` übernehmen (validate, summarize/confidence, redact, retry 429/5xx mit kurzem Backoff, SSL Default-Kontext, Zertifikatsprüfung nie aus).
- Tests mit Stub (Monkeypatch/lokaler HTTP-Server), kein Live-Call in CI.

### Claude's Discretion
- Konkrete Auswahl der Stellen (Ergebnis der Serena/Graphify-Suche), Frage-Formulierungen, Optionslisten (immer `other`-Option bei choice; Reihenfolge nicht mit erwarteter Antwort zuerst), Log-Format, Namen der Felder.
- Rebase-Freundlichkeit (Fork mit Upstream-Rebase-Kadenz): Änderungen an Upstream-Dateien minimal halten, Logik ins neue Modul, Call-Sites nur dünne Hooks.

</decisions>

<specifics>
## Specific Ideas

- `extract_rating` / `parse_rating` / `run_rating` -> Jev-choice über die 5 Stufen (Buy, Overweight, Hold, Underweight, Sell) + `other`, nur wenn Heuristik `None` liefert.
- Kandidaten für Schatten: Sentiment-Analyst (score), Research-/Portfolio-Manager-Ratings (Gegenprobe der strukturierten Ausgabe), Reflection/Memory-Tags, Signal-Verarbeitung im Paper-Run.
- Live-Smoke einmal manuell mit echtem Key (Operator-Key liegt in gitignored `.env` als `JEV_API_KEY`), Ergebnis in SUMMARY.

</specifics>

<canonical_refs>
## Canonical References

- https://docs.typesafe.ai/llms.txt, https://docs.typesafe.ai/api.md
- `C:/Users/admin/.claude/skills/jev/jev.py`, `C:/Users/admin/.claude/skills/jev/SKILL.md`
- `.planning/quick/261012-sg6-wire-jev-decision-model-typesafe-jev-1-1/261012-sg6-RESEARCH.md`
- `tradingagents/agents/rating.py` (#1170 REVIEW-Semantik)

</canonical_refs>
