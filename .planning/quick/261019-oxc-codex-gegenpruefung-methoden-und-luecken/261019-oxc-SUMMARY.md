---
phase: quick-261019-oxc
plan: 01
status: complete
completed: 2026-10-19
requirements: [QUICK-261019-oxc]
key-files:
  created:
    - .planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/codex-prompt.md
    - .planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/codex-output.md
    - .planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/261019-oxc-CODEX-REVIEW.md
    - .planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/261019-oxc-MILESTONE-DRAFT.md
---

# Quick 261019-oxc: Codex-Gegenprüfung und Meilenstein-Entwurf - Summary

Codex (gpt-6.1-sol, read-only, ChatGPT-Konto) hat die o31-Methodenaussagen am SHA `4a55d2c93f6e70f2f48e50be0fef271b4544b233` geprüft; daraus entstanden ein Review mit Disposition und ein Entwurf des Meilensteins "Vorhersage-Engine" (23 Anforderungskandidaten).

## Codex-Lauf

Ein Versuch, Exit 0, rund 8-10 Minuten, im Hintergrund; stderr und Exit-Code liegen im Scratchpad. Kein BLOCKED, kein INCOMPLETE, kein Timeout-Kill. `codex-output.md` ist die unveränderte Rohantwort.

## Ergebnis

- Codex-Urteile: 3 bestätigt (H-01, H-04, H-05), 9 teils (H-02, H-03, H-06 bis H-12), 0 nicht prüfbar in der Haupttabelle, 9 neue Befunde (N-01 bis N-09).
- Meine Disposition: 8 bestätigt (teils mit Präzisierung), 4 widerlegt (teilweise: H-06, H-08, H-10, H-11), 9 neu. Von 21 Zeilen sind 12 "geprüft" und 9 "nur übernommen".
- Teilaussagen "nicht prüfbar" (4): aktuelle Zahl abgerechneter Entscheidungen (H-12), M2-Gesamtverteilung, REQ-IBKR-56 und -58 (Windows-Zustand). Zeilen ohne Suchmuster: 9 (H-08, H-12, N-02 bis N-08); das sind positive Aussagen, die keinen Abwesenheitsbeleg brauchen.

## Wo Codex von o31 abweicht

Bestandsdetails: Titel-Deduplizierung und Ticker-Filter in den News, Jev-Klassifikation im Post-Screening, numerische raw/alpha im PM-Kontext, Ties verlassen den Nenner (o31 falsch), `Hold` = skip, kein `take_profit` im Schema. Lückenliste: M1-P1-2 durch `security-audit.yml` erledigt (M1 7/1/2/1), erster Paper-Fill 2026-10-19 dokumentiert, REQ-IBKR-23 nur teilweise (Nettierung offener Orders erst ab Phase 6), M2-Verteilung 52/9/9 nicht als Abnahmestand belegbar.

## Die fünf wichtigsten Lücken

1. Kein Out-of-Sample/Walk-Forward und keine Baselines (Buy-and-Hold, Zufall) mit Mehrfachtest-Kontrolle (P0).
2. Keine Kosten/Slippage in Settlement und Summary; Kommission im ersten Fill ca. 0,29 % einseitig (P0).
3. Kein Prognosemodell mit Wahrscheinlichkeit und Kalibrierung; Rating ist LLM-Urteil (P1).
4. Datenbasis nicht point-in-time (nicht archivierte Feeds, aktuelle adjustierte Kurse) und zu dünn (fester Pool, 20 von 20 Engine-Entscheidungen ohne Kauf) (P0).
5. Risiko nur als Stückzahlgrenze: keine Volatilitäts-/Konfidenz-Größe, kein Drawdown-Stopp, kein Abbaupfad über dem Orderlimit (P0). Dazu offene Betriebsnachweise (Heartbeat, Backup, Soll-Ist).

Codex-Verdikt: No-Go für Echtgeld.

## Anforderungs-IDs im Entwurf

PRED-01..04, VAL-01..06, RISK-01..05, DATA-01..04, OPS-01..04 (23 Kandidaten; 6 Phasen, jede ID in genau einer Zeile, 8 offene Fragen).

## Deviations

Keine; Plan wie vorgegeben ausgeführt. Zusatzregeln A bis C umgesetzt (Hintergrundlauf mit Exit-Code-Datei, Zählung der "nicht prüfbar"-Zeilen).

## Warnungen und Nachweis

- Hash-Vergleich `tradingagents/`, `cli/`, `pyproject.toml`: identisch zur Baseline.
- `git status`: neben dem Quick-Verzeichnis sind `.planning/ROADMAP.md` (geändert) und `.planning/phases/07-*/07-0N-PLAN.md` neu; das stammt von einer anderen Session, nicht von dieser. Keine Git-Schreibaktion, kein Code, kein Backtest, keine API-Kosten.
- Secret-Grep in den Ergebnisdateien: kein Treffer (nur Mustertext im PLAN).
- Zeilenangaben bei Codex weichen mehrfach um wenige Zeilen ab (z. B. `default_config.py:115`, `memory/log.py:174`); Befunde stimmen.
- Offener Punkt: Die o31-Seite und das Schaubild wurden nicht geändert; Korrekturbedarf ist im Review unter "Abgleich mit o31" benannt.

## Self-Check: PASSED

Vier Dateien plus SUMMARY im Quick-Verzeichnis vorhanden; Verify-Prüfungen für Review (42 H/N-Zeilen, 21 Dispositionen) und Entwurf (alle Gruppen mindestens 3, IDs eindeutig in Phasen) bestanden.
