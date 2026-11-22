"""Tests of the FastAPI integration (no network, no AI key: offline answers, a temporary database).
Needs: pip install fastapi httpx      Run: python test_service.py"""
import json
import os
import shutil
import sqlite3
import tempfile
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

import farms_store
from farm import DEMO_FARMS
from outage_service import Settings, mount, notify_step, outage_lifespan, run_job

HERE = os.path.dirname(os.path.abspath(__file__))
NOW = "2026-09-01T08:00"
ANSWERS = {"animals": {"poultry": "medium"}, "crops": ["vegetables"], "water_source": ["well"],
           "backup_energy": ["generator"], "extras": ["cold_room"], "locality": "مرناق"}


def make_settings(folder, **kw) -> Settings:
    events = os.path.join(folder, "events.json")
    shutil.copy(os.path.join(HERE, "events.json"), events)                      # the job may rewrite it: work on a copy
    base = dict(events=events, view=os.path.join(folder, "farmer_view.json"), db=os.path.join(folder, "outage.db"),
                articles=os.path.join(HERE, "articles.txt"), offline=True, now=NOW, job=False)
    base.update(kw)
    return Settings(**base)


def make_app(settings, **kw):
    app = FastAPI(**kw)
    mount(app, "/api/outage", settings)
    return app


def create_farm(client, **extra):
    profile = client.post("/api/outage/signup", json={"answers": ANSWERS}).json()["profile"]
    confirmed = [{"catalog_id": i["catalog_id"], "count": i["count"]} for i in profile["equipment"]]
    return client.post("/api/outage/farms", json={"locality": "مرناق", "confirmed": confirmed, "answers": ANSWERS, **extra})


def test_whole_flow_through_the_router_and_the_page_uses_the_prefix():
    with tempfile.TemporaryDirectory() as folder:
        client = TestClient(make_app(make_settings(folder)))
        assert client.get("/api/outage/health").json()["ok"]
        assert client.get("/api/outage/signup-options").json()["direction"] == "rtl"
        answer = create_farm(client)
        assert answer.status_code == 200
        farm_id = answer.json()["farm_id"]
        view = client.get(f"/api/outage/farmer-view?farm={farm_id}&now={NOW}").json()
        assert view["farm"]["farm_id"] == farm_id and view["farm"]["alerts"][0]["why"]
        page = client.get(f"/api/outage/f/{farm_id}")
        assert page.status_code == 200 and "/api/outage/farmer-view?farm=" in page.text and "__ENDPOINT__" not in page.text
        # bad requests keep the same {"error": ...} shape as the standard server
        assert client.get("/api/outage/farmer-view?farm=nope").status_code == 404
        assert client.post("/api/outage/farms", json={"locality": "مرناق", "confirmed": [{"catalog_id": "laser", "count": 1}]}).json()["error"]
        assert client.post("/api/outage/signup", json={}).status_code == 400


def test_phone_is_stored_privately_and_never_returned():
    with tempfile.TemporaryDirectory() as folder:
        settings = make_settings(folder)
        client = TestClient(make_app(settings))
        answer = create_farm(client, phone="+21612345678")
        farm_id = answer.json()["farm_id"]
        assert answer.json()["phone_saved"] and "+216" not in answer.text
        assert farms_store.get_phones(settings.db) == {farm_id: "+21612345678"}
        assert "12345678" not in client.get(f"/api/outage/farmer-view?farm={farm_id}&now={NOW}").text
        assert client.post("/api/outage/farms/phone", json={"farm_id": farm_id, "phone": "+21698765432"}).status_code == 200
        assert farms_store.get_phones(settings.db)[farm_id] == "+21698765432"
        assert client.post("/api/outage/farms/phone", json={"farm_id": farm_id, "phone": "12345"}).status_code == 400
        assert client.post("/api/outage/farms/phone", json={"farm_id": "nope", "phone": "+21612345678"}).status_code == 404
        assert create_farm(client, phone="abc").status_code == 400                 # a bad phone creates no farm
        assert len(farms_store.load_farms(settings.db)) == 1


def test_two_farms_with_the_same_name_do_not_collide():
    with tempfile.TemporaryDirectory() as folder:
        settings = make_settings(folder)
        client = TestClient(make_app(settings))
        a, b = create_farm(client).json()["farm_id"], create_farm(client).json()["farm_id"]
        assert a != b and len(farms_store.load_farms(settings.db)) == 2
        assert [f.id for f in farms_store.load_farms(settings.db)] == [a, b]


def test_demo_farms_are_used_until_a_farm_exists_and_json_farms_can_be_imported():
    with tempfile.TemporaryDirectory() as folder:
        db = os.path.join(folder, "outage.db")
        assert [f.id for f in farms_store.load_farms(db)] == [f.id for f in DEMO_FARMS]
        json_file = os.path.join(folder, "farms.json")
        farms_store.save_farm(DEMO_FARMS[1], json_file)                               # the old JSON storage still works
        assert farms_store.import_json_farms(json_file, db) == 1
        assert [f.id for f in farms_store.load_farms(db)] == ["demo-sousse"]


def test_the_job_builds_the_data_and_each_message_goes_out_only_once():
    with tempfile.TemporaryDirectory() as folder:
        settings = make_settings(folder, send=True)
        client = TestClient(make_app(settings))
        farm_id = create_farm(client, phone="+21612345678").json()["farm_id"]       # no sensors: general advice by message
        sent = []
        sender = lambda phone, body, channel: sent.append((phone, body, channel)) or f"SM{len(sent)}"   # noqa: E731
        lines = []
        status = run_job(settings, sender=sender, log=lines.append)
        assert status["state"] == "ok" and status["events"] > 0 and os.path.exists(settings.view)
        assert status["messages"]["sent"] == 1 and len(sent) == 1 and sent[0][2] == "whatsapp"
        assert f"/f/{farm_id}" in sent[0][1] or "التفاصيل" in sent[0][1]            # the message ends with the details line
        assert not any("+21612345678" in line for line in lines)                     # numbers are masked in the log
        run_job(settings, sender=sender, log=lambda *_: None)
        assert len(sent) == 1                                                        # second run: nothing new to send
        assert "SM1" in farms_store.sent_keys(settings.db).values()


def test_without_the_send_flag_messages_are_only_a_dry_run():
    with tempfile.TemporaryDirectory() as folder:
        settings = make_settings(folder, send=False)
        create_farm(TestClient(make_app(settings)), phone="+21612345678")
        status = run_job(settings, sender=lambda *a: 1 / 0, log=lambda *_: None)     # a real send would crash this sender
        assert status["messages"] == {"pending": 1, "sent": 0, "dry_run": 1, "failed": 0}
        assert farms_store.sent_keys(settings.db) == {}


def test_a_failing_send_is_reported_and_retried_next_run():
    import notify
    with tempfile.TemporaryDirectory() as folder:
        settings = make_settings(folder, send=True)
        create_farm(TestClient(make_app(settings)), phone="+21612345678")
        run_job(settings, sender=lambda *a: (_ for _ in ()).throw(notify.NotifyError("down")), log=lambda *_: None)
        assert settings.status["messages"]["failed"] == 1 and farms_store.sent_keys(settings.db) == {}
        run_job(settings, sender=lambda *a: "SM9", log=lambda *_: None)
        assert settings.status["messages"]["sent"] == 1


def test_a_broken_job_never_raises_and_keeps_the_old_data():
    with tempfile.TemporaryDirectory() as folder:
        settings = make_settings(folder, articles=os.path.join(folder, "missing.txt"))
        before = open(settings.events, "rb").read()
        status = run_job(settings, log=lambda *_: None)
        assert status["state"] == "failed" and "error" in status
        assert open(settings.events, "rb").read() == before


def test_the_automatic_job_starts_with_the_app_and_health_shows_it():
    with tempfile.TemporaryDirectory() as folder:
        settings = make_settings(folder, job=True, every_min=0)                     # run once at start
        app = make_app(settings, lifespan=outage_lifespan)
        with TestClient(app) as client:
            for _ in range(100):
                job = client.get("/api/outage/health").json()["job"]
                if job.get("state") in ("ok", "failed"):
                    break
                time.sleep(0.2)
            assert job["state"] == "ok", job
        assert os.path.exists(settings.view)


def test_public_url_goes_into_the_message_link():
    with tempfile.TemporaryDirectory() as folder:
        old = os.environ.get("DETAILS_URL")
        try:
            mount(FastAPI(), "/api/outage", make_settings(folder, public_url="https://app.example/api/outage"))
            from texts_ar import details_line
            assert details_line(DEMO_FARMS[1]) == "التفاصيل: https://app.example/api/outage/f/demo-sousse"
        finally:
            os.environ.pop("DETAILS_URL", None) if old is None else os.environ.__setitem__("DETAILS_URL", old)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(name, "OK")
