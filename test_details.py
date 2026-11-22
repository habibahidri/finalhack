"""Tests of the link at the end of the message. Run: python test_details.py"""
import os
from datetime import datetime

import texts_ar
from events import Event
from farm import DEMO_FARMS


def water_event():
    return Event(id=4, utility="water", event_type="water_regulation", window_start=datetime(2026, 7, 5, 0),
                 window_end=datetime(2026, 7, 5, 5), recurrence="daily", is_intermittent=False, window_may_extend=False,
                 list_is_exhaustive=True, max_single_cut_hours=None, expected_restoration=None,
                 restoration_without_notice=False, reason=None, place_keys=["sousse"])


def with_url(url):
    if url:
        os.environ["DETAILS_URL"] = url
    else:
        os.environ.pop("DETAILS_URL", None)


def test_without_a_public_address_the_message_still_says_details_in_the_app():
    with_url("")
    assert texts_ar.general_message(DEMO_FARMS[1], water_event(), "listed").endswith("التفاصيل في التطبيق.")


def test_with_a_public_address_the_message_ends_with_this_farms_link():
    with_url("https://farm.example/")
    message = texts_ar.general_message(DEMO_FARMS[1], water_event(), "listed")
    assert message.endswith("التفاصيل: https://farm.example/f/demo-sousse"), message
    with_url("")


def test_each_farm_gets_its_own_link():
    with_url("https://farm.example")
    a = texts_ar.general_message(DEMO_FARMS[0], water_event(), "listed")
    b = texts_ar.general_message(DEMO_FARMS[1], water_event(), "listed")
    assert "/f/demo-mornag" in a and "/f/demo-sousse" in b
    with_url("")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(name, "OK")
