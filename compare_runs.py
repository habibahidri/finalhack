"""Compares two runs (for example the AI run and the hand-made run) event by event.

Usage:  python compare_runs.py events.json events_offline.json
"""
import json
import sys


def load(path):
    return {e["id"]: e for e in json.load(open(path, encoding="utf-8"))}


def compare(a: dict, b: dict) -> list[str]:
    lines = []
    for event_id in sorted(set(a) | set(b)):
        x, y = a.get(event_id), b.get(event_id)
        if x is None or y is None:
            lines.append(f"#{event_id}: only in {'first' if y is None else 'second'} file")
            continue
        for field in ("utility", "event_type", "window_start", "window_end", "expected_restoration",
                      "is_intermittent", "recurrence", "window_may_extend", "restoration_without_notice"):
            if x[field] != y[field]:
                lines.append(f"#{event_id} {field}: {x[field]!r} vs {y[field]!r}")
        only_x = sorted(x["place_names"][k] for k in set(x["place_keys"]) - set(y["place_keys"]))
        only_y = sorted(y["place_names"][k] for k in set(y["place_keys"]) - set(x["place_keys"]))
        if only_x:
            lines.append(f"#{event_id} only in first file: {', '.join(only_x)}")
        if only_y:
            lines.append(f"#{event_id} only in second file: {', '.join(only_y)}")
    return lines or ["No difference."]


if __name__ == "__main__":
    first, second = (sys.argv[1:3] + ["events.json", "events_offline.json"])[:2]
    print("\n".join(compare(load(first), load(second))))
