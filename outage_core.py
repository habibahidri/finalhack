"""The logic of the API, written once and used by BOTH front doors: server.py (standard library) and outage_router.py (FastAPI).

Every function takes plain data and returns plain data, or raises ApiError(status, message) / ChoiceError (a 400).
Safety rules (unchanged): power and water numbers come from the catalog, never from the client; unknown ids and wrong
sizes are rejected; the phone number is stored privately and never returned.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime

from catalog import BACKUP_ENERGY, CATALOG, CROPS, ChoiceError, herd_water_lph, signup_options, validate_choices
from export_farmer_view import build
from farm import TUNIS, Equipment, Farm
from farms_store import is_db, load_farms, save_farm, set_phone as store_set_phone
from profile_estimator import estimate_profile

MAX_COUNT_PER_ITEM = 50
PHONE = re.compile(r"^\+\d{8,15}$")             # +216XXXXXXXX


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


ERRORS = (ApiError, ChoiceError)


def error_status(error: Exception) -> tuple[int, str]:
    return (error.status, error.message) if isinstance(error, ApiError) else (400, str(error))


def health(events_path: str) -> dict:
    return {"ok": True, "events_file": os.path.exists(events_path)}


def options() -> dict:
    return signup_options()


def signup(body: dict, llm_factory=None) -> dict:
    answers = body.get("answers")
    if not isinstance(answers, dict):
        raise ApiError(400, "answers is required")
    llm = None
    if body.get("use_ai") and llm_factory:
        try:
            llm = llm_factory()
        except Exception:  # noqa: BLE001 - no key / provider down: the sign-up still works with the rules list
            llm = None
    return {"profile": estimate_profile(answers, llm)}


def check_phone(phone) -> str:
    phone = str(phone or "").strip().replace(" ", "")
    if not PHONE.match(phone):
        raise ApiError(400, "phone must look like +216XXXXXXXX")
    return phone


def create_farm(body: dict, farms_path: str) -> dict:
    locality = str(body.get("locality", "")).strip()
    if not locality:
        raise ApiError(400, "locality is required")
    confirmed = body.get("confirmed")
    if not isinstance(confirmed, list) or not confirmed:
        raise ApiError(400, "confirmed must be a non-empty list of {catalog_id, count}")
    phone = None
    if body.get("phone"):
        if not is_db(farms_path):
            raise ApiError(400, "phone numbers need the database (outage.db)")
        phone = check_phone(body["phone"])
    raw_answers = body.get("answers")
    equipment = []
    for row in confirmed:
        cid = row.get("catalog_id") if isinstance(row, dict) else None
        if cid not in CATALOG:
            raise ApiError(400, f"unknown equipment: {cid}")
        count = row.get("count", 1)
        if not isinstance(count, int) or not 1 <= count <= min(CATALOG[cid]["max_count"], MAX_COUNT_PER_ITEM):
            raise ApiError(400, f"bad count for {cid}")
        spec = CATALOG[cid]                          # numbers come from the catalog, never from the client
        flow = spec.get("flow_lph") or 0
        if cid == "animal_drinkers":                  # water need computed from the animals chosen at sign-up
            flow = herd_water_lph(validate_choices({**raw_answers, "locality": locality})["animals"]) if isinstance(raw_answers, dict) else 0
        equipment.append(Equipment(spec["ar"], spec["role"], uses=spec["uses"], catalog_id=cid,
                                   power_w=spec.get("power_w", 0) * count,
                                   flow_lph=flow * (1 if cid == "animal_drinkers" else count)))
    farm_id = uuid.uuid4().hex[:8]
    answers = raw_answers if isinstance(raw_answers, dict) else {}
    crops = [c for c in (answers.get("crops") or []) if c in CROPS] if isinstance(answers.get("crops"), list) else []
    backup = [b for b in (answers.get("backup_energy") or []) if b in BACKUP_ENERGY and b != "none"] \
        if isinstance(answers.get("backup_energy"), list) else []
    farm = Farm(name=str(body.get("name") or f"مزرعة {locality}")[:60], locality=locality, id=farm_id,
                equipment=equipment, crops=crops, backup=backup)
    sensors = body.get("sensors")
    if isinstance(sensors, dict):                    # optional: farms with sensors
        farm.smart = True
        for key in ("tank_litres", "tank_level_pct", "battery_kwh", "battery_pct"):
            value = sensors.get(key)
            if value is not None:
                if not isinstance(value, (int, float)) or value < 0 or (key.endswith("_pct") and value > 100):
                    raise ApiError(400, f"bad sensor value: {key}")
                setattr(farm, key, float(value))
    save_farm(farm, farms_path)
    if phone:
        store_set_phone(farm_id, phone, farms_path)
    return {"farm_id": farm_id, "name": farm.name, "locality": farm.locality, "has_sensors": farm.smart,
            "phone_saved": bool(phone)}


def set_phone(body: dict, farms_path: str) -> dict:
    if not is_db(farms_path):
        raise ApiError(400, "phone numbers need the database (outage.db)")
    farm_id = str(body.get("farm_id", "")).strip()
    phone = check_phone(body.get("phone"))
    if farm_id not in {f.id for f in load_farms(farms_path) if f.id}:
        raise ApiError(404, "unknown farm")
    store_set_phone(farm_id, phone, farms_path)
    return {"farm_id": farm_id, "phone_saved": True}          # the number itself is never sent back


def farmer_view(query: dict, events_path: str, farms_path: str, default_now: str | None = None) -> dict:
    if not os.path.exists(events_path):
        raise ApiError(503, "no events yet: run the pipeline first")
    farms = [f for f in load_farms(farms_path) if f.id and f.id == query.get("farm")]
    if not farms:
        raise ApiError(404, "unknown farm")
    lang = query.get("lang", "ar")
    if lang not in ("ar", "fr"):
        raise ApiError(400, "lang must be ar or fr")
    try:
        chosen = query.get("now") or default_now
        now = datetime.fromisoformat(chosen).replace(tzinfo=TUNIS) if chosen else datetime.now(TUNIS)
    except ValueError:
        raise ApiError(400, "now must look like 2026-09-01T08:00")
    view = build(events_path, lang, farms_list=farms, live_now=now)
    return {"language": view["language"], "direction": view["direction"], "status_labels": view["status_labels"],
            "generated_at": datetime.now(TUNIS).isoformat(), "farm": view["moments"][0]["farms"][0]}
