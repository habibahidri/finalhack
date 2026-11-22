# Plugging the outage watch into your FastAPI app

## 1. Install
    pip install fastapi uvicorn httpx langgraph rapidfuzz
(`httpx` is only for the tests.) Keep the whole folder next to your app, or on your Python path.

## 2. The two lines
    from outage_service import outage_lifespan, mount
    app = FastAPI(lifespan=outage_lifespan)
    mount(app, "/api/outage")
If your app already has a lifespan, nest it: `async with outage_lifespan(app): ...your startup...`.
Try the smallest example: `uvicorn example_app:app --port 8000`, then open http://localhost:8000/api/outage/health

## 3. Endpoints (relative to the prefix, so `/api/outage/...`)
| Call | Use |
|---|---|
| GET /health | `{"ok", "events_file", "job": {state, started, finished, events, alerts, messages}}` |
| GET /signup-options | the icon form |
| POST /signup | `{answers}` -> estimated equipment to confirm |
| POST /farms | `{locality, confirmed:[{catalog_id,count}], answers?, name?, sensors?, phone?}` -> `{farm_id, ...}` |
| POST /farms/phone | `{farm_id, phone}` (+216XXXXXXXX). The number is never returned by any call |
| GET /farmer-view?farm=<id>[&now=ISO][&lang=ar] | the screen data |
| GET /f/<farm_id> | the farmer's page (the link at the end of the message) |
Errors are `{"error": "..."}` with 400 / 404 / 503. Antigravity's `API_BASE` becomes `https://your-app/api/outage` (no `/api` added by the UI).

## 4. What runs by itself
At app start, then every `OUTAGE_EVERY_MIN` minutes (default 30), in a background task of your app:
notices -> AI extraction -> events -> farmer data -> messages for farms without sensors that have a phone.
A failing run never stops your app and never wipes the previous data. A new farm gets its message at the next run (up to 30 min).

## 5. Settings (environment variables)
| Variable | Default | Meaning |
|---|---|---|
| OUTAGE_DB | outage.db | SQLite file: farms, phones, sent log. Created automatically |
| OUTAGE_EVENTS / OUTAGE_VIEW / OUTAGE_ARTICLES | events.json / farmer_view.json / articles.txt | files |
| OUTAGE_EVERY_MIN | 30 | 0 = run once at start only |
| OUTAGE_JOB | 1 | 0 = no automatic job |
| OUTAGE_OFFLINE | 0 | 1 = hand-made answers, no AI key. **Rewrites events.json: back it up first** |
| OUTAGE_NOW | (none) | demo date, e.g. 2026-09-01T08:00. Remove it in real use |
| OUTAGE_PUBLIC_URL | (none) | message links become `<url>/f/<farm id>`, e.g. https://your-app/api/outage |
| OUTAGE_SEND | 0 | 1 = really send. Needs TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM (or TWILIO_SMS_FROM) |
| OUTAGE_CHANNEL | whatsapp | or sms |
Without OUTAGE_SEND=1 messages are a DRY RUN (printed, phone masked, nothing sent, nothing logged).

## 6. Moving your current farms
    python -c "import farms_store; print(farms_store.import_json_farms('farms.json', 'outage.db'))"
Until the database has a farm, the two demo farms (demo-mornag, demo-sousse) are used.

## 7. Not included (be honest about it)
- Finding NEW announcements by itself: the job reads the fixed list in articles.txt.
- Login and rate limits (your app's job: /farms, /farms/phone and /f/<id> are open), and CORS (your app's middleware).
- Storage is SQLite: fine for a demo or one server; use your real database later (only farms_store.py changes).

## 8. Tests
    python test_service.py        (10 OK)     plus the older suites: test_farm, test_profile, test_server, test_job, test_graph, test_details, test_notify, test_pipeline
