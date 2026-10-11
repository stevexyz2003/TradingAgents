# IBKR-Anbindung — Schnittstelle und Betrieb

**Recherchestand:** 2026-10-11
**Zielkonto:** IBKR Paper `DUQ634065`
**Arbeitsplatz:** Windows 11 Pro, Python 3.13.13 (`.venv`), Projekt verlangt `>=3.11`
**Agent:** A von 2 (Schnittstelle + Betrieb). Ausführungs-Architektur, Idempotenz, Kill-Switch, Positionsgrößen, paper-log-Format und Scheduler-Mechanik sind **nicht** Gegenstand dieses Dokuments.
**Gesamt-Konfidenz:** HOCH für Schnittstelle/Betrieb/Handelszeiten (offizielle IBKR-Doku, maschinell abgerufen), MITTEL für Paper-2FA und Symbol-Mapping-Details (Quellenlage teils widersprüchlich bzw. kontospezifisch — unten jeweils markiert).

> **Methodenhinweis zu den Quellen.** IBKR hat seine API-Doku auf `interactivebrokers.com/docs/...` (Fern-basiert) umgezogen und liefert dort **maschinenlesbares Markdown**: an jede Seiten-URL `.md` anhängen, Index unter `.../llms.txt`. Alle als „offizielle Doku" zitierten Stellen in diesem Dokument sind über diesen Weg wörtlich abgerufen worden (nicht aus dem Modellgedächtnis). `WebFetch` bekommt dort 403; `curl` mit Browser-User-Agent funktioniert. Die in den `llms.txt`-Indizes genannten Links zeigen auf `ibkrcampus.com/docs/...` — **diese Domain liefert derzeit Cloudflare-Fehler 1000**; die Pfade sind aber 1:1 auf `www.interactivebrokers.com/docs/...` übertragbar.

---

## 0. Kurzfassung

Für ein unbeaufsichtigtes Paper-Trading-Gate ist **TWS API über IB Gateway** die einzig praktikable Wahl. Die Client Portal Web API ist für ein Privatkonto nur über das **Client Portal Gateway** authentifizierbar, und IBKR schreibt dazu wörtlich: *„Interactive Brokers does not support an automated authentication process for Client Portal Gateway"* plus **täglicher Browser-Login am selben Rechner**. Das ist für Dauerbetrieb disqualifizierend. Die programmatischen OAuth-Pfade (1.0a / 2.0) sind laut offizieller Doku **Advisor-, Broker-, Prop-, Fund- und Third-Party-Konten** vorbehalten — ein Individual-Konto steht dort nicht.

Der Preis der TWS-API-Wahl: ein **GUI-gebundener Java-Prozess** („For security reasons, a headless session of TWS or IBGW without a GUI is not supported"), **täglicher Auto-Restart** und **ein manueller Login pro Woche**. Das ist keine Schwäche der Bibliothek, sondern eine Produkteigenschaft von IBKR.

Zwei Dinge haben sich seit dem Common Sense der letzten Jahre materiell geändert und sind für die Planung entscheidend:

1. **IBC ist am 2026-09-01 in Rente gegangen und das Repo ist archiviert.** Der Maintainer begründet es unter anderem damit, dass IBC weniger gebraucht wird, *„particularly because of the auto-restart mechanism in Gateway and TWS"*. Es gibt also einen offiziellen Weg ohne IBC — aber IBC bleibt der einzige erprobte Weg, den **Login selbst** zu automatisieren.
2. **TWS API 10.49+ steht seit 2026-08-03 unter GPL.** Für einen öffentlichen Fork ist das ein Lizenzthema. `ib_async` ist davon nicht betroffen, weil es das Binärprotokoll selbst implementiert und `ibapi` nicht benötigt.

---

## 1. Welche Schnittstelle?

### 1.1 Was IBKR selbst sagt

Die einzige Stelle, an der IBKR sich zwischen den beiden APIs positioniert, ist die Doku-Seite zu `ib_insync`/`ib_async` — und sie ist unmissverständlich:

> „This is neither an endorsement or admonishment of either the ib_insync or ib_async library. **Interactive Brokers will always advise clients use our direct TWS API implementation whenever possible.**"
> — `/docs/tws-api/doc/third-party-api-platforms/non-standard-tws-api-languages-and-packages/ib-insync-and-ib-async` (HOCH)

**Was ich ausdrücklich *nicht* gefunden habe:** eine offizielle Aussage, die die TWS API als „Legacy" markiert. Das kursiert in Community-Quellen, ist aber durch nichts auf IBKR-Seite gedeckt — im Gegenteil, die TWS API wird aktiv weiterentwickelt (10.49 im August 2026, 10.50.02 Stable am 2026-09-09, 10.51.01 Latest am 2026-09-29, Protobuf-Migration, neuer Sync-Wrapper). „Legacy" ist dagegen belegbar für:

- **`ib_insync`** — offiziell: *„the original ib_insync package is built using a legacy release of the TWS API and is no longer updated"*.
- **Web API v1.0 / CP Web API** — existiert als eigener, getrennter Doku-Zweig („Web API v1.0 Documentation") neben der aktuellen „Web API Documentation". Die Versionierung impliziert eine Ablösung; eine explizite Deprecation-Aussage habe ich nicht gefunden (MITTEL).

### 1.2 Entscheidungsachsen im Direktvergleich

| Achse | TWS API über IB Gateway | Client Portal Web API (CPGW, Retail) |
|---|---|---|
| **Auth-Mechanismus** | Username/Passwort + 2FA in der Gateway-GUI | Browser-SSO-Login gegen lokalen Java-Proxy |
| **Automatisierbarkeit des Logins** | Teilweise — IBC füllt Credentials aus und klickt Login; 2FA muss der Mensch quittieren | **Offiziell nicht unterstützt**: „IBKR does not support an automated authentication process for Client Portal Gateway" |
| **Re-Auth-Kadenz** | Auto-Restart täglich **ohne** Re-Auth; Credentials laufen nach dem Samstagnacht-Server-Reset ab → **1× pro Woche manuell** | **täglich** Browser-Login („Clients must reauthenticate using the Client Portal Gateway at daily") |
| **Session-Lebensdauer** | So lange Gateway läuft; Socket-Reconnect jederzeit, kein Keep-alive-Ping nötig | max. **24 h**, Reset um Mitternacht NY/Zug/HK; Brokerage-Session stirbt nach **~5 min** Inaktivität → `/tickle` ca. jede Minute |
| **Ortsbindung** | Keine — API-Client kann über das Netz verbinden (Trusted IPs) | **Hart**: Browser-Login *und* alle API-Calls müssen auf **derselben Maschine** laufen wie CPGW |
| **2FA-Zwang** | Ja (kontoweit, s. §3.3) | Ja, über SSO |
| **Order-Typen** | Volle Abdeckung | **Teilmenge** — IBKR: „not all order types are available in both platforms" |
| **Marktdaten** | `reqMktData`/`reqHistoricalData`, Delayed-Fallback über `reqMarketDataType(3/4)` | `/iserver`-Endpunkte, nur mit aktiver Brokerage-Session |
| **Nicht verfügbar** | — | `CONTFUT` (Continuous Futures), `includeExpired` (Expired Futures) — beides laut offizieller Doku „not supported in the web api" |
| **Session-Exklusivität** | Gateway hält die Session; konkurrierender Login killt sie (Fehler 1100) | „A single username can only have one brokerage session active at a time **across all IB platforms**" |
| **Windows-Tauglichkeit** | Gut — Gateway ist ein Windows-Installer, Standard-Deployment | Gut, aber die Ortsbindung macht Container/Remote unmöglich |
| **Prozessgewicht** | Java-Desktop-App, Heap ≥ 4 GB empfohlen | Kleiner Java-Proxy, aber Browser-Abhängigkeit |

### 1.3 Begründung der Vorauswahl

**Die Web API fällt hier nicht wegen Funktionsumfang aus, sondern wegen Authentifizierung.** Der Pfad, der programmatisches Login erlaubt (OAuth 1.0a — „the only supported authentication method for Third Party Developers"), ist laut der offiziellen Auth-Übersicht an Advisor-/Broker-/Prop-Trading-/Hedge-Fund-/Third-Party-Kontotypen gebunden. Für „Individual Accounts" nennt dieselbe Seite **ausschließlich** das Client Portal Gateway. Und die „Getting Started"-Seite bestätigt das noch einmal: *„For retail and individual clients, Authentication to our WebAPI is managed using the Client Portal Gateway."*

Ein täglicher Browser-Login auf dem Zielrechner ist kein unbeaufsichtigter Betrieb. Ein wöchentlicher GUI-Login ist unschön, aber mit einem Wochenrhythmus vereinbar — und genau das ist der Unterschied, der die Entscheidung trägt.

> **Ehrliche Einschränkung.** Es gibt Dritt-Werkzeuge, die den CPGW-Login per headless Chromium automatisieren (`Voyz/IBeam`, Apache-2.0, v0.5.13 vom 2026-09-20, aktiv). Das funktioniert in der Praxis nachweislich, steht aber im direkten Widerspruch zur IBKR-Aussage „does not support an automated authentication process". Es ist damit ein Pfad gegen die Hersteller-Aussage, nicht mit ihr — für ein Projekt, das als Produktionspfad geplant wird, ein schlechter Tausch. Falls später doch eine REST-Anbindung gewünscht ist, ist die Kombination `IBeam` + `ibind` (Apache-2.0, v0.2.2 vom **2026-10-06**, sehr aktiv) der ausgereifte Weg.

---

## 2. Bibliothekslage (geprüft gegen PyPI- und GitHub-APIs, 2026-10-11)

### 2.1 Harte Zahlen

| Paket | Aktuelle Version | Release-Datum | Python | Lizenz | Aktivität (Default-Branch) |
|---|---|---|---|---|---|
| **`ib_async`** | **2.1.0** | **2025-12-08** | `>=3.10`, Classifier bis **3.14** | **BSD-2-Clause** | `main`: letzter Commit **2025-12-06**; `next`: **2026-07-14**; 1754 Stars, 99 offene Issues, nicht archiviert |
| `ib_insync` | 0.9.86 | 2023-07-02 | `>=3.6` | BSD-2-Clause | **Repo archiviert**, letzter Commit 2024-03-14 („In memoriam") |
| `ibapi` (PyPI) | **9.81.1.post1** | **2020-12-06** | `>=3.1` (Classifier bis 3.9) | IB API Non-Commercial / Commercial | **Tot auf PyPI** — die echte 10.x kommt nur aus dem TWS-API-Installer |
| `ibind` | 0.2.2 | **2026-10-06** | `>=3.10` | Apache-2.0 | Sehr aktiv (Release vor 5 Tagen) — aber **Web API**, nicht TWS API |
| `nautilus_trader` | 1.231.0 | 2026-08-02 | `>=3.12,<3.15` | **LGPL-3.0-or-later** | Aktiv; komplettes Trading-Framework, nicht nur Client |

### 2.2 `ib_insync` — Stand jetzt

Erledigt, und zwar offiziell von beiden Seiten. Das Repo `erdewit/ib_insync` ist **archiviert**, der letzte Commit ist „In memoriam" vom 2024-03-14; die letzte Veröffentlichung 0.9.86 ist von 2023-07-02. IBKR schreibt dazu: *„the original ib_insync package is built using a legacy release of the TWS API and is no longer updated. Users who wish to implement the ib_insync structure using supported releases of the Trader Workstation should migrate to the ib_async package."* (HOCH)

### 2.3 `ib_async` — der Nachfolger, mit Vorbehalten

Das ist die richtige Wahl, aber die oft gelesene Aussage „aktiv gepflegt" muss man präzisieren. Die Fakten:

- **Die veröffentlichte Linie ist ~10 Monate alt.** 2.1.0 wurde am 2025-12-08 auf PyPI geschoben, der zugehörige Commit ist vom 2025-12-06. Seitdem hat der `main`-Branch **keinen Commit** mehr bekommen.
- **Entwicklung läuft, aber auf `next`** (letzter Commit 2026-07-14) und ist **nicht released**. Es gibt vier Branches (`main`, `next`, `next-protobuf`, `gh-pages`). `next-protobuf` deutet auf die Arbeit an IBKRs Protobuf-Migration hin — relevant, weil IBKR die TWS API dorthin bewegt.
- **GitHub-Releases sind nicht gepflegt**: dort steht als „latest" noch `v2.0.1` (2025-06-22), obwohl 2.1.0 auf PyPI liegt. Wer nur auf GitHub-Releases schaut, sieht ein falsches Bild. Genau das erklärt die widersprüchlichen Einschätzungen im Netz (Snyk sagt „inactive", Aggregatoren sagen „Push im Mai 2026").
- **Bus-Faktor 1.** Einen Maintainer (Matt Stancliff), 99 offene Issues.
- **Kein `ibapi`-Bezug** — und das ist der entscheidende Vorteil: *„The ibapi package from IB is not needed. `ib_async` implements the full IBKR API binary protocol internally."* (README). Damit bleibt der Lizenzstatus BSD-2-Clause, unabhängig vom GPL-Wechsel bei IBKR.

**Konkrete, prüfbare Stolperstelle in den Dependencies von 2.1.0:**

```
requires_dist: ['aeventkit<3.0.0,>=2.1.0', 'nest_asyncio', 'tzdata<2026.0,>=2025.2']
```

Der `tzdata`-Deckel ist das Problem: **`tzdata` steht aktuell bei 2026.5 (hochgeladen 2026-10-03)**, es gibt 2026.1–2026.5. `ib_async` 2.1.0 schließt die gesamte 2026er-Linie aus. In diesem Projekt geht es derzeit gerade noch auf — die `.venv` hat `tzdata 2025.2` und `pytz 2025.2` installiert, beides erfüllt den Pin. Aber: jedes `pip`/`uv`-Upgrade von `tzdata` kollidiert künftig mit `ib_async`, und das Projekt arbeitet mit Zeitzonen (`pytz>=2025.2` ist deklarierte Dependency). Das ist eine Resolver-Falle, die man explizit festschreiben muss, kein Ratespiel.

Zweiter Punkt: **`nest_asyncio`**. `ib_async` patcht asyncio, um synchrone Aufrufe aus einem laufenden Loop zu erlauben. Das Projekt läuft auf LangGraph, das selbst asyncio nutzt. Das ist eine bekannte Reibungsfläche (verschachtelte Loops, Re-Entrance) und sollte durch eine klare Trennung behandelt werden — IBKR-Calls nicht aus einem LangGraph-Node heraus, sondern in einem eigenen Prozess/Thread mit eigenem Loop. (Bewertung MITTEL: dass `nest_asyncio` gezogen wird, ist belegt; dass es mit LangGraph konkret bricht, habe ich nicht verifiziert.)

### 2.4 `ibapi` — und der neue offizielle Sync-Wrapper

Hier liegt ein echtes Missverständnis-Risiko:

- **`pip install ibapi` liefert 9.81.1.post1 von 2020-12-06.** Das ist nicht die aktuelle TWS API. Die aktuelle Python-Implementierung wird **ausschließlich** über den TWS-API-Installer verteilt (`download2.interactivebrokers.com/installers/tws-api/`), und zwar **nur im „Latest"-Bundle**, nicht im „Stable": *„The API Latest for Windows 64-bit (v1051.01) additionally includes the Python API."* Stable ist 1050.02 (2026-09-09), Latest 1051.01 (2026-09-29).
- IBKR hat mit **TWS API 10.40** einen offiziellen **synchronen Wrapper** eingeführt: `from ibapi.sync_wrapper import *` → `TWSSyncWrapper(timeout=30)` mit `connect_and_start()`, `get_contract_details()`, `get_market_data_snapshot()`, `place_order_sync()`, `get_positions()`, `get_executions()`, `cancel_order_sync()`. *„The interface is exclusively available through the Python programming language."* Das ist die erste Antwort von IBKR selbst auf das, was `ib_insync` populär gemacht hat.
- **Aber: „TWS API 10.49+ is released under the GNU General Public License (GPL)."** (Changelog-Eintrag vom **2026-08-03**). Für dieses Repo — ein **öffentlicher** Fork — heißt das: `ibapi` 10.49+ in den Code ziehen zieht eine Copyleft-Frage nach sich, die vor dem ersten Commit geklärt sein müsste. Das disqualifiziert den offiziellen Sync-Wrapper für dieses Projekt nicht inhaltlich, aber es macht ihn zum teureren Weg.

> **Explizite Unsicherheit.** Ich habe den Volltext der GPL-Erklärung nur als Changelog-Eintrag, nicht als Lizenzdatei im Installer verifiziert (der Installer-Download wurde nicht entpackt). Ob GPL-2, GPL-3 und mit welchen Ausnahmen, ist damit **offen**. Wenn der Sync-Wrapper als Option bleiben soll, ist das ein Punkt für eigene Prüfung — nicht für eine Annahme.

### 2.5 Neuere Alternativen — was es gibt und was nicht

Ich habe GitHub nach Python-IBKR-Bibliotheken nach Sterne sortiert durchsucht. Jenseits von `ib_async` gibt es **keine** neue, ernstzunehmende TWS-API-Bibliothek: die Top-Treffer sind entweder archiviert (`IbPy` 2017, `ezibpy` 2022, `tws_async` 2017) oder Web-API-Clients (`ibind`, `EasyIB`, `areed1192/*`) oder Beispielprojekte. `nautilus_trader` (LGPL-3.0, 1.231.0 vom 2026-08-02) ist aktiv und hat einen IB-Adapter, ist aber ein vollständiges Event-Driven-Trading-Framework und wäre hier eine Parallelarchitektur zu LangGraph — falsches Werkzeug für eine Order-Brücke.

**Ergebnis:** `ib_async` hat kein Konkurrenzprodukt. Die Wahl ist nicht „die beste von vielen", sondern „die einzige mit modernem Interface" — mit genau einem Maintainer. Das ist ein Risiko, das man einplanen und nicht wegreden sollte.

---

## 3. Unbeaufsichtigter Betrieb — der kritische Punkt

### 3.1 Was IBKR architektonisch festlegt

Drei Sätze aus der offiziellen Doku bestimmen hier alles (`/docs/tws-api/doc/architecture/the-trader-workstation/the-ib-gateway`):

> „With either application (TWS or IBGW), the user must manually enter their username and password into a login window. **For security reasons, a headless session of TWS or IBGW without a GUI is not supported.**"

> „Both TWS and IBGW were designed to be **restarted daily**. This is necessary to perform functions such as **re-downloading contract definitions** in cases where contracts have been changed or new contracts have been added."

> „Beginning in version 974+ both applications offer an **autorestart** feature that allows the application to restart daily without user intervention. With this option enabled, TWS or IBGW can potentially run **from Sunday to Sunday without re-authenticating**. **After the nightly server reset on Saturday night it will be necessary to again enter security credentials.**"

Dazu die Seite „Daily & Weekly Reauthentication":

> „In TWS/IB Gateway – 'Global Configuration' – 'Lock and Exit', you can choose the time of your TWS being shut down. For API users, it is recommended to choose **'Never lock Trader Workstation'** and **'Auto restart'**."
> „**The weekly authentication cycle starts on every Monday.** If you receive `Login failed = Soft token=0 received instead of expected permanent for zdc1.ibllc.com:4001 (SSL)`, this means you need to **manually login again** to complete the weekly reauthentication task."

**Damit ist die Obergrenze der Unbeaufsichtigtheit festgelegt: eine Woche.** Der tägliche Restart ist automatisierbar und kostet keine Credentials. Der Wochenwechsel kostet einen menschlichen Login. Das ist nicht umgehbar, ohne gegen die Hersteller-Aussage zu arbeiten.

### 3.2 IBC / IBController — Status: in Rente

Das ist die wichtigste Änderung gegenüber jeder älteren Anleitung.

- `IbcAlpha/IBC` ist **GitHub-archiviert**; README: *„This project has been retired, as of 1 September 2026. By 'retired', I mean that there will be no further development of IBC, other than completing work in progress at that date and fixing any significant newly reported bugs. Nor will IBC be actively supported on this repository."*
- Letztes Release: **3.24.2 vom 2026-08-21**. Downloads bleiben verfügbar, ein abschließendes Release zur Abarbeitung offener Issues ist angekündigt. Forken ist ausdrücklich erlaubt.
- Begründung des Maintainers (Discussion 347, 2026-03-24): 23 Jahre Pflege, Alter 73 — **und**: *„There is less need for IBC than there used to be, particularly because of the auto-restart mechanism in Gateway and TWS. While IBC adds some convenience to the TWS/Gateway experience, there are plenty of users who manage without it."*
- Nachfolge-Kandidaten aus demselben Thread, alle **nicht geprüft** (LOW): ein Python-Reimplementat `ibg-controller` (Autor beansprucht 21 von 22 IBC-Env-Vars, Docker/headless-Fokus, pyatspi2 + In-JVM-Agent), ein angekündigter Java-Fork mit automatisiertem 2FA, sowie `gnzsnz/ib-gateway-docker` (MIT, 1273 Stars, Push **2026-10-09**, Release-Tag `ibgateway-stable@10.50.1f` vom 2026-10-06) — das ist das lebendigste Projekt im Umfeld, bündelt aber selbst IB Gateway **mit IBC** und ist Linux/Docker, nicht Windows.

**Einordnung für dieses Projekt:** IBC ist nicht kaputt und 3.24.2 wird auf absehbare Zeit funktionieren. Aber es ist kein Fundament mehr, auf das man neu baut. Die vom Hersteller selbst benannte Alternative — Gateways nativer Auto-Restart — trägt den Tagesrhythmus; IBC bräuchte man nur noch für die Login-Automatisierung, und die kann es wegen 2FA ohnehin nicht zu Ende bringen.

### 3.3 2FA — und ob Paper-Login ohne Zweitfaktor geht

**Hier ist die Quellenlage widersprüchlich und ich glätte das nicht.**

Was offiziell belegt ist:

- *„Two Factor Authentication (2FA) is **required for all users** at Interactive Brokers."* Unterstützte Verfahren für API-Nutzung: IB Key, Handy Key, SMS/Text, Digital Security Card+ (DSC+). **Nicht** unterstützt: Security Code Card („Bingo Card"), Temporary Security Code Card, Online Code Card. (`/docs/tws-api/doc/notes-limitations/supported-two-factor-authentication-2-fa`, HOCH)
- *„Note: **All IBKR accounts are required to enroll in two-factor authentication.**"* (Secure Login System Guide, zuletzt aktualisiert **2026-01-12**, HOCH)
- Für Individual-Konten gilt laut Client-Portal-Guide (Stand 2026-02-11): *„Existing account holders with a paper trading account can **log into TWS with their production account credentials** and select either a production or paper trading account."* Nur Advisors, Brokers, Hedge Funds, Administratoren, Referrer und Residents of India/Japan *müssen* die separaten Paper-Credentials nutzen.
- Separate Paper-Credentials existieren aber auch für Individual-Konten und sind im Client Portal unter „Settings → Account Configuration → Paper Trading Account" abrufbar/resetbar (Web-API-Doku, Abschnitt „Using a Paper Account").

Was **nicht** belegt ist: **ob der Login mit dem separaten Paper-Username einen Zweitfaktor verlangt.** Die offiziellen Aussagen betreffen die **Enrollment-Pflicht auf Kontoebene**, nicht den Prompt beim Paper-User-Login. Community-Berichte widersprechen sich direkt — mehrere Nutzer berichten 2025/2026, mit dem Paper-Username ohne zweiten Faktor einzuloggen, während das Live-Konto 2FA verlangt; andere behaupten das Gegenteil. Keine dieser Quellen ist offiziell.

**Konsequenz für die Planung:** Das ist eine **Fünf-Minuten-Messung am echten Konto** und keine Recherchefrage. Der erste Schritt im Meilenstein sollte sein: Gateway starten, mit dem Paper-Username von `DUQ634065` einloggen, beobachten, ob ein Zweitfaktor verlangt wird. Beide Ausgänge sind planbar:

- **Kein Zweitfaktor** → Login ist vollständig automatisierbar (IBC oder eigene Automation), der Wochenzyklus wird unbeaufsichtigt. Das wäre der beste Fall, und er ist plausibel.
- **Zweitfaktor** → ein manueller IB-Key-Quittierungsvorgang pro Woche. IBC kann dabei nur den Rand abfedern, nicht den Kern: *„IBC cannot itself assist in the process, so you'll have to actually perform the necessary actions on your device yourself"*. Konfigurierbar sind nur die Wiederholungsversuche: `ReloginAfterSecondFactorAuthenticationTimeout=yes` (startet den Login neu, wenn die 3-Minuten-Frist für die Alert-Quittierung verstreicht; wiederholbar beliebig oft), `SecondFactorAuthenticationExitInterval` und `TWOFA_TIMEOUT_ACTION=restart|exit`.

Praktisch angenehm ist dabei: der IB-Key-Alert kommt aufs Telefon, nicht an den Rechner. Der Mensch muss **nicht am Rechner sitzen** — er muss nur einmal pro Woche auf dem Handy tippen. Für ein tägliches Entscheidungs-Gate ist das zumutbar, solange der Ausfall erkannt wird (siehe Risiko 1 in §7).

### 3.4 Windows: was läuft, was bricht

Die präziseste Quelle hierzu ist der IBC User Guide, und seine Aussagen sind systembedingt, nicht IBC-spezifisch:

**Was funktioniert (HOCH):**
- **Windows Task Scheduler** mit `StartGateway.bat`, Option **„Run only when user is logged on"**. Begründung im Guide: *„Doing this will ensure that you can see and interact with TWS."*
- Argument **`/INLINE`** ist Pflicht beim Start aus dem Task Scheduler: *„Otherwise IBC starts and runs correctly, but Task Scheduler is not aware of it"* — ohne `/INLINE` öffnet das Startskript ein neues Fenster, der Task gilt als beendet, und periodische Neustarts erzeugen **mehrere parallele Instanzen** („with unpredictable results").
- Task-Einstellung „Windows beendet die Aufgabe nach X" muss **deaktiviert** werden.
- Muster für Selbstheilung: Task alle 10 Minuten wiederholen, aber „keine neue Instanz, wenn eine läuft". Das deckt Abstürze und Stromausfälle ab — *„TWS's auto-restart mechanism does not operate if TWS is shut down other than at the auto-restart time: for example via the File | Exit menu, or due to power failure or a program bug."*
- Wochengrenze explizit im Guide: *„Finally on the Sunday, if the task has not been ended before then, **IB will prevent that session running any further because the session credentials expire**. At this point it is necessary to start a new task to begin the whole cycle over again."*
- `ClosedownAt` in `config.ini`, um Freitagabend saubere Ruhe zu haben.

**Was bricht (HOCH):**
- **Ein echter Windows-Dienst ist kein gangbarer Weg.** Es gibt keinen offiziellen Dienst-Modus, und die GUI-Bindung („headless not supported") steht dagegen.
- **Task Scheduler mit „Run whether user is logged on or not" bricht.** Wörtlich: *„the task is always started in a separate user session which you cannot see and interact with, even if you are already logged on when the task starts... Therefore you are strongly advised NOT to use the option for 'Run whether user is logged on or not'."*
- **IBC + selbst-updatende TWS bricht.** *„IBC DOES NOT WORK with the self-updating version of TWS. You must install the offline version of TWS for use with IBC."* **Entwarnung für diesen Fall:** *„there is no self-updating version of the Gateway, so the normal Gateway installer will work fine if you only want to use the Gateway."* — ein weiteres Argument, Gateway statt TWS zu nehmen.
- **IBHK-Konten in TWS** haben kein „Never lock Trader Workstation" und keinen Auto-Restart; sie werden bei Inaktivität gesperrt und verlieren die API-Verbindung. IBKR empfiehlt diesen Nutzern ausdrücklich IB Gateway. (Hier wahrscheinlich nicht relevant, aber ein Fallstrick, falls das Konto an einer IBKR-Regionaleinheit hängt.)
- **Sperre/Lock der Windows-Sitzung** ist unkritisch (das Konto muss nur angemeldet sein), aber **Abmelden** beendet den Gateway-Prozess.

**Praktische Empfehlung Windows:** dedizierter lokaler Benutzer mit Autologon beim Boot, Task Scheduler-Task „bei Anmeldung" + Wiederholung alle 10 min mit Instanz-Sperre, Gateway mit „Auto restart" und „Never lock", `ClosedownAt` Freitagabend, neuer Zyklus Sonntag/Montag mit einem Login. Die Sicherheitsimplikation von Autologon benennt der IBC-Guide selbst — bei einem Paper-Konto ist sie tragbar, bei einem Live-Konto nicht ohne weiteres.

### 3.5 Read-Only-Modus und Order-Precautions

- **Read-Only API ist standardmäßig AN.** Offizielle Campus-Lektion „Installing & Configuring TWS for the API": *„The setting 'Read-Only' is enabled by default and will block all API orders. It must be unchecked to allow any orders from the API."* Der Laufzeit-Marker dafür ist **Fehler 10015 „Trading is not allowed in the API"** — ein sauberes, eindeutiges Signal. Wer in der Entwicklungsphase bewusst nur lesen will, lässt Read-Only an und setzt zusätzlich `ib_async`-seitig `IB.connect(..., readonly=True)`.
- **Order-Precautions können Orders blockieren**, weil TWS Bestätigungsdialoge erwartet. Unter „Global Configuration → API → Precautions" gibt es dafür „Bypass Order Precautions for API orders" und acht weitere Bypass-Schalter (Bond-Warnung, negative Yield-to-Worst, Called Bond, „same action pair trade", preisbasierte Volatilitätswarnung, „US Stocks market data in shares", „Redirect Order warning for Stock API orders", „No Overfill Protection"). Für unbeaufsichtigten Betrieb muss das bewusst konfiguriert sein, sonst hängen Orders an einem Dialog, den niemand wegklickt.

### 3.6 Verbindungsüberwachung — die Codes, auf die man hören muss

Die TWS API meldet Betriebszustände als „Fehler", die keine sind. Diese Liste ist das Minimum für eine ehrliche Health-Erkennung (alle aus `/doc/error-handling/error-codes` und `/system-message-codes`, HOCH):

| Code | Bedeutung | Reaktion |
|---|---|---|
| **1100** | „Connectivity between IB and the TWS has been lost." Ursachen laut Doku: Internet, **nightly reset**, oder **competing session** | Keine Orders senden; warten auf 1101/1102 |
| **1101** | Verbindung wieder da — **Marktdaten-Abos verloren**, müssen neu angefordert werden | Abos neu aufsetzen |
| **1102** | Verbindung wieder da — Abos erhalten | Weiterlaufen |
| **1300** | Socket-Port wurde während aktiver Verbindung geändert, Verbindung wird verworfen | Neu verbinden auf neuen Port |
| 2103 / 2105 | Market-Data- bzw. Historical-Data-Farm getrennt | Außerhalb des nightly reset ein echtes ISP-Problem |
| 2104 / 2106 / 2158 | Farm-Verbindungen OK | Nur Rauschen, nicht als Fehler loggen |
| 2107 / 2108 | Farm-Verbindung inaktiv, „available upon demand" | Normal, ignorieren |
| **2110** | „Connectivity between TWS and server is broken. It will be restored automatically." | Normalerweise nur beim nightly reset |
| **326** | „Unable to connect as the client id is already in use." | `clientId`-Kollision — eindeutige IDs vergeben |
| **502** | Socket nicht erreichbar (nicht von TWS erzeugt, erscheint **nicht** im TWS-Log) | Gateway läuft nicht / falscher Port / Firewall / Trusted IPs |
| **504** | „Not connected." | Request ohne Verbindung |
| **507** | Socket-EOF (Java) — u. a. bei doppelter `clientId` oder gesperrtem TWS | Reconnect |
| **10089** | „API data requires subscription" | Auf Delayed umschalten (siehe §4.2) |
| **10197** | „No market data during competing session" — Paper und Live gleichzeitig; **Live gewinnt** | Siehe §4.4 |

Wichtig für die Einordnung: `ib_async` liefert hierfür `connectedEvent` / `disconnectedEvent` / `errorEvent` und `IB.isConnected()`. Die Bibliothek bringt außerdem eine `Watchdog`-Klasse mit:

```
Watchdog(controller, ib, host='127.0.0.1', port=7497, clientId=1, connectTimeout=2,
         appStartupTime=30, appTimeout=20, retryDelay=2, readonly=False, account='',
         raiseSyncErrors=False, probeContract=Forex('EURUSD', exchange='IDEALPRO'),
         probeTimeout=4)
```

Zwei Dinge dazu, die man kennen sollte: **`controller` ist ein Pflichtargument** und ist in der Praxis die `IBC`-Klasse (`IBC(twsVersion, gateway=False, tradingMode='', ..., on2fatimeout='')`). Ohne IBC gibt es also keinen fertigen Watchdog — dann schreibt man die Reconnect-Schleife auf `disconnectedEvent` selbst. Und die Doku der Bibliothek ist dabei erfreulich unverblümt: *„Do not expect Watchdog to magically shield you from reality. Do not use Watchdog unless you understand what it does and doesn't do."*

Der `probeContract`-Mechanismus ist das klügste Detail daran: der Watchdog schickt periodisch einen harmlosen Request (Default EURUSD), weil eine TCP-Verbindung „oben" aussehen kann, während die Gateway-Session hinten tot ist. Das ist das Muster, das man übernehmen sollte — Liveness über eine echte Antwort, nicht über Socket-Status.

---

## 4. Paper-Konto-Spezifika

### 4.1 Ports — bestätigt

**Bestätigt durch zwei offizielle Quellen** (HOCH):

| Anwendung | Live | Paper |
|---|---|---|
| **TWS** | **7496** | **7497** |
| **IB Gateway** | **4001** | **4002** |

Belege: `/docs/excel/dde/dde-socket-bridge/configuring-the-socket-bridge/configure-the-connecting-socket-port` listet wörtlich „TWS Live Account: 7496 / TWS Paper Account: 7497 / IB Gateway Live Account: 4001 / IB Gateway Paper Account: 4002"; dieselbe Zuordnung in der Campus-Lektion „Installing & Configuring TWS for the API".

**Zwei Präzisierungen, die wichtig sind:**
1. Das sind **nur Defaults**. „these are just defaults, and can be modified as desired — the socket port in TWS must be configured to match the socket port used in the API clients' `connect()` function." Der Port ist also **keine Sicherheitsgarantie**, sondern eine Konvention. Wer ihn in der Gateway-GUI ändert, hat eine Live-Session auf 4002.
2. Wird der Port während einer laufenden API-Verbindung geändert, kommt **Fehler 1300** und die Verbindung wird verworfen.

Nebenbei: in IBKRs eigenem Sync-Wrapper-Beispiel steht `port=7496` — also der **Live**-TWS-Port — in einem Tutorial, das eine Kauforder über 100 AAPL platziert. Das ist ein gutes Beispiel dafür, warum man Ports nicht aus Beispielcode übernimmt.

### 4.2 Marktdaten — hier sind die Quellen widersprüchlich

**Widerspruch, den ich nicht auflösen kann und deshalb offenlege:**

- Der Client-Portal-Guide „About Paper Trading Accounts" (2026-02-11) und das Campus-Glossar (zuletzt 2026-07-21) sagen beide: *„Trading permissions, **market data subscriptions**, base currency, and other account configurations **are the same as specified for your regular account**."*
- Die Marktdaten-Doku sagt dagegen, dass Sharing **eingerichtet werden muss**: *„Market data may also be shared between a live and paper username so that both can retrieve data using the same market data subscription. **Each Live user can share data with one (1) Paper account**, with one Paper account allowed per live account."*
- Und IBKRs KB-Artikel 1719 (über Fehler 10197 referenziert) ergänzt die harte Einschränkung, dass bei geteilten Daten **beide Sessions auf demselben Gerät** laufen müssen, sonst behält die Live-Session die Echtzeitdaten und die Paper-Session bekommt keine. (Diese Aussage konnte ich nur über Suchergebnis-Zitate belegen, der KB-Volltext war nicht abrufbar — **MITTEL**.)

**Mein Schluss:** Das Paper-Konto hat **keine eigenen Abos**. Es erbt sie nur, wenn Sharing aktiv konfiguriert ist, und auch dann mit Einschränkungen. Die Glossar-Formulierung ist eine Vereinfachung, auf die man sich nicht verlassen sollte.

**Was man stattdessen tut — und das ist die robuste Antwort:** sich gar nicht auf Echtzeitdaten verlassen. Offizielle Mechanik (HOCH):
- `reqMarketDataType(3)` = **delayed**: „TWS will start sending regular (1) as default and delayed (3) market data." `reqMarketDataType(4)` = delayed-frozen. IBKR liefert immer die aktuellsten verfügbaren Daten und erlaubt zusätzlich delayed/frozen auf Anforderung.
- Ohne Abo: **Fehler 10089** „API data requires subscription". Fehler **10090** „Part of requested market data is not subscribed" für Teilabdeckung.
- **Marktdaten in TWS ≠ Marktdaten in der API.** Offiziell: „data on the API is considered off-platform... While you may receive live pricing through the Trader Workstation for some securities like US Stocks in your Trader Workstation, this may not be the same through your API." Es gibt sogar gleichnamige Bundles, eines kostenlos (nur TWS) und eines bezahlt (API).
- Voraussetzungen für API-Marktdaten überhaupt: IBKR **PRO** (nicht Lite), eröffnetes Konto (Demo-Konten können nicht abonnieren), **≥ 500 USD** zusätzlich zu den Abokosten, Abo im Client Portal gebucht **und** „Market Data API access" dort freigeschaltet.
- Verzögerungen laut IBKRs Paper-Trader-Delayed-Tabelle: US-Aktien 15 min, US-Optionen 15 min, US-Futures 10 min; Metalle, Forex und US-Bonds ohne Verzögerung. (MITTEL — über Suchergebnis belegt, Seite selbst nicht abgerufen.)

Für ein LLM-Entscheidungs-Gate, das Analysen aus Yahoo/Alpha-Vantage-Daten fährt und einmal täglich eine Order absetzt, sind 15 Minuten Verzögerung irrelevant. **Marktdaten sollten deshalb bewusst kein Teil des kritischen Pfads sein** — außer für den Limitpreis, und dafür genügt delayed oder gar ein `MKT`-Order-Typ.

### 4.3 Order-Verhalten im Paper — die offizielle Liste

Wörtlich aus dem Client-Portal-Guide „About Paper Trading Accounts" (2026-02-11) und dem Campus-Glossar (2026-07-21), inhaltsgleich (HOCH):

> - No support for some order types including: **VWAP, Auction, RFQ, and Pegged to Market**.
> - **Fills are simulated from the top of the book; no deep book access.**
> - Limited combo trading.
> - **Stops and other complex order types are always simulated** in paper trading, which may result in slightly different behavior from a production account.
> - Penny trading for US Options is not supported. Orders can be submitted but will not receive a penny fill.
> - **The trade simulator will reject the remainder of any exchange-directed market order that partially executes.** This may or may not match the behavior of a real-world exchange. **Market orders received while there is no quote on the opposite side will be held until the first partial fill.**
> - Mutual Fund trading is not supported in a Paper Trader Account.

Dazu, einordnend:
- *„Trades entered into a paper trading account will not actually execute on any exchange or settle at a clearing house. However, the **simulated price of the executions will be determined by real market prices and sizes**."*
- *„IBKR's Web API and TWS API can be used with IBKR paper accounts with minimal differences in functionality compared to live use. **Paper trades are executed by the same simulator employed by IBKR's own platforms.**"*
- Und die TWS-API-Doku ergänzt nüchtern: *„the Paper Trading Environment relies on more simulated technologies than the Live trading environment. As a result, certain behavior such as order execution may vary."*
- Startkapital: 1.000.000 USD Equity with Loan Value; Reset im Client Portal auf bis zu 5× des Live-Kontowerts möglich, Anträge vor 16:00 ET wirken zum nächsten Geschäftstag.

**Was es zu Slippage-Simulation offiziell nicht gibt:** keine Aussage, dass Slippage modelliert wird. Die beiden belegten Mechaniken — Top-of-Book-Fills und Ablehnung des Restes bei teilausgeführten exchange-directed Market-Orders — bedeuten in der Praxis: **Fills sind optimistischer als die Realität bei dünnen Büchern, und Teilausführungen verhalten sich anders als an einer echten Börse.** Für ein Entscheidungs-Gate, das Signale bewerten will, heißt das: die Paper-Fills sind ein Test der *Mechanik*, nicht eine Messung der *Ausführungsqualität*. Alles, was später aus Paper-Returns Alpha ableitet, hat hier eine systematische Verzerrung nach oben.

### 4.4 Paper und Live verwechseln — die konkreten Fallen

Das ist der Abschnitt, bei dem sich Sorgfalt am meisten auszahlt. Fünf Fallen, jede mit einem belegten Mechanismus:

**Falle 1 — der Login-Toggle.** Für Individual-Konten gilt offiziell: man loggt sich mit den **Produktions-Credentials** ein und wählt im Login-Fenster per Umschalter Live oder Paper. Ein falsch gesetzter Toggle führt dieselben Credentials in die Live-Umgebung. Gegenmittel: **separaten Paper-Username verwenden** (im Client Portal unter „Paper Trading Account" abrufbar, Passwort dort resetbar) — dann gibt es gar keinen Toggle. Die Web-API-Doku sagt genau das: „unlike other parts of Interactive Brokers, there is no slider... customers must use their specific Paper username to authenticate." Bei IBC/`ib_async`-IBC entspricht das `tradingMode='paper'`.

**Falle 2 — der Port ist keine Garantie.** 4002 ist ein Default, umkonfigurierbar. Niemals „Port 4002 ⇒ es ist Paper" annehmen.

**Falle 3 — die Kontonummer ist die eigentliche Wahrheit.** Beim Verbindungsaufbau liefert TWS laut offizieller Doku ungefragt „the account number(s) accessible in this TWS session" (`managedAccounts`). **Das ist der zuverlässige Guard: nach `connect()` prüfen, dass die Menge der verwalteten Konten genau `{"DUQ634065"}` ist, und bei Abweichung sofort trennen, ohne eine einzige Order zu senden.** Dass Paper-Kontonummern mit `DU` beginnen und Live-Konten mit `U`, ist durch das Zielkonto `DUQ634065` praktisch belegt, aber **ich habe keine offizielle IBKR-Dokumentation dieser Namenskonvention gefunden** (MITTEL). Deshalb: auf die **exakte Kontonummer** prüfen, nicht auf das Präfix. Ein Präfix-Check ist ein nützlicher zweiter Gürtel, kein Ersatz.

**Falle 4 — konkurrierende Sessions.** Offiziell dokumentiert als **Fehler 10197** „No market data during competing session": *„Indicates that the user is logged into the paper account and live account simultaneously trying to request live market data using both the accounts. In such a scenario preference would be given to the live account."* Und Fehler **1100** nennt „a competing session" als eine von drei Ursachen für Verbindungsverlust. Für die Web API ist das noch schärfer: eine Brokerage-Session pro Username **über alle Plattformen hinweg**. Praktisch: wer sich während eines laufenden Gateway-Betriebs mit demselben Username in TWS, Client Portal oder Mobile einloggt, kann den automatisierten Lauf abschießen.

**Falle 5 — der Statement-Pfad.** Paper-Auszüge gibt es nur über einen Client-Portal-Login **mit den Paper-Credentials**. Wer zur Verifikation in das Live-Portal schaut, sieht die Paper-Trades nicht und zieht womöglich den falschen Schluss.

**Zusätzlich relevant:** *„Trading permissions ... are the same as specified for your regular account."* Das heißt: was im Paper handelbar ist, entscheidet die **Berechtigungsmatrix des Live-Kontos**. Wenn dort keine Futures-, Forex- oder Krypto-Permission liegt, scheitern genau diese Instrumente auch im Paper — mit einem Order-Reject, nicht mit einer hilfreichen Meldung. Siehe §5.

---

## 5. Symbol-Auflösung

### 5.1 Der wichtigste Befund zuerst: nicht am Yahoo-Symbol ansetzen

In `tradingagents/dataflows/symbols.py` normalisiert `normalize_symbol()` jeden Eingabe-Ticker auf die **Yahoo-Finance-Schreibweise**, und zwar verlustbehaftet. Beispiel aus dem Code selbst:

```
"XAUUSD": "GC=F", "XAU": "GC=F", "GOLD": "GC=F"
```

Drei verschiedene Eingaben, ein Yahoo-Symbol — und das Yahoo-Symbol ist ein **COMEX-Future**, obwohl IBKR für genau diesen Fall ein natives Spot-Instrument hat. Die offizielle IBKR-Commodities-Doku zeigt als Beispiel wörtlich:

```python
contract.symbol = "XAUUSD"; contract.secType = "CMDTY"
contract.exchange = "SMART"; contract.currency = "USD"
```

Wer also `XAUUSD+` durch den Yahoo-Normalizer schickt und dann das Ergebnis `GC=F` nach IBKR übersetzt, kauft einen Future mit Verfallsdatum, Multiplikator 100 und Margin-Anforderungen, wo ein SMART-geroutetes Spot-CMDTY gemeint war. Dasselbe Muster bei Index-CFDs: `SPX500`/`US500` → `^GSPC` (Yahoo-Index, nicht handelbar), während IBKR mit `IBDE30`-artigen CFD-Symbolen (`secType="CFD"`, `SMART`) oder Index-Futures etwas Handelbares anbietet.

**Empfehlung: eine eigene IBKR-Mapping-Tabelle, die auf dem Roh-Ticker ansetzt, nicht auf dem Yahoo-Ergebnis.** `normalize_symbol()` bleibt, was es ist — die Vendor-Normalisierung für Datenabfragen. Die Broker-Auflösung ist ein zweiter, unabhängiger Pfad vom gleichen Eingang. Das ist architektonisch sauberer und verhindert genau die Klasse von Fehlern, nach der gefragt wurde. (Dass `_TICKER_PATH_RE` `^`, `=` und `+` erlaubt, ist für die Dateisystem-Sicherheit richtig und hat mit der Contract-Auflösung nichts zu tun.)

### 5.2 Contract-Struktur: was IBKR minimal braucht

Offiziell (`/doc/contracts-financial-instruments/the-contract-object`, HOCH):

> „In all contracts, the minimum viable structure requires **at least a conId and exchange**; **or** a symbol, secType, exchange, primaryExchange, and currency."

Und zwei Verhaltensregeln aus der Contract-Details-Doku:
> „Invoking reqContractDetails with a Contract object which has currency = USD will **only return US contracts**, even if there are non-US instruments which have the USD currency."
> Derivate-Anfragen sind **intern gepaced** und müssen maximal spezifiziert sein (Symbol, SecType, Exchange, Currency, Strike, Right, LastTradeDateOrExpiration, ggf. TradingClass).

### 5.3 Mapping-Tabelle für die Instrumentenklassen, die das Framework erzeugen kann

Alle `secType`/`exchange`-Werte unten sind den offiziellen Contract-Referenzseiten entnommen (HOCH); die Zuordnung der konkreten Yahoo-/Broker-Symbole zu IBKR-Symbolen ist mein Schluss aus diesen Seiten und **muss gegen `reqContractDetails` am Konto verifiziert werden** (MITTEL):

| Framework-Ticker | IBKR-Contract | Paper handelbar? |
|---|---|---|
| `AAPL`, `MSFT`, `NVDA` | `secType="STK"`, `exchange="SMART"`, `currency="USD"`, `primaryExchange="NASDAQ"` | **Ja** — der Normalfall |
| `SPY` | `STK` / `SMART` / `USD` / `primaryExchange="ARCA"` | Ja |
| `^GSPC`, `^NDX`, `^DJI`, `^GDAXI` | `secType="IND"` — IBKR-Symbol ist **nicht** das Yahoo-Symbol (`^GSPC` → `SPX` an `CBOE`, `^GDAXI` → `DAX` an `EUREX`) | **Nein** — siehe §5.4 |
| `GC=F`, `CL=F`, `SI=F` (Yahoo-Futures) | `secType="FUT"`, z. B. `symbol="GC"`, `exchange="COMEX"`, `currency="USD"` + **`lastTradeDateOrContractMonth`** + ggf. `multiplier` | Nur mit Futures-Permission auf dem **Live**-Konto; Expiry-Rollover ist Pflichtarbeit |
| `XAUUSD`, `XAGUSD` (Roh-Ticker, **vor** dem Normalizer) | `secType="CMDTY"`, `symbol="XAUUSD"`, `exchange="SMART"`, `currency="USD"` | Mit Metals-Permission; Spot-Metalle haben laut IBKR keine Marktdaten-Verzögerung |
| `EURUSD=X`, `EURUSD` | `secType="CASH"`, `symbol="EUR"`, `currency="USD"`, `exchange="IDEALPRO"` (`IDEAL` = „Virtual Forex", `IDEALPRO` = „true forex trading") | Mit Forex-Permission. **Achtung:** bei `CASH` bestimmt `symbol` die Order-Menge, `currency` die Cash-Quantity-Größe |
| `BTC-USD`, `ETH-USD` | `secType="CRYPTO"`, `exchange="PAXOS"` oder `"ZEROHASH"` (IB-IE: `ZEROHASHE`), `currency="USD"` (nur USD) | Nur mit Krypto-Permission. **Wichtig: der `conId` unterscheidet sich je Listing-Exchange** — BTC@PAXOS 479624278 ≠ BTC@Zerohash 541686651. „Not all accounts are permitted for both routing destinations." |
| `BTC=F` | CME-Bitcoin-Future, `secType="FUT"` mit Expiry — **nicht** dasselbe wie `CRYPTO` | Praktisch unwahrscheinlich; mindestens Futures- **und** Krypto-Futures-Permission |
| `0700.HK`, `9992.HK` | `secType="STK"`, `exchange="SEHK"`, `currency="HKD"` | Nur mit HK-Permission; HK-Marktdaten haben die TWS-vs-API-Bundle-Falle (§4.2) |
| `600519.SS` | China-A-Aktien | Für ein Retail-Konto praktisch nicht zugänglich — **abweisen** |
| `SPX500`, `US500`, `GER40` (CFD-Namen) | `secType="CFD"`, `exchange="SMART"`, IBKR-eigene Symbole (`IBDE30`-Stil) | Nur mit CFD-Permission; für US-Residents regulatorisch ausgeschlossen |
| — | `secType="CONTFUT"` | **Nie** — offiziell: „can **not** be used for placing orders, for live market data, ... in the Web API" |

### 5.4 Sind Indizes handelbar?

**Nein — aber ich kann es nicht mit einem Zitat belegen und sage das so.** Die offizielle Index-Seite definiert `secType="IND"` ausschließlich als Contract-Struktur (Symbol, Exchange, Currency) **ohne** jedes Order-Beispiel, während die Seiten zu Stocks, Futures, FX, Commodities, CFDs und Crypto jeweils Order-Pfade zeigen. Ein Index ist eine Rechengröße ohne Lieferbarkeit; gehandelt werden Index-**Futures**, -**Optionen**, -**CFDs** oder ETFs. Eine Seite, die „IND ist nicht orderbar" wörtlich sagt, habe ich nicht gefunden (**MITTEL**).

Weil ich es nicht belegen kann, ist die Konsequenz keine Annahme, sondern eine **Allow-List**: nur `{"STK", "CASH", "FUT", "CMDTY", "CRYPTO", "CFD"}` dürfen in eine Order. `IND`, `CONTFUT`, `OPT`, `FOP`, `BAG`, `BOND`, `FUND`, `WAR` werden mit einer expliziten Fehlermeldung abgelehnt, nicht „durchprobiert". Das ist zugleich die Antwort auf die eigentliche Frage: **man muss nicht wissen, ob IBKR `IND` ablehnt, wenn man es selbst vorher ablehnt.**

### 5.5 Der verlässliche Weg, eine Fehlauflösung zu erkennen

Fünf Schichten, von billig nach teuer. Jede einzelne ist belegt; zusammen bilden sie eine Kette, bei der eine falsche Position mehrere unabhängige Prüfungen überleben müsste.

**Schicht 1 — Allow-List und Vorab-Mapping.** Nur explizit gemappte Roh-Ticker werden gehandelt. Unbekannt ⇒ Abbruch, nicht „SMART/USD probieren". Ein `AAPL`, das das Framework korrekt meint, und ein halluziniertes `XYZQ` müssen hier schon auseinanderfallen.

**Schicht 2 — Qualifizieren und auf Eindeutigkeit bestehen.** Das ist der Kern. `ib_async` bietet dafür genau die richtige Semantik:

```
IB.qualifyContracts(*contracts, returnAll: bool = False)
```
Aus der Quelle: *„Looks up all contract details, but only returns matching Contract objects. If 'returnAll' is True, instead of returning 'None' on an ambiguous contract request, the return slot will have a list of the matching contracts. Previously the conflicts were only sent to the log, which isn't useful if you are logging to a file and not watching immediately. Note: return value has elements in same position as input request. **If a contract cannot be qualified (bad values, ambiguous), the return value for the contract position in the result is None.**"*

Darunter `reqContractDetails`, dessen Semantik die Bibliothek im Docstring sauber dokumentiert: *„If the returned list is empty then the contract is **not known**; If the list has multiple values then the contract is **ambiguous**."*

Regel: **genau ein Treffer, sonst Abbruch.** `returnAll=True` verwenden, damit die Kandidatenliste im Log landet statt im Nirwana — das ist explizit der Grund, warum der Parameter existiert.

**Schicht 3 — Identität gegen Erwartung prüfen.** Nach dem Qualifizieren liegen `conId`, `primaryExchange`, `currency`, `localSymbol`, `tradingClass` und `longName` vor. Aus IBKRs eigenem Sync-Wrapper-Beispiel für AAPL: `ConId: 265598, ..., PrimaryExchange: NASDAQ, Currency: USD, LocalSymbol: AAPL, TradingClass: NMS`, `longName = "APPLE INC"`. Diese Werte gegen die Mapping-Tabelle prüfen und den `conId` **persistieren** — IBKR empfiehlt das selbst: *„We can save time in future sessions by storing information like the ConID and Exchange to a database for future reference."* Ab dem zweiten Lauf handelt man dann über `conId` + `exchange` (die offiziell minimale, eindeutige Contract-Form) und nicht mehr über eine Symbol-Suche. Ein geänderter `conId` bei gleichem Symbol ist das Alarmsignal für Corporate Actions.

**Schicht 4 — Handelbarkeit abfragen, nicht annehmen.** `ContractDetails` liefert dafür vier Felder: `validExchanges` („Valid exchange fields when placing an order for this contract"), `orderTypes` („Supported order types for this product"), `minSize`/`sizeIncrement` und — am direktesten — **`ineligibilityReasonList`**: „List of details why the account **cannot trade** the given security". Letzteres ist genau das gesuchte Signal. **Vorsicht bei der Doku:** die offizielle Referenzseite `/ref/ineligibility-reason` beschreibt die Felder `id` und `description` erkennbar falsch („The order's unique identifier...") — ein Copy-Paste-Fehler in IBKRs Tabelle. Das Feld ist echt, seine Dokumentation ist Schrott; den Inhalt muss man am Konto empirisch ansehen.

Ebenfalls relevant: die Pseudo-Börse **`VALUE`**. Offiziell: *„The VALUE exchange is a holding exchange used for clients to close positions on a contract that is **no longer listed**."* Ein qualifizierter Contract, dessen `validExchanges` nur noch `VALUE` enthält, ist ein Delisting — man kann schließen, aber nicht eröffnen.

**Schicht 5 — `whatIf` als letzter Vorab-Check.** Offiziell: *„If `WhatIf` is set to true the order will undergo a **credit check** for the expected post-trade margin requirement **without executing** an order... This is equivalent to creating a order ticket in TWS, clicking 'Preview', and viewing the information in the 'Margin Impact' panel."* Der zurückgegebene `OrderState` enthält Margin-Impact **und Kommissionen** — und die `OrderState`-Erweiterung aus TWS API 10.33 brachte zusätzlich ein `rejectReason`-Feld. `ib_async` hat das als `IB.whatIfOrder()`. Das ist der stärkste Einzel-Check: eine Order auf den falschen Contract fällt hier durch Margin, Kommission oder Reject-Grund auf, **bevor** sie gesendet wird.

**Laufzeit-Fehlercodes, die eine Fehlauflösung verraten** (alle offiziell, HOCH):

| Code | Text | Bedeutung |
|---|---|---|
| **200** | „No security definition has been found for the request." | Contract existiert nicht — Mapping falsch |
| **200** | „The contract description specified for ... is ambiguous" | Mehrere Treffer — zu unspezifisch |
| **203** | „...is ambiguous; you must specify the currency." | `currency` fehlt |
| **412** | „The contract is not available for trading." | Richtiger Contract, nicht handelbar |
| **154** | „Orders cannot be transmitted for a halted security." | Handelsunterbrechung |
| **110** | Preis verletzt die Minimum-Price-Variation | `minTick`/`marketRuleIds` nicht beachtet |
| **387** | „Unsupported order type for this exchange and security type." | Order-Typ passt nicht zum Instrument |
| **406** | „The currency is not allowed." | Währung nicht freigeschaltet |
| **201** | „Order rejected – Reason: ..." | Sammelcode; den Grund-Text loggen |
| **10015** | „Trading is not allowed in the API." | Read-Only-Modus aktiv (§3.5) |

**Nachgelagerte Pacing-Grenzen,** die bei einer Auflösungsschleife wichtig werden: `reqMatchingSymbols` braucht **≥ 1 Sekunde** zwischen aufeinanderfolgenden Aufrufen und liefert **maximal 16** Treffer (und sucht nur **Aktien**). Derivate-`reqContractDetails` sind intern gepaced. Und die generelle Obergrenze wurde geändert: laut Changelog ist „your maximum requests per second ... now based on your **Market Data Lines divided by 2**" — also kontoabhängig, nicht die früher kolportierte Pauschale. Mit persistiertem `conId` entfällt das Problem nach dem ersten Lauf ohnehin.

---

## 6. Handelszeiten

### 6.1 Die Datenquelle

`reqContractDetails` ist nicht nur Identitätsauflösung, sondern auch der Handelskalender. Offiziell:

> „Another function of `IBApi::EClient::reqContractDetails` is to request the **trading schedule** of an instrument via the **TradingHours** and **LiquidHours** fields. The corresponding **timeZoneId** field will then indicate the time zone for the trading schedule of the instrument. **TWS sends these timeZoneId strings to the API from the schedule responses as-is, and may not exactly match the time zones displayed in the TWS contract description.**"

Felddefinitionen aus `/ref/contract-details`:
- `tradingHours` — „The trading hours of the product."
- `liquidHours` — „The liquid hours (**regular trading hours**) of the contract on the specified exchange."
- `timeZoneId` — „The time zone for the trading hours of the product."

### 6.2 Das Format — mit echtem Beispiel

Aus IBKRs eigenem Sync-Wrapper-Tutorial, AAPL-`ContractDetails` im Rohzustand:

```
timeZoneId  = US/Eastern
tradingHours= 20261001:0400-20261001:2000;20261002:0400-20261002:2000;20261003:CLOSED;
              20261004:CLOSED;20261005:0400-20261005:2000;20261006:0400-20261006:2000
liquidHours = 20261001:0930-20261001:1600;20261002:0930-20261002:1600;20261003:CLOSED;
              20261004:CLOSED;20261005:0930-20261005:1600;20261006:0930-20261006:1600
```

Das ist die ganze Antwort auf „statt eine Uhrzeit hart zu kodieren": **IBKR liefert pro Kalendertag entweder ein konkretes Zeitfenster oder `CLOSED`.** Feiertage und Halbtage brauchen keine eigene Logik und keinen Feiertagskalender — sie stehen als `CLOSED` bzw. als verkürztes Fenster direkt in den Daten. Hier sieht man auch, dass `tradingHours` (04:00–20:00, inkl. Pre/Post) und `liquidHours` (09:30–16:00, RTH) deutlich auseinanderliegen.

**Zwei Doku-Ungenauigkeiten, die man kennen sollte:**
1. Die Referenz sagt: „This value will contain the trading hours of **the current day as well as the next's**." Das echte Beispiel enthält **sechs** Tage. Verlass dich auf das Parsen, nicht auf die behauptete Fensterbreite.
2. Dieselbe Referenz nennt bei `liquidHours` ein „Format for TWS versions until 969: `20090507:0700-1830`" — also ohne wiederholtes Datum auf der rechten Seite. Das moderne Format wiederholt das Datum (`20261001:0400-20261001:2000`). Ein Parser sollte beide Varianten verkraften, nicht eine annehmen.

### 6.3 Mit `ib_async` ist es ein Einzeiler

Die Bibliothek parst das bereits, und zwar korrekt — inklusive Zeitzone und `CLOSED`-Behandlung. `ContractDetails` bietet:

```python
def tradingSessions(self) -> list[TradingSession]:  # parst tradingHours
def liquidSessions(self)  -> list[TradingSession]:  # parst liquidHours
```

Die Implementierung (aus der API-Doku der Bibliothek) splittet an `;`, **überspringt jeden Eintrag mit `CLOSED`**, und erzeugt pro Session `datetime.strptime(t, "%Y%m%d:%H%M").replace(tzinfo=ZoneInfo(self.timeZoneId))` — also **zeitzonenbewusste** `datetime`-Objekte in der Börsenzeitzone. Damit lautet die Handelbarkeitsprüfung:

> Ist `datetime.now(tz=UTC)` in einem der `liquidSessions()`-Intervalle? → RTH-Order ohne Sonderflags. Nur in `tradingSessions()`, nicht in `liquidSessions()`? → Pre-/Post-Market, `order.outsideRth = True` nötig. In keinem von beiden? → **nicht handeln**.

### 6.4 Was dazu gehört, damit es im Dauerbetrieb trägt

- **Täglich neu holen.** Der tägliche Gateway-Restart existiert laut IBKR genau deshalb: „to perform functions such as **re-downloading contract definitions** in cases where contracts have been changed or new contracts have been added." Ein `ContractDetails`-Cache, der über den Restart hinweg lebt, kann die Zeitfenster von gestern enthalten. Cache-TTL ≤ 1 Handelstag.
- **Order-Flags passend setzen.** `order.outsideRth = True` für Pre/Post. Für die Overnight-Session: `order.includeOvernight = True` (= „OVERNIGHT+DAY") oder `contract.exchange = "OVERNIGHT"` (nur Overnight). Warnung aus der offiziellen Doku: *„Orders routed to the `OVERNIGHT` exchange with `order.includeOvernight = True` will behave as 'OVERNIGHT+DAY'."*
- **Flag-Rückmeldungen beachten:** Fehler **2109** „Attribute 'Outside Regular Trading Hours' is ignored based on the order type and destination. PlaceOrder is now processed." (Warnung, Order läuft), **411** „The 'Outside Regular Trading Hours' flag is not valid for this order", **351** „The 'Regular Trading Hours only' flag is not valid for this order".
- **Handelszeiten sind nicht Handelbarkeit.** Ein Contract kann mitten in `liquidHours` angehalten sein. Zwei zusätzliche Signale: der **`HALTED`-Tick** (erscheint im Snapshot als `'HALTED': 0.0`, siehe IBKRs eigenes Beispiel) und **Fehler 154** „Orders cannot be transmitted for a halted security".
- **Alternative/Ergänzung:** `IB.reqHistoricalSchedule()` existiert in `ib_async` und liefert einen Handelsplan über die `HistoricalSession`-Struktur. Als Kreuzprobe gegen den `tradingHours`-Parser nützlich; als Primärquelle nicht nötig.

---

## 7. Empfehlung

### Die eine empfohlene Kombination

> **IB Gateway (Paper-Modus, Port 4002) als lokaler Prozess auf dem Windows-Arbeitsplatz + `ib_async` 2.1.0 (gepinnt) als Python-Client + Windows Task Scheduler-Task unter einem angemeldeten Desktop-Benutzer mit „Run only when user is logged on", Gateways nativem täglichen Auto-Restart und einem manuellen Login pro Woche.**

Im Detail:

| Komponente | Wahl | Weil |
|---|---|---|
| **Schnittstelle** | TWS API (Socket), **nicht** Web API | Web API für Individual-Konten nur über CPGW; dort „does not support an automated authentication process" + **täglicher** Browser-Login + Ortsbindung. IBKR selbst: „always advise clients use our direct TWS API implementation whenever possible." |
| **Server-Prozess** | **IB Gateway**, nicht TWS | ~40 % weniger Ressourcen, API-identisch, **kein selbst-updatender Installer** (TWS hat einen und der bricht mit IBC), kein Inaktivitäts-Lock |
| **Bibliothek** | **`ib_async` 2.1.0**, Version gepinnt, hinter einem eigenen schmalen Adapter | Einziger moderner TWS-API-Client; BSD-2-Clause; implementiert das Protokoll selbst und braucht kein `ibapi` → **kein GPL-Kontakt**; Python 3.10–3.14 klassifiziert, passt zu 3.13.13 lokal und `>=3.11` im Projekt; bringt `qualifyContracts(returnAll=True)`, `whatIfOrder()`, `tradingSessions()`/`liquidSessions()`, `connect(readonly=...)` fertig mit |
| **Betriebsform** | Task Scheduler, angemeldeter Benutzer, `/INLINE`, Wiederholung alle 10 min mit Instanz-Sperre, Gateway „Never lock" + „Auto restart", `ClosedownAt` Freitagabend | Belegt im IBC User Guide; Windows-Dienst und „Run whether user is logged on or not" sind ausdrücklich keine Optionen |
| **IBC** | **Optional, kein Fundament.** Zuerst ohne IBC bauen (nativer Auto-Restart trägt den Tag). IBC 3.24.2 nur dann nachrüsten, wenn die 2FA-Messung zeigt, dass der Paper-Login ohne Zweitfaktor geht | IBC ist seit 2026-09-01 in Rente und archiviert; der Maintainer begründet es selbst mit dem nativen Auto-Restart. Ohne IBC entfällt auch `ib_async.Watchdog` (braucht einen `controller`) → eigene Reconnect-Logik auf `disconnectedEvent` + `probeContract`-Muster |
| **Marktdaten** | Bewusst **nicht** im kritischen Pfad. `reqMarketDataType(3)` (delayed) als Default, 10089/10090 als erwarteten Zustand behandeln | Paper hat keine eigenen Abos; Sharing ist an „gleiches Gerät" gebunden; API-Daten ≠ TWS-Daten. 15 min Verzögerung sind für ein tägliches Gate irrelevant |
| **Guards** | Nach `connect()`: `managedAccounts == {"DUQ634065"}`, sonst sofort trennen. secType-Allow-List. `qualifyContracts(returnAll=True)` mit „genau ein Treffer". `conId` persistieren. `whatIf=True` vor jeder echten Order | Jede Schicht in §5.5 belegt; Port 4002 allein ist **keine** Garantie |

**Reihenfolge für den Meilenstein** (und das ist die eigentliche Planungsaussage): Schritt 0 ist **nicht** Code, sondern eine Messung. Gateway installieren, mit dem **separaten Paper-Username** von `DUQ634065` auf Port 4002 einloggen und notieren: (a) wird ein Zweitfaktor verlangt? (b) was liefert `managedAccounts`? (c) was liefert `reqContractDetails` für `AAPL` und für je ein Exemplar der exotischen Klassen (`SPX`/`IND`, `GC`/`FUT`, `XAUUSD`/`CMDTY`, `EUR.USD`/`CASH`, `BTC`/`CRYPTO`) — inklusive `ineligibilityReasonList`? Diese drei Antworten entscheiden mehr über den Zuschnitt der Phasen als jede weitere Recherche.

### Die drei größten Risiken dieser Wahl

**1. Der wöchentliche Login ist ein menschlicher Single Point of Failure — und sein Ausfall ist still.**
Offiziell: Auto-Restart trägt „from Sunday to Sunday", danach „it will be necessary to again enter security credentials", und der Wochenzyklus beginnt montags. Wird der Login vergessen, läuft der Gateway-Prozess weiter und der Task Scheduler ist zufrieden — nur die IBKR-Session ist tot. Der Lauf scheitert dann nicht mit „nicht eingeloggt", sondern mit `Soft token=0 received instead of expected permanent`, Fehler 1100 oder 502, und wenn niemand darauf hört, produziert das Gate tagelang nichts und niemand merkt es. **Das ist dieselbe Klasse von Fehler, die diesem Repo schon einmal 12 rote Läufe (2026-09-25 bis 2026-10-10) eingebracht hat — damals Zugangsdaten, nicht Code.** Gegenmittel: ein Liveness-Signal, das nicht am Order-Ergebnis hängt, sondern am Session-Zustand (`isConnected()` **plus** eine echte Antwort auf einen `probeContract`-Request), plus ein lauter Alarm bei n aufeinanderfolgenden Fehlschlägen. Falls die 2FA-Messung ergibt, dass der Paper-Login ohne Zweitfaktor geht, schrumpft dieses Risiko erheblich — dann ist der Wochen-Login automatisierbar.

**2. `ib_async` hat Bus-Faktor 1, eine zehn Monate alte Release-Linie und einen Dependency-Deckel, der schon jetzt greift.**
2.1.0 ist vom 2025-12-08, `main` steht seit 2025-12-06 still, die Arbeit liegt unreleased auf `next` (2026-07-14), GitHub-Releases zeigen fälschlich noch v2.0.1, 99 offene Issues, ein Maintainer. Dazu der konkrete Pin `tzdata<2026.0` bei aktuellem `tzdata` **2026.5** — hier geht es nur auf, weil die `.venv` noch `tzdata 2025.2` hat; jedes Upgrade kollidiert. Und IBKR bewegt die TWS API gerade auf **Protobuf**, was an der Bibliothek als unveröffentlichter `next-protobuf`-Branch sichtbar ist: wenn IBKR die Protokoll-Umstellung erzwingt und `ib_async` nicht rechtzeitig released, steht der Client. Gegenmittel: Version hart pinnen, `tzdata` mitpinnen, die IBKR-Nutzung hinter einem schmalen eigenen Adapter mit ≤ 10 Methoden kapseln (`connect`, `resolve`, `is_tradable_now`, `preview`, `place`, `positions`, `health`), damit ein Austausch gegen den offiziellen `TWSSyncWrapper` eine Datei kostet und nicht eine Umschreibung — **aber mit dem Wissen, dass dieser Fallback GPL-belastet ist** (TWS API 10.49+, Changelog 2026-08-03) und für einen öffentlichen Fork vorher lizenzrechtlich geklärt werden müsste.

**3. Falsche Auflösung und Paper/Live-Verwechslung erzeugen plausible, aber falsche Ergebnisse — nicht Abstürze.**
Ein `^GSPC`, das als Index-Future statt als Index auflöst, oder ein `XAUUSD+`, das über den Yahoo-Normalizer zum COMEX-Future wird, kauft etwas Handelbares mit falschem Nominal, falschem Multiplikator und falscher Margin. Das wirft keine Exception; es füllt das Decision-Log mit Returns, die zu einer anderen Position gehören als die Entscheidung. Dasselbe gilt für die Live-Verwechslung: der Port ist nur ein Default, und für Individual-Konten ist der Login-Toggle mit Produktions-Credentials der dokumentierte Normalweg. Gegenmittel ist die fünfschichtige Kette aus §5.5 — Allow-List, genau-ein-Treffer, Identitätsvergleich gegen persistierten `conId`, `ineligibilityReasonList`/`validExchanges`, `whatIf`-Preview — plus die harte `managedAccounts`-Zusicherung gegen `DUQ634065` als erste Anweisung nach jedem `connect()`. Zusätzlich sollte die IBKR-Auflösung bewusst **nicht** auf dem Yahoo-normalisierten Symbol aufsetzen, sondern als zweiter unabhängiger Pfad auf dem Roh-Ticker.

---

## Quellen

**Offizielle IBKR-Dokumentation** (abgerufen 2026-10-11 als Markdown über `.md`-Suffix, Konfidenz HOCH):
- TWS API Doku-Index: `https://www.interactivebrokers.com/docs/tws-api/llms.txt`
- `ib_insync and ib_async`: `/docs/tws-api/doc/third-party-api-platforms/non-standard-tws-api-languages-and-packages/ib-insync-and-ib-async`
- `The IB Gateway` (headless/Auto-Restart/Samstagnacht-Reset): `/docs/tws-api/doc/architecture/the-trader-workstation/the-ib-gateway`
- `Daily & Weekly Reauthentication`: `/docs/tws-api/doc/tws-settings/daily-weekly-reauthentication`
- `Supported Two Factor Authentication (2FA)`: `/docs/tws-api/doc/notes-limitations/supported-two-factor-authentication-2-fa`
- `Requirements` (min. Python 3.11.0, IBKR Pro): `/docs/tws-api/doc/notes-limitations/requirements`
- `TWS API Limitations` (Paper-Hinweise, Kanada-Restriktion): `/docs/tws-api/doc/notes-limitations/tws-api-limitations`
- `Establishing an API connection`, `Broken API socket connection`: `/docs/tws-api/doc/connectivity/...`
- `Order Precautions`, `"Never Lock Trader Workstation" Setting`: `/docs/tws-api/doc/tws-settings/...`
- `Contract Details` Intro + `ContractDetails`/`Contract`/`IneligibilityReason` Referenz: `/docs/tws-api/doc/contracts-financial-instruments/contract-details/introduction`, `/docs/tws-api/ref/contract-details`, `/ref/ineligibility-reason`
- Contract-Referenz je Assetklasse: `/docs/tws-api/contracts/{stocks,indices,futures,fx-pairs,commodities,cryptocurrency,cf-ds}` und `/contracts/contract-management/the-value-exchange`
- `Stock Symbol Search` (`reqMatchingSymbols`, ≥1 s, max 16): `/docs/tws-api/doc/contracts-financial-instruments/stock-symbol-search/...`
- `Test Order Impact (WhatIf)`: `/docs/tws-api/doc/orders/test-order-impact-what-if`
- `Trading The Overnight Session`: `/docs/tws-api/doc/orders/place-order/trading-the-overnight-session`
- `Error Codes` / `System Message Codes`: `/docs/tws-api/doc/error-handling/...`
- `Market Data Type Behavior`, Fehler 10089: `/docs/tws-api/doc/market-data-delayed/...`, `/doc/error-handling/common-error-resolution/...`
- Sync-Wrapper (TWSSyncWrapper, TWS API 10.40+, AAPL-ContractDetails-Rohausgabe): `/docs/tws-api/sync-doc/introduction`, `/sync-doc/tws-sync-wrapper-class`
- TWS-API-Changelog (**GPL ab 10.49, Eintrag 2026-08-03**; Pacing = Market Data Lines / 2): `/docs/tws-api/changelog`
- Installer-Versionen (Stable 1050.02 / 2026-09-09, Latest 1051.01 / 2026-09-29, Python nur in „Latest"): `https://download2.interactivebrokers.com/installers/tws-api/index.html`
- Web API: `/docs/web-api/introduction`, `/getting-started`, `/authentication/introduction`, `/authentication/sessions`, `/authentication/trading`, `/authentication/paper`, `/authentication/faq`, `/authentication/cpgw/client-portal-gateway-faq`, `/authentication/cpgw/limitations-of-the-client-portal-gateway`
- General: `/docs/general/market-data-subscriptions/{market-data-requirements,tws-data-vs-api-data,market-data-users/market-data-sharing}`, `/docs/general/order-types/notes-limitations/order-type-by-api`
- Ports (offiziell, zwei unabhängige Stellen): `/docs/excel/dde/dde-socket-bridge/configuring-the-socket-bridge/configure-the-connecting-socket-port` und Campus-Lektion `interactivebrokers.com/campus/trading-lessons/installing-configuring-tws-for-the-api/` (dort auch „Read-Only enabled by default")
- Paper-Konto: `ibkrguides.com/clientportal/aboutpapertradingaccounts.htm` (Stand 2026-02-11), Campus-Glossar „Paper Trading Account" (zuletzt 2026-07-21), `ibkr.info/article/2879` Secure Login System (Stand 2026-01-12)

**Repo-/Paket-Stände** (PyPI-JSON- und GitHub-API-Abfragen, 2026-10-11, Konfidenz HOCH):
- `ib_async` 2.1.0 / 2025-12-08 / BSD-2-Clause / `requires_dist: aeventkit<3.0.0,>=2.1.0, nest_asyncio, tzdata<2026.0,>=2025.2`; `github.com/ib-api-reloaded/ib_async` (`main` 2025-12-06, `next` 2026-07-14, GH-Release-Stand v2.0.1, 1754 Stars, 99 Issues)
- `ib_insync` 0.9.86 / 2023-07-02; `github.com/erdewit/ib_insync` **archiviert**, letzter Commit 2024-03-14
- `ibapi` (PyPI) 9.81.1.post1 / 2020-12-06
- `ibind` 0.2.2 / 2026-10-06 / Apache-2.0; `Voyz/IBeam` v0.5.13 / 2026-09-20 / Apache-2.0
- `nautilus_trader` 1.231.0 / 2026-08-02 / LGPL-3.0-or-later
- `tzdata` aktuell **2026.5** / 2026-10-03; `aeventkit` 2.1.0 / 2025-06-22
- `IbcAlpha/IBC`: **archiviert**, Retirement-README, letztes Release 3.24.2 / 2026-08-21, Discussion #347 (Begründung des Maintainers, 2026-03-24), `userguide.md` (Windows Task Scheduler, `/INLINE`, Second Factor Authentication, Sonntags-Ablauf)
- `gnzsnz/ib-gateway-docker`: MIT, Push 2026-10-09, Release `ibgateway-stable@10.50.1f` / 2026-10-06, 1273 Stars

**`ib_async`-API-Oberfläche** (Context7 `/websites/ib-api-reloaded_github_io_ib_async` + direkte Abfrage von `ib-api-reloaded.github.io/ib_async/api.html`, Konfidenz HOCH): `IB.qualifyContracts(*contracts, returnAll=False)`, `IB.reqContractDetails()`, `IB.reqMatchingSymbols()`, `IB.whatIfOrder()`, `IB.reqMarketDataType()`, `IB.connect(..., readonly=False)`, `ContractDetails.tradingSessions()/liquidSessions()` inkl. Parser-Implementierung, `ibcontroller.IBC(twsVersion, gateway, tradingMode, ..., on2fatimeout)`, `ibcontroller.Watchdog(controller, ib, ..., probeContract=Forex('EURUSD', exchange='IDEALPRO'), probeTimeout=4)`

**Projektkontext:** `.planning/MILESTONE.md`, `tradingagents/dataflows/symbols.py` (`normalize_symbol`, `_ALIASES`, `_TICKER_PATH_RE`), `pyproject.toml` (`requires-python = ">=3.11"`, `pytz>=2025.2`), lokale `.venv` (Python 3.13.13, `tzdata 2025.2`, `pytz 2025.2`)

**Bewusst als unsicher markiert:** Paper-Login-2FA-Verhalten (offizielle Aussagen betreffen Enrollment auf Kontoebene, nicht den Paper-User-Prompt; Community-Quellen widersprechen sich) · `DU`-Präfix-Konvention (keine offizielle Doku gefunden) · Nicht-Handelbarkeit von `secType="IND"` (nur indirekt erschlossen) · Geräte-Bindung bei geteilten Paper-Marktdaten (KB 1719 nur über Zitate belegt) · genaue GPL-Variante der TWS API 10.49+ (nur Changelog-Satz, keine Lizenzdatei geprüft) · Zuordnung einzelner Yahoo-Symbole zu IBKR-Symbolen (muss am Konto gegen `reqContractDetails` verifiziert werden)
