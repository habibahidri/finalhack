# Putting the outage watch online, and the sign-up screen

## What exists now
- `GET /api/outage/join`  the sign-up page (works in any browser, phone first). Same steps as `add_farmer.py`.
- `GET /api/outage/f/<farm id>`  the farmer's page (the link in the message).
- The API is the same one Antigravity uses (see the table in INTEGRATION_FASTAPI.md).

## For Antigravity: the sign-up screen, if it replaces /join
All calls are relative to `API_BASE` = `https://<your-address>/api/outage` (no `/api` added by the UI).
1. `GET /signup-options` -> sections (`animals` with sizes, `crops`, `water_source`, `backup_energy`, `extras`; `locality` = a text field).
   `backup_energy` option `none` is exclusive: choosing it clears the others.
2. `POST /signup` `{"answers": {"animals": {"poultry": "small"}, "crops": ["vegetables"], "water_source": ["well"],
   "backup_energy": ["generator"], "extras": ["cold_room"], "locality": "مرناق"}}`
   -> `{"profile": {"equipment": [{"catalog_id", "name_ar", "count", "reason_ar", "source"}]}}`. Show it; let the farmer change counts or remove items.
3. `POST /farms` `{"locality", "answers", "confirmed": [{"catalog_id", "count"}], "sensors"?: {"tank_litres", "tank_level_pct", "battery_kwh", "battery_pct"}, "phone"?: "+21622345678"}`
   -> `{"farm_id", "has_sensors", "phone_saved"}`. Then open `/f/<farm_id>` or call `GET /farmer-view?farm=<id>`.
Errors are `{"error": "..."}` with status 400/404/503. Phone: `+` and 8 to 15 digits (add `+216` in the UI when the farmer types 8 digits).

## Option A, for the jury demo: run on your laptop and share a tunnel (most reliable)
1. `python run_all.py --demo`
2. In another window use a tunnel tool such as cloudflared or ngrok pointing to `http://localhost:8000`; it gives you an https address.
3. Restart with that address in the message links: `python run_all.py --demo --public-url https://<tunnel-address>/api/outage`
4. Antigravity's `API_BASE` = `https://<tunnel-address>/api/outage`. The laptop must stay on and awake.

## Option B, a real host (Render, Railway, Fly.io, any VPS)
- Build: `pip install -r requirements.txt`
- Start: `uvicorn example_app:app --host 0.0.0.0 --port $PORT`   (or your own app with the two mount lines)
- Environment variables (set them in the host's dashboard, never in files):
  `GEMINI_API_KEY`, `OUTAGE_DISCOVER=1`, `OUTAGE_PUBLIC_URL=https://<host>/api/outage`,
  `OUTAGE_CORS=https://<antigravity-app-address>` (default `*` is for demos only).
  For a demo date add `OUTAGE_NOW=2026-09-01T08:00`. Never set `OUTAGE_OFFLINE` on a host.
- Messages stay a dry run until `OUTAGE_SEND=1` and the Twilio variables are set.
Things to check on the host (not tested by the author, free plans differ):
- Disk: many free plans wipe files on restart or redeploy. Then `outage.db` (farms, phones), `extraction_store.json` (answers already paid for)
  and `farmer_view.json` are lost. Use a persistent disk, or commit `extraction_store.json` with the code so no article is paid twice.
- Sleep: a free service that sleeps also stops the automatic job. Ping `/api/outage/health` every few minutes, or use a paid always-on instance.
- One process only: the job runs inside the app; do not start several workers.

## Before it is public (not provided)
No login, no rate limit: anyone with the address can create farms, and `/f/<farm id>` opens that farm's page (the demo ids demo-mornag and demo-sousse are guessable).
Put your app's own protection in front before a real launch, and set `OUTAGE_CORS` to the real screen address.
