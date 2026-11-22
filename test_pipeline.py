"""Offline tests for blocks 3 to 6. Run: python test_pipeline.py   (needs articles.txt and gold_extractions.json)"""
import json
from types import SimpleNamespace

from cleaning import clean_text, parse_articles
from events import build_events, events_for_places
from extract import ExtractionError, extract_notices
from extraction_schema import ExtractionBatch
from geocode import PlaceRegistry


def load_items():
    gold = json.load(open("gold_extractions.json", encoding="utf-8"))
    registry, items = PlaceRegistry.seeded(), []
    for doc in parse_articles("articles.txt"):
        for notice in ExtractionBatch.model_validate(gold[doc["url"]]).notices:
            items.append({"url": doc["url"], "notice": notice,
                          "places": [registry.resolve(p.text, p.region_group) for p in notice.places]})
    return registry, items


def test_cleaning_removes_noise_keeps_facts():
    docs = parse_articles("articles.txt")
    assert len(docs) == 7
    raw = docs[0]["text"]
    cleaned = clean_text(raw)
    assert len(cleaned) < len(raw) * 0.6                   # repeats removed (the zone lists must stay)
    assert len(clean_text(docs[2]["text"])) < len(docs[2]["text"]) / 5   # page full of repeats and ads
    for noise in ("Décrivez votre projet", "cookies", "newsletter", "Copyright"):
        assert noise.lower() not in cleaned.lower(), noise
    for fact in ("13h00", "18h00", "Midoun", "sans préavis", "pas définitive"):
        assert fact in cleaned, fact


def test_gold_is_valid_and_complete():
    _, items = load_items()
    assert len(items) == 7


def test_place_matching():
    r = PlaceRegistry.seeded()
    same = [("Gremit El Gharbia", "Grimita El Gharbia"), ("Al Smaïdia", "Essmaïdia"),
            ("Hammam-Lif", "Hammam Lif"), ("El Mourouj", "المروج"), ("Le Kram", "الكرم"),
            ("Bou Salem", "Bousalem"), ("Chtouine", "Chetouine")]
    different = [("Menzel Bourguiba", "Menzel Bouzelfa"), ("Sfax Sud", "Sfax Ouest"),
                 ("Kalaa Kebira", "Kalaa Seghira"), ("Sakiet Ezzit", "Sakiet Eddaïer")]
    for a, b in same:
        assert r.resolve(a)["key"] == r.resolve(b)["key"], (a, b)
    for a, b in different:
        assert r.resolve(a)["key"] != r.resolve(b)["key"], (a, b)


def test_ambiguous_names_are_flagged():
    registry, _ = load_items()
    assert registry.resolve("El Hamma")["ambiguous"]       # Gabès and Sud-Ouest in the same notice


def test_event_merging():
    _, items = load_items()
    events = build_events(items)
    assert len(events) == 6                                 # 7 notices, the two SONEDE reports merge
    merged = [e for e in events if len(e.sources) == 2]
    assert len(merged) == 1 and merged[0].event_type == "water_works"
    assert len(merged[0].place_keys) == 5                   # spelling variants collapsed
    assert merged[0].confidence > max(e.confidence for e in events if len(e.sources) == 1)
    # different days never merge, even with almost the same area
    assert sum(1 for e in events if e.event_type == "rotating_shedding" and len(e.place_keys) > 150) == 2


def test_farm_locality_lookup_french_and_arabic():
    registry, items = load_items()
    events = build_events(items)
    midoun = events_for_places(events, [registry.lookup("Midoun")])
    assert [e.window_start.day for e in midoun] == [1, 2]  # only the two September notices
    mourouj = events_for_places(events, [registry.lookup("المروج")])
    assert len(mourouj) == 3                                # one French notice, two Arabic ones
    assert registry.lookup("Paris") is None


class RateLimited(Exception):
    status_code = 429


class FakeGroq:
    """Same shape as the Groq client. Each item of `replies` is a text, or an exception to raise."""
    def __init__(self, replies):
        self.replies, self.calls, self.requests = list(replies), 0, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        self.requests.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])


def test_extraction_retry_and_failure():
    good = json.dumps({"notices": [{"is_outage_notice": False, "confidence": 0.9}]})
    client = FakeGroq(["sorry, here is the answer: nothing", "```json\n" + good + "\n```"])
    notices = extract_notices("Été 2027 : faut-il craindre de nouvelles coupures ?", client=client)
    assert client.calls == 2 and notices[0].is_outage_notice is False
    first = client.requests[0]
    assert first["messages"][0]["role"] == "system" and first["response_format"] == {"type": "json_object"}
    try:
        extract_notices("x", client=FakeGroq(["bad", "still bad"]))
        raise AssertionError("should have failed")
    except ExtractionError:
        pass


class FakeGemini:
    """Same shape as google.genai.Client: models.list() and models.generate_content()."""
    def __init__(self, names, replies):
        self.replies, self.calls, self.configs = list(replies), 0, []
        listed = [SimpleNamespace(name=f"models/{n}", supported_actions=["generateContent"]) for n in names]
        self.models = SimpleNamespace(list=lambda: listed, generate_content=self._generate)

    def _generate(self, model, contents, config):
        self.calls += 1
        self.configs.append((model, config))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(text=reply)


GEMINI_NAMES = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-3-flash", "gemini-3-flash-image",
                "gemini-3-pro", "gemini-3-flash-lite", "text-embedding-9"]


def test_gemini_picks_newest_stable_flash_and_extracts():
    good = json.dumps({"notices": [{"is_outage_notice": False, "confidence": 0.9}]})
    client = FakeGemini(GEMINI_NAMES, ["not json at all", good])
    notices = extract_notices("x", client=client)
    assert notices[0].is_outage_notice is False and client.calls == 2
    model, config = client.configs[0]
    assert model == "gemini-3-flash"                       # not preview, image, lite, pro or 2.5
    assert config.response_mime_type == "application/json" and config.temperature == 0


def test_gemini_rate_limit_and_unknown_model():
    import extract
    waits = []
    extract.SLEEP = waits.append
    good = json.dumps({"notices": [{"is_outage_notice": False, "confidence": 0.9}]})

    class Busy(Exception):
        code = 429

    client = FakeGemini(GEMINI_NAMES, [Busy(), good])
    assert extract_notices("x", client=client)[0].is_outage_notice is False and waits == [20]
    extract.SLEEP = __import__("time").sleep

    class Missing(Exception):
        code = 404

    try:
        extract_notices("x", client=FakeGemini(GEMINI_NAMES, [Missing()]))
        raise AssertionError("should have failed")
    except ExtractionError as error:
        assert "gemini-3-flash" in str(error) and "GEMINI_MODEL" in str(error)


def test_provider_choice_from_environment():
    import os
    import extract
    saved = {k: os.environ.pop(k, None) for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "LLM_PROVIDER")}
    try:
        try:
            extract.make_llm()
            raise AssertionError("should ask for a key")
        except ExtractionError as error:
            assert "GEMINI_API_KEY" in str(error)
    finally:
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value


def test_prompt_contains_schema_and_valid_example():
    from extraction_schema import EXAMPLE_ANSWER, build_system_prompt
    prompt = build_system_prompt()
    for field in ("utility", "event_type", "place_groups", "names", "region_group", "window_may_extend",
                  "is_outage_notice"):
        assert f'"{field}"' in prompt, field
    assert '"places":' not in prompt and "PlaceMention" not in prompt   # the model never sees the old format
    ExtractionBatch.model_validate(EXAMPLE_ANSWER)          # the example itself must pass our validation
    assert len(prompt) < 12000


def test_failed_reply_is_saved_for_diagnosis():
    import os
    import extract
    wrong_shape = json.dumps({"notices": [{"is_outage_notice": True, "confidence": 0.9, "Sud-Ouest": ["Nefta"]}]})
    try:
        extract_notices("x", client=FakeGroq([wrong_shape, wrong_shape]))
        raise AssertionError("should have failed")
    except ExtractionError as error:
        assert "utility et event_type" in str(error) and extract.FAILED_REPLY_FILE in str(error)
    assert "Sud-Ouest" in open(extract.FAILED_REPLY_FILE, encoding="utf-8").read()
    os.remove(extract.FAILED_REPLY_FILE)


def test_cache_avoids_second_call_and_respects_changes(tmp_path="cache_test.json"):
    import os
    good = json.dumps({"notices": [{"is_outage_notice": False, "confidence": 0.9}]})
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    try:
        client = FakeGroq([good, good])
        extract_notices("same text", client=client, cache_path=tmp_path)
        again = extract_notices("same text", client=client, cache_path=tmp_path)
        assert client.calls == 1 and again[0].is_outage_notice is False      # second time: from the cache
        extract_notices("other text", client=client, cache_path=tmp_path)
        assert client.calls == 2                                              # new text: asks again
        open(tmp_path, "w").write("{ damaged")
        extract_notices("same text", client=FakeGroq([good]), cache_path=tmp_path)  # damaged cache ignored
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_compare_runs_shows_place_and_field_differences():
    from compare_runs import compare
    a = {1: dict(utility="water", event_type="water_works", window_start=None, window_end="16:00",
                 expected_restoration=None, is_intermittent=False, recurrence=None, window_may_extend=False,
                 restoration_without_notice=False, place_keys=["x", "y", "z"], place_names={"x": "X", "y": "Y", "z": "Z"})}
    b = {1: dict(a[1], window_end=None, expected_restoration="16:00", place_keys=["x", "y"])}
    lines = compare(a, b)
    assert "#1 window_end: '16:00' vs None" in lines and "#1 only in first file: Z" in lines
    assert compare(a, a) == ["No difference."]


def test_place_groups_are_expanded_and_deduplicated():
    reply = {"notices": [{
        "is_outage_notice": True, "utility": "electricity", "event_type": "rotating_shedding",
        "place_groups": [
            {"region_group": "Grand Tunis", "names": ["Ezzahra", " Le Kram ", "Ezzahra", ""]},
            {"region_group": "Sud-Ouest", "names": ["Ezzahra", "Nefta"], "level_hint": "locality"},
        ],
        "confidence": 0.9}]}
    notice = ExtractionBatch.model_validate(reply).notices[0]
    assert [(p.text, p.region_group) for p in notice.places] == [
        ("Ezzahra", "Grand Tunis"), ("Le Kram", "Grand Tunis"),
        ("Ezzahra", "Sud-Ouest"), ("Nefta", "Sud-Ouest")]       # same name in two regions is kept
    assert notice.place_groups == [] and notice.places[3].level_hint == "locality"
    # the old format (used by gold_extractions.json) still works
    old = {"notices": [dict(reply["notices"][0], place_groups=[], places=[{"text": "Nefta"}])]}
    assert ExtractionBatch.model_validate(old).notices[0].places[0].text == "Nefta"
    # a notice with neither format is still rejected
    empty = {"notices": [dict(reply["notices"][0], place_groups=[])]}
    try:
        ExtractionBatch.model_validate(empty)
        raise AssertionError("should have been rejected")
    except ValueError:
        pass


def test_grounding_check_finds_invented_places():
    from extract import ungrounded_places
    text = "Les zones concernées : Ezzahra, Le Kram et المروج dans la délégation d'Enfidha."
    notice = ExtractionBatch.model_validate({"notices": [{
        "is_outage_notice": True, "utility": "electricity", "event_type": "rotating_shedding",
        "place_groups": [{"region_group": "Grand Tunis", "names": ["Ezzahra", "Le Kram", "المروج", "Hammamet"]}],
        "confidence": 0.9}]}).notices[0]
    assert ungrounded_places(notice, text) == ["Hammamet"]


def test_grounding_check_on_real_articles_has_no_false_alarms():
    from extract import ungrounded_places
    gold = json.load(open("gold_extractions.json", encoding="utf-8"))
    for doc in parse_articles("articles.txt"):
        notice = ExtractionBatch.model_validate(gold[doc["url"]]).notices[0]
        assert ungrounded_places(notice, clean_text(doc["text"])) == [], doc["number"]


class NotFound(Exception):
    status_code = 404


def test_unknown_model_lists_available_models():
    client = FakeGroq([NotFound()])
    models = [SimpleNamespace(id=i) for i in ("whisper-large-v3", "model-a", "model-b")]
    client.models = SimpleNamespace(list=lambda: SimpleNamespace(data=models))
    try:
        extract_notices("x", client=client)
        raise AssertionError("should have failed")
    except ExtractionError as error:
        assert "model-a, model-b" in str(error) and "whisper" not in str(error)


def test_extraction_waits_when_rate_limited():
    import extract
    waits = []
    extract.SLEEP = waits.append
    good = json.dumps({"notices": [{"is_outage_notice": False, "confidence": 0.9}]})
    client = FakeGroq([RateLimited(), RateLimited(), good])
    assert extract_notices("x", client=client)[0].is_outage_notice is False
    assert client.calls == 3 and waits == [20, 40]
    extract.SLEEP = __import__("time").sleep


def test_overloaded_model_switches_then_gives_clear_message():
    import extract

    class Busy(Exception):
        code = 503

    class Fake:
        def __init__(self, replies):
            self.model, self.replies, self.spare_models, self.used = "flash-a", list(replies), ["flash-b"], []

        def switch_model(self):
            if not self.spare_models:
                return False
            self.model = self.spare_models.pop(0)
            return True

        def ask(self, messages):
            self.used.append(self.model)
            reply = self.replies.pop(0) if self.replies else Busy()
            if isinstance(reply, Exception):
                raise reply
            return reply

    extract.SLEEP = lambda s: None
    good = json.dumps({"notices": [{"is_outage_notice": False, "confidence": 0.9}]})
    llm = Fake([Busy()] * 4 + [good])           # flash-a busy 4 times, flash-b answers
    assert extract_notices("x", client=llm)[0].is_outage_notice is False
    assert llm.used[-1] == "flash-b"
    dead = Fake([])                              # everything busy -> clear message, not a traceback
    try:
        extract_notices("x", client=dead)
        raise AssertionError("should fail")
    except extract.ExtractionError as error:
        assert "overloaded" in str(error)
    extract.SLEEP = __import__("time").sleep


def test_incomplete_answer_is_detected_and_retried():
    import extract
    from extract import incomplete_reason
    docs = parse_articles("articles.txt")
    gold = json.load(open("gold_extractions.json", encoding="utf-8"))
    text = clean_text(docs[0]["text"])
    good = gold[docs[0]["url"]]
    # real data: no false alarm on any of the 7 articles
    for doc in docs:
        n = ExtractionBatch.model_validate(gold[doc["url"]]).notices[0]
        assert incomplete_reason(n, clean_text(doc["text"])) is None, doc["number"]
    # answer that only lists region headings (what Groq did) -> detected, then corrected on retry
    bad = json.loads(json.dumps(good))
    bad["notices"][0]["places"] = [{"text": x} for x in
                                   ["Grand Tunis", "Nord", "Nord-Ouest", "Centre", "Sfax", "Sud", "Sud-Ouest"]]
    assert "region headings" in incomplete_reason(ExtractionBatch.model_validate(bad).notices[0], text)
    client = FakeGroq([json.dumps(bad), json.dumps(good)])
    notices = extract_notices(text, client=client)
    assert client.calls == 2 and len(notices[0].places) == 200


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(name, "OK")
