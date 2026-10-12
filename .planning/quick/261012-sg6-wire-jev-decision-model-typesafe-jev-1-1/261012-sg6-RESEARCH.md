# Quick Task 261012-sg6: Jev (typesafe/jev-1.13 via OpenRouter) – Research

**Recherchiert:** 2026-10-12
**Domäne:** OpenRouter Decisions-Route (alpha) + TypeSafe System One (Jev 1.13)
**Konfidenz:** MITTEL-HOCH. Schema und Endpoint stammen aus den Live-Docs. Die Route ist `alpha` und kann sich noch ändern.

<user_constraints>
## User Constraints (aus CONTEXT.md, verbindlich)

- Key im **Windows Credential Manager** via `keyring` (System-Python, NICHT `.venv`). Service `openrouter`, Username `api_key`. Der Operator gibt ihn selbst per `getpass` ein. Er erscheint nie in Repo, `.env`, Logs, SUMMARY oder Chat, und Fehlermeldungen echoen ihn nicht.
- Skill global unter `~/.claude/skills/jev/` (SKILL.md + `jev.py`). Wird nicht committet; ins Repo kommt nur `.planning/`-Doku.
- stdlib-only Python-CLI, aufgerufen mit System-`python`. Ausgabe als JSON: Antworten inkl. Konfidenz, Latenz und Kosten.
- Live-Test: ausgedachte Sales-Mail mit drei Fragen: Lead-Stärke (score), Mail-Typ (choice), persönliche Antwort nötig (noul).
- Regeln für die SKILL.md: Jev entscheidet, Claude schreibt. Bei niedriger Konfidenz entscheidet Claude. Vor dem Senden privater Inhalte den Operator fragen.
- Claude's Discretion: Interface (JSON-Datei/stdin), Retry/Timeout, Kostenermittlung.
- Kein Eingriff in `tradingagents/`.
</user_constraints>

## 1. Endpoint und Auth

| | |
|---|---|
| Methode/URL | `POST https://openrouter.ai/api/alpha/decisions` (NICHT unter `/api/v1`: die Operation überschreibt die Server-Base) [CITED: openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-questions-and-answers-request] |
| Header | `Authorization: Bearer <OPENROUTER_KEY>`, `Content-Type: application/json` |
| Modell | `"model": "typesafe/jev-1.13"` (die Antwort meldet z.B. `typesafe/jev-1.13-20260917`) |
| Optional | `session_id` (≤256), `user` (≤256), `trace` {trace_id, trace_name, …}, `provider` (ProviderPreferences, z.B. `{"data_collection":"deny","zdr":true}`) |

Optional empfohlen: die OpenRouter-Header `HTTP-Referer` / `X-Title` zur Attribution [ASSUMED, für die Funktion nicht nötig].

## 2. Request-Schema: die 3 Antwortformen

`state` (string | object | array, Pflicht) ist der zu bewertende Inhalt. `questions` ist eine Map `frage_id -> Question`. Jede Frage hat `type` + `instructions` (string/object/array). Die Frage-IDs gehen NICHT ans Modell, deshalb muss die volle Frage in `instructions` stehen [CITED: docs.typesafe.ai/primitives.md].

| Form | `type` | `criteria` | Grenzen |
|---|---|---|---|
| Option aus Liste wählen | `choice` | Pflicht: Objekt `{option: beschreibung \| null}` | max. 255 Optionen [CITED: docs.typesafe.ai/api.md] |
| Score auf Skala | `score` | Pflicht: Array der Level-Beschreibungen, **niedrigstes zuerst**, 0-basiert | 2–10 Level (der OpenRouter-Spec erlaubt minItems 1, TypeSafe-Docs verlangen min. 2, also 2–10 einhalten) |
| Wahrscheinlichkeit wahr | `noul` | Objekt mit Keys `"true"` und `"false"` (bei OpenRouter beide Pflicht, bei TypeSafe optional, deshalb immer beide setzen) | – |

### Beispiel-Request (Live-Test, copy-paste-fähig)
```json
{
  "model": "typesafe/jev-1.13",
  "state": "Subject: Quick question about your enterprise plan\n\nHi, I'm Head of Ops at Brightline Logistics (240 employees). We're evaluating tools to replace our spreadsheets before Q1 and have budget approved. Could you send pricing for ~50 seats and a demo slot next week?\n\nThanks, Dana",
  "questions": {
    "lead_strength": {
      "type": "score",
      "instructions": "How strong a sales lead is this email?",
      "criteria": ["Cold: no buying intent or fit", "Lukewarm: some interest, no clear need or budget", "Warm: clear need, timeline or budget unclear", "Hot: clear need, budget and timeline, asks for next step"]
    },
    "email_kind": {
      "type": "choice",
      "instructions": "What kind of email is this?",
      "criteria": {"sales_inquiry": "Prospect asking about buying", "support_request": "Existing customer needs help", "partnership": "Proposal to collaborate", "spam_or_marketing": "Unsolicited bulk/marketing", "other": "None of the above"}
    },
    "needs_personal_reply": {
      "type": "noul",
      "instructions": "Does this email need a personal, human-written reply (not a template)?",
      "criteria": {"true": "A person should write an individual reply", "false": "A template or no reply is fine"}
    }
  }
}
```

## 3. Response-Schema und Konfidenz

```json
{
  "id": "gen-dec-1789738314-X5e5eKGQdvR9rblyX250",
  "model": "typesafe/jev-1.13-20260917",
  "provider": "TypeSafe",
  "answers": {
    "is_bug":  {"type": "noul", "noul": 0.96},
    "team":    {"type": "choice", "choice": "payments", "confidence": 0.75,
                "probabilities": {"account": 0, "frontend": 0.16, "payments": 0.84}},
    "urgency": {"type": "score", "score": 1.99, "confidence": 0.99,
                "legend": {"0": "...", "1": "...", "2": "..."},
                "probabilities": {"0": 0, "1": 0.01, "2": 0.99}}
  },
  "usage": {"input_tokens": 476, "output_tokens": 70, "cost": 0.000019992}
}
```
(Beispiel aus den OpenRouter-Docs, `legend` dort gekürzt.) [CITED: OpenRouter-Decisions-Doku]

- **Wo die Konfidenz steht:** `answers.<id>.confidence` (0..1), nur bei `choice` und `score`. `noul` hat **kein** `confidence`. Vergleichbare Größe laut Docs: `abs(2p-1)` [CITED: docs.typesafe.ai/confidence.md].
- `choice` liefert die Option mit der höchsten Wahrscheinlichkeit. Konfidenz = (p_max − 1/n)/(1 − 1/n).
- `score` ist der wahrscheinlichkeitsgewichtete Mittelwert und kann zwischen Leveln liegen (z.B. 1.43). Das passende Label kommt über `round(score)` → `legend`.
- **Gating-Empfehlung der Docs:** < 0.5 gilt als unsicher (Mensch/Claude entscheidet). Für High-Stakes ohne Rückfrage nur > 0.9. Für den Skill: `confidence < 0.5` bzw. `abs(2p-1) < 0.5` (also p zwischen 0.25 und 0.75) gilt als „Jev unsicher, Claude entscheidet“.

## 4. Latenz und Kosten

- **Kosten:** Primär `usage.cost` (USD, im Spec *optional*) direkt aus der Antwort. Fallback: `GET https://openrouter.ai/api/v1/generation?id=<id>` (Bearer-Auth) liefert `data.total_cost`, `data.latency` (ms) und `data.generation_time` (ms); `api_type` kennt den Wert `decisions` [CITED: openrouter.ai/docs/api/api-reference/generations/get-generation]. Ob `gen-dec-…`-IDs dort tatsächlich auflösbar sind, steht nicht in den Docs, und die Daten kommen evtl. verzögert. Deshalb nur als Best-Effort mit 1–2 Retries im Abstand von ca. 1 s und bei Fehlschlag `null` [ASSUMED].
- **Preis-Plausibilität:** $0.042 pro Mio. Input-Token, Output gratis [CITED: docs.typesafe.ai/models.md]. 476 Token ergeben ca. $0.00002, was zum Beispiel passt.
- **Latenz:** Client-seitig mit `time.perf_counter()` um den Request messen (Wall-Clock inkl. Netz). Das ist die primäre Angabe, `data.latency` nur ergänzend.

## 5. Limits und Fehler

- Kontext: 64k Token pro Request (state + alle Fragen); state + längste Frage ≤ 32k [CITED: models.md]. Ein Maximum für die Fragenanzahl ist nicht dokumentiert.
- Rate-Limit (TypeSafe direkt): 100k Token/s, 80 Req/s, dynamisch.
- OpenRouter-Fehlerformat: `{"error": {"code": int, "message": str, "metadata": {...}}, "user_id"?: ...}`. Codes: 400, 401, 402 (kein Guthaben), 403, 404, 413, 429, 500, 502, 503, 524, 529. TypeSafe direkt nutzt zusätzlich 422 für Validierung. Retry nur bei 429/502/503/524/529 mit Exponential Backoff (z.B. 3 Versuche: 1 s, 2 s, 4 s). 4xx sonst sofort mit exaktem `error.message` ausgeben.
- **Jaggedness (jev-1.13)** [CITED: docs.typesafe.ai/model-jaggedness/jev-1.13.md], gehört in die SKILL.md: Es liest wörtlich. Rechnen, Zählen und Datumslogik bleiben im Code. Bei `choice` gibt es einen Bias zur ersten Option (Reihenfolge variieren, eine „other“-Option anbieten). Keine Doppelnegationen. Den state knapp und relevant halten. Prompt-Injection im state ist möglich. Fragen sind voneinander unabhängig; Folgefragen kommen in einen zweiten Request.

## 6. Pitfalls für den stdlib-Python-Client (Windows)

1. **System-Python:** `C:\Users\admin\AppData\Local\Programs\Python\Python310` hat `keyring` und `certifi`, aber **kein `truststore`** [VERIFIED: Glob site-packages]. `python --version` ließ sich in dieser Session nicht ausführen, weil die Shell hing. Der Executor soll das zuerst prüfen.
2. **SSL / Firmen-CA:** Unter Windows lädt `ssl.create_default_context()` über `load_default_certs()` den Windows-Zertifikatsspeicher (ROOT/CA). Damit wird eine dort installierte Firmen-CA in der Regel akzeptiert, anders als bei npm/uv mit gebündelten Roots [ASSUMED, Standardverhalten von CPython unter Windows]. Deshalb **kein** `certifi.where()` als cafile übergeben, das würde die Firmen-CA umgehen. Vorgeschlagene Reihenfolge:
   (a) `ssl.create_default_context()`;
   (b) wenn `truststore` importierbar ist, `truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)`;
   (c) Env/Option `JEV_CA_FILE` → `create_default_context(cafile=...)`.
   **Niemals** `CERT_NONE` / `verify=False`. Ein `ssl.SSLCertVerificationError` muss eine klare Meldung mit Hinweis auf (c) ergeben.
3. **Key-Hygiene:** `keyring.get_password("openrouter","api_key")`. Bei `None` folgt eine Meldung mit dem Setup-Befehl (`python -c "import keyring,getpass; keyring.set_password('openrouter','api_key',getpass.getpass('OpenRouter key: '))"`), den der Operator selbst ausführt. Den Header nie loggen. Bei `HTTPError` nur `e.code` + JSON `error` ausgeben, nicht `e.headers` oder den Request. In Exception-Reprs keinen Key-String durchreichen.
4. **urllib-Details:** `HTTPError` hat einen lesbaren Body (`e.read()`) mit dem OpenRouter-Fehler-JSON, also auslesen und ausgeben. `timeout=30` setzen. Body als `json.dumps(...).encode("utf-8")`. Antwort mit `.decode("utf-8")` lesen, weil die Windows-Konsole cp1252 nutzt: Ausgabe per `sys.stdout.reconfigure(encoding="utf-8")` oder `ensure_ascii=True`.
5. **Proxy:** urllib übernimmt `HTTPS_PROXY` bzw. die Windows-Registry-Proxyeinstellungen automatisch (`getproxies()`). Falls ein Firmenproxy existiert, braucht es keinen Zusatzcode [ASSUMED].
6. **Interface-Vorschlag:** `python jev.py ask --file req.json` oder `-` für stdin. Die Eingabe ist `{state, questions}`; das Skript ergänzt `model`. Ausgabe-JSON: `{answers, latency_ms, cost_usd, input_tokens, id, model, uncertain: [ids]}`. Ein `setup`-Subcommand erledigt die getpass-Eingabe des Keys.
7. **Datenschutz:** Den Request ggf. mit `"provider": {"data_collection": "deny"}` senden. Ob TypeSafe als Provider dadurch ausgeschlossen wird, ist unbekannt (bei einem einzigen Provider könnte das zu 404 „no endpoints“ führen) [ASSUMED]. Deshalb im Live-Test zunächst **ohne** senden und als Option dokumentieren.

## Package Legitimacy Audit
Keine neuen Pakete: stdlib plus das bereits installierte `keyring`. `truststore` nur optional, wenn importierbar, wird nicht installiert.

## Annahmen-Log
| # | Annahme | Risiko |
|---|---|---|
| A1 | `GET /api/v1/generation?id=gen-dec-…` funktioniert für Decisions | gering: `usage.cost` ist primär, Fallback `null` |
| A2 | Windows-Zertifikatsspeicher deckt die Firmen-CA für Python-urllib ab | mittel: Fallback `JEV_CA_FILE` bzw. truststore |
| A3 | `provider.data_collection=deny` ist mit TypeSafe kompatibel | gering: im Test weglassen |
| A4 | Die alpha-Route bleibt stabil | mittel: Endpoint als Konstante, in SKILL.md auf die Docs-URL verweisen |

## Quellen
- https://docs.typesafe.ai/llms.txt, /api.md, /primitives.md, /primitives/score.md, /confidence.md, /models.md, /model-jaggedness/jev-1.13.md
- https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-questions-and-answers-request
- https://openrouter.ai/docs/api/api-reference/generations/get-generation
