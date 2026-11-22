import os
import tempfile

import discover
from cleaning import parse_articles

HOME = "https://news.example.tn/"
LISTING = """<html><body>
<a href="/sonede-coupure-deau-demain-a-sousse/">SONEDE: coupure d'eau demain à Sousse</a>
<a href="/steg-coupures-electricite-mardi/">STEG</a>
<a href="/match-de-football-resume/">Football</a>
<a href="/tag/steg/">STEG tag</a>
<a href="https://other-site.com/steg-coupure-electricite/">other site</a>
<a href="/%D8%A7%D9%86%D9%82%D8%B7%D8%A7%D8%B9-%D8%A7%D9%84%D9%83%D9%87%D8%B1%D8%A8%D8%A7%D8%A1-%D8%A8%D9%85%D8%B1%D9%86%D8%A7%D9%82/">انقطاع الكهرباء بمرناق</a>
<a href="/cuisine-recette-eau-de-rose/">Recette</a>
</body></html>"""
GOOD = ("<html><p>" + "La SONEDE annonce une coupure d'eau potable demain de 8h à 14h dans plusieurs quartiers de Sousse. " * 3
        + "</p></html>")
OFF_TOPIC = "<html><p>" + "La STEG est citée ici en passant dans un article de sport. " * 2 + "</p></html>"


def fake_fetch(pages):
    def fetch(url):
        if url not in pages:
            raise RuntimeError("404")
        return pages[url]
    return fetch


def make_articles(folder, existing_url="https://news.example.tn/steg-coupures-electricite-mardi/"):
    path = os.path.join(folder, "articles.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"=== ARTICLE 7 ===\nURL: {existing_url}\n{'texte ' * 40}\n\n")
    return path


def test_only_outage_looking_links_of_the_same_site_are_candidates():
    links = discover.find_links(LISTING, HOME)
    urls = [u for u, t in links if discover.looks_relevant(u, t)]
    assert "https://news.example.tn/sonede-coupure-deau-demain-a-sousse/" in urls
    assert "https://news.example.tn/steg-coupures-electricite-mardi/" in urls
    assert any("%D8%A7%D9%86" in u for u in urls)                              # Arabic link found through its title
    assert not any("football" in u or "cuisine" in u or "other-site" in u or "/tag/" in u for u in urls)


def test_new_articles_are_appended_in_the_format_the_job_reads_and_known_ones_are_skipped():
    with tempfile.TemporaryDirectory() as folder:
        path = make_articles(folder)
        pages = {HOME: LISTING, "https://news.example.tn/sonede-coupure-deau-demain-a-sousse/": GOOD}
        result = discover.discover(path, [HOME], fetch=fake_fetch(pages), log=lambda *_: None)
        assert result["added"] == ["https://news.example.tn/sonede-coupure-deau-demain-a-sousse/"]
        docs = parse_articles(path)                                            # same reader as the job
        assert [d["number"] for d in docs] == [7, 8]                           # numbering continues
        assert "coupure d'eau potable" in docs[1]["text"]
        again = discover.discover(path, [HOME], fetch=fake_fetch(pages), log=lambda *_: None)
        assert again["added"] == [] and len(parse_articles(path)) == 2         # nothing added twice


def test_dry_run_writes_nothing_and_off_topic_pages_are_remembered_not_added():
    with tempfile.TemporaryDirectory() as folder:
        path = make_articles(folder)
        before = open(path, encoding="utf-8").read()
        listing = '<a href="/steg-coupure-match-sportif/">STEG</a>'
        pages = {HOME: listing, "https://news.example.tn/steg-coupure-match-sportif/": OFF_TOPIC}
        dry = discover.discover(path, [HOME], fetch=fake_fetch(pages), dry_run=True, log=lambda *_: None)
        assert dry["candidates"] == ["https://news.example.tn/steg-coupure-match-sportif/"]
        assert open(path, encoding="utf-8").read() == before
        calls = []
        real = fake_fetch(pages)
        discover.discover(path, [HOME], fetch=lambda u: calls.append(u) or real(u), log=lambda *_: None)
        assert open(path, encoding="utf-8").read() == before                   # rejected: not added
        calls.clear()
        discover.discover(path, [HOME], fetch=lambda u: calls.append(u) or real(u), log=lambda *_: None)
        assert calls == [HOME]                                                 # ...and not downloaded again


def test_failures_never_raise_and_the_cap_is_respected():
    with tempfile.TemporaryDirectory() as folder:
        path = make_articles(folder)
        result = discover.discover(path, ["https://down.example.tn/"], fetch=fake_fetch({}), log=lambda *_: None)
        assert result["pages_failed"] == 1 and result["added"] == []
        many = "".join(f'<a href="/sonede-coupure-eau-{i}/">SONEDE {i}</a>' for i in range(9))
        pages = {HOME: many, **{f"https://news.example.tn/sonede-coupure-eau-{i}/": GOOD for i in range(9)}}
        result = discover.discover(path, [HOME], fetch=fake_fetch(pages), max_new=3, log=lambda *_: None)
        assert len(result["added"]) == 3
        assert discover.discover("/nonexistent-folder/x.txt", [HOME], fetch=fake_fetch(pages),
                                 log=lambda *_: None)["added"] == []           # broken path: no exception


def test_the_job_calls_discovery_only_when_asked_and_never_offline():
    import pipeline_job

    calls = []
    original = discover.discover
    discover.discover = lambda *a, **k: calls.append(1) or {"added": ["u"], "candidates": [], "pages_failed": 0}
    try:
        with tempfile.TemporaryDirectory() as folder:
            kw = dict(events_out=os.path.join(folder, "e.json"), view_out=os.path.join(folder, "v.json"),
                      farms_path=os.path.join(folder, "f.json"), log=lambda *_: None)
            here = os.path.dirname(os.path.abspath(__file__))
            articles = os.path.join(here, "articles.txt")
            assert pipeline_job.run_once(articles, offline=True, discover_new=True, **kw)["discovered"] == 0
            assert pipeline_job.run_once(articles, offline=True, **kw)["discovered"] == 0
            assert calls == []                                                 # offline or not asked: never called
    finally:
        discover.discover = original


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(name, "OK")
