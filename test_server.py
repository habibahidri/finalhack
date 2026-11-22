import json
import os
import tempfile
import threading
import urllib.error
import urllib.request

from server import create_server

HERE = os.path.dirname(os.path.abspath(__file__))
EVENTS = os.path.join(HERE, "events.json")
ANSWERS = {"animals": {"poultry": "medium"}, "crops": ["vegetables"], "water_source": ["well"],
           "backup_energy": ["generator"], "extras": ["cold_room"], "locality": "مرناق"}


class Api:
    def __init__(self, folder, llm_factory=None):
        self.server = create_server(EVENTS, os.path.join(folder, "farms.json"), 0, llm_factory)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


def test_whole_flow_signup_confirm_and_screen_data():
    with tempfile.TemporaryDirectory() as folder:
        api = Api(folder)
        try:
            assert api.call("GET", "/api/health")[1]["ok"]
            assert "GET /api/health" in api.call("GET", "/")[1]["try_these"]       # the plain address explains itself
            status, form = api.call("GET", "/api/signup-options")
            assert status == 200 and form["direction"] == "rtl"
            status, out = api.call("POST", "/api/signup", {"answers": ANSWERS})
            profile = out["profile"]
            assert status == 200 and profile["equipment"] and not profile["ai_used"]
            confirmed = [{"catalog_id": i["catalog_id"], "count": i["count"]} for i in profile["equipment"]]
            status, farm = api.call("POST", "/api/farms", {"locality": "مرناق", "confirmed": confirmed, "answers": ANSWERS})
            assert status == 200 and farm["farm_id"]
            status, view = api.call("GET", f"/api/farmer-view?farm={farm['farm_id']}&now=2026-09-01T08:00")
            assert status == 200 and view["language"] == "ar" and view["farm"]["farm"].startswith("مزرعة")
            alert = view["farm"]["alerts"][0]
            assert alert["event_id"] == 1 and alert["why"] and alert["sources"] and alert["mode"] == "general_sms"
            status, view = api.call("GET", f"/api/farmer-view?farm={farm['farm_id']}&now=2026-12-01T08:00")
            assert view["farm"]["overall"] == "clear" and view["farm"]["all_clear_text"]
        finally:
            api.stop()


def test_bad_requests_are_rejected_and_numbers_are_not_trusted():
    with tempfile.TemporaryDirectory() as folder:
        api = Api(folder)
        try:
            assert api.call("POST", "/api/signup", {})[0] == 400
            assert api.call("POST", "/api/signup", {"answers": {"animals": {"dragons": "small"}, "locality": "x"}})[0] == 400
            assert api.call("POST", "/api/farms", {"locality": "مرناق", "confirmed": [{"catalog_id": "laser", "count": 1}]})[0] == 400
            assert api.call("POST", "/api/farms", {"locality": "مرناق", "confirmed": [{"catalog_id": "cold_room", "count": 999}]})[0] == 400
            assert api.call("POST", "/api/farms", {"locality": "", "confirmed": [{"catalog_id": "cold_room", "count": 1}]})[0] == 400
            assert api.call("GET", "/api/farmer-view?farm=nope")[0] == 404
            assert api.call("GET", "/api/nothing")[0] == 404
            # watts sent by the client are ignored: they come from the catalog
            status, farm = api.call("POST", "/api/farms", {"locality": "مرناق", "confirmed": [
                {"catalog_id": "cold_room", "count": 1, "power_w": 1}], "sensors": {"battery_kwh": 2, "battery_pct": 90, "tank_litres": 5000, "tank_level_pct": 70}})
            assert status == 200 and farm["has_sensors"]
            saved = json.load(open(os.path.join(folder, "farms.json"), encoding="utf-8"))[0]
            assert saved["equipment"][0]["power_w"] == 800
            assert api.call("POST", "/api/farms", {"locality": "x", "confirmed": [{"catalog_id": "cold_room", "count": 1}],
                                                  "sensors": {"battery_pct": 500}})[0] == 400
        finally:
            api.stop()


def test_farm_with_sensors_gets_the_full_plan_and_ai_failure_does_not_break_signup():
    def broken_llm():
        raise RuntimeError("no key")

    with tempfile.TemporaryDirectory() as folder:
        api = Api(folder, llm_factory=broken_llm)
        try:
            status, out = api.call("POST", "/api/signup", {"answers": ANSWERS, "use_ai": True})   # AI asked, AI unavailable
            assert status == 200 and not out["profile"]["ai_used"]
            status, farm = api.call("POST", "/api/farms", {"locality": "مرناق", "confirmed": [
                {"catalog_id": "cold_room", "count": 1}, {"catalog_id": "well_pump", "count": 1}],
                "sensors": {"battery_kwh": 2, "battery_pct": 90}})
            status, view = api.call("GET", f"/api/farmer-view?farm={farm['farm_id']}&now=2026-09-01T08:00")
            assert view["farm"]["has_sensors"] and view["farm"]["alerts"][0]["mode"] == "smart_plan"
            assert view["farm"]["alerts"][0]["actions"]
        finally:
            api.stop()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(name, "OK")