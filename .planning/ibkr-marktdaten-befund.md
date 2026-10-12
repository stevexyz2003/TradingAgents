# IBKR-Marktdaten- und Währungsbefund (Messung, M2 Vorarbeit)

**Gemessen:** 2026-10-11, Sonntagabend (**Markt geschlossen** — das ist für
Befund 4 wesentlich) · Gateway **10.50.1** · Konto `DUQ634065` · `ib_async` 2.1.0

Ergänzt [ibkr-konto-befund.md](./ibkr-konto-befund.md). Beantwortet die Frage,
ob die Mengenrechnung aus Phase 4 überhaupt rechnen kann: Woher kommt ein Preis,
und wie verträgt sich ein **EUR**-Konto mit **USD**-Aktien?

## 1. Aktienkurse: verfügbar, aber nur verzögert und ohne Bid/Ask

Mit `reqMarketDataType(3)` (delayed, kein Abo nötig):

```text
AAPL  last=336.08 close=340.42 bid=-1 ask=-1 marketDataType=3
MSFT  last=535.0  close=522.61 bid=-1 ask=-1 marketDataType=3
NVDA  last=229.33 close=230.48 bid=-1 ask=-1 marketDataType=3
```

IBKR meldet dazu **10167** („Sie haben die angeforderten Marktdaten nicht
abonniert. Es werden verzögerte Marktdaten angezeigt"). Nutzbar sind `last` und
`close`; **`bid`/`ask` sind `-1`**, also nicht vorhanden.

**Folge für Phase 4:** Eine Limit-Order darf ihren Preis nicht aus dem Spread
ableiten — den gibt es hier nicht. Als Referenz bleibt `last` bzw. `close`, und
der ist verzögert. Wer einen Limit-Abstand in Prozent rechnet, rechnet ihn gegen
einen veralteten Kurs; das gehört in die Begründung des Limit-Verfahrens.

## 2. Wechselkurs EUR/USD: über Marktdaten **nicht** verfügbar

```text
EUR.USD last=nan close=nan bid=nan ask=nan
10089: Für die angeforderten Marktdaten ist ein zusätzliches Abonnement für APIs erforderlich
```

Anders als die Aktien fällt Forex **nicht** auf verzögerte Daten zurück, sondern
liefert gar nichts. Ein Kurs ist ohne Abo nicht zu holen.

## 3. Kontobericht: kennt derzeit nur BASE und EUR

```text
alle Währungen im Kontobericht: ['BASE', 'EUR']
ExchangeRate je Währung:        (keine Zeile)
USD-Zeilen:                     (keine)
```

Der naheliegende Ausweg — den Kurs aus `accountValues()` lesen — trägt **vor der
ersten USD-Position nicht**: Die USD-Zeile (und damit `ExchangeRate`) entsteht
erst, wenn das Konto tatsächlich USD hält oder schuldet. Das Konto ist flach
(0 Positionen), also gibt es sie nicht.

**Damit ist die Lage für Phase 4:** Das Konto rechnet in EUR
(`NetLiquidation=1005888.32 EUR`, `BuyingPower=6705922.13 EUR`), die Instrumente
notieren in USD, und einen eigenen Umrechnungskurs hat der Ausführer nicht. Eine
Positionsgröße lässt sich deshalb **nicht** sauber als „X EUR pro Order"
ausdrücken und in Stückzahl umrechnen — jedenfalls nicht vor dem ersten Kauf.

Das stützt die bereits gesetzte Entscheidung, in **festen Stückzahl-Blöcken** zu
arbeiten statt in Beträgen: Stückzahlen brauchen keinen Wechselkurs. Die
Begrenzung „harte Positionsgröße pro Order" ist dann als Stückzahl **und**
optional als Obergrenze in USD (`Stück × last`) formulierbar, ohne EUR zu
berühren.

## 4. `whatIf` — **GELÖST**: die Order-Voreinstellung verwarf die Anfrage

**Ursache gefunden am 2026-10-12.** Nicht der geschlossene Markt, nicht die
Bibliothek — die **Order-Voreinstellung des Gateways**:

`LimitOrder(...)` aus `ib_async` setzt kein `tif`. Das Gateway schreibt es dann
gemäß seiner Voreinstellung auf `DAY` um, meldet das als **10349** — und
**verwirft dabei die whatIf-Anfrage**. Zurück kommt eine leere Liste statt eines
`OrderState`, ohne Fehler. Der 10349 lag bei jeder Messung vor und sah wie eine
Randnotiz aus.

**Die Lösung ist eine Zeile:** `order.tif` explizit setzen.

```text
whatIf tif='DAY'  -> OrderState   whatIf tif='GTC'  -> OrderState   (identisch)
    initMarginChange     = 640.64
    maintMarginChange    = 582.4
    commission           = 4.0
    commissionCurrency   = EUR
```
(SAP/IBIS, 10 Stück LMT 180, gemessen bei **offenem** XETRA-Handel 14:48 MESZ.)

Dass der Markt offen war, widerlegte zugleich die alte Hypothese: Dieselbe
leere Liste kam auch bei `tradingHours=True` und `liquidHours=True`.

### Und damit ist auch die Währungsfrage aus Befund 3 gelöst

Dieselbe Abfrage auf **AAPL** (USD-Papier, EUR-Konto, US-Pre-Market):

```text
AAPL whatIf tif='DAY' -> OrderState
    initMarginChange     = 997.14      <- Kontowährung EUR
    maintMarginChange    = 906.49
    commission           = 1.00003
    commissionCurrency   = USD         <- Instrumentwährung
```

10 × 336 USD ≈ 3360 USD ≈ 3100 EUR; 997 EUR entspricht rund 32 % Initial Margin.
**Margin kommt in Kontowährung, Kommission in Instrumentwährung.**

Für Phase 4 heißt das: Das Preview liefert die Umrechnung **implizit**. Ob eine
Order ins EUR-Budget passt, ist über `initMarginChange` prüfbar, ohne dass der
Ausführer je einen EUR/USD-Kurs braucht — der über Marktdaten ohnehin nicht zu
bekommen ist (Befund 2). Kein Marktdaten-Abo nötig.

### Anforderungen, die daraus folgen

1. **`tif` wird bei jeder Order explizit gesetzt** — sonst greift die
   Voreinstellung des Gateways und die Preview-Anfrage verschwindet
   wortlos. Der tatsächlich gesetzte Wert wird aus dem Ergebnis zurückgelesen.
2. **Gate G2 prüft auf einen `OrderState` mit Margin-Feldern**, nicht auf
   „kein Fehler". Eine leere Liste ist eine Ablehnung (siehe
   Sicherungsprinzip S-01).
3. **Budgetprüfung über `initMarginChange`** in Kontowährung statt über eine
   eigene Währungsrechnung.
4. **10349 ist kein harmloser Hinweis**, sondern der Marker dieses Problems —
   er gehört in die Liste der behandelten Codes.

## Offene Punkte

1. Entscheiden, ob verzögerte Kurse für das Limit-Verfahren genügen oder ob ein
   Marktdaten-Abo nötig wird — Letzteres ist eine Kostenentscheidung des
   Operators, keine technische.
3. Nach der ersten USD-Position prüfen, ob `ExchangeRate` dann im Kontobericht
   erscheint; damit wäre die Umrechnung für Auswertungen (nicht für die
   Order-Erzeugung) verfügbar.
