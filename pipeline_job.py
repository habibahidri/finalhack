"""The automatic job: announcements -> events -> farmer_view.json, with no manual step.

  python pipeline_job.py                       run once (uses the saved AI answers, so only NEW articles cost anything)
  python pipeline_job.py --every 30            repeat every 30 minutes, until you stop it
  python pipeline_job.py --refresh             download the article pages again first (needs internet)
  python pipeline_job.py --offline             no API key: hand-made answers (demo safety net)

Safety rules: an article that fails is skipped (the others still count); if everything fails, the previous
files are kept untouched, so the screen never goes empty because of a bad run.
"""
import argparse
import json
import os
import sys
from datetime import datetime

from cleaning import parse_articles
from events import build_events, status_at
from export_farmer_view import build as build_farmer_view
from farm import TUNIS
from farms_store import load_farms
from geocode import PlaceRegistry
from run_pipeline import load_notices


def _write_json(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)                       # replace in one step: readers never see half a file


def run_once(articles="articles.txt", offline=False, events_out="events.json", view_out="farmer_view.json",
             lang="ar", farms_path="farms.json", now=None, log=print, discover_new=False) -> dict:
    now = now or datetime.now(TUNIS)
    import extraction_store
    extraction_store.reset_budget()                 # AI calls allowed in this run (OUTAGE_AI_PER_RUN)
    found = 0
    if discover_new and not offline:                # offline answers only exist for the 7 known articles
        import discover
        found = len(discover.discover(articles, discover.sources_from_env(), log=log,
                                      max_new=int(os.environ.get("OUTAGE_DISCOVER_MAX", discover.MAX_NEW_DEFAULT)))["added"])
    registry = PlaceRegistry.seeded()
    items, failures = [], 0
    docs = parse_articles(articles)
    for doc in docs:
        try:
            notices = load_notices(doc, offline)
        except Exception as error:  # noqa: BLE001 - one bad article must not stop the others
            failures += 1
            log(f"article {doc['number']} skipped: {type(error).__name__}: {' '.join(str(error).split())[:160]}")
            continue
        for notice in notices:
            if notice.is_outage_notice:
                places = [registry.resolve(p.text, p.region_group) for p in notice.places]
                items.append({"url": doc["url"], "notice": notice, "places": places})
    if not items and failures:
        log("every article failed: previous files are kept unchanged")
        return {"ok": False, "articles": len(docs), "failures": failures, "discovered": found}
    events = build_events(items)
    _write_json(events_out, [{**e.to_dict(), "status": status_at(e, now)} for e in events])
    view = build_farmer_view(events_out, lang, farms_list=load_farms(farms_path), live_now=now)
    _write_json(view_out, view)
    alerts = sum(len(f["alerts"]) for f in view["moments"][0]["farms"])
    log(f"{now:%d/%m/%Y %H:%M}: {len(docs)} articles ({failures} failed) -> {len(events)} events -> "
        f"{len(view['moments'][0]['farms'])} farms, {alerts} alerts. Wrote {events_out} and {view_out}")
    return {"ok": True, "articles": len(docs), "failures": failures, "events": len(events), "alerts": alerts, "discovered": found}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--articles", default="articles.txt")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="download the article pages again first")
    parser.add_argument("--discover", action="store_true", help="look for NEW announcements first (needs internet)")
    parser.add_argument("--every", type=float, help="repeat every N minutes")
    parser.add_argument("--lang", default="ar", choices=["ar", "fr"])
    parser.add_argument("--now", help="pretend it is this moment (demo), e.g. 2026-09-01T08:00")
    args = parser.parse_args()
    fixed_now = datetime.fromisoformat(args.now).replace(tzinfo=TUNIS) if args.now else None
    while True:
        if args.refresh:
            from read_articles import download
            download(args.articles)
        run_once(args.articles, args.offline, lang=args.lang, now=fixed_now, discover_new=args.discover)
        if not args.every:
            break
        from extract import SLEEP
        print(f"next run in {args.every:g} min (Ctrl+C to stop)")
        try:
            SLEEP(args.every * 60)
        except KeyboardInterrupt:
            sys.exit(0)


if __name__ == "__main__":
    main()
