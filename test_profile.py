import json

from catalog import ChoiceError, signup_options, validate_choices, CATALOG, ANIMALS, CROPS
from profile_estimator import baseline_equipment, estimate_profile, profile_to_farm

CHOICES = {"animals": {"poultry": "large", "cows": "medium"}, "crops": ["vegetables"], "water_source": ["well"],
           "backup_energy": ["generator"], "extras": ["cold_room"], "locality": "المروج"}


class FakeLLM:
    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def ask(self, messages, system=None):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        assert system and "CATALOG" in system.upper()          # uses its own prompt, not the extraction one
        return self.reply


def test_rules_give_the_expected_equipment():
    items = {i["catalog_id"]: i for i in baseline_equipment(CHOICES)}
    assert {"poultry_fans", "milking_machine", "milk_cooling_tank", "shed_lighting", "animal_drinkers",
            "drip_irrigation", "well_pump", "cold_room"} <= set(items)
    assert items["poultry_fans"]["count"] == 12 and items["poultry_fans"]["power_w"] == 3600
    assert items["animal_drinkers"]["flow_lph"] == round((20 * 80 + 10000 * 0.25) / 24, 1)   # 20 cows + 10 000 hens
    assert all(i["confirm"] and i["source"] == "rules" for i in items.values())


def test_form_answers_are_validated():
    for bad in ({"animals": {"dragons": "small"}, "locality": "x"}, {"animals": {"cows": "huge"}, "locality": "x"},
                {"crops": ["gold"], "locality": "x"}, {"crops": ["olives"]}):
        try:
            validate_choices(bad)
            raise AssertionError(bad)
        except ChoiceError:
            pass


def test_signup_options_match_the_catalog_and_are_arabic():
    form = signup_options()
    assert form["language"] == "ar" and form["direction"] == "rtl"
    ids = {s["id"]: {o["id"] for o in s.get("options", [])} for s in form["sections"]}
    assert ids["animals"] == set(ANIMALS) and ids["crops"] == set(CROPS)
    assert all(any("؀" <= ch <= "ۿ" for ch in o["label_ar"]) for s in form["sections"] for o in s.get("options", []))
    validate_choices(form["answer_shape"])                      # the documented example is itself valid


def test_ai_can_adjust_count_add_items_and_explain_but_not_invent():
    reply = json.dumps({"items": [
        {"catalog_id": "poultry_fans", "count": 100, "reason_ar": "مدجنة كبيرة"},     # too many -> capped
        {"catalog_id": "incubator", "count": 1, "reason_ar": "ربما عندك حاضنة"},      # allowed catalog item, added
        {"catalog_id": "laser_cannon", "count": 1, "reason_ar": "x"},                  # unknown -> ignored
        {"catalog_id": "animal_drinkers", "count": 5, "reason_ar": "x"}],              # water flow stays from rules
        "questions_ar": ["هل عندك غرفة تبريد؟", "q2", "q3"]}, ensure_ascii=False)
    profile = estimate_profile(CHOICES, FakeLLM(reply))
    items = {i["catalog_id"]: i for i in profile["equipment"]}
    assert profile["ai_used"] and items["poultry_fans"]["count"] == CATALOG["poultry_fans"]["max_count"]
    assert items["poultry_fans"]["source"] == "ai" and items["incubator"]["source"] == "ai"
    assert "laser_cannon" not in items and items["animal_drinkers"]["source"] == "rules"
    assert len(profile["questions_ar"]) == 2 and any("laser_cannon" in n for n in profile["notes"])


def test_signup_still_works_when_the_ai_fails_or_answers_badly():
    for llm in (FakeLLM(RuntimeError("503")), FakeLLM("not json at all"), FakeLLM('{"items":[{"catalog_id":"cold_room","count":0}]}')):
        profile = estimate_profile(CHOICES, llm)
        assert not profile["ai_used"] and profile["notes"]
        assert {i["catalog_id"] for i in profile["equipment"]} == {i["catalog_id"] for i in baseline_equipment(CHOICES)}
    assert estimate_profile(CHOICES)["ai_used"] is False        # no AI client at all


def test_profile_becomes_a_farm_without_sensors():
    profile = estimate_profile(CHOICES)
    farm = profile_to_farm(profile, confirmed_ids=["cold_room", "poultry_fans"])
    assert not farm.smart and farm.locality == "المروج" and {e.name for e in farm.equipment} == {"غرفة التبريد", "مراوح تهوية الدجاج"}
    assert farm.water_autonomy() is None                        # unknown -> general advice only


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(name, "OK")
