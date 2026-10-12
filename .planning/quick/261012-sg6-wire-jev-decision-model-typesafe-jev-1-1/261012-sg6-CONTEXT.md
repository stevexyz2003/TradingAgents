# Quick Task 261012-sg6: Jev (typesafe/jev-1.13 via OpenRouter) einbinden - Context

**Gathered:** 2026-10-12
**Status:** Ready for planning

<domain>
## Task Boundary

Quelle: Operator-Screenshot `docs/screenshots/Screenshot 2026-10-12 202142.png` ("Wire Jev into your agent"). Wortlaut der Aufgabe:

> i want to add a new kind of AI model called Jev to this workspace. Jev doesn't write anything. you hand it some text plus a few questions, and it answers them almost instantly, for almost nothing. it's made for sorting and deciding.
> - Jev is brand new, so you won't know it yet. before anything else, read how it works: https://docs.typesafe.ai/llms.txt
> - i'll use it through OpenRouter, where it's called typesafe/jev-1.13. how to call it there: https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-questions-and-answers-request. it's a brand new route, so follow those docs if anything has moved
> - ask me for my OpenRouter key (i get one at https://openrouter.ai/keys). keep it somewhere safe on my computer, never inside a file i might share, and never show it back to me
> - Jev can only answer in 3 shapes: pick one option from a list, give a score on a scale, or say how likely something is true. most answers also come back with how sure it is
> - do one real test so i can watch it work. make up a short sales email and ask Jev 3 things: how strong a lead is this, what kind of email is it, and does it need a personal reply. show me its answers, how long it took and what it cost. if the test fails, show me the exact error
> - then save what you learned as a reusable skill (or whatever your setup calls a saved instruction), so next time i can say "use Jev to sort these" about any pile of text
> the rule from here on: Jev decides, you write. when Jev isn't sure about something, you make the call yourself. anything you send to Jev leaves my computer, so ask me before sending anything private.

Nicht Teil von TradingEngineX-Code: kein Eingriff in `tradingagents/` o.ä.; Integration ist eine Workspace-/Agent-Fähigkeit.

</domain>

<decisions>
## Implementation Decisions

### Key-Ablage
- OpenRouter-Key im **Windows Credential Manager** über Python `keyring` (Backend WinVaultKeyring, im System-Python `python` vorhanden; NICHT in `.venv`).
- Service-Name `openrouter`, Username `api_key`.
- Key wird vom Operator selbst in seinem Terminal eingegeben (getpass) — weder Orchestrator noch Agents sehen ihn je. Niemals in Repo, `.env`, Logs, SUMMARY oder Chat ausgeben; Fehlermeldungen dürfen den Key nicht echoen.

### Skill-Ort
- Global: `~/.claude/skills/jev/` (SKILL.md + Skript). Liegt außerhalb des Repos → wird nicht committet; im Repo nur `.planning/`-Doku.

### Aufruf
- Kleines **stdlib-only Python-CLI-Skript** im Skill-Ordner (z.B. `~/.claude/skills/jev/jev.py`), aufgerufen mit System-`python`. Liest Key per `keyring`, schickt Text + Fragen an die OpenRouter-Decisions-Route für `typesafe/jev-1.13`, gibt JSON zurück (Antworten je Frage inkl. Konfidenz, Latenz, Kosten).
- Unterstützt die 3 Antwortformen (Auswahl aus Liste, Score auf Skala, Wahrscheinlichkeit wahr) — genaue Request-Schemas aus den Live-Docs (Route ist neu; Docs gehen vor Annahmen).

### Claude's Discretion
- Skript-Interface (Fragen per JSON-Datei/stdin vs. CLI-Args), Retry-/Timeout-Verhalten, Kosten-Ermittlung (Response-Felder vs. OpenRouter-Generation-Endpoint).
- SKILL.md-Formulierung, inkl. Regeln: "Jev decides, Claude writes"; bei niedriger Konfidenz entscheidet Claude selbst; vor dem Senden privater Inhalte den Operator fragen.

</decisions>

<specifics>
## Specific Ideas

- Live-Test: ausgedachte kurze Sales-Mail (keine echten Daten) mit 3 Fragen: Lead-Stärke (Score), Mail-Typ (Auswahl), persönliche Antwort nötig (Wahrscheinlichkeit). Ergebnis mit Antworten, Dauer, Kosten dem Operator zeigen; bei Fehler exakte Fehlermeldung (ohne Key).
- Skill-Trigger: "use Jev to sort these" / "nutze Jev zum Sortieren".

</specifics>

<canonical_refs>
## Canonical References

- https://docs.typesafe.ai/llms.txt
- https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-questions-and-answers-request
- https://openrouter.ai/keys

</canonical_refs>
