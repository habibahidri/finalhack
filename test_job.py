import json
import os
import tempfile
from datetime import datetime

import pipeline_job
from farm import TUNIS, Equipment, Farm
from farms_store import load_farms, save_farm
from pipeline_job import run_once

HERE = os.path.dirname(os.path.abspath(__file__))
ARTICLES = os.path.join(HERE, "articles.txt")
NOW = datetime(2026, 9, 1, 8, 0, tzinfo=TUNIS)


def paths(folder):
    return dict(events_out=os.path.join(folder, "e.json"), view_out=os.path.join(folder, "v.json"),
                farms_path=os.path.join(folder, "farms.json"), log=lambda *_: None)


def test_job_makes_events_and_farmer_view_by_itself():
    with tempfile.TemporaryDirectory() as folder:
        result = run_once(ARTICLES, offline=True, now=NOW, **paths(folder))
        assert result["ok"] and result["events"] == 6 and result["failures"] == 0
        view = json.load(open(os.path.join(folder, "v.json"), encoding="utf-8"))
        assert len(view["moments"]) == 1 and view["language"] == "ar"      # one live moment, not the demo list
        assert any(f["alerts"] for f in view["moments"][0]["farms"])
        assert not [n for n in os.listdir(folder) if n.endswith(".tmp")]   # no half-written file left


def test_one_bad_article_does_not_stop_the_others():
    original = pipeline_job.load_notices
    calls = {"n": 0}

    def flaky(doc, offline, use_cache=True):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("503 busy")
        return original(doc, offline)

    pipeline_job.load_notices = flaky
    try:
        with tempfile.TemporaryDirectory() as folder:
            result = run_once(ARTICLES, offline=True, now=NOW, **paths(folder))
            assert result["ok"] and result["failures"] == 1 and result["events"] >= 4
    finally:
        pipeline_job.load_notices = original


def test_if_everything_fails_the_previous_files_are_kept():
    original = pipeline_job.load_notices

    def broken(doc, offline, use_cache=True):
        raise RuntimeError("API down")

    with tempfile.TemporaryDirectory() as folder:
        p = paths(folder)
        run_once(ARTICLES, offline=True, now=NOW, **p)
        before = open(p["view_out"], encoding="utf-8").read()
        pipeline_job.load_notices = broken
        try:
            result = run_once(ARTICLES, offline=True, now=NOW, **p)
        finally:
            pipeline_job.load_notices = original
        assert not result["ok"] and open(p["view_out"], encoding="utf-8").read() == before


def test_registered_farms_are_stored_and_used_by_the_job():
    with tempfile.TemporaryDirectory() as folder:
        p = paths(folder)
        assert len(load_farms(p["farms_path"])) == 2                        # no file yet: the two demo farms
        farm = Farm("مزرعة جديدة", "مرناق", equipment=[Equipment("غرفة التبريد", "essential", power_w=800)])
        save_farm(farm, p["farms_path"])
        save_farm(Farm("مزرعة جديدة", "سوسة"), p["farms_path"])             # same name: replaced, not duplicated
        farms = load_farms(p["farms_path"])
        assert [f.locality for f in farms] == ["سوسة"]
        save_farm(farm, p["farms_path"])
        run_once(ARTICLES, offline=True, now=NOW, **p)
        view = json.load(open(p["view_out"], encoding="utf-8"))
        names = [f["farm"] for f in view["moments"][0]["farms"]]
        assert names == ["مزرعة جديدة"] and view["moments"][0]["farms"][0]["alerts"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(name, "OK")
