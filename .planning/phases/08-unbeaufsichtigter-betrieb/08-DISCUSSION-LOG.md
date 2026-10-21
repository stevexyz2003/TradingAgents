# Phase 8: Unbeaufsichtigter Betrieb - Discussion Log

> **Nur zur Nachvollziehbarkeit.** Nicht als Input für Planung, Research oder Ausführung verwenden.
> Die Entscheidungen stehen in `08-CONTEXT.md`; dieses Log hält fest, welche Alternativen erwogen wurden.

**Date:** 2026-10-21
**Phase:** 08-unbeaufsichtigter-betrieb
**Areas discussed:** Laufkette & Zeitplan, Heartbeat & Wächter, Lücken & Catch-up, Wochenlogin vs. IBC
**Todos folded:** 321 im Lesefenster, Pipeline-Test-Orders, summary.json-Überschreiben (alle drei)

---

## Laufkette & Zeitplan

| Frage | Optionen | Gewählt |
|---|---|---|
| Form des Laufs | Ein Unterbefehl `daily` (empf.) / PowerShell-Wrapper / getrennte Tasks | Ein Unterbefehl |
| Startzeit | 16:30 (empf.) / 15:45 / morgens nach CI | 16:30 |
| Retry | 3× alle 15 min, 30 min Limit (empf.) / 1× nach 30 min / kein Retry | 3× / 15 min / 30 min |
| Tage | Mo–Fr (empf.) / täglich | Mo–Fr |
| Nach execute-Fehler | immer publish + Heartbeat (empf.) / Abbruch | immer publish + Heartbeat |
| Code-Stand | eigener Betriebs-Klon (empf.) / Entwicklungsbaum | Betriebs-Klon |
| Standby | wecken (empf.) / nein | wecken |
| RELEASE-Ablauf | Heartbeat + Wächter warnt (empf.) / nur Heartbeat | Heartbeat + Wächter |
| Klon-Update | Tag manuell (empf.) / fork/main manuell / automatisch | Tag manuell |
| .env | State-Ordner (empf.) / im Klon | State-Ordner |
| Rollout | 2 Tage trocken (empf.) / sofort scharf | **sofort scharf** (abweichend von der Empfehlung) |
| Push-Creds | GCM (empf.) / eigener PAT | GCM |
| Gateway fehlt | nur melden (empf.) / Prozess starten | nur melden |
| Manueller Lauf am selben Tag | Idempotenz reicht (empf.) / PAUSE-Datei | Idempotenz |

## Heartbeat & Wächter

| Frage | Optionen | Gewählt |
|---|---|---|
| Form | heartbeat.json + runs.jsonl (empf.) / nur heartbeat.json / nur runs.jsonl | beides |
| Schwelle | Werktagsregel + 3 h (empf.) / fest 26/74 h / NYSE-Kalender | Werktagsregel |
| Cron | Mo–Fr 18:00 UTC (+ Sa 06:00) (empf.) / stündlich | Mo–Fr 18:00 UTC |
| Rot bei | alt + Fehler + RELEASE (empf.) / nur alt / alt + Fehler ohne KILL | alt + Fehler + RELEASE (KILL eingeschlossen) |
| Zusatzfelder | Entscheidung+Aktion / Code-Stand / RELEASE / Dauer+Versuch | alle vier |
| Unbekanntes | null + Zustand (empf.) / Ledger-Sicht | null + Zustand |
| SC3-Nachweis | Dispatch mit `now` (empf.) / alten Heartbeat pushen / Test-Branch | Dispatch mit `now` |
| Rechte | contents: read, stdlib (empf.) / wie daily-paper-run | contents: read, stdlib |

## Lücken & Catch-up

| Frage | Optionen | Gewählt |
|---|---|---|
| Lücke sichtbar | gap-Eintrag (empf.) / nur runs.jsonl | gap-Eintrag |
| Alte Entscheidungen | superseded vermerken (empf.) / ignorieren | superseded |
| Nachweis | geplanter Aussetzer (empf.) / auf echten Ausfall warten | geplanter Aussetzer |
| Fehlerlauf = Lücke? | nein, nur fehlende Läufe (empf.) / ja | nein |
| Bericht | neue Zustände (empf.) / nur Ledger | neue Zustände |

## Wochenlogin vs. IBC

| Frage | Optionen | Gewählt |
|---|---|---|
| Betrieb | manuell + IBC-Entscheidung am Ende (empf.) / IBC ausgeschlossen / IBC einbauen | manuell + Entscheidung am Ende |
| Zeitpunkt | Montag vor 16:30 (empf.) / Sonntagabend | Montag |
| Vergessener Login | Wächter + `login-required` (empf.) / nur Exit 3 / plus Windows-Erinnerung | Wächter + `login-required` |
| Gateway-Settings belegen | Checkliste im Handbuch (empf.) / jts.ini auslesen | Checkliste |

## Folded Todos

| Todo | Gewählte Lösung |
|---|---|
| 321 im Lesefenster | wie im Todo beschrieben (sofort `READ_ONLY_API`, Exit 5) |
| Pipeline-Test-Orders | Ausschlussliste im Repo (empf.) — gegen Liste + rating_source und Ledger-Annotation |
| summary.json-Überschreiben | wie im Todo beschrieben (Merge je Ticker) |

## Claude's Discretion

Logrotation, direkter `python.exe`-Start ohne cmd-Hülle, Zeitzonen-Darstellung, Bezugspunkt der Lückenerkennung und erster Lauf, Namen von Wächter-Workflow und Prüfskript.

## Deferred Ideas

IBC-Einbau, `rating_source: pipeline-test`, Windows-Erinnerungsdialog, Observability der Analyseseite.
