# Brief for Antigravity: farmer screen of PlantDNA ("Outage watch")

## Your job (and its limits)
Design the farmer-facing screen and connect it to a JSON file. Do NOT write business logic: no risk
calculation, no equipment rules, no text generation. The backend (Python) already decides everything and writes
`farmer_view.json`. The screen only displays it. If something looks missing, ask; do not invent it.

## Who uses it
A farmer in Tunisia, on a phone, often outdoors, sometimes with a weak connection. Reads Arabic first (French is secondary). Wants one answer: "Is something coming that affects my farm? What do I do?" Not technical.

## What the screen must answer, in this order
1. Is there something or not? (one big status: "Rien a signaler" / "A surveiller" / "A faire maintenant")
2. What exactly? (headline: what, when, where)
3. What should I do? (short list of actions: Garder / Faire avant / Faire apres / Eteindre, per equipment)
4. Why are you telling me this? (explainable part: collapsible "Pourquoi cette alerte ?")
5. Where does it come from? (links to the real announcements)

## Design principles
- Simple first: the status and the actions are visible without scrolling or tapping. Explanations are one tap away.
- Explainable: every alert shows its reasons (`why`), its assumptions (`assumptions`) and its sources. Never hide
  uncertainty: show "estimation" and the percentages as given.
- Never rely on color alone: status = icon + word + color. Large text (min 16 px), large touch targets (44 px).
- Calm, earthy, high-contrast palette (agriculture, not a bank). Light and dark mode.
- ARABIC by default, right-to-left (`direction: rtl` in the JSON). All texts come from the JSON/forms files, so French can
  be added later. Use logical CSS properties (no hard-coded left/right); numbers stay as 0-9; test an Arabic font.
- Works on a 360 px wide phone first; desktop is a wider version of the same layout.

## Screens / components
1. **Farm header**: farm name, locality, small badge "Capteurs connectes" or "Sans capteurs".
2. **Status banner**: from `overall` and `overall_label` (values: clear | info | watch | action).
3. **Alert card** (one per item in `alerts`, most urgent first):
   - headline, time range (`when_start`/`when_end`), utility icon (water / electricity)
   - `actions`: rows with an action chip (`action_label`, with `action` for styling) + equipment + short reason
   - "Pourquoi cette alerte ?" expandable: the list `why` (title + detail), then `assumptions` as small notes
   - `sources`: link chips (name + url, opens the original announcement)
4. **Sensor card** (only if `has_sensors`): tank % and hours left, battery % and hours left, from `sensors`.
5. **No-sensor variant** (`mode` = "general_sms"): show the advice as a message bubble (`summary`) with the note
   "Ce conseil est aussi envoye par SMS", and a hint "Ajoutez des capteurs pour un plan precis".
6. **All-clear state** (`alerts` empty): friendly text from `all_clear_text`, no empty boxes.
7. **States**: loading, no connection (show last data with its date), data older than 6 h ("Information a verifier").
8. **Demo bar** (visible only in demo mode): dropdown "Pretend it is..." listing `moments[].label`; changing it
   shows that moment's data. Plus a footer: "Demo: fermes et capteurs simules".

## Data contract: `farmer_view.json` (do not rename keys)
```
{ "status_labels": {info, watch, action, clear -> text},
  "moments": [ { "label": "01/09/2026 08:00", "iso": "...",
    "farms": [ { "farm", "locality", "has_sensors": bool,
      "sensors": null | {tank_pct, tank_hours, battery_pct, battery_hours},
      "overall": "clear|info|watch|action", "overall_label", "all_clear_text": null | string,
      "alerts": [ { "event_id", "utility": "water|electricity", "status": "info|watch|action", "status_label",
        "headline", "when_start", "when_end": null|iso, "channel": "app|sms", "mode": "smart_plan|general_sms",
        "summary": string,
        "actions": [ {"equipment","action": "Keep|Before|After|Off","action_label","reason"} ],
        "why": [ {"key","title","detail"} ],
        "assumptions": [string],
        "sources": [ {"name","url"} ] } ] } ] } ] }
```
A real example file is provided (`farmer_view.json`). In production the same shape will come from an API
endpoint, so load it through one function `loadFarmerView()` that can later be switched from file to URL.

## Wiring rules
- Read the file with `fetch`; render only what is in it. No hard-coded alert text.
- Status colors/icons are mapped in ONE place (clear, info, watch, action) so the designer can change them.
- Keep the page working by simply opening it (no build step needed for the demo), no external network calls except the
  source links.

## Out of scope
Login, map, notification sending, editing the farm, charts. (A map may come later.)

## Acceptance check
- With the demo moment "01/09/2026 08:00": Mornag shows an information alert with a plan; Sousse shows the
  water advice as a message bubble; a moment with no alert shows the all-clear state.
- Every alert can be explained in one tap and shows its sources.

## Part 2: sign-up with icons (new)
Before any alert exists, the farmer signs up with **pictures, not typing**.
- File `signup_options.json` describes the form (sections, options, `icon` names, Arabic labels, `direction: rtl`).
  Render each section from it. You choose the real icons or photos: the `icon` field is only a name (cow, sheep,
  chicken, tomato, well, tank, generator...).
- Section `animals` is "multi_with_size": tap an animal, then pick a size (قليل / متوسط / كثير) with its hint.
- Other sections are multi-select (`crops`, `water_source`, `backup_energy`, `extras`); `locality` is a place search.
- Big tiles (min 96 px), one question per screen on a phone, a visible progress bar, a Back button, no typing
  except the place search. Skipping a section is allowed.
- The form sends this answer (the file shows the exact shape in `answer_shape`):
  `{"animals":{"poultry":"medium"},"crops":["vegetables"],"water_source":["well"],"backup_energy":["generator"],"extras":["cold_room"],"locality":"مرناق"}`
- Then show the **"Your equipment" confirmation screen**. The backend returns
  `{"equipment":[{"catalog_id","name_ar","count","power_w","flow_lph","reason_ar","source":"rules|ai","confirm":true}],
  "questions_ar":[...],"ai_used":bool}`. Show each item as a card: name, count (+ / - stepper), the reason in one
  line, a toggle to remove it. Say clearly "هذه تقديرات، صحّحها إذا لزم". Items with `source:"ai"` get a small
  "اقتراح" tag. If `questions_ar` is not empty, show them as one-tap Yes/No questions.
- On confirm, send back the list of `catalog_id` the farmer kept (and the counts). Nothing else is computed in the UI.

## Arabic notes for the screens
- SMS text is Unicode: 70 characters per message (67 when split). The advice bubble shows the text as sent.
- Status words come from `status_labels` in `farmer_view.json` (للعلم / للمتابعة / تصرّف الآن / لا شيء يستدعي الانتباه).

## Part 3: talk to the backend through the API (new)
The Python server (`python server.py`, default http://localhost:8000) gives the screens live data. Use ONE config
value `API_BASE` (default `http://localhost:8000`). All answers are JSON, CORS is open for the demo.
| Step | Call | Returns |
|---|---|---|
| Load the icon form | `GET /api/signup-options` | same content as `signup_options.json` |
| Farmer finished the form | `POST /api/signup` body `{"answers": {...}, "use_ai": false}` | `{"profile": {"equipment":[...], "questions_ar":[...], "ai_used":bool, "notes":[...]}}` |
| Farmer confirmed the equipment | `POST /api/farms` body `{"locality":"مرناق","confirmed":[{"catalog_id":"cold_room","count":1}],"answers":{...same answers...}}` (optional `"name"`, optional `"sensors":{"tank_litres","tank_level_pct","battery_kwh","battery_pct"}`) | `{"farm_id":"a1b2c3d4","name":...,"has_sensors":bool}` |
| Show the farmer screen | `GET /api/farmer-view?farm=<farm_id>` (demo: add `&now=2026-09-01T08:00`; optional `&lang=ar`) | `{"language","direction","status_labels","generated_at","farm":{...}}` where `farm` has the same fields as one entry of `farmer_view.json` -> `moments[0].farms[]` |
Rules: store `farm_id` in the browser (localStorage) after sign-up; reload the farmer view every few minutes; show the
Arabic error text from `error` only in a calm message ("تعذّر التحميل، حاول لاحقا"), never raw technical text.
**Demo safety net:** if the server does not answer within 3 seconds, fall back to the local `farmer_view.json` file and show a
small "offline demo" tag. Errors: 400 bad input, 404 unknown farm, 503 no events yet.
Never send power / water numbers from the UI: the backend takes them from its catalog.
