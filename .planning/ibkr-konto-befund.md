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

### Messung 2: Schalter an — 2026-10-12

Aufruf: dieselbe Sonde unverändert (`preview_order`, AAPL BUY 1, conId 265598, NASDAQ, USD),
Gateway 10.50.1 auf 127.0.0.1:7497, "Read-Only API" vom Operator eingeschaltet.

```text
state             = READ_ONLY_API
initMarginChange  = None
maintMarginChange = None
commission        = None
effective_tif     = None       (gesendet: DAY)
warningText       = ''
errors            = [(321, "Bei der Validierung der Anfrage ist ein Fehler aufgetreten.-'bC' :
                      cause - Die API befindet sich im schreibgeschützten Modus.")]
Dauer bis Ende   = 10,02 s     (Timeout der Vorschau; bei Schalter aus 0,79 s)
```

Bewertung: Der Schalter blockt die whatIf-Vorschau. Das Gateway antwortet mit Fehler 321
(read-only) und liefert keine Margin-/Kommissionsdaten; der Adapter mappt das auf
`READ_ONLY_API`.

Nachweis „nichts gesendet":

- `open_orders(265598)` vorher: leer; nachher: leer.
- Positionen vorher: 0; nachher: 0 (unverändert).
- Sonden-Log (`probe_m2.log`, 190 Zeilen): keine Treffer für `orderStatus`, `execDetails`,
  `ReadOnlyViolation`.

### Folge für SC2

Variante (a): Der Schalter blockt whatIf. Phase 4 schützt daher allein die Socket-Sperre
(Id 3 nur STK-whatIf, 04-02); der Gateway-Schalter bleibt während Phase 4 aus. Der SC2-Satz
zu 321 wird angepasst; die Bestätigung gibt der Operator im 04-VERIFICATION.md (D-14).
Der Operator schaltet "Read-Only API" nach dieser Messung wieder aus; die Bestätigung holt 04-09 ein.

### Nicht messbar

Fehler 154 (Halt) lässt sich am Paper-Gateway nicht herbeiführen. `halted` ist nur über die
offizielle Codeliste und einen Fake-Test belegt (A5). Das bleibt eine offene REQ-67-Lücke
für die Verifikation; es wird keine Messung behauptet.

## Kill-Storno, Orderhistorie und orderRef (Phase 5, D-06) — 2026-10-17

Gemessen am Samstag, 2026-10-17, zwischen 11:44 und 11:59 UTC, über **TWS Paper**
(nicht IB Gateway) auf `127.0.0.1:7497`, Konto `DUQ634065`, Serverversion 178.
Gateway und TWS lassen pro Benutzer nur eine Sitzung zu. Die TWS-Anmeldung hat
das Gateway deshalb getrennt, und TWS hat die API übernommen. Die API-Einstellungen
in TWS sind getrennt von denen des Gateways: „ActiveX- und Socket-Clients aktivieren“
musste der Operator erst einschalten (vorher `GATEWAY_UNREACHABLE`, Exit 3).

Ausgangslage:

- „Schreibgeschützte API“ in TWS **aus** (Screenshot des Operators, 13:46 MESZ).
- Vom Operator in TWS von Hand angelegt: AAPL KAUFEN 1, LMT 115.00, DAY, SMART
  (Kurs zu diesem Zeitpunkt ≈ 342,6). `permId 1440521754`, `client_id 0`.
- Vorab (Agent selbst): `ruff check .` sauber; `pytest -k g3` 14 passed; die volle
  Suite hat 2425 passed, 1 failed. Der Fehler ist der bekannte, schon vor der Phase
  rote Test `test_yfinance_keeps_its_cache_out_of_the_users_home` (Windows-TEMP
  liegt unter Home).
- Im echten State-Ordner lagen vorher weder `KILL` noch `RELEASE`.

### Messung 1: Einzeiler

Beide Handbuch-Einzeiler wurden wörtlich am echten Pfad ausgeführt
(`RELEASE` um 11:44:30 UTC, `KILL` um 11:59:06 UTC).

```text
RELEASE = {"account": "DUQ634065", "valid_until": "2026-11-16"}   (UTF-8 ohne BOM)
KILL    = leere Datei, Length 0
```

Der Executor las beide wie erwartet (`ibkr-state=SWITCHES release=release-ok
kill=kill-active valid_until=2026-11-16`). Gegenprobe in einem Scratch-Ordner:
`Set-Content` (ANSI) und `>` (BOM) ergeben beide `release-invalid`.

### Messung 2: Kill-Storno (SC3)

Historie vorher (`ibkr_order_probe.py --history`, 11:58:58 UTC): genau eine offene
Order, die Testorder. Der Haltepunkt (fremde offene Orders) griff nicht.

```json
"open": [{"source": "open", "order_ref": "", "status": "PreSubmitted", "action": "BUY",
          "quantity": 1.0, "filled": null, "con_id": 265598, "perm_id": 1440521754,
          "order_id": 0, "client_id": 0}],
"completed": [], "executions": []
```

Aufruf: `.venv/Scripts/python.exe scripts/ibkr_executor.py execute AAPL`, mit `KILL`
und gültigem `RELEASE`.

```text
execute: kill-active (KILL file present)
execute: kill-active, global cancel sent, 0 open order(s) left
exit=4
```

Log (`logs/ibkr_executor.log`):

```text
13:59:09,319 WARNING ibkr-state=SWITCHES release=release-ok kill=kill-active valid_until=2026-11-16
13:59:09,452 INFO    ibkr-state=CONNECTED account=DUQ634065 clientId=20001 readonly=True (...)
13:59:09,455 WARNING ibkr-state=GLOBAL_CANCEL_SENT code=- detail="count=1 reason=kill_switch"
13:59:10,062 INFO    ibkr-state=KILL_CANCEL remaining=0 rechecks=2 detail=""
```

Neue Zeilen in `ledger-dryrun.jsonl` (die Datei entstand mit diesem Lauf):

```json
{"command":"execute","event":"run_start","kill":"kill-active","kill_detail":"","mode":"dryrun","release":"release-ok","release_account":"DUQ634065","release_detail":"","run_id":"6c280f64947449b9b3a07bfdd1ef39ba","seq":1,"tickers":["AAPL"],"ts":"2026-10-17T11:59:09.319567+00:00","v":1,"valid_until":"2026-11-16"}
{"detail":"","event":"kill_cancel","kill":"kill-active","kill_detail":"","mode":"dryrun","outcome":"sent","rechecks":2,"release":"release-ok","release_account":"DUQ634065","release_detail":"","remaining":0,"run_id":"6c280f64947449b9b3a07bfdd1ef39ba","sent":1,"seq":2,"ts":"2026-10-17T11:59:10.060716+00:00","v":1,"valid_until":"2026-11-16"}
{"event":"run_end","exit":4,"mode":"dryrun","run_id":"6c280f64947449b9b3a07bfdd1ef39ba","seq":3,"state":"kill-active","ts":"2026-10-17T11:59:10.063065+00:00","v":1}
```

Ergebnis: Exit 4, genau ein globales Storno (`sent=1`), nach zwei Nachlese-Runden
keine offene Order mehr (`remaining=0`, Dauer ≈ 0,6 s).

### Messung 3: Orderhistorie nach dem Storno (A2)

`KILL` entfernt, dann `ibkr_order_probe.py --history` (11:59:18 UTC):

```json
{
  "open": [],
  "completed": [{"source": "completed", "order_ref": "", "status": "Cancelled",
                 "action": "BUY", "quantity": 1.0, "filled": 0.0, "con_id": 265598,
                 "perm_id": 1440521754, "order_id": 0, "client_id": 0}],
  "executions": []
}
```

Die stornierte Order erscheint unter `completed` mit Status `Cancelled`, `filled 0.0`,
derselben `perm_id`. Executions gibt es keine.

### Messung 4: orderRef mit | am whatIf (A3, A5)

`ibkr_order_probe.py --whatif AAPL --order-ref "2026-10-09|AAPL"` (11:59:19 UTC):

```json
{"ticker": "AAPL", "order_ref": "2026-10-09|AAPL", "state": "OK", "errors": [],
 "echo_order_ref": "2026-10-09|AAPL", "echo_account": "DUQ634065",
 "effective_tif": "DAY", "sent_tif": "DAY", "init_margin_change": 100.68,
 "commission": 1.000003}
```

Danach `RELEASE` entfernt. Im State-Ordner liegen weder `KILL` noch `RELEASE`. Neu
sind `ledger-dryrun.jsonl` (die drei Zeilen oben) und `ledger.jsonl.lock` (die Lockdatei).

### Folgen

- **(a) A1 bestätigt:** `reqGlobalCancel` (Nachricht 58) storniert auch **manuell in
  TWS angelegte** Orders (`client_id 0`), obwohl der Executor auf clientId 20001
  verbunden ist. Der Handbuch-Hinweis „takes back all open orders of the account,
  including orders you placed by hand in TWS“ ist damit belegt.
- **(b) Klassifikation stimmt:** Gemessener Status ist `Cancelled` mit `filled 0.0`.
  `resolve_entry` zählt `Cancelled` zu `_CANCELLED` und klassifiziert das als
  `not_filled`, passend zur Messung.
- **(c) Trenner bleibt `|`:** `DECISION_KEY_SEPARATOR = "|"` wird am whatIf
  angenommen und unverändert im Echo zurückgegeben. Ein Wechsel auf `_` ist nicht nötig.
- **(d) Echo-Konto vorhanden (D-22):** `echo_account = "DUQ634065"` steht im Echo.
- **Keine Abweichungen** von den Annahmen, also keine Lücke für einen Gap-Closure-Plan.
  Zur Einordnung: Gemessen wurde über TWS statt Gateway (gleiche API, Serverversion 178).
  Am Samstag blieb eine DAY-Limit-Order außerhalb der Handelszeit als `PreSubmitted` offen.

### Abnahme (Task 3) — 2026-10-17, 12:01 UTC

Der Operator konnte TWS nicht mehr einsehen, weil das wieder gestartete IB Gateway die
TWS-Sitzung getrennt hatte. Die Abnahme lief deshalb serverseitig über das Gateway auf
`127.0.0.1:7497`:

- `ibkr_order_probe.py --history`: `open` ist leer, `completed` enthält `perm_id 1440521754`
  mit `status Cancelled` und `filled 0.0`. Das Storno ist damit serverseitig bestätigt.
- `ibkr_order_probe.py --whatif AAPL --order-ref "2026-10-09|AAPL"`: `state OK`, keine
  Fehler. Daraus folgt: „Read-Only API“ ist im Gateway **aus** (bei eingeschaltetem
  Schalter käme `READ_ONLY_API` mit Fehler 321, siehe Phase 4, D-14). Der Schalter
  bleibt aus, weil Phase 6 senden wird.

## Erste echte Order (Phase 6)

### Versuch 2026-10-19: verschoben, keine BUY-Entscheidung (D-03)

Ausgangslage (Montag, 2026-10-19; regulärer US-Handelstag, Sitzung bis 16:00 New York):

- IB Gateway Paper auf `127.0.0.1:7497`, Konto `DUQ634065`.
- „Read-Only API“ laut Operator **an um 16:35 MESZ** (14:35 UTC). Die Sonde unten hat
  den Schalter aber schon um 14:29:47 UTC als wirksam gemessen. Die Meldung ist
  also nur ungefähr, und der Schalter war spätestens ab 14:29 UTC an.
- State-Ordner vorher: kein `KILL`, kein `RELEASE`, kein `ledger.jsonl` (nur
  `ledger-dryrun.jsonl` und eine leere `ledger.jsonl.lock` vom 2026-10-17).
- Vorab (Agent selbst): `ruff check .` sauber; `pytest tests/test_ibkr_call_order.py
  tests/test_ibkr_never_sent.py` 48 passed. Volle Suite: 2883 passed, 6 failed:
  `test_yfinance_keeps_its_cache_out_of_the_users_home` (bekannt) plus fünf
  plattformbedingte Fehler ohne IBKR-Bezug (`test_chatgpt_auth.py` ×2 prüft
  `0o600` unter Windows, `test_cli_commands.py` ×1, `test_cli_updates.py` ×2).
- `resolve AAPL MSFT NVDA` (14:29:38 UTC):

```text
resolve: AAPL ok conId=265598 NASDAQ/USD/AAPL tradable until 2026-10-19T15:45:00-04:00
resolve: MSFT ok conId=272093 NASDAQ/USD/MSFT tradable until 2026-10-19T15:45:00-04:00
resolve: NVDA ok conId=4815747 NASDAQ/USD/NVDA tradable until 2026-10-19T15:45:00-04:00
EXIT=0
```

#### Read-Only-Beleg vor RELEASE

`scripts/smoke/ibkr_order_probe.py --whatif AAPL --quantity 1 --order-ref readonly-proof`
um 14:29:47 UTC, Exit 0:

```json
{
  "ticker": "AAPL",
  "order_ref": "readonly-proof",
  "state": "READ_ONLY_API",
  "errors": [
    [
      321,
      "Bei der Validierung der Anfrage ist ein Fehler aufgetreten.-'bC' : cause - Die API befindet sich im schreibgesch\\u00fctzten Modus."
    ]
  ],
  "echo_order_ref": null,
  "echo_account": null,
  "effective_tif": null,
  "sent_tif": "DAY",
  "init_margin_change": null,
  "commission": null
}
```

Maschinelle Prüfung (`state == "READ_ONLY_API"` und Code 321 in `errors`): **Exit 0**.
Der erste Prüflauf endete mit Exit 1, weil PowerShells `>` die Datei mit BOM
schreibt und `json.load(encoding="utf-8")` daran scheitert. Die Prüfung lief danach
unverändert mit `utf-8-sig`. Das Kriterium wurde nicht aufgeweicht.

#### Ticker für die erste Order (D-03)

`scripts/ibkr_executor.py preview AAPL MSFT NVDA` (14:30:05 UTC, Trockenlauf,
paper-log `fork/paper-log` @ `5541cd9`), Exit 2:

```text
preview: AAPL skipped-hold (trade_date 2026-10-16)
preview: MSFT skipped-hold (trade_date 2026-10-16)
preview: NVDA skipped-hold (trade_date 2026-10-16)
```

`preview.json`: alle drei Zeilen `rating: "Hold"`, `rating_source: "engine"`,
`state: "skipped-hold"`, `sent: false`.

**Keine BUY-Entscheidung heute.** Nach D-03 wird keine Entscheidung künstlich
erzeugt. Deshalb gab es kein `RELEASE`, keinen `--live`-Lauf und keine Probe
`--history`. „Messung 1: 321 im scharfen Pfad“ steht noch aus.

Folgen:

- 06-09 wird an einem anderen Handelstag wiederholt, sobald der paper-log für
  mindestens einen Ticker eine frische Entscheidung mit BUY-Plan enthält. 06-10
  folgt am selben Tag.
- Der Read-Only-Schalter wirkt am whatIf über das Gateway (zweiter unabhängiger
  Beleg nach Phase 4).
- State-Ordner nachher: kein `RELEASE`, kein `KILL`, kein `ledger.jsonl`.
### Versuch 2026-10-19, zweiter Anlauf: Pipeline-Test mit gelockertem D-03

**D-03 gelockert (Operator, 2026-10-19):** Nach 20 von 20 Engine-Entscheidungen
ohne BUY für trade_date 2026-10-16 hat der Operator entschieden, D-03 zu lockern.
Gelaufen waren AAPL, MSFT und NVDA im Lauf vom 17.10. sowie zwei zusätzliche
Paper-Runs am 19.10. per `workflow_dispatch`:

- Run 39270361112: AMZN, GOOGL, AVGO, AMD, JPM Hold; META, TSLA Underweight;
  $1.59.
- Run 39273689753: LLY, UNH, XOM, COST, WMT, KO, CAT, V Hold; NFLX, ORCL
  Underweight; $2.16.

Die erste Order läuft deshalb als **Pipeline-Test** über den eigenen Branch
`fork/paper-log-pipeline-test` (`8453e76`, Basis `paper-log` @ `1d53d29`). Er
enthält genau einen zusätzlichen, im Text als „OPERATOR-APPROVED PIPELINE TEST,
NOT AN ENGINE DECISION“ markierten Eintrag `[2026-10-16 | AAPL | Overweight |
pending]` und die passende Zeile in `runs/2026-10-16/summary.json` (mit dem Feld
`pipeline_test`). Overweight ergibt genau 1 Block, also 1 Aktie. Die
Engine-Entscheidung für AAPL am 2026-10-16 bleibt Hold. Der echte `paper-log`
ist unverändert.

Der Executor-Code bleibt unverändert, der Branch kommt über eine eigene
Env-Datei mit `--env-file`: nur `IBKR_HOST`, `IBKR_PORT`, `IBKR_ACCOUNT_ID`,
`IBKR_TRADING_MODE` aus `.env` plus `IBKR_PAPER_LOG_BRANCH=paper-log-pipeline-test`.
Die Umgebungsvariable allein greift nicht: Der Executor liest nur `.env` oder
`--env-file`, und ohne Datei las er `paper-log`, Ergebnis `summary-missing`
(fail-closed).

**Bekannte Unschärfe:** Das Ledger schreibt beim `intent` `rating_source: engine`,
weil die Testzeile in `summary.json` `engine` tragen muss (nur `engine` wird
gehandelt). Die Herkunft belegen `preview.json` (`paper_log.branch`, `sha`) und
dieser Befund.

Trockenlauf mit Schalter aus (15:27:24 UTC):
`preview: AAPL preview-ok BUY 1 (trade_date 2026-10-16, weekend_gap 3d)`, Exit 0;
MKT, DAY, `init_margin_change` 100.97, Freshness `fresh`, Sitzung `ok`,
`sent: false`.

#### Read-Only-Beleg vor RELEASE

„Read-Only API“ laut Operator an um 17:28 MESZ. Die Sonde
`--whatif AAPL --quantity 1 --order-ref readonly-proof-2` lief um 15:28:37 UTC
mit Exit 0 und `state` `READ_ONLY_API`, `errors` `[[321, "… Die API befindet sich im
schreibgeschützten Modus."]]`. Die maschinelle Prüfung endete mit **Exit 0**.

`preview AAPL` (Pipeline-Test-Branch, 15:28:56 UTC), Exit 5:

```text
preview: AAPL preview-read-only BUY 1 (trade_date 2026-10-16, weekend_gap 3d)
```

`--history` (15:29:19 und 15:29:35 UTC) endete beide Male mit Exit 3:
`ibkr-state=REQUEST_TIMEOUT detail="reqCompletedOrders did not answer within 10.0s"`.

#### Messung 1: 321 im scharfen Pfad (D-11, D-15)

`RELEASE` angelegt um 15:30:11 UTC (`valid_until` 2026-11-18), danach
`execute AAPL --live --env-file pipeline-test.env` (genau ein Ticker), **Exit 3**:

```text
17:30:13,379 ibkr-state=SWITCHES release=release-ok kill=kill-absent valid_until=2026-11-18
17:30:14,345 ibkr-state=CONNECTED account=DUQ634065 clientId=20001 readonly=True (...)
17:30:14,509 ibkr-account AvailableFunds=1006271.92 EUR
17:30:14,513 Warning 321, reqId -1: ... Die API befindet sich im schreibgeschützten Modus.
17:30:14,513 WARNING ibkr-state=READ_ONLY_API code=321 detail="... schreibgeschützten Modus."
17:30:24,528 ERROR ibkr-state=REQUEST_TIMEOUT code=- detail="reqCompletedOrders did not answer within 10.0s"
```

Ledger (`ledger.jsonl`, neu angelegt):

```json
{"command":"execute","event":"run_start","kill":"kill-absent","mode":"live","release":"release-ok","release_account":"DUQ634065","run_id":"0158062ab0ed42bcb0893dc8b153030c","seq":1,"tickers":["AAPL"],"ts":"2026-10-19T15:30:13.380136+00:00","v":1,"valid_until":"2026-11-18"}
{"error":"GatewayUnavailable","event":"run_end","mode":"live","outcome":"error","run_id":"0158062ab0ed42bcb0893dc8b153030c","seq":2,"ts":"2026-10-19T15:30:24.526502+00:00","v":1}
```

Kein `intent`, kein `placed`, kein `ORDER_SENT`, keine `alarm`-Zeile. `RELEASE`
wurde um 15:30:33 UTC entfernt.

**Abweichung von der Erwartung (D-15):** Die Sperre greift im scharfen Pfad
**früher** als erwartet. Sie trifft nicht erst den whatIf (`preview-read-only`,
Exit 5), sondern schon das Lesen der Orderhistorie: `reqCompletedOrders` bekommt im
Read-Only-Modus eine 321 ohne Request-Bezug (`reqId -1`) und keine Antwort. Das
Lesefenster läuft nach 10 s ab, der Lauf endet fail-closed mit
`REQUEST_TIMEOUT`, Exit 3. `placeOrder` wird nicht erreicht. Die 321 steht im
Log des `--live`-Laufs. Der gesperrte Zustand ist damit belegt, Exit-Code und
State weichen aber vom Wortlaut von D-15 ab.

Folgen:

- (a) **Lücke für die Verifikation:** Eine 321 mit `reqId -1` während eines
  Lesefensters wird nicht als `READ_ONLY_API` (Exit 5) zugeordnet, sondern
  endet als Timeout (Exit 3). Das ist sicher, aber die Diagnose ist ungenau.
  Laut Plan keine Codeänderung am Messtag.
- (b) Im Handbuch ist zu ergänzen, dass `--history` und `execute --live` bei
  eingeschaltetem Schalter mit `REQUEST_TIMEOUT` enden.
- (c) Ob `reqCompletedOrders` über das Gateway bei ausgeschaltetem Schalter
  antwortet, prüft 06-10 Task 1. In Phase 5 lief die Historie über TWS.
#### Messung 2: Erste echte Order (SC3)

Handbuch-Commit der Freischaltung `698cffe` um 15:37:00 UTC, also vor der Order.
`RELEASE` angelegt um 15:37:08 UTC, danach
`execute AAPL --live --env-file pipeline-test.env` (Pipeline-Test-Branch `8453e76`),
**Exit 10**:

```text
execute: post-order-mismatch (AAPL: order quantity 0.0, expected 1.0); run stopped - see IBKR_EXECUTION.md
```

Log (gekürzt):

```text
17:37:11,923 ibkr-state=PREVIEW detail="state=OK init_margin=100.9 commission=1.000003 tif sent=DAY effective=DAY order_ref=2026-10-16|AAPL"
17:37:11,926 ibkr-state=EXECUTE_INTENT ticker=AAPL key=2026-10-16|AAPL sha=8453e764... side=BUY quantity=1
17:37:11,927 placeOrder: orderId=18 clientId=20001 BUY 1 MKT DAY orderRef='2026-10-16|AAPL' account='DUQ634065'
17:37:12,140 orderStatus: PreSubmitted permId=717633249
17:37:12,284 execDetails execId='0000e0d5.6ad60c69.01.01' exchange='IEX' side='BOT' shares=1.0 price=342.86 orderRef='2026-10-16|AAPL'
17:37:12,290 commissionReport commission=1.000003 USD
17:37:12,353 ibkr-state=ORDER_SENT key=2026-10-16|AAPL detail="order_id=18 perm_id=717633249 status=Filled filled=1.0 timed_out=False"
17:37:12,354 ibkr-state=ORDER_PLACED ticker=AAPL order_id=18 perm_id=717633249 status=Filled
17:37:12,362 ERROR ibkr-state=POST_ORDER_MISMATCH ticker=AAPL detail="order quantity 0.0, expected 1.0"
```

Ledger (`ledger.jsonl`, Zeilen dieses Laufs, gekürzt):

```json
{"event":"intent","decision_key":"2026-10-16|AAPL","order_ref":"2026-10-16|AAPL","side":"BUY","quantity":1,"con_id":265598,"rating":"Overweight","rating_source":"engine","paper_log_sha":"8453e7642f257f6cf1cdd5ebb1738feee3632b3f","ts":"2026-10-19T15:37:11.925690+00:00"}
{"event":"placed","order_id":18,"perm_id":717633249,"status":"Filled","source":"placer","ts":"2026-10-19T15:37:12.353884+00:00"}
{"event":"filled","exec_id":"0000e0d5.6ad60c69.01.01","exec_time":"2026-10-19T15:37:12+00:00","filled_qty":1.0,"price":342.86,"order_id":18,"perm_id":717633249,"order_ref":"2026-10-16|AAPL","side":"BUY","source":"placer","ts":"2026-10-19T15:37:12.361115+00:00"}
{"event":"alarm","state":"post-order-mismatch","detail":"order quantity 0.0, expected 1.0","fills_booked":true,"seen":{"status":"Filled","filled":1.0,"perm_id":717633249,"order_ref":"2026-10-16|AAPL"}}
{"event":"run_end","exit":10,"state":"post-order-mismatch"}
```

Die Kette `intent → placed → filled` ist vollständig: `order_id`, `perm_id`,
`order_ref == decision_key`, `exec_id`, `filled_qty` und Preis sind vorhanden. Die
Order war 0,43 s nach dem Senden gefüllt (IEX, 342.86 USD, Kommission 1.00 USD).
`RELEASE` wurde um 15:37:23 UTC entfernt.

#### Messung 3: Historie nach dem Fill (SC5, SC6, A3)

`ibkr_order_probe.py --history` (15:37:25 UTC), Exit 0:

```json
{
  "open": [],
  "completed": [
    {"source": "completed", "order_ref": "2026-10-16|AAPL", "status": "Filled", "action": "BUY",
     "quantity": 0.0, "filled": 1.0, "con_id": 265598, "perm_id": 717633249, "order_id": 0, "client_id": 0}
  ],
  "executions": [
    {"exec_id": "0000e0d5.6ad60c69.01.01", "order_ref": "2026-10-16|AAPL", "con_id": 265598,
     "perm_id": 717633249, "order_id": 18, "client_id": 20001, "shares": 1.0, "price": 342.86,
     "side": "BUY", "time": "2026-10-19T15:37:12+00:00"}
  ]
}
```

Position (`account`, 15:37:34 UTC): AAPL 1.0, Cash 1,005,152.87 EUR. Das
entspricht dem Ziel der Leiter (Overweight = 1 Block = 1 Aktie, vorher 0).

#### Ursache des Alarms

Die abgeschlossene Order aus `reqCompletedOrders` meldet über das Gateway
**`quantity` 0.0** (totalQuantity), `order_id` 0 und `client_id` 0, obwohl sie mit
`filled` 1.0 und Status `Filled` gefüllt ist. Die Prüfung nach der Order
(`scripts/ibkr_executor.py`, Vergleich `float(order.quantity) != want`) nimmt
`quantity` als Ordergröße und schlägt deshalb Alarm. Alle anderen Prüfungen
stimmten: Status, Seite, `filled`, `orderRef`, `conId`, Executions und Summe der
Executions. Es ist ein **Fehlalarm**, aber Exit 10 stoppt den Lauf.

Folgen:

- (a) Die Kette `intent → placed → filled` ist mit allen Feldern vollständig (SC3).
  Dazu kommt ein falsches `alarm`.
- (b) Die Execution trägt den `orderRef` (A3 bestätigt). Die abgeschlossene Order
  trägt ihn auch, hat aber `order_id` 0 und `client_id` 0. Abgleichen lässt sie
  sich über `orderRef` oder `permId`, nicht über `orderId`.
- (c) Keine Korrektur beobachtet, es gibt nur `.01.01`. SC5 bleibt beim Fixture.
- (d) Der Fill kam nach 0,43 s, weit unter den 60 s.
- (e) **Lücke (Gap-Closure):** Die Prüfung nach der Order darf `quantity` einer
  abgeschlossenen Order nicht gegen die Ordergröße prüfen, wenn das Gateway dort
  0 meldet. Prüfen sollte sie `filled` und die Summe der Executions. Laut Plan
  lief deshalb **kein zweiter Lauf** (SC4 offen) und es gab keine Codeänderung
  am Messtag. Weil `fills_booked` true ist, bleibt der Eintrag nach WR-02 offen,
  bis der Fix da ist.
- D-13: Die gemessene execId-Form `0000e0d5.6ad60c69.01.01` (vier Segmente, Punkt,
  8+8+2+2 Hex-Zeichen) entspricht dem Platzhalter im Fixture
  `0000e0d5.6710a3c5.01.01`. Das Fixture bleibt unverändert.