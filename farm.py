"""Blocks 7 and 7b: events -> what it means for ONE farm (risk, equipment plan, alert message).

Rules are plain code on purpose ("code decides"): the same inputs always give the same plan.

Run the demo on the events found by run_pipeline.py:
  python farm.py events.json --now 2026-09-01T08:00
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from events import Event, status_at
from geocode import PlaceRegistry, normalize

TUNIS = timezone(timedelta(hours=1))

# How the equipment can react to a cut (the farmer fills this once).
#   essential : must keep working (cold room, incubator...)    -> Keep, powered by the battery
#   flexible  : can be moved in time (pump, irrigation...)     -> Before / After
#   optional  : can simply be switched off (lighting, shed...) -> Off
ROLES = ("essential", "flexible", "optional")


@dataclass
class Equipment:
    name: str
    role: str                    # essential | flexible | optional
    uses: str = "electricity"    # electricity | water
    power_w: float = 0           # label value, used to estimate battery autonomy
    flow_lph: float = 0          # litres per hour, used to estimate tank autonomy
    catalog_id: str = ""         # id in catalog.py (lets the agents know what the item is); empty = guessed from the name


@dataclass
class Farm:
    name: str
    locality: str                # name as the farmer writes it (French or Arabic)
    id: str = ""                 # stable id given at sign-up (the app uses it to ask for its own screen data)
    smart: bool = False          # True only if the farm has sensors (tank level, battery level)
    tank_litres: float = 0.0
    tank_level_pct: Optional[float] = None     # last sensor reading, 0-100
    battery_kwh: float = 0.0
    battery_pct: Optional[float] = None        # last sensor reading, 0-100
    tank_hours: float = 0.0      # optional: autonomy already known, used if there is no level reading
    battery_hours: float = 0.0
    equipment: list[Equipment] = field(default_factory=list)
    farm_id: str = ""            # alias of id (kept so old farms.json files still load)
    crops: list[str] = field(default_factory=list)   # crops chosen at sign-up (used by the Crop agent)
    backup: list[str] = field(default_factory=list)  # backup energy chosen at sign-up: generator | battery | solar

    def __post_init__(self):
        self.id = self.id or self.farm_id          # one identity, two names
        self.farm_id = self.farm_id or self.id

    def water_autonomy(self) -> Optional[float]:
        """Hours the tank lasts. None when we cannot know (no sensor): then only general advice is sent."""
        if not self.smart:
            return None
        flow = sum(e.flow_lph for e in self.equipment if e.uses == "water")
        if self.tank_level_pct is not None and self.tank_litres and flow:
            return round(self.tank_litres * self.tank_level_pct / 100 / flow, 1)
        return self.tank_hours or None

    def power_autonomy(self) -> Optional[float]:
        """Hours the battery runs the essential equipment (80 % of the charge is usable)."""
        if not self.smart:
            return None
        load = sum(e.power_w for e in self.equipment if e.uses == "electricity" and e.role == "essential")
        if self.battery_pct is not None and self.battery_kwh and load:
            return round(self.battery_kwh * 1000 * 0.8 * self.battery_pct / 100 / load, 1)
        return self.battery_hours or None


@dataclass
class Impact:
    event: Event
    match: str                   # "listed" (name is in the notice) | "possible" (not listed, notice incomplete)
    probability: float
    cut_hours: float
    covered: bool                # tank/battery lasts longer than the cut
    level: str                   # low | medium | high
    plan: list[dict]
    message: str
    mode: str = "smart_plan"     # smart_plan (levels known) | general_sms (no sensor data)
    channel: str = "app"         # app (dashboard / push) | sms
    notify: bool = True
    trace: list = field(default_factory=list)   # what the agents did (not exported to farmer_view.json)


ASSUMED_ROTATING_CUT_HOURS = 2.0   # used only when a rotating-cut notice gives no maximum (shown as an estimate)


def _is_estimated(event: Event) -> bool:
    return event.event_type == "rotating_shedding" and not event.max_single_cut_hours


def _hours(event: Event) -> float:
    """Longest time without service the farm should plan for."""
    if event.max_single_cut_hours:
        return event.max_single_cut_hours
    if _is_estimated(event):          # 13h-18h is a wide slot, NOT one continuous cut
        return ASSUMED_ROTATING_CUT_HOURS
    if event.window_start and event.window_end:
        return round((event.window_end - event.window_start).total_seconds() / 3600, 1)
    if event.window_start and event.expected_restoration:
        return round((event.expected_restoration - event.window_start).total_seconds() / 3600, 1)
    return 4.0                   # unknown: assume a short cut rather than ignore it


def _probability(event: Event, match: str) -> float:
    """Chance that this farm is really without service during the window (simple and explainable)."""
    if match == "possible":
        base = 0.25               # notices say "liste non definitive": the farm may be hit anyway
    elif event.event_type == "rotating_shedding":
        base = 0.6                # listed, but the cut is rotating: not every listed place at every hour
    else:
        base = 0.9                # works / regulation: the place is cut for the whole announced window
    return round(base * (0.5 + 0.5 * event.confidence), 2)


def _plan(farm: Farm, event: Event, cut_hours: float) -> list[dict]:
    """Equipment prioritizer (7b): Keep / Before / After / Off for each piece of equipment."""
    plan = []
    water_cut = event.utility == "water"
    reserve = (farm.water_autonomy() if water_cut else farm.power_autonomy()) or 0
    for item in farm.equipment:
        affected = item.uses == event.utility
        if not affected:
            plan.append({"equipment": item.name, "action": "Keep", "why": "not affected by this cut"})
        elif item.role == "essential":
            if reserve >= cut_hours:
                why = f"reserve {reserve:g} h covers the {cut_hours:g} h cut"
                plan.append({"equipment": item.name, "action": "Keep", "why": why})
            else:
                why = f"reserve {reserve:g} h is shorter than the {cut_hours:g} h cut: prepare before"
                plan.append({"equipment": item.name, "action": "Before", "why": why})
        elif item.role == "flexible":
            plan.append({"equipment": item.name, "action": "Before",
                         "why": "run it before the window, restart after"})
        else:
            plan.append({"equipment": item.name, "action": "Off", "why": "not needed during the cut"})
    from texts_ar import plan_reason

    for row, item in zip(plan, farm.equipment):         # same order: add the flag and the Arabic reason
        row["affected"] = item.uses == event.utility
        row["why_ar"] = plan_reason(item.role, row["affected"], reserve, cut_hours)
    return plan


def _agent_plan(farm: Farm, event: Event, cut_hours: float):
    """The agent graph proposes and reconciles; if anything goes wrong the plain rule plan is used (the demo never breaks)."""
    try:
        from graph import run_graph
        return run_graph(farm, event, cut_hours)
    except Exception as error:  # noqa: BLE001 - langgraph missing or a bug: fall back to the rules
        return _plan(farm, event, cut_hours), [f"fallback to rules: {type(error).__name__}"]


def _message(farm: Farm, event: Event, impact_level: str, cut_hours: float, covered: bool, plan: list[dict],
             match: str, lang: str = "fr") -> str:
    if lang == "ar":
        from texts_ar import app_message
        return app_message(farm, event, impact_level, cut_hours, covered, plan, match, _is_estimated(event))
    kind = "Coupure d'eau" if event.utility == "water" else "Coupure d'electricite"
    start = f"{event.window_start:%d/%m a %Hh%M}" if event.window_start else "date non precisee"
    end = f" jusqu'a {event.window_end:%Hh%M}" if event.window_end else ""
    if event.event_type == "rotating_shedding":
        kind += " tournante"
    estimate = " (estimation)" if _is_estimated(event) else ""
    lines = [f"{kind} annoncee le {start}{end} ({farm.locality}). "
             f"Duree a prevoir : {cut_hours:g} h{estimate}. Risque : {impact_level}."]
    if match == "possible":
        lines.append("Votre localite n'est pas citee, mais la liste de l'avis n'est pas complete.")
    if event.event_type == "rotating_shedding":
        lines.append("Ce creneau n'est pas une coupure continue : coupures par intermittence, retablissement sans preavis.")
    steps = {"Generator": [], "Before": [], "Off": [], "Keep": []}
    for row in plan:
        if row["action"] in steps and "not affected" not in row["why"]:
            steps[row["action"]].append(row["equipment"])
    if event.utility == "water" and not covered:
        lines.append(f"Remplissez le reservoir avant (autonomie {farm.water_autonomy():g} h < coupure).")
    if event.utility == "electricity" and not covered:
        lines.append(f"Chargez la batterie avant (autonomie {farm.power_autonomy():g} h < coupure).")
    if steps["Generator"]:
        lines.append("Demarrer le groupe electrogene pour : " + ", ".join(steps["Generator"]) + ".")
    if steps["Before"]:
        lines.append("Avant : " + ", ".join(steps["Before"]) + ".")
    if steps["Keep"]:
        lines.append("Garder : " + ", ".join(steps["Keep"]) + ".")
    if steps["Off"]:
        lines.append("Eteindre : " + ", ".join(steps["Off"]) + ".")
    return " ".join(lines)


def general_sms(farm: Farm, event: Event, match: str, lang: str = "fr") -> str:
    """Used when the tank / battery level is unknown: general advice only, no numbers we cannot know.
    French uses plain letters (no accents) to stay in one 160-character SMS."""
    if lang == "ar":
        from texts_ar import general_sms as arabic_sms
        return arabic_sms(farm, event, match)
    start = f"{event.window_start:%d/%m %Hh}" if event.window_start else "bientot"
    end = f"-{event.window_end:%Hh}" if event.window_end else ""
    where = farm.locality + (" (possible)" if match == "possible" else "")
    if event.utility == "water":
        return (f"SONEDE: coupure d'eau {start}{end} a {where}. "
                "Remplissez reservoirs et bidons, arrosez avant, gardez de l'eau pour le betail.")
    kind = " tournante" if event.event_type == "rotating_shedding" else ""
    return (f"STEG: coupure{kind} {start}{end} a {where}. "
            "Chargez batteries, evitez d'ouvrir la chambre froide, eteignez le non-essentiel.")


def _level(probability: float, covered: bool, cut_hours: float) -> str:
    if probability < 0.3:
        return "low"
    if covered:
        return "low" if probability < 0.6 else "medium"
    return "high" if probability >= 0.5 and cut_hours >= 2 else "medium"


def farm_impacts(farm: Farm, events: list[Event], registry: PlaceRegistry, now: datetime,
                 lang: str = "fr") -> list[Impact]:
    """Every announced or active event that can touch this farm, most urgent first."""
    key = registry.lookup(farm.locality)
    region_keys = _same_area_keys(registry, key)
    results = []
    for event in events:
        if status_at(event, now) == "expired":
            continue
        if key and key in event.place_keys:
            match = "listed"
        elif region_keys & set(event.place_keys) and not event.list_is_exhaustive:
            match = "possible"
        else:
            continue
        cut = _hours(event)
        probability = _probability(event, match)
        reserve = farm.water_autonomy() if event.utility == "water" else farm.power_autonomy()
        if reserve is None:                          # no sensor data: do not guess, send general advice by SMS
            level = "medium" if probability >= 0.3 else "low"
            results.append(Impact(event, match, probability, cut, False, level, [],
                                  general_sms(farm, event, match, lang), mode="general_sms", channel="sms",
                                  notify=probability >= 0.3))
            continue
        covered = reserve >= cut
        plan, trace = _agent_plan(farm, event, cut)
        level = _level(probability, covered, cut)
        message = _message(farm, event, level, cut, covered, plan, match, lang)
        results.append(Impact(event, match, probability, cut, covered, level, plan, message, trace=trace))
    results.sort(key=lambda i: (i.event.window_start or now))
    return results


def _same_area_keys(registry: PlaceRegistry, key: Optional[str]) -> set[str]:
    """Places that share a region with the farm place, in the notices we know (used for 'possible')."""
    if key is None:
        return set()
    regions = set(registry.places[key].get("regions") or [])
    if not regions:
        return set()
    return {k for k, p in registry.places.items() if k != key and regions & set(p.get("regions") or [])}


def mentions_a_farm(text: str, farms: list[Farm]) -> bool:
    """Cheap check before calling the AI: does the article even contain a farm locality?"""
    haystack = normalize(text)
    return any(normalize(f.locality) in haystack for f in farms)


def load_events(path: str) -> list[Event]:
    rows = json.load(open(path, encoding="utf-8"))
    events = []
    for row in rows:
        row.pop("status", None)
        for name in ("window_start", "window_end", "expected_restoration"):
            row[name] = datetime.fromisoformat(row[name]) if row.get(name) else None
        events.append(Event(**row))
    return events


DEMO_FARMS = [
    # smart farm: sensors give the tank and battery levels -> full plan
    Farm("مزرعة مرناق (بها حساسات)", "مرناق", smart=True, id="demo-mornag",
         tank_litres=5000, tank_level_pct=70, battery_kwh=2, battery_pct=90, equipment=[
             Equipment("غرفة التبريد", "essential", power_w=400),
             Equipment("مضخة البئر", "flexible", power_w=1500),
             Equipment("الريّ بالتقطير", "flexible", uses="water", flow_lph=400),
             Equipment("إنارة الحظيرة", "optional", power_w=100),
         ]),
    # farm without sensors: general advice by SMS
    Farm("مزرعة سوسة (بدون حساسات)", "سوسة", id="demo-sousse", equipment=[
        Equipment("الريّ بالتقطير", "flexible", uses="water"),
        Equipment("غرفة التبريد", "essential"),
    ]),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("events", nargs="?", default="events.json")
    parser.add_argument("--lang", default="ar", choices=["ar", "fr"], help="language of the alerts (default: ar)")
    parser.add_argument("--no-view", action="store_true", help="do not write farmer_view.json")
    parser.add_argument("--now", help="pretend it is this moment, e.g. 2026-09-01T08:00 (Tunis time)")
    args = parser.parse_args()

    now = datetime.fromisoformat(args.now).replace(tzinfo=TUNIS) if args.now else datetime.now(TUNIS)
    events = load_events(args.events)
    registry = PlaceRegistry.seeded()
    for event in events:                                  # make the registry know the places of the notices
        for k, name in event.place_names.items():
            registry.add(name)
    from farms_store import load_farms

    farms = load_farms()                       # registered farms (farms.json), or the demo farms
    for farm in farms:
        print(f"\n=== {farm.name} ({farm.locality}) ===")
        impacts = farm_impacts(farm, events, registry, now, args.lang)
        if not impacts:
            print("No announced or active cut concerns this farm.")
        for imp in impacts:
            e = imp.event
            print(f"\n#{e.id} {e.utility} {e.event_type} | {imp.match} | probability {imp.probability} "
                  f"| risk {imp.level.upper()} | {imp.mode} -> {imp.channel}")
            for row in imp.plan:
                print(f"   {row['action']:6} {row['equipment']:28} {row['why']}")
            print(f"   {imp.channel.upper()}: {imp.message}  [{len(imp.message)} characters]")


    if not args.no_view:                       # same run also makes the data for the farmer screen
        from export_farmer_view import write_view

        write_view(args.events, "farmer_view.json", args.lang, farms_list=farms, live_now=now)
        print(f"\nfarmer_view.json written ({len(farms)} farms, as of {now:%d/%m/%Y %H:%M})")


if __name__ == "__main__":
    main()