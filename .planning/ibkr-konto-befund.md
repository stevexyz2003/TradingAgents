# IBKR-Konto-Befund — M2 Phase 1 (REQ-IBKR-01, REQ-IBKR-02)

**Gemessen:** 2026-10-11 (zweiter Durchgang am Gateway 10.50.1) · Konto `DUQ634065` · gemessen per Wegwerf-Sonde über
`ib_async` 2.1.0, ausschließlich lesend (`readonly=True`), nichts platziert.

## Die fünf Fragen

### 1. Verlangt der Paper-Login einen Zweitfaktor? — **NEIN**

Operator-Messung: Anmeldung am IB Gateway mit Benutzername und Kennwort allein
war erfolgreich, kein Zweitfaktor-Prompt.

**Abgeleitete Betriebsform: Wochenlogin automatisierbar.** Damit ist der
unbeaufsichtigte Betrieb aus Phase 8 möglich, ohne dass ein Mensch täglich
quittieren muss. Die offizielle Doku war hier widersprüchlich („all accounts
required to enroll in 2FA" betrifft das Enrollment auf Kontoebene, nicht den
Prompt beim Login mit dem separaten Paper-Username) — die Messung entscheidet.

### 2. Läuft Gateway/TWS im Paper-Modus, und was sagt `managedAccounts`?

`managedAccounts()` liefert wörtlich: `['DUQ634065']` — genau die erwartete
Einermenge. Der Paper-Guard aus REQ-IBKR-04 ist damit umsetzbar wie geplant.

**Abweichung von der Annahme, mit Folgen für `.env`:** Es läuft ein **IB
Gateway** (Screenshot `docs/screenshots/Screenshot 2026-10-11 200033.png`:
Titelleiste „IBKR-GATEWAY", API-Server verbunden), aber der API-Port ist auf
**7497** konfiguriert, nicht auf dem Gateway-Default 4002. Port 4002 ist zu.

Das belegt den Recherche-Satz, dass der Port **keine** Paper-Garantie ist — hier
trägt ein Gateway den TWS-Paper-Port. **Entschieden am 2026-10-11:** `.env` wurde
auf `IBKR_PORT=7497` korrigiert, das Gateway bleibt unverändert; der Grund für die
Abweichung vom Default steht als Kommentar in `.env`. Damit ist die Port-Angabe
nur noch Konfiguration, und die Paper-Zusicherung hängt allein am
`managedAccounts`-Guard — so, wie REQ-IBKR-04 es verlangt.

Verbindungsdaten: `serverVersion=178`, Gateway-Zeit `2026-10-11 18:00:40+00:00`.

### 3. Kapital und Bestand

`AccountType=INDIVIDUAL` · `NetLiquidation=1005888.32 EUR` ·
`TotalCashValue=1005459.44 EUR` · `BuyingPower=6705922.13 EUR` · `positions: 0`

**Befund mit Folgen für die Mengenrechnung:** Die Kontowährung ist **EUR**, die
gehandelten Ticker (AAPL, MSFT, NVDA) notieren in **USD**. Eine Positionsgröße
in „USD pro Order" ist damit nicht gleich einer Größe in Kontowährung; REQ-IBKR
zur Positionsgröße muss die Währung benennen, und der Wechselkurs geht in die
Soll-Rechnung ein. Das war in der Planung nicht vorgesehen.

### 4. Contract-Auflösung je secType

Alle sechs Sonden lieferten einen Treffer (Rohausgabe unten). Kernwerte:

| Sonde | conId | secType | exchange | localSymbol | Treffer |
|---|---|---|---|---|---|
| AAPL | 265598 | STK | SMART (primary NASDAQ) | `AAPL` | 1 |
| SPX | 416904 | IND | CBOE | `SPX` | 1 |
| XAUUSD | 69067924 | CMDTY | SMART | `XAUUSD` | 1 |
| EURUSD | 12087792 | CASH | IDEALPRO | `EUR.USD` | 1 |
| BTC | 479624278 | CRYPTO | PAXOS | `BTC.USD` | 1 |
| ES | 515416632 | FUT | CME | `ESZ6` | **21** |

**Zwei Befunde, die die Auflösungskette ändern:**

- **`ineligibilityReasonList` existiert in `ib_async` 2.1.0 nicht.** Die
  Recherche führt es als Schicht 4 der fünfschichtigen Erkennungskette; das
  Attribut ist auf `ContractDetails` schlicht nicht vorhanden (vollständige
  Feldliste in der Rohausgabe). Die Kette muss ohne auskommen — tragfähig
  bleiben `validExchanges`, `orderTypes` und der `whatIf`-Preview.
- **`FUT ES` liefert 21 Treffer**, je Kontraktmonat einen. Das bestätigt, dass
  „genau ein Treffer" als Eindeutigkeitskriterium nötig ist: ein Future ohne
  Monatsangabe ist mehrdeutig, und ein stillschweigendes `details[0]` würde den
  nächstbesten Kontraktmonat kaufen.

Dass `XAUUSD` als `CMDTY` auf `SMART` existiert (conId 69067924), bestätigt den
Recherche-Befund gegen `normalize_symbol()`, das `XAUUSD+` verlustbehaftet nach
`GC=F` (COMEX-Future) normalisiert — zwei verschiedene Instrumente.

### 5. Handelszeiten — gelöst, ohne harte Uhrzeiten

Für AAPL: `timeZoneId='US/Eastern'`, und `tradingHours` nennt den Messtag
wörtlich `20261011:CLOSED` (Sonntag) gefolgt von `0400-2000` je Handelstag;
`liquidHours` entsprechend `0930-1600`. `tradingSessions()` liefert daraus
zeitzonenbewusste `datetime`-Paare. Feiertage und Halbtage kommen damit vom
Server, ein eigener Kalender ist nicht nötig (REQ-IBKR zur Handelszeit ist
umsetzbar wie geplant).

## Erfolgskriterium 5: Read-Only — **erfüllt (2. Messung), mit zwei Korrekturen**

**Read-Only ist am Gateway NICHT aktiv** (gemessen 2026-10-11 20:15). Der
bewusste Platzierungsversuch (`BUY 1 AAPL LMT 1.00`, ein Limit, das nie füllt)
wurde **angenommen** statt mit Fehler 10015 abgelehnt:

```text
managedAccounts=['DUQ634065']
contract conId=265598 AAPL
platziere: BUY 1 AAPL LMT 1.00 (nie fuellbar)
  [API] code=10349 msg=Die Gueltigkeitsdauer der Order wurde gemaess Order-Voreinstellungen auf DAY gesetzt.
  [API] code=399  msg=Order-Mitteilung: KAUFEN 1 AAPL NASDAQ.NMS Warnung: Ihre Order
                      wird nicht vor 2026-10-12 09:30:00 US/Eastern an der Boerse platziert.
orderStatus='PreSubmitted' orderId=4 filled=0.0
ERGEBNIS: Read-Only ist NICHT aktiv - Order wurde angenommen.
storniere sofort ...
  [API] code=202 msg=Order storniert - Grund:
  Status nach Cancel: 'Cancelled'
offene Orders gesamt=0 davon aus dieser Probe=0
```

Die Probe-Order wurde sofort storniert, nichts wurde gefüllt, keine Order blieb
im Buch, der Kontostand ist unverändert. **Erfolgskriterium 5 ist damit NICHT
erfüllt** — es verlangt, dass ein Platzierungsversuch scheitert. Erfüllbar wird
es erst, nachdem „Read-Only API" im Gateway aktiviert wurde; der Nachweis ist
dann zu wiederholen.

Was die Messung trotzdem belegt: Der **Schreibpfad funktioniert** (das Gateway
nimmt Orders an, vergibt `orderId`, akzeptiert `orderRef`, storniert auf
`cancelOrder`) — für Phase 6 ist das die Vorab-Bestätigung, dass nichts außer
der Freigabe fehlt.

### Drei Nebenbefunde mit Folgen

1. **Das Gateway läuft am 2026-12-15 aus.** Code 2172 wörtlich: „Die von Ihnen
   verwendete Version der Anwendung (1045.1) erfordert ein Upgrade, da die
   momentane Version ab 20261215 nicht mehr unterstützt wird. Die unterstützte
   Mindestversion ab diesem Zeitpunkt ist 1050.1." Das fällt mitten in die
   Bauzeit von M2 und gehört in Phase 8 (Betrieb), nicht in eine Fußnote.
2. **Die Order-Voreinstellungen überschreiben die Gültigkeitsdauer** (Code
   10349: TIF wurde auf DAY gesetzt, ohne dass die Order das verlangt hat). Wer
   GTC erwartet, bekommt stillschweigend DAY. Die Order-Erzeugung muss den
   tatsächlich gesetzten TIF aus dem `Trade`-Objekt zurücklesen statt dem
   eigenen Wunsch zu vertrauen.
3. **Warnung 399 bestätigt die Handelszeiten-Regel aus der Praxis:** Eine Order
   außerhalb der Sitzung wird nicht abgelehnt, sondern angenommen und bis zur
   Eröffnung geparkt. Die Prüfung auf `tradingSessions()` vor der Platzierung
   ist damit keine Formalie — ohne sie entsteht eine Order, die Stunden später
   zu einem unbekannten Kurs auf den Markt trifft.

## 2. Messung (20:24): Read-Only aktiv — Nachweis erbracht

Nach Aktivierung von „Read-Only API" im Gateway **10.50.1** wurde derselbe
Platzierungsversuch wiederholt und **abgelehnt**:

```text
managedAccounts=['DUQ634065']
platziere: BUY 1 AAPL LMT 1.00 (nie fuellbar)
  [API] code=321 msg=Bei der Validierung der Anfrage ist ein Fehler aufgetreten.
                     -'bC' : cause - Die API befindet sich im schreibgeschuetzten Modus.
orderStatus='ValidationError' orderId=4 filled=0.0
offene Orders gesamt=0 davon aus dieser Probe=0
```

**Korrektur 1 — der Fehlercode:** Erwartet war **10015** („Trading is not allowed
in the API"). Das reale Gateway 10.50.1 liefert **321** mit der Klartextursache
„Die API befindet sich im schreibgeschützten Modus", und der Order-Status bleibt
`ValidationError`. REQUIREMENTS.md und ROADMAP.md sind entsprechend korrigiert —
ein Test gegen 10015 wäre nie grün geworden.

**Korrektur 2 — Read-Only ist keine Voreinstellung.** Die Annahme „im Gateway
standardmäßig an" ist falsch: In der ersten Messung war der Schreibschutz aus und
die Order wurde angenommen. Es ist eine aktive Handlung des Operators, auf deren
Vorhandensein sich keine Phase verlassen darf.

**Zustand danach:** Der Operator hat den Schreibschutz nach dem Nachweis wieder
**deaktiviert** (20:27). Für die Phasen 2–4 heißt das: Es gibt keinen
Gateway-seitigen Schutz mehr, es trägt allein der clientseitige
`readonly=True`-Parameter von `ib_async`. Das ist schwächer — eine Verbindung,
die ihn vergisst, darf schreiben. REQ-IBKR-03 muss das behandeln.

**Nebenbeobachtung, nicht isoliert:** Mit aktivem Read-Only kamen bereits beim
Verbinden zwei 321-Meldungen, bevor eine Order im Spiel war, und ein
anschließender Sondierungslauf über die Lese-Aufrufe **blieb ohne Antwort
hängen** statt zu scheitern. Welcher Aufruf das war, ist nicht isoliert — der
Schreibschutz wurde vorher wieder deaktiviert. Für Phase 2 bleibt die
belastbare Konsequenz: **jeder API-Aufruf braucht ein Timeout**, ein Hänger ohne
Zeitgrenze legt den täglichen Ausführer still.

## Handlungsbedarf (Operator)

1. ~~Port-Widerspruch auflösen~~ — **erledigt 2026-10-11**, `.env` steht auf 7497.
2. ~~„Read-Only API" aktivieren und Nachweis wiederholen~~ — **erledigt
   2026-10-11 20:24** (Marker 321 statt 10015). Schreibschutz danach vom
   Operator wieder deaktiviert.
3. **Gateway-Upgrade auf ≥ 1050.1 vor dem 2026-12-15** einplanen (Code 2172).

## Rohausgabe der Sonde

```text
=== connect 127.0.0.1:7497 clientId=98 ==========================
connected=True serverVersion=178
TWS/Gateway time: 2026-10-11 18:01:00+00:00

=== managedAccounts (Paper-Guard, REQ-IBKR-04) ==================
['DUQ634065']

=== accountSummary: Kapital =====================================
DUQ634065 AccountType = INDIVIDUAL 
DUQ634065 AvailableFunds = 1005888.32 EUR
DUQ634065 BuyingPower = 6705922.13 EUR
DUQ634065 NetLiquidation = 1005888.32 EUR
DUQ634065 TotalCashValue = 1005459.44 EUR
All Currency = EUR EUR
All Currency = BASE BASE

=== positions ===================================================
count=0

=== ContractDetails: vorhandene Felder (Research-Korrektur) =====
['aggGroup', 'bondType', 'callable', 'category', 'contract', 'contractMonth', 'convertible', 'coupon', 'couponType', 'cusip', 'descAppend', 'evMultiplier', 'evRule', 'industry', 'issueDate', 'lastTradeTime', 'liquidHours', 'longName', 'marketName', 'marketRuleIds', 'maturity', 'mdSizeMultiplier', 'minSize', 'minTick', 'nextOptionDate', 'nextOptionPartial', 'nextOptionType', 'notes', 'orderTypes', 'priceMagnifier', 'putable', 'ratings', 'realExpirationDate', 'secIdList', 'sizeIncrement', 'stockType', 'subcategory', 'suggestedSizeIncrement', 'timeZoneId', 'tradingHours', 'underConId', 'underSecType', 'underSymbol', 'validExchanges']

=== reqContractDetails STK  AAPL ================================
Treffer: 1
  conId=265598 localSymbol='AAPL' primaryExchange='NASDAQ' currency='USD' secType='STK' exchange='SMART'
  validExchanges='SMART,AMEX,NYSE,CBOE,PHLX,ISE,CHX,ARCA,NASDAQ,DRCTEDGE,BEX,BATS,EDGEA,BYX,IEX,EDGX,FOXRIVER,PEARL,NYSENAT,LTSE,MEMX,IBEOS,OVERNIGHT,TPLUS0,PSX,T24X,TXSE'
  ineligibilityReasonList='<ATTRIBUT FEHLT in ib_async 2.1.0>'
  timeZoneId='US/Eastern'
  tradingHours='20261011:CLOSED;20261012:0400-20261012:2000;20261013:0400-20261013:2000;20261014:0400-20261014:2000;20261015:0400-20261015:2000;20261016:0400-20261016:2000'
  liquidHours='20261011:CLOSED;20261012:0930-20261012:1600;20261013:0930-20261013:1600;20261014:0930-20261014:1600;20261015:0930-20261015:1600;20261016:0930-20261016:1600'
  tradingSessions()=[TradingSession(start=datetime.datetime(2026, 10, 12, 4, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Eastern')), end=datetime.datetime(2026, 10, 12, 20, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Eastern'))), TradingSession(start=datetime.datetime(2026, 10, 13, 4, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Eastern')), end=datetime.datetime(2026, 10, 13, 20, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Eastern')))]

=== reqContractDetails IND  SPX =================================
Treffer: 1
  conId=416904 localSymbol='SPX' primaryExchange='' currency='USD' secType='IND' exchange='CBOE'
  validExchanges='CBOE'
  ineligibilityReasonList='<ATTRIBUT FEHLT in ib_async 2.1.0>'
  timeZoneId='US/Central'
  tradingHours='20261011:CLOSED;20261012:0830-20261012:1500;20261013:0830-20261013:1500;20261014:0830-20261014:1500;20261015:0830-20261015:1500;20261016:0830-20261016:1500'
  liquidHours='20261011:CLOSED;20261012:0830-20261012:1500;20261013:0830-20261013:1500;20261014:0830-20261014:1500;20261015:0830-20261015:1500;20261016:0830-20261016:1500'
  tradingSessions()=[TradingSession(start=datetime.datetime(2026, 10, 12, 8, 30, tzinfo=zoneinfo.ZoneInfo(key='US/Central')), end=datetime.datetime(2026, 10, 12, 15, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Central'))), TradingSession(start=datetime.datetime(2026, 10, 13, 8, 30, tzinfo=zoneinfo.ZoneInfo(key='US/Central')), end=datetime.datetime(2026, 10, 13, 15, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Central')))]

=== reqContractDetails CMDTY XAUUSD =============================
Treffer: 1
  conId=69067924 localSymbol='XAUUSD' primaryExchange='' currency='USD' secType='CMDTY' exchange='SMART'
  validExchanges='SMART'
  ineligibilityReasonList='<ATTRIBUT FEHLT in ib_async 2.1.0>'
  timeZoneId='US/Eastern'
  tradingHours=';20261011:1800-20261012:1700;20261012:1800-20261013:1700;20261013:1800-20261014:1700;20261014:1800-20261015:1700;20261015:1800-20261016:1700'
  liquidHours=';20261011:1800-20261012:1700;20261012:1800-20261013:1700;20261013:1800-20261014:1700;20261014:1800-20261015:1700;20261015:1800-20261016:1700'
  tradingSessions()=[TradingSession(start=datetime.datetime(2026, 10, 11, 18, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Eastern')), end=datetime.datetime(2026, 10, 12, 17, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Eastern'))), TradingSession(start=datetime.datetime(2026, 10, 12, 18, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Eastern')), end=datetime.datetime(2026, 10, 13, 17, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Eastern')))]

=== reqContractDetails CASH EURUSD ==============================
Treffer: 1
  conId=12087792 localSymbol='EUR.USD' primaryExchange='' currency='USD' secType='CASH' exchange='IDEALPRO'
  validExchanges='IDEALPRO'
  ineligibilityReasonList='<ATTRIBUT FEHLT in ib_async 2.1.0>'
  timeZoneId='US/Eastern'
  tradingHours=';20261011:1715-20261012:1700;20261012:1715-20261013:1700;20261013:1715-20261014:1700;20261014:1715-20261015:1700;20261015:1715-20261016:1700'
  liquidHours=';20261011:1715-20261012:1700;20261012:1715-20261013:1700;20261013:1715-20261014:1700;20261014:1715-20261015:1700;20261015:1715-20261016:1700'
  tradingSessions()=[TradingSession(start=datetime.datetime(2026, 10, 11, 17, 15, tzinfo=zoneinfo.ZoneInfo(key='US/Eastern')), end=datetime.datetime(2026, 10, 12, 17, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Eastern'))), TradingSession(start=datetime.datetime(2026, 10, 12, 17, 15, tzinfo=zoneinfo.ZoneInfo(key='US/Eastern')), end=datetime.datetime(2026, 10, 13, 17, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Eastern')))]

=== reqContractDetails CRYPTO BTC ===============================
Treffer: 1
  conId=479624278 localSymbol='BTC.USD' primaryExchange='' currency='USD' secType='CRYPTO' exchange='PAXOS'
  validExchanges='PAXOS'
  ineligibilityReasonList='<ATTRIBUT FEHLT in ib_async 2.1.0>'
  timeZoneId='US/Eastern'
  tradingHours=';20261009:1601-20261010:1600;20261010:1601-20261011:1600;20261011:1601-20261012:1600;20261012:1601-20261013:1600;20261013:1601-20261014:1600;20261014:1601-20261015:1600;20261015:1601-20261016:1600;20261017:CLOSED;20261016:1601-20261017:1600;20261017:1601-20261018:1600;20261018:1601-20261019:1600'
  liquidHours=';20261009:1601-20261010:1600;20261010:1601-20261011:1600;20261011:1601-20261012:1600;20261012:1601-20261013:1600;20261013:1601-20261014:1600;20261014:1601-20261015:1600;20261015:1601-20261016:1600;20261017:CLOSED;20261016:1601-20261017:1600;20261017:1601-20261018:1600;20261018:1601-20261019:1600'
  tradingSessions()=[TradingSession(start=datetime.datetime(2026, 10, 9, 16, 1, tzinfo=zoneinfo.ZoneInfo(key='US/Eastern')), end=datetime.datetime(2026, 10, 10, 16, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Eastern'))), TradingSession(start=datetime.datetime(2026, 10, 10, 16, 1, tzinfo=zoneinfo.ZoneInfo(key='US/Eastern')), end=datetime.datetime(2026, 10, 11, 16, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Eastern')))]

=== reqContractDetails FUT  ES ==================================
Treffer: 21
  conId=515416632 localSymbol='ESZ6' primaryExchange='' currency='USD' secType='FUT' exchange='CME'
  validExchanges='CME,QBALGO'
  ineligibilityReasonList='<ATTRIBUT FEHLT in ib_async 2.1.0>'
  timeZoneId='US/Central'
  tradingHours=';20261011:1700-20261012:1600;20261012:1700-20261013:1600;20261013:1700-20261014:1600;20261014:1700-20261015:1600;20261015:1700-20261016:1600'
  liquidHours='20261011:CLOSED;20261012:0830-20261012:1600;20261013:0830-20261013:1600;20261014:0830-20261014:1600;20261015:0830-20261015:1600;20261016:0830-20261016:1600'
  tradingSessions()=[TradingSession(start=datetime.datetime(2026, 10, 11, 17, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Central')), end=datetime.datetime(2026, 10, 12, 16, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Central'))), TradingSession(start=datetime.datetime(2026, 10, 12, 17, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Central')), end=datetime.datetime(2026, 10, 13, 16, 0, tzinfo=zoneinfo.ZoneInfo(key='US/Central')))]

=== reqExecutions (Fenster-Frage, REQ-IBKR-01) ==================
count=0

=== offene Orders ===============================================
reqAllOpenOrders -> 0
reqCompletedOrders(apiOnly=False) -> 0

=== ENDE - nichts platziert, Verbindung getrennt ================
```

## whatIf-Vorschau und Read-Only-Schalter (Phase 4, D-14) — 2026-10-12

Gemessen am echten Paper-Gateway 10.50.1 (`127.0.0.1:7497`, Konto `DUQ634065`) über
`IbkrBroker.preview_order` mit einer Wegwerf-Sonde (liegt im Scratchpad, nicht im Repo).
Vorab liefen die Barrier-Tests grün (`whatif_barrier or place_order_refused or preview`:
37 passed); die Sperre aus 04-02 (Id 3 nur als STK-whatIf) war damit aktiv.

### Messung 1: Schalter aus

Zustand: „Read-Only API" im Gateway **aus** (Stand 2026-10-11 20:27, Operator-Messung oben).

Aufruf: `preview_order(con_id=265598, symbol="AAPL", sec_type="STK", currency="USD",
primary_exchange="NASDAQ", action="BUY", quantity=1)`; Dauer 0,79 s.

```text
state             = OK
initMarginChange  = 100.86     (Kontowährung EUR)
maintMarginChange = 91.69
commission        = 1.000003
commissionCurrency= USD        (Instrumentwährung)
effective_tif     = DAY        (gesendet: DAY)
warningText       = ''         (leer)
errors            = []
```

Bewertung:

- **A2 (warningText):** bleibt bei dieser Vorschau leer; kein Warntext trotz geschlossener
  Börse (Montag, vor Handelsbeginn der Regulärzeit). Kein Fehler, kein Sondercode.
- **A3 (tif-Echo):** Das Echo liefert `DAY`, gleich dem gesendeten Wert; `TIF_OVERRIDDEN`
  trat nicht auf. Das Zurücklesen des tif aus dem Echo funktioniert.
- **A4 (Contract-Felder):** conId 265598, STK, USD, primary NASDAQ reichen dem Gateway für
  eine vollständige Vorschau; keine Nachfrage, keine Fehlermeldung.
- **Plausibilität:** Margin pro Stück ≈ 100,9 EUR gegenüber ≈ 99,7 EUR pro Stück in
  Befund 4 des Marktdaten-Befunds (997,14 EUR für 10 Stück); Kommission 1,000003 USD
  entspricht dem Mindestwert von 1,00003 USD dort. Die Größenordnung stimmt.

Nachweis „nichts gesendet":

- `open_orders(265598)` vorher: leer; nachher: leer.
- Positionen vorher: 0; nachher: 0 (unverändert).
- Sonden-Log (188 Zeilen): keine Treffer für `orderStatus`, `execDetails`,
  `ReadOnlyViolation`; einzige Previewzeile: `state=OK init_margin=100.86
  commission=1.000003 tif sent=DAY effective=DAY`.
