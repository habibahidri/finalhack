"""Runs blocks 3 to 6 on the file made by read_articles.py.

Examples:
  python run_pipeline.py articles.txt --offline              (no API key: uses gold_extractions.json)
  python run_pipeline.py articles.txt                        (real extraction: needs GEMINI_API_KEY or GROQ_API_KEY)
  python run_pipeline.py articles.txt --offline --locality Midoun
"""
import argparse
import json
import time
from datetime import datetime, timedelta, timezone

from cleaning import clean_text, parse_articles
from events import build_events, events_for_places, status_at
from extraction_schema import ExtractionBatch
from geocode import PlaceRegistry

TUNIS = timezone(timedelta(hours=1))


CACHE_FILE = "extraction_cache.json"


def _gold_for(url: str):
    try:
        gold = json.load(open("gold_extractions.json", encoding="utf-8"))
        return ExtractionBatch.model_validate(gold[url]).notices if url in gold else None
    except (OSError, ValueError, KeyError):
        return None


def load_notices(doc: dict, offline: bool, use_cache: bool = True):
    if offline:
        gold = _gold_for(doc["url"])
        if gold is None:
            raise ValueError("offline mode has no hand-made answer for this article (only the 7 original ones): "
                             "unset OUTAGE_OFFLINE and set an AI key to read it")
        return gold
    import extraction_store as store
    from extract import ExtractionError, extract_notices, ungrounded_places

    text = clean_text(doc["text"])
    if use_cache:
        saved = store.get(text)
        if saved is not None:                              # already read once: no key, no model, no wait
            return ExtractionBatch.model_validate(saved).notices
    try:
        wait = store.wait_before_retry(doc["url"]) if use_cache else 0
        if wait:
            raise ExtractionError(f"failed recently, next try in {wait} min")
        if not store.take_budget():
            raise ExtractionError("AI budget of this run used (OUTAGE_AI_PER_RUN): continues at the next run")
        started = time.time()
        notices = extract_notices(text, cache_path=CACHE_FILE if use_cache else None)
        print(f"article {doc['number']}: {time.time() - started:.1f} s (new, now saved)")
        store.put(text, doc["url"], ExtractionBatch(notices=notices).model_dump(mode="json"))
    except Exception as error:  # noqa: BLE001 - busy, quota, no key...: never lose the article
        no_key = "No API key" in str(error) or "is not set" in str(error)    # fixable by the user: do not make it wait an hour
        if "failed recently" not in str(error) and "budget" not in str(error) and not no_key:
            store.mark_failed(doc["url"], f"{type(error).__name__}: {error}")
        fallback = _gold_for(doc["url"])
        if fallback is None:
            raise
        print(f"article {doc['number']}: AI unavailable ({' '.join(str(error).split())[:90]}) -> using the hand-made answer")
        return fallback
    for notice in notices:
        missing = ungrounded_places(notice, text)
        if missing:
            print(f"  warning: {len(missing)} place(s) not found in the article text: {', '.join(missing[:8])}")
    return notices


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("articles", nargs="?", default="articles.txt")
    parser.add_argument("--offline", action="store_true", help="use gold_extractions.json instead of an LLM")
    parser.add_argument("--fresh", action="store_true", help="ignore the saved answers and ask the AI again")
    parser.add_argument("--out", default="events.json")
    parser.add_argument("--now", help="pretend it is this moment, e.g. 2026-09-01T08:00 (Tunis time)")
    parser.add_argument("--lang", default="ar", choices=["ar", "fr"], help="language of the farmer alerts")
    parser.add_argument("--no-view", action="store_true", help="do not write farmer_view.json")
    parser.add_argument("--locality", help="show the events that concern this place (French or Arabic name)")
    args = parser.parse_args()

    registry = PlaceRegistry.seeded()
    items = []
    for doc in parse_articles(args.articles):
        for notice in load_notices(doc, args.offline, use_cache=not args.fresh):
            if not notice.is_outage_notice:
                print(f"article {doc['number']}: not an outage notice, skipped")
                continue
            places = [registry.resolve(p.text, p.region_group) for p in notice.places]
            items.append({"url": doc["url"], "notice": notice, "places": places})
    events = build_events(items)

    now = datetime.fromisoformat(args.now).replace(tzinfo=TUNIS) if args.now else datetime.now(TUNIS)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump([{**e.to_dict(), "status": status_at(e, now)} for e in events], f, ensure_ascii=False, indent=1)

    print(f"\n{len(items)} notices -> {len(events)} events (saved in {args.out})\n")
    for e in events:
        window = f"{e.window_start:%d %b %Y %H:%M}" if e.window_start else "no date"
        end = f" to {e.window_end:%H:%M}" if e.window_end else ""
        print(f"#{e.id} {e.utility:11} {e.event_type:18} {window}{end} | {len(e.place_keys)} places"
              f" | {len(e.sources)} source(s) | confidence {e.confidence} | {status_at(e, now)}")

    if not args.no_view:                       # the farmer screen data is made by the same run
        from export_farmer_view import write_view
        from farms_store import load_farms

        view = write_view(args.out, "farmer_view.json", args.lang, farms_list=load_farms(), live_now=now)
        alerts = sum(len(f["alerts"]) for f in view["moments"][0]["farms"])
        print(f"\nfarmer_view.json written: {len(view['moments'][0]['farms'])} farms, {alerts} alerts "
              f"(as of {now:%d/%m/%Y %H:%M})")

    if args.locality:
        key = registry.lookup(args.locality)
        print(f"\nEvents concerning '{args.locality}':")
        if key is None:
            print("  place not known in any notice")
        for e in events_for_places(events, [key] if key else []):
            print(f"  #{e.id} {e.utility} {e.event_type} {e.window_start:%d %b %Y %H:%M}")
        if key and registry.places[key]["regions"] and len(registry.places[key]["regions"]) > 1:
            print(f"  warning: this name appears in several regions: {registry.places[key]['regions']}")


if __name__ == "__main__":
    main()
