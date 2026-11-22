"""Enter a farmer in the terminal (the same steps as the app's sign-up form), then see what he would get.

  python add_farmer.py                       (the app must be running: python run_all.py)
  python add_farmer.py --base http://localhost:8000 --now 2026-09-01T08:00

Steps: your answers -> equipment estimated (you confirm) -> farm created (with or without sensors, optional phone)
-> the screen data / message for the demo date. The phone number is never printed back.
"""
import argparse
import json
import urllib.error
import urllib.request


def call(base, method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise SystemExit(f"{method} {path} -> {error.code}: {error.read().decode('utf-8')}")
    except urllib.error.URLError:
        raise SystemExit(f"cannot reach {base}. Is 'python run_all.py' running in another window?")


def ask(question, default=""):
    answer = input(f"{question}" + (f" [{default}]" if default else "") + " : ").strip()
    return answer or default


def fix_phone(raw: str) -> str:
    """33333333 -> +21633333333 ; 0021633333333 -> +21633333333 ; +216... unchanged."""
    phone = raw.replace(" ", "").replace("-", "")
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if phone.isdigit() and len(phone) == 8:
        phone = "+216" + phone
    if phone.isdigit() and phone.startswith("216"):
        phone = "+" + phone
    return phone


def pick(section, options_by_number) -> list[str]:
    for number, option in options_by_number.items():
        print(f"   {number}) {option['label_fr']}  ({option['label_ar']})")
    raw = ask("numbers separated by commas, empty = none")
    chosen = []
    for part in raw.replace(" ", "").split(","):
        if part.isdigit() and int(part) in options_by_number:
            chosen.append(options_by_number[int(part)]["id"])
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--prefix", default="/api/outage")
    parser.add_argument("--now", default="")
    args = parser.parse_args()

    options = call(args.base, "GET", f"{args.prefix}/signup-options")
    answers: dict = {}
    for section in options["sections"]:
        if "options" not in section:                 # the place search: asked at the end
            continue
        numbered = {i + 1: o for i, o in enumerate(section["options"])}
        print(f"\n{section['id']}  ({section['title_ar']})")
        chosen = pick(section, numbered)
        if section["type"] == "multi_with_size":
            sizes = {i + 1: s for i, s in enumerate(section["sizes"])}
            answers[section["id"]] = {}
            for item in chosen:
                print(f"  how many {item}?  " + "  ".join(f"{n}={s['id']}" for n, s in sizes.items()))
                n = ask("number", "2")
                answers[section["id"]][item] = sizes.get(int(n) if n.isdigit() else 2, sizes[2])["id"]
        else:
            answers[section["id"]] = chosen
    answers["locality"] = ask("\nLocality (French or Arabic, e.g. Mornag, Sousse, مرناق)", "Mornag")

    profile = call(args.base, "POST", f"{args.prefix}/signup", {"answers": answers})["profile"]
    if not profile["equipment"]:
        raise SystemExit("\nNo animals, crops or extras chosen, so there is no equipment to protect. Run it again and choose at least one.")
    print("\nEquipment estimated:")
    for item in profile["equipment"]:
        print(f"   {item['name_ar']} x{item['count']}  [{item['source']}]")
    if ask("Confirm this list? (y/n)", "y").lower() not in ("y", "yes", "o", "oui"):
        raise SystemExit("cancelled: nothing was saved")
    body = {"locality": answers["locality"], "answers": answers,
            "confirmed": [{"catalog_id": i["catalog_id"], "count": i["count"]} for i in profile["equipment"]]}
    if ask("Does the farm have sensors (tank and battery levels)? (y/n)", "n").lower() in ("y", "yes", "o", "oui"):
        body["sensors"] = {"tank_litres": float(ask("tank litres", "5000")), "tank_level_pct": float(ask("tank level %", "70")),
                           "battery_kwh": float(ask("battery kWh", "2")), "battery_pct": float(ask("battery %", "90"))}
    phone = ask("Phone for the message, international format, e.g. +216...  (empty = none)")
    if phone:
        body["phone"] = fix_phone(phone)
    farm = call(args.base, "POST", f"{args.prefix}/farms", body)
    print(f"\nfarm created: id = {farm['farm_id']}  (sensors: {farm['has_sensors']})")
    print(f"page for the farmer: {args.base}{args.prefix}/f/{farm['farm_id']}")
    print("The next job run (at most 30 min) sends the message if the farm has no sensors and a phone; "
          "the page shows the plan right away.")
    query = f"&now={args.now}" if args.now else ""
    view = call(args.base, "GET", f"{args.prefix}/farmer-view?farm={farm['farm_id']}{query}")["farm"]
    print(f"\nstatus now: {view['overall_label']}")
    for alert in view["alerts"]:
        print("  message :", alert["summary"])
        for action in alert["actions"]:
            print(f"    {action['action_label']}: {action['equipment']}")
    if not view["alerts"]:
        print("  no outage concerns this farm at this moment.")


if __name__ == "__main__":
    main()
