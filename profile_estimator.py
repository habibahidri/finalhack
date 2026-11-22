"""Sign-up answer -> estimated equipment list -> Farm.

  rules (always work, no API)  ->  baseline equipment
  AI (optional)                ->  may adjust counts, add catalog items, and write a short reason in Arabic
  code                         ->  validates: only catalog items, counts capped, numbers come from the catalog
  farmer                       ->  confirms or edits the list (every item has confirm=True until then)

The AI cannot invent equipment or wattage: if it fails or answers badly, the rules result is used.
"""
from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from catalog import ANIMALS, CATALOG, herd_water_lph, validate_choices
from farm import Equipment, Farm

AI_SYSTEM_PROMPT = """You help a Tunisian farmer register. You receive what the farmer chose (animals with a size,
crops, water source, backup energy, extras) and a first equipment list made by rules.
Your job: decide which equipment from the CATALOG this farm probably has, and how many of each.
Rules:
- Use only the catalog ids given. Never invent equipment, never give wattage or flow numbers.
- You may change counts and add catalog items that are likely; you may not remove an item only because you are unsure.
- reason_ar: one short sentence in simple Modern Standard Arabic saying why this farm probably has it.
- questions_ar: at most 2 short questions in Arabic to ask the farmer if something important is unclear.
Answer with JSON only: {"items":[{"catalog_id":"...","count":1,"reason_ar":"..."}],"questions_ar":["..."]}
"""

SIZE_FAN_COUNT = {"small": 2, "medium": 6, "large": 12}


class AiItem(BaseModel):
    catalog_id: str
    count: int = Field(ge=1)
    reason_ar: str = ""


class AiAnswer(BaseModel):
    items: list[AiItem] = []
    questions_ar: list[str] = []


def _item(catalog_id: str, count: int, reason_ar: str, source: str, flow_lph: Optional[float] = None) -> dict:
    spec = CATALOG[catalog_id]
    flow = flow_lph if flow_lph is not None else (spec.get("flow_lph") or 0) * count
    return {
        "catalog_id": catalog_id, "name_ar": spec["ar"], "count": count, "uses": spec["uses"], "role": spec["role"],
        "power_w": spec.get("power_w", 0) * count, "flow_lph": round(flow, 1),
        "reason_ar": reason_ar, "source": source, "confirm": True,
    }


def baseline_equipment(choices: dict) -> list[dict]:
    """Deterministic rules: the same sign-up always gives the same list."""
    c = validate_choices(choices)
    items: dict[str, dict] = {}

    def add(cid, count, reason):
        if cid not in items:
            items[cid] = _item(cid, count, reason, "rules")

    animals = c["animals"]
    if "poultry" in animals:
        add("poultry_fans", SIZE_FAN_COUNT[animals["poultry"]], "لأنك تربّي الدجاج والحرارة تضرّه")
    if "cows" in animals and animals["cows"] != "small":
        add("milking_machine", 1, "لأنك تربّي الأبقار")
        add("milk_cooling_tank", 1, "لحفظ الحليب باردا")
    if any(a in animals and a != "bees" for a in animals):
        add("shed_lighting", 1, "لإنارة الحظيرة")
    drinking = {a: s for a, s in animals.items() if ANIMALS[a]["litres_day"] > 0}
    if drinking:
        items["animal_drinkers"] = _item("animal_drinkers", 1, "الحيوانات تحتاج الماء باستمرار", "rules",
                                         flow_lph=herd_water_lph(drinking))
    if any(crop in c["crops"] for crop in ("vegetables", "olives", "dates", "fruit_trees")) or "greenhouse" in c["extras"]:
        add("drip_irrigation", 1, "لسقي المزروعات")
    if "greenhouse" in c["extras"]:
        add("greenhouse_fans", 2, "لتهوية البيوت المحمية")
    if "well" in c["water_source"]:
        add("well_pump", 1, "لأن مياهك من بئر")
    if "cold_room" in c["extras"]:
        add("cold_room", 1, "اخترت غرفة تبريد")
    if "incubator" in c["extras"]:
        add("incubator", 1, "اخترت حاضنة بيض")
    return list(items.values())


def _validate_ai(raw: str) -> AiAnswer:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON in the reply")
    return AiAnswer.model_validate(json.loads(raw[start:end + 1]))


def estimate_profile(choices: dict, llm=None) -> dict:
    """Returns {'equipment': [...], 'questions_ar': [...], 'ai_used': bool, 'notes': [...]}."""
    clean = validate_choices(choices)
    equipment = {i["catalog_id"]: i for i in baseline_equipment(clean)}
    result = {"locality": clean["locality"], "choices": clean, "ai_used": False, "questions_ar": [], "notes": []}
    if llm is not None:
        try:
            from extract import _ask

            prompt = json.dumps({"CATALOG": {k: v["ar"] for k, v in CATALOG.items()}, "farmer_choices": clean,
                                 "rules_list": [{"catalog_id": i["catalog_id"], "count": i["count"]}
                                                for i in equipment.values()]}, ensure_ascii=False)
            answer = _validate_ai(_ask(llm, [{"role": "user", "content": prompt}], AI_SYSTEM_PROMPT))
            for ai in answer.items:
                if ai.catalog_id not in CATALOG or ai.catalog_id == "animal_drinkers":
                    result["notes"].append(f"ignored unknown item: {ai.catalog_id}")      # never trust the AI here
                    continue
                count = min(ai.count, CATALOG[ai.catalog_id]["max_count"])
                if ai.catalog_id in equipment:
                    old = equipment[ai.catalog_id]
                    if count != old["count"]:
                        equipment[ai.catalog_id] = {**_item(ai.catalog_id, count, ai.reason_ar or old["reason_ar"], "ai")}
                    elif ai.reason_ar:
                        old["reason_ar"] = ai.reason_ar
                else:
                    equipment[ai.catalog_id] = _item(ai.catalog_id, count, ai.reason_ar, "ai")
            result["questions_ar"] = [q for q in answer.questions_ar if q.strip()][:2]
            result["ai_used"] = True
        except (ValueError, ValidationError, json.JSONDecodeError) as error:
            result["notes"].append(f"AI answer ignored ({error}); the rules list is used")
        except Exception as error:  # noqa: BLE001 - API down, rate limit...: the sign-up must still work
            detail = " ".join(str(error).split())[:300]          # the provider's own reason (never contains the key)
            result["notes"].append(f"AI not available ({type(error).__name__}: {detail}); the rules list is used")
    result["equipment"] = list(equipment.values())
    return result


def profile_to_farm(profile: dict, name: Optional[str] = None, confirmed_ids: Optional[list[str]] = None) -> Farm:
    """Builds the Farm used by farm.py. Only items the farmer confirmed (default: all) are kept.
    The farm has no sensors, so it gets general advice; sensors can be attached later."""
    items = [i for i in profile["equipment"] if confirmed_ids is None or i["catalog_id"] in confirmed_ids]
    return Farm(
        name=name or f"مزرعة {profile['locality']}", locality=profile["locality"], smart=False,
        equipment=[Equipment(i["name_ar"], i["role"], uses=i["uses"], power_w=i["power_w"], flow_lph=i["flow_lph"])
                   for i in items],
    )
