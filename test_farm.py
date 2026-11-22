from datetime import datetime, timedelta, timezone

from events import Event
from farm import Equipment, Farm, farm_impacts, mentions_a_farm
from geocode import PlaceRegistry

TZ = timezone(timedelta(hours=1))
NOW = datetime(2026, 9, 1, 8, 0, tzinfo=TZ)


def make_event(**kw):
    base = dict(id=1, utility="electricity", event_type="rotating_shedding",
                window_start=datetime(2026, 9, 1, 13, tzinfo=TZ), window_end=datetime(2026, 9, 1, 18, tzinfo=TZ),
                recurrence=None, is_intermittent=True, window_may_extend=False, list_is_exhaustive=False,
                max_single_cut_hours=None, expected_restoration=None, restoration_without_notice=True,
                reason=None, place_keys=["mornag"], place_names={"mornag": "Mornag"}, sources=["u"], confidence=0.9)
    base.update(kw)
    return Event(**base)


def setup():
    registry = PlaceRegistry.seeded()
    registry.add("Mornag")
    farm = Farm("F", "Mornag", smart=True, tank_hours=6, battery_hours=3, equipment=[
        Equipment("Chambre froide", "essential"), Equipment("Pompe", "flexible"),
        Equipment("Lumiere", "optional"), Equipment("Goutte-a-goutte", "flexible", uses="water")])
    return registry, farm


def test_rotating_slot_is_not_a_continuous_cut():
    registry, farm = setup()
    imp = farm_impacts(farm, [make_event()], registry, NOW)[0]
    assert imp.cut_hours == 2.0 and "estimation" in imp.message and imp.covered      # 13h-18h is NOT 5 h
    actions = {r["equipment"]: r["action"] for r in imp.plan}
    assert actions == {"Chambre froide": "Keep", "Pompe": "Before", "Lumiere": "Off", "Goutte-a-goutte": "Keep"}


def test_battery_too_short_asks_to_prepare():
    registry, farm = setup()
    farm.battery_hours = 1
    imp = farm_impacts(farm, [make_event(max_single_cut_hours=3)], registry, NOW)[0]
    assert not imp.covered and imp.plan[0]["action"] == "Before" and "batterie" in imp.message


def test_water_cut_uses_the_tank():
    registry, farm = setup()
    event = make_event(utility="water", event_type="water_works", is_intermittent=False,
                       window_end=datetime(2026, 9, 1, 21, tzinfo=TZ))            # 8 h, tank = 6 h
    imp = farm_impacts(farm, [event], registry, NOW)[0]
    assert imp.cut_hours == 8 and not imp.covered and "reservoir" in imp.message
    assert {r["equipment"]: r["action"] for r in imp.plan}["Goutte-a-goutte"] == "Before"


def test_other_place_expired_and_unlisted_events_are_ignored():
    registry, farm = setup()
    other = make_event(place_keys=["sousse"])
    old = make_event(window_start=NOW - timedelta(days=3), window_end=NOW - timedelta(days=3, hours=-2))
    assert farm_impacts(farm, [other, old], registry, NOW) == []


def test_arabic_name_of_the_farm_place_is_found():
    registry, farm = setup()
    farm.locality = "مرناق"
    registry.add("Mornag", aliases=["مرناق"])
    assert len(farm_impacts(farm, [make_event()], registry, NOW)) == 1


def test_prefilter_before_calling_the_ai():
    registry, farm = setup()
    assert mentions_a_farm("Coupure a Mornag demain", [farm])
    assert not mentions_a_farm("Coupure a Sfax demain", [farm])


def test_farm_without_sensors_gets_a_general_sms():
    registry, _ = setup()
    farm = Farm("F", "Mornag", equipment=[Equipment("Chambre froide", "essential")])      # smart=False
    imp = farm_impacts(farm, [make_event()], registry, NOW)[0]
    assert imp.mode == "general_sms" and imp.channel == "sms" and imp.plan == []
    assert len(imp.message) <= 160 and "STEG" in imp.message and "Mornag" in imp.message
    water = make_event(utility="water", event_type="water_works", is_intermittent=False)
    sms = farm_impacts(farm, [water], registry, NOW)[0].message
    assert len(sms) <= 160 and "SONEDE" in sms


def test_sensor_levels_give_the_autonomy():
    farm = Farm("F", "Mornag", smart=True, tank_litres=5000, tank_level_pct=70, battery_kwh=2, battery_pct=90,
                equipment=[Equipment("Froid", "essential", power_w=400),
                           Equipment("Goutte", "flexible", uses="water", flow_lph=400)])
    assert farm.water_autonomy() == 8.8            # 5000 x 0.70 / 400
    assert farm.power_autonomy() == 3.6            # 2000 Wh x 0.8 x 0.9 / 400 W
    registry, _ = setup()
    imp = farm_impacts(farm, [make_event()], registry, NOW)[0]
    assert imp.mode == "smart_plan" and imp.channel == "app" and imp.covered


def test_sensor_offline_falls_back_to_sms():
    registry, _ = setup()
    farm = Farm("F", "Mornag", smart=True, tank_litres=5000, tank_level_pct=None, battery_kwh=2, battery_pct=None,
                equipment=[Equipment("Froid", "essential", power_w=400)])
    assert farm_impacts(farm, [make_event()], registry, NOW)[0].mode == "general_sms"


def test_arabic_texts_for_both_modes():
    from texts_ar import sms_parts
    registry, farm = setup()
    imp = farm_impacts(farm, [make_event()], registry, NOW, lang="ar")[0]
    assert "انقطاع الكهرباء المتناوب" in imp.message and "تقدير" in imp.message and "Coupure" not in imp.message
    assert all(r["why_ar"] for r in imp.plan)
    plain = Farm("F", "Mornag", equipment=[Equipment("غرفة التبريد", "essential")])
    sms = farm_impacts(plain, [make_event()], registry, NOW, lang="ar")[0].message
    assert sms.startswith("الستاغ") and "قد يعود التيار دون إنذار" in sms and sms.endswith("التفاصيل في التطبيق.")
    assert sms_parts(sms) <= 4                                         # Arabic SMS: 70 chars, then 67 per part
    water = make_event(utility="water", event_type="water_works", is_intermittent=False)
    assert farm_impacts(plain, [water], registry, NOW, lang="ar")[0].message.startswith("الصوناد")
    import os
    os.environ["DETAILS_URL"] = "https://example.org/x"                 # a configured link replaces the app mention
    try:
        assert "https://example.org/x" in farm_impacts(plain, [water], registry, NOW, lang="ar")[0].message
    finally:
        del os.environ["DETAILS_URL"]


def test_farmer_view_export_is_arabic_and_complete():
    import json, os, tempfile
    from export_farmer_view import build
    events = os.path.join(os.path.dirname(os.path.abspath(__file__)), "events.json")
    data = build(events, "ar")
    assert data["language"] == "ar" and data["direction"] == "rtl"
    alerts = [a for m in data["moments"] for f in m["farms"] for a in f["alerts"]]
    assert alerts and all(a["why"] and a["sources"] and a["headline"] for a in alerts)
    assert all(any("\u0600" <= ch <= "\u06ff" for ch in a["headline"]) for a in alerts)
    assert all(w["detail"] for a in alerts for w in a["why"])
    json.dumps(data, ensure_ascii=False)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(name, "OK")
