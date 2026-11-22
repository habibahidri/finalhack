"""Tests of notify.py (no network, no Twilio). Run: python test_notify.py"""
import json, os, tempfile
import notify

VIEW = {"moments": [{"iso": "2026-09-01T08:00", "farms": [
    {"farm_id": "demo-sousse", "farm": "S", "alerts": [{"event_id": 4, "mode": "general_sms", "summary": "نص"}]},
    {"farm_id": "demo-mornag", "farm": "M", "alerts": [{"event_id": 1, "mode": "smart_plan", "summary": "plan"}]},
    {"farm_id": "no-phone", "farm": "N", "alerts": [{"event_id": 4, "mode": "general_sms", "summary": "x"}]}]}]}


def files(tmp):
    for name, data in (("v.json", VIEW), ("p.json", {"demo-sousse": "+21612345678", "demo-mornag": "+21687654321"})):
        json.dump(data, open(os.path.join(tmp, name), "w", encoding="utf-8"))
    return [os.path.join(tmp, n) for n in ("v.json", "p.json", "log.json")]


def test_only_general_advice_with_a_phone_is_sent_and_dry_run_sends_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        v, p, log = files(tmp)
        calls = []
        todo = notify.run(v, p, log, send=False, sender=lambda *a: calls.append(a))
        assert [t["farm_id"] for t in todo] == ["demo-sousse"] and not calls and not os.path.exists(log)


def test_a_message_is_sent_once_and_a_failure_is_reported_not_logged():
    with tempfile.TemporaryDirectory() as tmp:
        v, p, log = files(tmp)
        notify.run(v, p, log, send=True, sender=lambda *a: "SM1")
        again = notify.run(v, p, log, send=True, sender=lambda *a: "SM2")
        assert again == []
        os.remove(log)
        def boom(*a): raise notify.NotifyError("refused")
        res = notify.run(v, p, log, send=True, sender=boom)
        assert res[0]["status"].startswith("failed") and not os.path.exists(log)


def test_twilio_request_and_errors_without_secrets():
    env = {"TWILIO_ACCOUNT_SID": "ACx", "TWILIO_AUTH_TOKEN": "SECRET", "TWILIO_WHATSAPP_FROM": "whatsapp:+1000"}
    seen = {}
    class R:
        def __enter__(s): return s
        def __exit__(s, *a): pass
        def read(s): return b'{"sid": "SM9"}'
    def opener(req, timeout): seen["body"] = req.data.decode(); return R()
    assert notify.twilio_send("+21612345678", "hi", "whatsapp", env, opener) == "SM9"
    assert "whatsapp%3A%2B21612345678" in seen["body"]
    for bad in (lambda: notify.twilio_send("0612", "hi", "sms", env, opener),
                lambda: notify.twilio_send("+21612345678", "hi", "sms", env, opener)):
        try: bad(); assert False
        except notify.NotifyError as e: assert "SECRET" not in str(e)


def test_old_view_without_farm_id_matches_the_phone_by_farm_name():
    view = {"moments": [{"iso": "x", "farms": [{"farm": "مزرعة سوسة", "alerts": [{"event_id": 4, "mode": "general_sms", "summary": "t"}]}]}]}
    todo = notify.pending_messages(view, {"مزرعة سوسة": "+21612345678"}, {})
    assert len(todo) == 1


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print(n, "OK")