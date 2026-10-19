---
phase: quick-261019-h63
verified: 2026-10-19
status: passed
score: 7/7 must-haves verified
overrides_applied: 1
overrides:
  - must_have: "#17: Exit-Bar zaehlt, wenn Datum vor heute ODER Sitzung laut Boersenzeit geschlossen"
    reason: "Sitzungsklausel bewusst weggelassen; die reine Datumsregel ist strenger, nie falsch, verzoegert hoechstens um einen Tag"
    accepted_by: "Operator/Orchestrator"
    accepted_at: "2026-10-19"
---

# Quick 261019-h63: Verifikation

**Ziel:** Codex-Folgefixes #17, #1, #2, #4 umsetzen.
**Ergebnis:** Ziel erreicht. Nichts gefunden, das ein Gap waere.

## Tests und Lint (selbst ausgefuehrt)

- `pytest tests/test_memory_log.py tests/test_backtest.py tests/test_cli_memory_log.py tests/test_patterns_evaluate.py tests/test_state_maintenance.py tests/test_graph_end_to_end.py -q`: 233 passed
- `ruff check` auf allen geaenderten Quell- und Testdateien: sauber

## Must-haves

| # | Wahrheit | Status | Beleg |
|---|----------|--------|-------|
| 1 | Heutiger Exit-Bar (Aktie und Benchmark) wird nie abgerechnet | VERIFIED | `settlement._by_day(closes, now)` behaelt nur Bars mit boersenlokalem Datum < heute (tz aus Index, naiv = UTC); `fetch_returns` reicht `now` an beide Aufrufe; fehlender Bar fuehrt zu pending ohne Fehler. Neue Tests in TestSettlementWindow setzen `now` explizit. |
| 2 | Ties (auch -0.0) in keinem Nenner, je Rating ausgewiesen | VERIFIED | `backtest._tally`: Nenner = len - ties, `v == 0` faengt -0.0; `RatingScore.ties` und `raw_ties`. Gilt fuer Alpha und Raw. |
| 3 | Alpha- und Raw-Quote nebeneinander, Hold vs. nur-Ties unterscheidbar | VERIFIED | Render: "beat the benchmark", "price direction", "no decisive outcome", "no direction claimed" fuer Hold; `RatingScore` positional kompatibel (neue Felder mit Default am Ende). |
| 4 | SETTLEMENT-Body-Zeile, Tag byte-gleich | VERIFIED | Ausgabe des Probelaufs: Tag `[2026-10-13 | GC=F | Buy | pending]` unveraendert, Zeile `SETTLEMENT: holding=5d | benchmark=GC=F | entry=next_close` zwischen Tag und `DECISION:`. docker_smoke.sh-Matcher (`... | pending]`, Zeile 209) matcht weiter. |
| 5 | Settlement je Eintrag mit gespeicherten Werten, Config-Fallback, unbekannte Konvention in failed | VERIFIED | `settle_pending`: Aufloesung in der Schleife; `fetch_returns` ohne zusaetzliches `now=` (Mock-Signatur erhalten); unbekannte entry-Konvention und unlesbare holding gehen in `result.failed` und bleiben pending. |
| 6 | GC=F-Round-Trip; record_decision verliert nie eine Entscheidung an der Validierung | VERIFIED | Probelauf: `benchmark` wird als `GC=F` geparst (Split am ersten `=`). `record_decision` faengt nur `ValueError`, loggt Warnung und speichert im Altformat. Nach `update_with_outcome` bleibt die Zeile erhalten und wird weiter geparst. |
| 7 | Alt-Eintraege und externe Leser | VERIFIED | Probelauf mit Alt-Block plus Neublock: `load_entries` (settlement `{}` bzw. gefuellt), `patterns.evaluate.log_text_to_entries` (2 Eintraege), `state_maintenance.check_decision_log` (None). Parser liest SETTLEMENT nur vor `DECISION:` (nicht faelschbar durch Modelltext). |

## Nebenbedingungen

- Keine Dateien unter `scripts/` oder `tradingagents/patterns/` in den drei Commits geaendert (`git diff --stat` leer fuer diese Pfade); IBKR-Dateien unberuehrt.
- Alle drei Commits tragen "Upstream candidate" im Body.
- Das Working Tree ist sauber bis auf nicht eingecheckte `.planning/`-Dateien.

## Akzeptierte Abweichung

- #17: Klausel "oder Sitzung laut Boersenzeit geschlossen" entfaellt. Das ist im Commit-Body dokumentiert, die Datumsregel ist strenger.

## Hinweise (keine Blocker)

- Die Alt-Fixtures stammen laut Plan aus `fork/paper-log`; ob echt oder nachgebaut, steht im SUMMARY. Verhalten wurde zusaetzlich mit einem eigenen Alt-Block geprueft.
- Menschliche Pruefung nicht noetig (kein UI, kein Live-Netzwerkpfad).
