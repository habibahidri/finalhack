"""Permanent memory of what the AI already read, so an article is extracted ONCE, ever.

Why: the AI key has a quota, a call takes seconds, and the service is sometimes busy (503). With this store:
  - an article already extracted is answered from the file: no key, no model, no wait, no quota;
  - a new article costs at most one extraction, and at most OUTAGE_AI_PER_RUN (default 4) per run;
  - an article whose extraction failed (busy, quota) is NOT retried before OUTAGE_RETRY_MIN (default 60) minutes;
  - for the 7 original articles only, if the AI is unavailable the hand-made answers of gold_extractions.json
    are used instead (the log says so), so the demo never stays empty.

The key is the hash of the cleaned article text, not the model name: switching model (busy) keeps every answer.
File: extraction_store.json (env OUTAGE_STORE). Copy it to another computer to bring the answers with you.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta

STORE_FILE = os.environ.get("OUTAGE_STORE", "extraction_store.json")
_budget = {"left": None}


def _path() -> str:
    return os.environ.get("OUTAGE_STORE", STORE_FILE)


def text_key(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def _load() -> dict:
    try:
        data = json.load(open(_path(), encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}                                      # a damaged store is ignored, never fatal


def _save(data: dict) -> None:
    tmp = _path() + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, _path())
    except OSError:
        pass


def get(text: str):
    """The saved notices (list of dicts, ExtractionBatch format) or None."""
    entry = _load().get("answers", {}).get(text_key(text))
    return entry["batch"] if entry else None


def put(text: str, url: str, batch: dict) -> None:
    data = _load()
    data.setdefault("answers", {})[text_key(text)] = {"url": url, "saved": datetime.now().isoformat(timespec="seconds"),
                                                      "batch": batch}
    data.get("failed", {}).pop(url, None)
    _save(data)


def mark_failed(url: str, reason: str) -> None:
    data = _load()
    data.setdefault("failed", {})[url] = {"at": datetime.now().isoformat(timespec="seconds"), "reason": reason[:160]}
    _save(data)


def wait_before_retry(url: str, now: datetime | None = None) -> int:
    """Minutes still to wait before this article may be tried again (0 = go)."""
    entry = _load().get("failed", {}).get(url)
    if not entry:
        return 0
    minutes = float(os.environ.get("OUTAGE_RETRY_MIN", "60"))
    ready = datetime.fromisoformat(entry["at"]) + timedelta(minutes=minutes)
    left = (ready - (now or datetime.now())).total_seconds() / 60
    return max(0, int(left) + 1) if left > 0 else 0


def reset_budget() -> None:
    """Called at the start of each job run."""
    _budget["left"] = int(os.environ.get("OUTAGE_AI_PER_RUN", "4"))


def take_budget() -> bool:
    if _budget["left"] is None:
        reset_budget()
    if _budget["left"] <= 0:
        return False
    _budget["left"] -= 1
    return True
