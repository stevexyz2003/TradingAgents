# Redundante Absicherung des Handels — Grundregel und Anforderungs-Kandidaten

**Erstellt:** 2026-10-12 · Quick-Task `261012-ap2` · Operator-Vorgabe:
„Sichere den Handel wenn es geht immer redundant ab."

**Status:** Kein Code. Dieses Dokument ist für die Übernahme nach
`REQUIREMENTS.md` gedacht — es entstand parallel zur Phase-2-Planung und fasst
deshalb bewusst keine Planungsdatei an.

---

## Die Grundregel

> **Eine Freigabe braucht einen positiven Beweis. Das Ausbleiben eines Fehlers
> ist kein Beweis.**

Jede Stelle, an der Code eine Order weiterlaufen lässt, muss auf etwas zeigen
können, das sie *gesehen* hat — einen Status, einen Wert, eine Bestätigung.
„Es kam keine Ablehnung" reicht nie.

Das ist keine Theorie. In dieser Sitzung wurde die Regel viermal gemessen:

| Beobachtung | Was naive Logik daraus gemacht hätte |
|---|---|
| `whatIfOrder()` lieferte `[]`, ohne Fehler | „Preview ok, Order freigeben" |
| Read-Only meldet **321**, nicht das erwartete 10015 | „Kein 10015 → Schreibrecht da" |
| Gateway auf Port 7497 statt 4002 | „Port stimmt nicht → kein Paper-Konto" bzw. umgekehrt |
| Ein Lese-Aufruf **hängte** statt zu scheitern | Ewiges Warten, kein Fehler, kein Alarm |

Dazu aus der Smoke-Arbeit am selben Tag: Eine Assertion schlug *genau dann* fehl,
wenn ihr Marker gefunden wurde (SIGPIPE unter `pipefail`). Ein Gate, das
unbemerkt die Bedeutung wechselt, ist schlimmer als keins.

---

## Anforderungs-Kandidaten

### S-01 — Leere oder unvollständige Antwort gilt als Ablehnung
Liefert `whatIfOrder()` keine Margin-/Kommissionswerte — leere Liste, `None`,
fehlende Felder — wird das wie eine abgelehnte Vorschau behandelt: keine Order,
benannter Zustand, eigener Exit-Code. **Nachweis:** Test mit gestubbtem Leer-
Rückgabewert; es darf kein `placeOrder` erfolgen.

### S-02 — Jeder API-Aufruf hat ein Timeout
Kein Aufruf ohne Zeitgrenze, und ein Timeout ist ein benannter Fehlerzustand,
kein stilles Weiterlaufen. **Begründung:** gemessen, dass ein Aufruf im
Read-Only-Modus ohne Antwort hängen blieb. **Nachweis:** Test mit nicht
antwortender Gegenstelle endet im Fehlerpfad, nicht im Hänger.

### S-03 — Zwei unabhängige Quellen pro sicherheitskritischem Fakt
Keine Order, solange nicht **zwei voneinander unabhängige** Signale übereinstimmen:

| Fakt | Quelle A | Quelle B |
|---|---|---|
| Es ist das Paper-Konto | `managedAccounts == {DUQ634065}` | Kontofeld der Order selbst |
| Aktuelle Position | lokaler Ledger | `reqPositions()` am Konto |
| Entscheidung schon ausgeführt? | Ledger-Eintrag auf `decision_key` | `orderRef`-Suche über offene/erledigte Orders |
| Instrument handelbar | `tradingSessions()` | Order-Status nach Platzierung (Warnung 399 = geparkt, nicht aktiv) |

Widersprechen sich A und B, gilt der **vorsichtigere** Wert und der Lauf meldet
den Widerspruch. **Nachweis:** je ein Test, der A und B absichtlich auseinander
laufen lässt und zeigt, dass keine Order entsteht.

### S-04 — Der Kill-Switch ist fail-closed und wird mehrfach geprüft
Freigabe erfordert **beides**: ausdrückliche Freigabe vorhanden **und**
Kill-Datei abwesend. Geprüft wird unmittelbar vor **jeder** Order, nicht einmal
beim Start. Fehlt die Freigabedatei oder ist sie unlesbar, wird nicht gehandelt.
Als scharfer Arm bleibt `reqGlobalCancel` für bereits liegende Orders.
**Nachweis:** Test mit unlesbarer Freigabedatei → keine Order.

### S-05 — Nach der Order wird gegen IBKR verifiziert, nicht gegen den eigenen Zustand
Was der Ausführer glaubt platziert zu haben, zählt nicht. Nach jeder Order wird
der tatsächliche Zustand bei IBKR gelesen (Status, Stückzahl, `orderRef`) und
mit der Absicht verglichen. Abweichung = Alarm, kein stilles Fortfahren.

### S-06 — Jede Schutzmaßnahme braucht eine Negativ-Kontrolle
Zu jeder Sicherung gehört ein Test, der beweist, dass sie **greift**: ein Lauf,
in dem sie auslösen *muss* und der Durchlauf scheitert. Eine Sicherung ohne
Negativ-Kontrolle ist eine Behauptung. **Begründung:** Genau so wurde der
SIGPIPE-Fehler im Smoke-Gate gefunden — die Negativ-Kontrolle fiel auf, nicht
der Positivlauf.

### S-07 — Fehlercodes werden gemessen, nicht angenommen
Erwartete Codes werden gegen das reale Gateway geprüft, bevor ein Test auf sie
baut. **Begründung:** Die Anforderung nannte 10015, real ist es 321 — ein Test
gegen 10015 wäre nie grün geworden und hätte eine Sicherung vorgetäuscht.

### S-08 — Preisloses Rechnen statt stiller Annahmen
Ohne verfügbaren Wechselkurs (EUR-Konto, USD-Instrumente) wird in Stückzahlen
gerechnet. Fehlt ein Kurs oder ein Preis, wird die Größe **nicht geschätzt** —
der Lauf meldet und hält an. `bid`/`ask` sind bei verzögerten Daten `-1`; ein
Limitverfahren darf sie nicht als Zahl verwenden.

---

## Was das kostet

Redundanz macht den Ausführer langsamer und das Scheitern häufiger — es wird
Tage geben, an denen nichts gehandelt wird, weil zwei Quellen sich widersprechen.
Das ist der Zweck. Ein nicht ausgeführter Handel kostet eine Gelegenheit; ein
doppelt ausgeführter oder gegen eine veraltete Entscheidung gestellter Handel
kostet Geld und das Vertrauen in den Track-Record.
