"""Fixed catalog: what the farmer can choose at sign-up, and which equipment each choice usually implies.

The AI never invents equipment or numbers: it can only pick items from CATALOG, and the typical power / water values
come from here. Everything is a typical estimate that the farmer confirms afterwards.
Arabic is the main language (ar); French (fr) is kept for the team.
"""
from __future__ import annotations

import json

# ----------------------------------------------------------------------------- sign-up choices
SIZES = {"small": {"ar": "قليل", "hint_ar": "عدد صغير"},
         "medium": {"ar": "متوسط", "hint_ar": "عدد متوسط"},
         "large": {"ar": "كثير", "hint_ar": "عدد كبير"}}

# typical head counts per size class (assumption shown to the farmer) and daily water need per animal (litres)
ANIMALS = {
    "cows":    {"ar": "أبقار", "fr": "vaches", "icon": "cow", "counts": {"small": 5, "medium": 20, "large": 80}, "litres_day": 80},
    "sheep":   {"ar": "أغنام", "fr": "moutons", "icon": "sheep", "counts": {"small": 20, "medium": 100, "large": 400}, "litres_day": 8},
    "goats":   {"ar": "ماعز", "fr": "chevres", "icon": "goat", "counts": {"small": 20, "medium": 100, "large": 400}, "litres_day": 8},
    "poultry": {"ar": "دجاج", "fr": "volailles", "icon": "chicken", "counts": {"small": 500, "medium": 3000, "large": 10000}, "litres_day": 0.25},
    "camels":  {"ar": "إبل", "fr": "dromadaires", "icon": "camel", "counts": {"small": 3, "medium": 10, "large": 30}, "litres_day": 40},
    "bees":    {"ar": "نحل", "fr": "abeilles", "icon": "bee", "counts": {"small": 10, "medium": 50, "large": 200}, "litres_day": 0},
}
CROPS = {
    "vegetables": {"ar": "خضروات", "fr": "legumes", "icon": "tomato"},
    "olives": {"ar": "زيتون", "fr": "oliviers", "icon": "olive"},
    "dates": {"ar": "نخيل (تمور)", "fr": "palmiers dattiers", "icon": "palm"},
    "fruit_trees": {"ar": "أشجار مثمرة", "fr": "arbres fruitiers", "icon": "fruit"},
    "cereals": {"ar": "حبوب", "fr": "cereales", "icon": "wheat"},
}
WATER_SOURCES = {"well": {"ar": "بئر", "fr": "puits/forage", "icon": "well"},
                 "sonede": {"ar": "الصوناد", "fr": "SONEDE", "icon": "tap"},
                 "tank": {"ar": "خزان ماء", "fr": "reservoir", "icon": "tank"}}
BACKUP_ENERGY = {"generator": {"ar": "مولّد كهرباء", "fr": "groupe electrogene", "icon": "generator"},
                 "battery": {"ar": "بطارية", "fr": "batterie", "icon": "battery"},
                 "solar": {"ar": "طاقة شمسية", "fr": "solaire", "icon": "sun"},
                 "none": {"ar": "لا شيء", "fr": "rien", "icon": "none"}}
EXTRAS = {"cold_room": {"ar": "غرفة تبريد", "fr": "chambre froide", "icon": "snowflake"},
          "greenhouse": {"ar": "بيوت محمية", "fr": "serres", "icon": "greenhouse"},
          "incubator": {"ar": "حاضنة بيض", "fr": "incubateur", "icon": "egg"}}

# ----------------------------------------------------------------------------- equipment catalog
# role: essential (must keep running) | flexible (can be moved in time) | optional (can be switched off)
# power_w / flow_lph are PER UNIT, typical values. max_count caps what the AI may propose.
CATALOG = {
    "poultry_fans":      {"ar": "مراوح تهوية الدجاج", "uses": "electricity", "role": "essential", "power_w": 300, "max_count": 40},
    "milking_machine":   {"ar": "آلة الحلب", "uses": "electricity", "role": "flexible", "power_w": 1500, "max_count": 4},
    "milk_cooling_tank": {"ar": "خزان تبريد الحليب", "uses": "electricity", "role": "essential", "power_w": 1200, "max_count": 3},
    "cold_room":         {"ar": "غرفة التبريد", "uses": "electricity", "role": "essential", "power_w": 800, "max_count": 3},
    "incubator":         {"ar": "حاضنة البيض", "uses": "electricity", "role": "essential", "power_w": 300, "max_count": 5},
    "greenhouse_fans":   {"ar": "مراوح البيوت المحمية", "uses": "electricity", "role": "essential", "power_w": 250, "max_count": 20},
    "well_pump":         {"ar": "مضخة البئر", "uses": "electricity", "role": "flexible", "power_w": 1500, "max_count": 3},
    "shed_lighting":     {"ar": "إنارة الحظيرة", "uses": "electricity", "role": "optional", "power_w": 150, "max_count": 5},
    "drip_irrigation":   {"ar": "الريّ بالتقطير", "uses": "water", "role": "flexible", "flow_lph": 600, "max_count": 5},
    "animal_drinkers":   {"ar": "مشارب الحيوانات", "uses": "water", "role": "essential", "flow_lph": None, "max_count": 1},
}


def herd_water_lph(animals: dict[str, str]) -> float:
    """Litres per hour the animals drink, from the size class the farmer chose (typical values)."""
    total = sum(ANIMALS[a]["counts"][s] * ANIMALS[a]["litres_day"] for a, s in animals.items() if a in ANIMALS)
    return round(total / 24, 1)


def signup_options() -> dict:
    """The form, as data: the designer turns it into icons / photos. Keys (ids) are stable."""
    def options(table):
        return [{"id": k, "label_ar": v["ar"], "label_fr": v["fr"], "icon": v["icon"]} for k, v in table.items()]
    return {
        "language": "ar", "direction": "rtl",
        "sections": [
            {"id": "animals", "title_ar": "ماذا تربّي؟", "type": "multi_with_size", "options": options(ANIMALS),
             "size_question_ar": "كم العدد تقريبا؟",
             "sizes": [{"id": k, "label_ar": v["ar"], "hint_ar": v["hint_ar"]} for k, v in SIZES.items()]},
            {"id": "crops", "title_ar": "ماذا تزرع؟", "type": "multi", "options": options(CROPS)},
            {"id": "water_source", "title_ar": "من أين تأتيك المياه؟", "type": "multi", "options": options(WATER_SOURCES)},
            {"id": "backup_energy", "title_ar": "هل عندك طاقة احتياطية؟", "type": "multi", "options": options(BACKUP_ENERGY)},
            {"id": "extras", "title_ar": "هل عندك أيضا؟", "type": "multi", "options": options(EXTRAS)},
            {"id": "locality", "title_ar": "أين توجد مزرعتك؟", "type": "place_search"},
        ],
        "answer_shape": {"animals": {"cows": "medium"}, "crops": ["vegetables"], "water_source": ["well"],
                         "backup_energy": ["generator"], "extras": ["cold_room"], "locality": "المروج"},
    }


class ChoiceError(ValueError):
    pass


def validate_choices(choices: dict) -> dict:
    """Checks the form answer: only known ids, known sizes. Returns a clean copy."""
    clean = {"animals": {}, "crops": [], "water_source": [], "backup_energy": [], "extras": [],
             "locality": str(choices.get("locality", "")).strip()}
    if not clean["locality"]:
        raise ChoiceError("locality is required")
    for animal, size in (choices.get("animals") or {}).items():
        if animal not in ANIMALS or size not in SIZES:
            raise ChoiceError(f"unknown animal or size: {animal}/{size}")
        clean["animals"][animal] = size
    for key, table in (("crops", CROPS), ("water_source", WATER_SOURCES), ("backup_energy", BACKUP_ENERGY),
                       ("extras", EXTRAS)):
        for item in choices.get(key) or []:
            if item not in table:
                raise ChoiceError(f"unknown choice in {key}: {item}")
            if item not in clean[key]:
                clean[key].append(item)
    return clean


if __name__ == "__main__":
    with open("signup_options.json", "w", encoding="utf-8") as f:
        json.dump(signup_options(), f, ensure_ascii=False, indent=1)
    print("signup_options.json written")
