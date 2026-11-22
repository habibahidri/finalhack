"""Plugs the outage watch into a FastAPI app and keeps it running by itself.

  from outage_service import outage_lifespan, mount
  app = FastAPI(lifespan=outage_lifespan)
  mount(app, "/api/outage")

What runs on its own (inside your app, no extra terminal): at start and then every OUTAGE_EVERY_MIN minutes
  notices -> AI extraction -> events -> farmer data (events.json, farmer_view.json) -> messages for farms without sensors.
A failing run never stops your app and never wipes the previous data; /health shows the last run.
Messages are a DRY RUN (printed only) unless OUTAGE_SEND=1 and the Twilio variables are set.

Settings (environment variables):
  OUTAGE_DB            outage.db        farms, phone numbers, sent log (SQLite, created automatically)
  OUTAGE_EVENTS        events.json      OUTAGE_VIEW farmer_view.json    OUTAGE_ARTICLES articles.txt
  OUTAGE_EVERY_MIN     30               0 = run once at start only      OUTAGE_JOB=0 turns the job off
  OUTAGE_OFFLINE=1     hand-made answers, no AI key (REWRITES events.json: back it up first)
  OUTAGE_DISCOVER=1    look for NEW STEG/SONEDE announcements at each run (see discover.py; off by default)
  OUTAGE_NOW           demo date, e.g. 2026-09-01T08:00 (remove it in real use)
  OUTAGE_PUBLIC_URL    address in the message links: <url>/f/<farm id>  (e.g. https://your-app/api/outage)
  OUTAGE_SEND=1        really send (needs TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM or TWILIO_SMS_FROM)
  OUTAGE_CHANNEL       whatsapp (default) or sms
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime

from farm import TUNIS


def _flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    events: str = "events.json"
    view: str = "farmer_view.json"
    db: str = "outage.db"
    articles: str = "articles.txt"
    every_min: float = 30.0
    offline: bool = False
    send: bool = False
    channel: str = "whatsapp"
    now: str | None = None
    public_url: str = ""
    job: bool = True
    discover: bool = False
    status: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get
        return cls(events=env("OUTAGE_EVENTS", "events.json"), view=env("OUTAGE_VIEW", "farmer_view.json"),
                   db=env("OUTAGE_DB", "outage.db"), articles=env("OUTAGE_ARTICLES", "articles.txt"),
                   every_min=float(env("OUTAGE_EVERY_MIN", "30")), offline=_flag("OUTAGE_OFFLINE"),
                   send=_flag("OUTAGE_SEND"), channel=env("OUTAGE_CHANNEL", "whatsapp"),
                   now=env("OUTAGE_NOW") or None, public_url=env("OUTAGE_PUBLIC_URL", "").strip(),
                   job=_flag("OUTAGE_JOB", True), discover=_flag("OUTAGE_DISCOVER"))


def notify_step(settings: Settings, sender=None, log=print) -> dict:
    """Messages for farms without sensors that have a phone number and were not sent yet (each one only once)."""
    import notify
    import farms_store

    sender = sender or notify.twilio_send
    view = notify.load_json(settings.view, {})
    todo = notify.pending_messages(view, farms_store.get_phones(settings.db), farms_store.sent_keys(settings.db))
    counts = {"pending": len(todo), "sent": 0, "dry_run": 0, "failed": 0}
    for item in todo:
        label = f"{item['farm']} -> {item['phone'][:4]}****  [{settings.channel}] ({len(item['body'])} characters)"
        if not settings.send:
            counts["dry_run"] += 1
            log(f"DRY RUN  {label}")
            continue
        try:
            message_id = sender(item["phone"], item["body"], settings.channel)
            farms_store.mark_sent(item["key"], message_id, settings.db)       # logged right after each send: never twice
            counts["sent"] += 1
            log(f"SENT     {label}")
        except notify.NotifyError as error:
            counts["failed"] += 1
            log(f"FAILED   {label}: {error}")
    return counts


def run_job(settings: Settings, sender=None, log=print) -> dict:
    """One full run. Never raises: the result (also kept in settings.status) says what happened."""
    status = {"state": "running", "started": datetime.now(TUNIS).isoformat(timespec="seconds")}
    settings.status = status
    try:
        import pipeline_job

        now = datetime.fromisoformat(settings.now).replace(tzinfo=TUNIS) if settings.now else None
        result = pipeline_job.run_once(settings.articles, settings.offline, events_out=settings.events,
                                       view_out=settings.view, farms_path=settings.db, now=now, log=log,
                                       discover_new=settings.discover)
        status.update(result)
        if result.get("ok"):
            status["messages"] = notify_step(settings, sender, log)
        status["state"] = "ok" if result.get("ok") else "kept previous data"
    except Exception as error:  # noqa: BLE001 - a bad run must never stop the app
        status.update(state="failed", error=f"{type(error).__name__}: {' '.join(str(error).split())[:160]}")
        log(f"job failed: {status['error']}")
    status["finished"] = datetime.now(TUNIS).isoformat(timespec="seconds")
    settings.status = status
    return status


async def _loop(settings: Settings) -> None:
    while True:
        await asyncio.to_thread(run_job, settings)
        if settings.every_min <= 0:
            return
        await asyncio.sleep(settings.every_min * 60)


@asynccontextmanager
async def outage_lifespan(app):
    """Starts the automatic job with your app and stops it with it. If your app already has a lifespan, nest this one:
         async with outage_lifespan(app): ...your own startup..."""
    settings = getattr(app.state, "outage", None)
    task = asyncio.create_task(_loop(settings)) if settings and settings.job else None
    try:
        yield
    finally:
        if task:
            task.cancel()


def mount(app, prefix: str = "/api/outage", settings: Settings | None = None) -> Settings:
    from outage_router import router

    settings = settings or Settings.from_env()
    app.state.outage = settings
    if settings.public_url:
        os.environ["DETAILS_URL"] = settings.public_url          # texts_ar writes <url>/f/<farm id> at the end of the message
    app.include_router(router, prefix=prefix)
    return settings
