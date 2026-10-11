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

## 4. `whatIf` liefert bei geschlossenem Markt eine **leere Liste**

```text
ib.whatIfOrder(AAPL, LimitOrder BUY 10 @ 336.00, whatIf=True)
typ: list
repr: []
(einziger Code: 10349 - Gültigkeitsdauer gemäß Order-Voreinstellungen auf DAY gesetzt)
```

Erwartet war ein `OrderState` mit `initMarginChange`, `maintMarginChange`,
`equityWithLoanChange` und `commission` — in Kontowährung, womit das Preview
zugleich die fehlende Umrechnung aus Befund 3 geliefert hätte.

**Stattdessen kam `[]`, ohne Fehlermeldung.** Kein `OrderState`, keine Ablehnung,
kein Grund.

**Nicht abschließend geklärt:** Die Messung lief am Sonntagabend bei
geschlossenem Markt. Ob das Preview zu Handelszeiten Werte liefert, ist **zu
Handelszeiten erneut zu messen** — frühestens Montag nach 09:30 US/Eastern
(15:30 MESZ). Dies hier ist ein Befund, keine Diagnose.

**Was unabhängig vom Grund für Phase 4 gilt:** Gate G2 steht und fällt mit dem
Preview. Der Ausführer darf eine leere Antwort **niemals** als Freigabe lesen.
„Kein `OrderState`" muss denselben Weg nehmen wie „Preview abgelehnt": keine
Order, benannter Zustand, Exit-Code. Sonst entsteht genau das, wogegen G2 gebaut
wurde — eine Order, die ein nicht stattgefundenes Preview passiert hat.

## Offene Punkte

1. `whatIf` zu Handelszeiten erneut messen (Befund 4).
2. Entscheiden, ob verzögerte Kurse für das Limit-Verfahren genügen oder ob ein
   Marktdaten-Abo nötig wird — Letzteres ist eine Kostenentscheidung des
   Operators, keine technische.
3. Nach der ersten USD-Position prüfen, ob `ExchangeRate` dann im Kontobericht
   erscheint; damit wäre die Umrechnung für Auswertungen (nicht für die
   Order-Erzeugung) verfügbar.
