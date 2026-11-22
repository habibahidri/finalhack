"""The whole sign-up idea, end to end:  form answers -> equipment estimate -> farm -> advice for an outage.

  python signup_demo.py events.json                (rules only, no API key needed)
  python signup_demo.py events.json --ai           (adds the AI step; needs GEMINI_API_KEY or GROQ_API_KEY)
  python signup_demo.py events.json --save         (also saves the farm in farms.json for the automatic job)
"""
import json
import sys
from datetime import datetime

from events import status_at
from farm import TUNIS, farm_impacts, load_events
from geocode import PlaceRegistry
from profile_estimator import estimate_profile, profile_to_farm

# What the icon form would send (sample): a poultry + cows farm in Mornag.
ANSWERS = {"animals": {"poultry": "medium", "cows": "small"}, "crops": ["vegetables"], "water_source": ["well", "tank"],
           "backup_energy": ["generator"], "extras": ["cold_room"], "locality": "مرناق"}


def main() -> None:
    path = next((a for a in sys.argv[1:] if not a.startswith("--")), "events.json")
    llm = None
    if "--ai" in sys.argv:
        from extract import make_llm
        llm = make_llm()
    profile = estimate_profile(ANSWERS, llm)
    print(f"1. Equipment estimated for the farm (AI used: {profile['ai_used']}):")
    for item in profile["equipment"]:
        print(f"   {item['name_ar']:24} x{item['count']}  {item['power_w']:>5} W  {item['flow_lph']:>6} L/h  [{item['source']}]  {item['reason_ar']}")
    for note in profile["notes"]:
        print("   note:", note)
    for q in profile["questions_ar"]:
        print("   question to the farmer:", q)
    farm = profile_to_farm(profile)                      # the farmer confirmed everything (demo)
    if "--save" in sys.argv:                             # store it: the automatic job will include this farm
        from farms_store import save_farm
        save_farm(farm)
        print(f"   saved in farms.json: {farm.name}")
    events = load_events(path)
    registry = PlaceRegistry.seeded()
    for event in events:
        for name in event.place_names.values():
            registry.add(name)
    now = datetime(2026, 9, 1, 8, 0, tzinfo=TUNIS)
    print(f"\n2. Advice for {farm.name}, as of {now:%d/%m/%Y %H:%M}:")
    impacts = farm_impacts(farm, events, registry, now, lang="ar")
    for imp in impacts or []:
        print(f"   [{imp.channel}] {imp.message}")
    if not impacts:
        print("   nothing announced for this place")


if __name__ == "__main__":
    main()
