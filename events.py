"""Block 6: merge notices into canonical events, with confidence and lifecycle."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

# Initial reliability per source (later adjusted from farmer feedback).
RELIABILITY = {
    "tunisienumerique.com": 0.75, "tuniscope.com": 0.75, "mosaiquefm.net": 0.80,
    "businessnews.com.tn": 0.75, "lapresse.tn": 0.75,
}
DEFAULT_RELIABILITY = 0.50
MIN_PLACE_OVERLAP = 0.5  # share of common places needed to merge two notices


def reliability(url: str) -> float:
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    return RELIABILITY.get(domain, DEFAULT_RELIABILITY)


@dataclass
class Event:
    id: int
    utility: str
    event_type: str
    window_start: Optional[datetime]
    window_end: Optional[datetime]
    recurrence: Optional[str]
    is_intermittent: bool
    window_may_extend: bool
    list_is_exhaustive: bool
    max_single_cut_hours: Optional[float]
    expected_restoration: Optional[datetime]
    restoration_without_notice: bool
    reason: Optional[str]
    place_keys: list[str] = field(default_factory=list)
    place_names: dict[str, str] = field(default_factory=dict)   # key -> display name
    sources: list[str] = field(default_factory=list)            # URLs (evidence)
    confidence: float = 0.0

    def to_dict(self) -> dict:
        data = asdict(self)
        for name in ("window_start", "window_end", "expected_restoration"):
            data[name] = data[name].isoformat() if data[name] else None
        return data


def _span(start: Optional[datetime], end: Optional[datetime]):
    if start is None:
        return None
    return start, (end or start + timedelta(hours=24))


def _overlap(a, b) -> bool:
    sa, sb = _span(a.window_start, a.window_end), _span(b.window_start, b.window_end)
    return bool(sa and sb and sa[0] <= sb[1] and sb[0] <= sa[1])


def _jaccard(a: list[str], b: list[str]) -> float:
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a and b else 0.0


def _noisy_or(values: list[float]) -> float:
    """Combines independent evidence: two 0.7 sources give 0.91, not 0.7."""
    remaining = 1.0
    for value in values:
        remaining *= 1 - value
    return round(1 - remaining, 2)


def build_events(items: list[dict]) -> list[Event]:
    """items: [{'url': str, 'notice': OutageExtraction, 'places': [resolved place dicts]}]"""
    events: list[Event] = []
    evidence: dict[int, list[float]] = {}
    for item in items:
        n = item["notice"]
        candidate = Event(
            id=0, utility=n.utility.value, event_type=n.event_type.value,
            window_start=n.window_start, window_end=n.window_end, recurrence=n.recurrence,
            is_intermittent=n.is_intermittent, window_may_extend=n.window_may_extend,
            list_is_exhaustive=n.list_is_exhaustive, max_single_cut_hours=n.max_single_cut_hours,
            expected_restoration=n.expected_restoration,
            restoration_without_notice=n.restoration_without_notice, reason=n.reason,
            place_keys=sorted({p["key"] for p in item["places"]}),
            place_names={p["key"]: p["name"] for p in item["places"]},
            sources=[item["url"]],
        )
        score = n.confidence * reliability(item["url"])
        match = next(
            (e for e in events
             if e.utility == candidate.utility and e.event_type == candidate.event_type
             and _overlap(e, candidate)
             and _jaccard(e.place_keys, candidate.place_keys) >= MIN_PLACE_OVERLAP),
            None,
        )
        if match is None:
            candidate.id = len(events) + 1
            events.append(candidate)
            evidence[candidate.id] = [score]
            continue
        # Same event reported again: union of places and windows, keep every source.
        match.place_keys = sorted(set(match.place_keys) | set(candidate.place_keys))
        match.place_names.update(candidate.place_names)
        match.sources += [u for u in candidate.sources if u not in match.sources]
        starts = [d for d in (match.window_start, candidate.window_start) if d]
        ends = [d for d in (match.window_end, candidate.window_end) if d]
        match.window_start, match.window_end = (min(starts) if starts else None), (max(ends) if ends else None)
        match.window_may_extend |= candidate.window_may_extend
        match.expected_restoration = match.expected_restoration or candidate.expected_restoration
        evidence[match.id].append(score)
    for event in events:
        event.confidence = _noisy_or(evidence[event.id])
    return events


def status_at(event: Event, now: datetime) -> str:
    """Lifecycle: announced -> active -> expired (restored/cancelled come from later updates)."""
    if event.window_start is None or now < event.window_start:
        return "announced"
    if event.recurrence == "daily":
        return "active"  # recurring until the operator announces the end
    end = event.window_end or event.window_start + timedelta(hours=24)
    return "active" if now <= end else "expired"


def events_for_places(events: list[Event], keys: list[str]) -> list[Event]:
    wanted = set(keys)
    return [e for e in events if wanted & set(e.place_keys)]
