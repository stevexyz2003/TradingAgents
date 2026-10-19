# Quick 261018-kof: Operator-Entscheidungen zu den offenen Codex-Befunden

**Entschieden:** 2026-10-19 (Operator, jeweils die empfohlene Option)
**Umsetzung:** offen, als Folge-Quick-Task. Jede Änderung als kleiner Upstream-Patch mit Test und Vermerk „Upstream candidate“.

| Befund | Entscheidung | Umsetzung |
|---|---|---|
| #1 Gleichstand durch Rundung | **Aus dem Nenner nehmen** | `summarize` zählt ein Alpha von genau 0 weder als Treffer noch als Fehltreffer und weist Gleichstände getrennt aus. Damit ist es mit `tradingagents/patterns/` vergleichbar. Das Log-Format bleibt. |
| #2 „Richtung getroffen“ | **Beide ausweisen** | `backtest` zeigt Alpha-Treffer („Benchmark geschlagen“) und Raw-Treffer („Kursrichtung“) nebeneinander und eindeutig beschriftet. |
| #4 Parameter-Drift beim Settlement | **Bei Entscheidung fixieren** | Haltedauer, Benchmark und Einstiegskonvention werden beim Speichern der Entscheidung in den Log-Eintrag geschrieben, das Settlement nutzt diese Werte. Für alte Einträge ohne Felder gilt die aktuelle Konfiguration. Der Parser muss beide Formate lesen. |
| #17 vorläufiger Exit-Bar | **Jetzt patchen** | Das Settlement übernimmt den Ausstiegsbar nur, wenn die Sitzung abgeschlossen ist: Das Bar-Datum liegt vor dem aktuellen Börsentag der Börse oder die Sitzung ist laut Börsenzeit geschlossen. Andernfalls bleibt der Eintrag pending. |

Reihenfolge: #17 zuerst, weil es die Abrechnung falsch machen kann. Dann #1 und #2 (beide in `backtest.py`). Zuletzt #4, weil es das Log-Format ändert und damit die größte Rebase-Fläche hat.
