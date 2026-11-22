"""Tests of the agent graph. Run: python test_graph.py   (prints one OK line per test)"""
from datetime import datetime

import graph
from events import Event
from farm import DEMO_FARMS, Equipment, Farm, _plan


def event(utility="electricity"):
    return Event(id=1, utility=utility, event_type="rotating_shedding" if utility == "electricity" else "water_regulation",
                 window_start=datetime(2026, 9, 1, 13), window_end=datetime(2026, 9, 1, 18), recurrence=None,
                 is_intermittent=True, window_may_extend=False, list_is_exhaustive=False, max_single_cut_hours=None,
                 expected_restoration=None, restoration_without_notice=True, reason=None, place_keys=["mornag"])


def poultry_farm(battery_kwh=2.0, battery_pct=90, tank_litres=5000):
    return Farm("poultry", "مرناق", smart=True, id="t1", tank_litres=tank_litres, tank_level_pct=100,
                battery_kwh=battery_kwh, battery_pct=battery_pct, equipment=[
                    Equipment("مراوح تهوية الدجاج", "essential", power_w=1800),
                    Equipment("غرفة التبريد", "essential", power_w=800),
                    Equipment("مضخة البئر", "flexible", power_w=1500),
                    Equipment("إنارة الحظيرة", "optional", power_w=150),
                    Equipment("مشارب الحيوانات", "essential", uses="water", flow_lph=40),
                ])


def actions(plan):
    return {r["equipment"]: r["action"] for r in plan}


def test_same_plan_as_the_rules_when_nobody_disagrees():
    farm = DEMO_FARMS[0]
    plan, trace = graph.run_graph(farm, event(), 2.0)
    assert actions(plan) == actions(_plan(farm, event(), 2.0)), (actions(plan), trace)
    assert any("rules check: pass" in t for t in trace)


def test_water_for_animals_beats_saving_the_battery():
    plan, trace = graph.run_graph(poultry_farm(), event(), 2.0)       # battery 0.6 h < 2 h cut
    assert actions(plan)["مضخة البئر"] == "Before"                    # energy said Off, water said Before
    row = next(r for r in plan if r["equipment"] == "مضخة البئر")
    assert "الأولوية" in row["decision_ar"] and "الأولوية" not in row["why_ar"]


def test_battery_budget_keeps_what_fits_by_priority():
    # 4 kWh: fans (1800 W x 2 h = 3600 Wh) do not fit in 3200 Wh, the cold room (1600 Wh) does
    plan, _ = graph.run_graph(poultry_farm(battery_kwh=4.0, battery_pct=100), event(), 2.0)
    a = actions(plan)
    assert a["غرفة التبريد"] == "Keep" and a["مراوح تهوية الدجاج"] == "Before" and a["إنارة الحظيرة"] == "Off"


def test_short_tank_keeps_water_for_animals_not_irrigation():
    farm = Farm("w", "مرناق", smart=True, id="t2", tank_litres=1000, tank_level_pct=100, equipment=[
        Equipment("الريّ بالتقطير", "flexible", uses="water", flow_lph=600),
        Equipment("مشارب الحيوانات", "essential", uses="water", flow_lph=400)])
    plan, _ = graph.run_graph(farm, event("water"), 3.0)               # tank lasts 1 h, cut is 3 h
    assert actions(plan)["الريّ بالتقطير"] == "Off"
    assert actions(plan)["مشارب الحيوانات"] == "Before"


def test_a_bad_agent_is_caught_and_retried_once():
    original = graph.AGENT_FUNCS["energy"]
    graph.AGENT_FUNCS["energy"] = lambda farm, u, cut, r: [
        graph._prop(i, "Off", "bad", "سيئ", 2, "energy") for i in farm.equipment if i.name == "غرفة التبريد"]
    try:
        plan, trace = graph.run_graph(DEMO_FARMS[0], event(), 2.0)
    finally:
        graph.AGENT_FUNCS["energy"] = original
    assert actions(plan)["غرفة التبريد"] != "Off"
    assert any("FAIL" in t and "one retry" in t for t in trace) and any("rules check: pass" in t for t in trace)


def test_short_reserve_without_power_figures_still_means_prepare_before():
    farm = Farm("h", "مرناق", smart=True, id="t3", battery_hours=1.0, equipment=[Equipment("غرفة التبريد", "essential")])
    plan, _ = graph.run_graph(farm, event(), 2.0)                       # battery known only in hours, 1 h < 2 h
    assert plan[0]["action"] == "Before" and actions(plan) == actions(_plan(farm, event(), 2.0))


def test_generator_replaces_prepare_before_for_essential_equipment():
    farm = poultry_farm()
    farm.backup = ["generator"]
    plan, _ = graph.run_graph(farm, event(), 2.0)                       # battery 0.6 h < 2 h cut
    a = actions(plan)
    assert a["مراوح تهوية الدجاج"] == "Generator" and a["غرفة التبريد"] == "Generator"
    assert a["مضخة البئر"] == "Before" and a["إنارة الحظيرة"] == "Off"


def test_generator_is_not_used_when_the_battery_is_enough():
    farm = poultry_farm(battery_kwh=10.0, battery_pct=100)
    farm.backup = ["generator"]
    plan, _ = graph.run_graph(farm, event(), 2.0)
    assert actions(plan)["غرفة التبريد"] == "Keep" and "Generator" not in actions(plan).values()


def test_a_farm_without_sensors_gets_no_plan():
    plan, trace = graph.run_graph(DEMO_FARMS[1], event(), 2.0)
    assert plan == [] and "no sensors" in trace[0]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(name, "OK")