---
title: Open info findings (IN-*) from the phase 2-4 reviews, triaged against the code
created: 2026-10-18
resolves_phase: 6
area: tooling
source:
  - .planning/phases/02-verbindung-paper-guard-und-kontolesen/02-REVIEW.md (IN-01..07)
  - .planning/phases/03-symbol-aufl-sung-handelbarkeit-und-handelszeiten/03-REVIEW.md (IN-01..08)
  - .planning/phases/04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev/04-REVIEW.md (IN-01..07)
files:
  - scripts/ibkr_executor.py
  - scripts/ibkr_broker.py
  - scripts/ibkr_contracts.py
---

## Problem

Die Code-Reviews von Phase 2, 3 und 4 haben je 7-8 Info-Befunde (IN-*) gemeldet, die
Review-Fix-Läufe aber nur CR/WR beauftragt. Am 2026-10-18 gegen `main` (`178df83`)
gesichtet. Drei davon werden erst mit dem Senden in Phase 6 scharf und gehören in deren
Planung; der Rest ist Aufräumarbeit.

## Für Phase 6 relevant (beim Planen entscheiden)

- **P4 IN-05 — Budget je Ticker statt summiert.** Jeder Ticker eines Laufs wird gegen
  dieselbe `AvailableFunds`-Messung geprüft (`ibkr_executor.py:1963`, `:2191`); die Summe
  der `initMarginChange` mehrerer BUY-Absichten nicht. Im Trockenlauf harmlos, beim echten
  Senden mehrerer Käufe in einem Lauf eine Lücke. Bei `MAX_QTY_PER_ORDER = 2` und dem
  heutigen Paper-Kontostand praktisch ohne Folgen, als Leitplanke aber falsch.
- **P2 IN-07 — `IBKR_HOST` nicht auf Loopback beschränkt** (`ibkr_executor.py`, Settings).
  Entschärft durch die Gateway-Einstellung „Allow connections from localhost only"
  (gesetzt, 2026-10-12); im Code fehlt die zweite Quelle im Sinne von REQ-IBKR-63.
- **P4 IN-03 — Steuerzeichen in Order-Stringfeldern.** Praktisch entschärft: der
  `decision_key`, der als `orderRef` gesendet wird, läuft seit Phase 5 durch eine
  `fullmatch`-Whitelist (`ibkr_guards.py:347-349`), die übrigen Felder sind Konstanten.
  Für Phase 6 nur prüfen, ob ein neues String-Feld dazukommt.

## Schon erledigt (nicht mehr anfassen)

- **P2 IN-02, P4 IN-04 — nicht-endliche Kontowerte / Budget fail-open:** behoben in
  `178df83` (2026-10-18).
- **P3 IN-06 — `None` in der Kandidatenliste:** behoben (`ibkr_broker.py`, `any(c is None …)`).
- **P4 IN-01 — `match` mit `$`:** in `ibkr_guards.py` auf `fullmatch` umgestellt (Phase 5);
  `ibkr_paperlog.py:18-21` und `ibkr_decision.py:136` nutzen weiter `match` mit `$` — bei
  `.strip()`-ten Settings ohne Wirkung, beim Aufräumen mitnehmen.
- **P2 IN-04 — Code 2107:** im Lesefenster seit `d344433` harmlos (`WINDOW_BENIGN_CODES`),
  in `STATE_BY_CODE` aber weiter ohne Namen (loggt `UNKNOWN` auf WARNING).

## Aufräumen, ungeprüft offen (eine Quick-Task nach Phase 6)

P2 IN-01 (Zeilenverweis im Handbuch), IN-03 (doppelte Ticker im `PortfolioContext`),
IN-05 (Isolationstests rein lexikalisch), IN-06 (`fsync` vor `os.replace`, verwaiste
`.tmp`); P3 IN-01 (Altformat über Mitternacht), IN-02 (History-Zeile ohne `-aborted` nach
Crash), IN-03 (Anker-Ticker doppelt), IN-04/IN-05 (falsche Datei in Log/Konsole), IN-07
(ungetestete Zweige im Lernpfad), IN-08 (Wall-Clock-Assertion); P4 IN-02 (veraltete
Docstrings), IN-06 (Decision-Log-Kopie als geteilter Fixpfad), IN-07 (`--out` löscht vor
der Validierung). Fundstellen stehen in den jeweiligen REVIEW-Dateien.
