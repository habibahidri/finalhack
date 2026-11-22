"""Tries the whole API flow against a running server, like the app will do.

  1. in one window:   python server.py
  2. in another:      python try_api.py
  Options: --prefix /api/outage (FastAPI app)   --base http://localhost:8000   --now 2026-09-01T08:00   --sensors   (make it a farm with sensors)
"""
import argparse
import json
import urllib.error
import urllib.request

ANSWERS = {"animals": {"poultry": "medium", "cows": "small"}, "crops": ["vegetables"], "water_source": ["well", "tank"],
           "backup_energy": ["generator"], "extras": ["cold_room"], "locality": "مرناق"}


def call(base, method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise SystemExit(f"{method} {path} -> {error.code}: {error.read().decode('utf-8')}")
    except urllib.error.URLError:
        raise SystemExit(f"cannot reach {base}. Is 'python server.py' running in another window?")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--now", default="2026-09-01T08:00")
    parser.add_argument("--prefix", default="/api", help="/api for server.py, /api/outage for the FastAPI app")
    parser.add_argument("--sensors", action="store_true")
    args = parser.parse_args()

    print("1. sign-up answers sent:", json.dumps(ANSWERS, ensure_ascii=False))
    profile = call(args.base, "POST", f"{args.prefix}/signup", {"answers": ANSWERS})["profile"]
    print("2. equipment estimated (the farmer would confirm this list):")
    for item in profile["equipment"]:
        print(f"   {item['name_ar']}  x{item['count']}  [{item['source']}]")
    confirmed = [{"catalog_id": i["catalog_id"], "count": i["count"]} for i in profile["equipment"]]
    body = {"locality": ANSWERS["locality"], "confirmed": confirmed, "answers": ANSWERS}
    if args.sensors:
        body["sensors"] = {"tank_litres": 5000, "tank_level_pct": 70, "battery_kwh": 2, "battery_pct": 90}
    farm = call(args.base, "POST", f"{args.prefix}/farms", body)
    print(f"3. farm created: id = {farm['farm_id']}  (sensors: {farm['has_sensors']})")
    view = call(args.base, "GET", f"{args.prefix}/farmer-view?farm={farm['farm_id']}&now={args.now}")["farm"]
    print(f"4. screen data for {view['farm']} as of {args.now}: status = {view['overall_label']}")
    for alert in view["alerts"]:
        print("   headline:", alert["headline"])
        print("   message :", alert["summary"])
        for action in alert["actions"]:
            print(f"   {action['action_label']}: {action['equipment']}")
        print("   why     :", " | ".join(w["title"] for w in alert["why"]))
    print(f"\nOpen in the browser:  {args.base}{args.prefix}/farmer-view?farm={farm['farm_id']}&now={args.now}")


if __name__ == "__main__":
    main()