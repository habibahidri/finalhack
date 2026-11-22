import json
import os
import tempfile
from datetime import datetime, timedelta

import extract
import extraction_store as store
import run_pipeline
from cleaning import parse_articles
from extraction_schema import ExtractionBatch

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = parse_articles(os.path.join(HERE, "articles.txt"))
GOLD = json.load(open(os.path.join(HERE, "gold_extractions.json"), encoding="utf-8"))


def fresh_store(folder):
    os.environ["OUTAGE_STORE"] = os.path.join(folder, "store.json")
    os.environ.pop("OUTAGE_AI_PER_RUN", None)
    os.environ.pop("OUTAGE_RETRY_MIN", None)
    store.reset_budget()


class FakeAI:
    """Replaces extract.extract_notices: counts calls, answers with the hand-made notices or fails."""
    def __init__(self, fail=None):
        self.calls, self.fail = 0, fail

    def __call__(self, text, cache_path=None, **kw):
        self.calls += 1
        if self.fail:
            raise extract.ExtractionError(self.fail)
        return ExtractionBatch.model_validate(GOLD[self.url]).notices


def run(doc, ai, use_cache=True):
    ai.url = doc["url"]
    original = extract.extract_notices
    extract.extract_notices = ai
    try:
        return run_pipeline.load_notices(doc, offline=False, use_cache=use_cache)
    finally:
        extract.extract_notices = original


def test_an_article_is_extracted_once_then_answered_from_the_store_without_ai_or_key():
    with tempfile.TemporaryDirectory() as folder:
        fresh_store(folder)
        ai = FakeAI()
        first = run(DOCS[0], ai)
        again = run(DOCS[0], ai)
        assert ai.calls == 1 and len(first) == len(again) > 0
        assert os.path.exists(os.environ["OUTAGE_STORE"])
        for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY"):
            os.environ.pop(var, None)
        assert len(run(DOCS[0], FakeAI(fail="No API key"))) == len(first)      # no key needed any more


def test_a_busy_ai_is_not_asked_again_before_the_waiting_time_and_known_articles_fall_back_to_gold():
    with tempfile.TemporaryDirectory() as folder:
        fresh_store(folder)
        busy = FakeAI(fail="503 busy")
        notices = run(DOCS[1], busy)                                           # known article: hand-made answer
        assert busy.calls == 1 and notices
        run(DOCS[1], busy)
        assert busy.calls == 1                                                 # waits: no second call
        assert store.wait_before_retry(DOCS[1]["url"]) > 0
        later = datetime.now() + timedelta(minutes=61)
        assert store.wait_before_retry(DOCS[1]["url"], now=later) == 0         # after an hour it may try again


def test_an_unknown_article_that_fails_raises_so_the_job_counts_it_and_retries_later():
    with tempfile.TemporaryDirectory() as folder:
        fresh_store(folder)
        doc = {"number": 99, "url": "https://example.tn/new-notice/", "text": "STEG coupure " * 30}
        try:
            run(doc, FakeAI(fail="503 busy"))
        except extract.ExtractionError:
            pass
        else:
            raise AssertionError("must raise: there is no hand-made answer for a new article")
        assert store.wait_before_retry(doc["url"]) > 0


def test_the_ai_budget_of_a_run_is_respected_and_saved_answers_do_not_use_it():
    with tempfile.TemporaryDirectory() as folder:
        fresh_store(folder)
        os.environ["OUTAGE_AI_PER_RUN"] = "2"
        store.reset_budget()
        ai = FakeAI()
        for doc in DOCS[:2]:
            run(doc, ai)
        assert ai.calls == 2
        run(DOCS[2], ai)                                                       # budget used: gold fallback, no call
        assert ai.calls == 2
        run(DOCS[0], ai)
        run(DOCS[1], ai)                                                       # answered from the store: free
        assert ai.calls == 2
        store.reset_budget()
        run(DOCS[2], ai)
        assert ai.calls == 3                                                   # next run: budget is back


def test_a_damaged_store_is_ignored_and_fresh_ignores_the_store():
    with tempfile.TemporaryDirectory() as folder:
        fresh_store(folder)
        open(os.environ["OUTAGE_STORE"], "w").write("{not json")
        ai = FakeAI()
        assert run(DOCS[0], ai)
        assert run(DOCS[0], ai, use_cache=False) and ai.calls == 2             # --fresh asks the AI again


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(name, "OK")
