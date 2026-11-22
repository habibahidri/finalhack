import add_farmer
import signup_page
from fastapi import FastAPI
from fastapi.testclient import TestClient

import outage_service


def make_app(prefix):
    app = FastAPI()
    outage_service.mount(app, prefix, outage_service.Settings(job=False))
    return TestClient(app)


def test_the_signup_page_is_served_under_whatever_prefix_the_app_mounts_it():
    for prefix in ("/api/outage", "/x/y"):
        page = make_app(prefix).get(f"{prefix}/join")
        assert page.status_code == 200 and "text/html" in page.headers["content-type"]
        assert f'const BASE = "{prefix}";' in page.text and 'dir="rtl"' in page.text
        assert "/signup-options" in page.text and "/farms" in page.text


def test_the_prefix_cannot_break_out_of_the_script():
    html = signup_page.render('/a"</script><script>alert(1)//')
    assert "</script><script>alert(1)" not in html


def test_phone_numbers_are_completed_like_a_tunisian_would_write_them():
    assert add_farmer.fix_phone("22 345 678") == "+21622345678"
    assert add_farmer.fix_phone("0021622345678") == "+21622345678"
    assert add_farmer.fix_phone("21622345678") == "+21622345678"
    assert add_farmer.fix_phone("+21622345678") == "+21622345678"


def test_offline_mode_says_clearly_when_an_article_has_no_hand_made_answer():
    import run_pipeline
    try:
        run_pipeline.load_notices({"number": 9, "url": "https://example.tn/new/", "text": "x"}, offline=True)
    except ValueError as error:
        assert "offline mode" in str(error)
    else:
        raise AssertionError("must explain, not raise a bare KeyError")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(name, "OK")
