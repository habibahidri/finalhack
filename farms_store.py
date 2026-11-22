"""Where the registered farms are kept: a SQLite file (outage.db) or, for the older tools, a JSON file (farms.json).

The path decides: a name ending in .db / .sqlite uses SQLite, anything else uses the JSON file as before.
SQLite also keeps the phone numbers (private, never part of a farm's screen data) and the log of messages already sent.
If there are no registered farms yet, the two demo farms are used so the demo always has something to show.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone

from farm import DEMO_FARMS, Equipment, Farm

FARMS_FILE = "farms.json"
DB_FILE = "outage.db"


def is_db(path) -> bool:
    return str(path).lower().endswith((".db", ".sqlite", ".sqlite3"))


def farm_from_dict(data: dict) -> Farm:
    data = dict(data)
    data["equipment"] = [Equipment(**e) for e in data.get("equipment", [])]
    return Farm(**data)


# ----------------------------------------------------------------------------- SQLite
def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS farms (id TEXT PRIMARY KEY, name TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS phones (farm_id TEXT PRIMARY KEY, phone TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sent_log (key TEXT PRIMARY KEY, message_id TEXT, sent_at TEXT NOT NULL);
    """)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _farm_key(farm: Farm) -> str:
    return farm.id or farm.farm_id or farm.name


def _db_load(path: str) -> list[Farm]:
    with closing(_connect(path)) as conn:
        rows = conn.execute("SELECT data FROM farms ORDER BY created_at, rowid").fetchall()
    return [farm_from_dict(json.loads(r[0])) for r in rows] or list(DEMO_FARMS)


def _db_save(farm: Farm, path: str) -> None:
    key = _farm_key(farm)
    with closing(_connect(path)) as conn, conn:
        conn.execute("INSERT INTO farms (id, name, data, created_at) VALUES (?, ?, ?, ?) "
                     "ON CONFLICT(id) DO UPDATE SET name=excluded.name, data=excluded.data",
                     (key, farm.name, json.dumps(asdict(farm), ensure_ascii=False), _now()))


# ----------------------------------------------------------------------------- farms (both storages)
def load_farms(path: str = FARMS_FILE) -> list[Farm]:
    if is_db(path):
        return _db_load(path)
    if not os.path.exists(path):
        return list(DEMO_FARMS)
    with open(path, encoding="utf-8") as f:
        return [farm_from_dict(d) for d in json.load(f)]


def save_farm(farm: Farm, path: str = FARMS_FILE) -> None:
    """Adds the farm, or replaces the one with the same id (the name is only used for old farms without an id)."""
    if is_db(path):
        return _db_save(farm, path)
    same = lambda f: (f.farm_id == farm.farm_id) if farm.farm_id else (f.name == farm.name)   # noqa: E731
    farms = [f for f in (load_farms(path) if os.path.exists(path) else []) if not same(f)]
    farms.append(farm)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump([asdict(x) for x in farms], f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)                      # a half-written file is never seen by the reader


def import_json_farms(json_path: str, db_path: str = DB_FILE) -> int:
    """Copies the farms of an old farms.json into the database (same id = replaced). Returns how many."""
    with open(json_path, encoding="utf-8") as f:
        farms = [farm_from_dict(d) for d in json.load(f)]
    for farm in farms:
        _db_save(farm, db_path)
    return len(farms)


# ----------------------------------------------------------------------------- phones and sent log (SQLite only)
def _need_db(path: str) -> None:
    if not is_db(path):
        raise ValueError("phones and the sent log need the SQLite database (a path ending in .db)")


def set_phone(farm_id: str, phone: str, path: str = DB_FILE) -> None:
    _need_db(path)
    with closing(_connect(path)) as conn, conn:
        conn.execute("INSERT INTO phones (farm_id, phone, updated_at) VALUES (?, ?, ?) "
                     "ON CONFLICT(farm_id) DO UPDATE SET phone=excluded.phone, updated_at=excluded.updated_at",
                     (farm_id, phone, _now()))


def get_phones(path: str = DB_FILE) -> dict:
    """{farm_id: phone}. Private: used only by the message sender, never put in an API answer."""
    _need_db(path)
    with closing(_connect(path)) as conn:
        return dict(conn.execute("SELECT farm_id, phone FROM phones").fetchall())


def sent_keys(path: str = DB_FILE) -> dict:
    _need_db(path)
    with closing(_connect(path)) as conn:
        return dict(conn.execute("SELECT key, message_id FROM sent_log").fetchall())


def mark_sent(key: str, message_id: str, path: str = DB_FILE) -> None:
    _need_db(path)
    with closing(_connect(path)) as conn, conn:
        conn.execute("INSERT OR REPLACE INTO sent_log (key, message_id, sent_at) VALUES (?, ?, ?)", (key, message_id, _now()))
