---
title: Mark non-engine (pipeline-test) orders in the ledger
created: 2026-10-20
area: tooling
source: .planning/phases/06-die-erste-echte-order/06-VERIFICATION.md (gap 2)
files:
  - scripts/ibkr_decision.py (RATING_SOURCES, evaluate_decision)
  - scripts/ibkr_ledger.py (intent fields)
  - phase 7 Soll-Ist report
---

## Problem

Die erste echte Order (2026-10-19, BUY 1 AAPL, Key `2026-10-16|AAPL`) war ein
Pipeline-Test vom Branch `fork/paper-log-pipeline-test`, keine Entscheidung der
Engine. Im Ledger steht beim `intent` trotzdem `rating_source: engine`, weil der
Executor nur `engine` handelt. Die Herkunft belegen nur `paper_log_sha`
(`8453e76…`), `preview.json` und der Befund.

Der Soll-Ist-Bericht aus Phase 7 würde diese Order als Engine-Order zählen und die
Bilanz der Engine verfälschen.

## Lösung

- Phase 7 / Soll-Ist: Den Key `2026-10-16|AAPL` mit `paper_log_sha`
  `8453e7642f257f6cf1cdd5ebb1738feee3632b3f` ausdrücklich als Pipeline-Test
  ausschließen oder kennzeichnen. Am einfachsten über eine kleine Ausschlussliste
  im Repo mit Begründung.
- Optional für künftige Tests: Ein eigener `rating_source`-Wert (z. B.
  `pipeline-test`), den der Executor nur mit einem expliziten Flag handelt und der
  im `intent` mitgeschrieben wird. Nur bei Bedarf; heute gibt es keinen weiteren
  Pipeline-Test.
