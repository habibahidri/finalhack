"""Sends the general message (farms without sensors) by WhatsApp or SMS through Twilio.

  python notify.py                      -> DRY RUN: prints what would be sent, sends nothing
  python notify.py --send               -> really sends (needs the environment variables below)
  python notify.py --channel sms        -> SMS instead of WhatsApp (default: whatsapp)

Reads farmer_view.json (made by the backend) and phones.json: {"demo-sousse": "+216XXXXXXXX", ...}  (farm_id -> phone; the farm name also works).
Only alerts with mode "general_sms" are sent: the same text for SMS and WhatsApp. A farm with sensors reads its plan in the app.
Each (farm, event, moment) is sent once: sent_log.json remembers it.

Environment variables (never put them in a file or a chat):
  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
  TWILIO_WHATSAPP_FROM   e.g. whatsapp:+14155238886   (the Twilio sandbox number shown in your Twilio console)
  TWILIO_SMS_FROM        a Twilio phone number, only for --channel sms
WhatsApp sandbox: each phone must first send the join code shown in the Twilio console to the sandbox number.
"""
import argparse
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
PHONE = re.compile(r"^\+\d{8,15}$")


class NotifyError(Exception):
    pass


def load_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:         # utf-8-sig: also reads files that Windows PowerShell saved with a BOM
            return json.load(f)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as error:
        raise NotifyError(f"{path} is not valid JSON ({error.msg}, line {error.lineno})") from None


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def pending_messages(view: dict, phones: dict, sent: dict) -> list[dict]:
    """The messages to send: general_sms alerts of farms that have a phone number and were not sent yet."""
    out = []
    for moment in view.get("moments", []):
        for farm in moment.get("farms", []):
            ident = farm.get("farm_id") or farm.get("farm", "")       # older files have no farm_id: the farm name is used
            phone = phones.get(farm.get("farm_id", "")) or phones.get(farm.get("farm", ""))
            if not phone:
                continue
            for alert in farm.get("alerts", []):
                if alert.get("mode") != "general_sms":
                    continue
                key = f"{ident}|{alert['event_id']}|{moment['iso']}"
                if key not in sent:
                    out.append({"key": key, "farm": farm["farm"], "farm_id": ident, "phone": phone,
                                "body": alert["summary"]})
    return out


def twilio_send(phone: str, body: str, channel: str, env=os.environ, opener=urllib.request.urlopen) -> str:
    """One real message. Returns Twilio's message id. Raises NotifyError with a safe text (no secrets)."""
    if not PHONE.match(phone):
        raise NotifyError(f"bad phone number format: {phone} (use +216XXXXXXXX)")
    sid, token = env.get("TWILIO_ACCOUNT_SID"), env.get("TWILIO_AUTH_TOKEN")
    sender = env.get("TWILIO_WHATSAPP_FROM" if channel == "whatsapp" else "TWILIO_SMS_FROM")
    if not (sid and token and sender):
        raise NotifyError("missing TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / "
                          + ("TWILIO_WHATSAPP_FROM" if channel == "whatsapp" else "TWILIO_SMS_FROM"))
    to = f"whatsapp:{phone}" if channel == "whatsapp" else phone
    data = urllib.parse.urlencode({"To": to, "From": sender, "Body": body}).encode()
    request = urllib.request.Request(API.format(sid=sid), data=data)
    request.add_header("Authorization", "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode())
    try:
        with opener(request, timeout=20) as response:
            return json.loads(response.read().decode()).get("sid", "?")
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:300]
        raise NotifyError(f"Twilio refused (HTTP {error.code}): {detail}") from None
    except Exception as error:  # noqa: BLE001 - network down etc.
        raise NotifyError(f"could not reach Twilio ({type(error).__name__})") from None


def run(view_path="farmer_view.json", phones_path="phones.json", log_path="sent_log.json", channel="whatsapp",
        send=False, sender=twilio_send) -> list[dict]:
    view, phones, sent = load_json(view_path, {}), load_json(phones_path, {}), load_json(log_path, {})
    todo = pending_messages(view, phones, sent)
    for item in todo:
        label = f"{item['farm']} -> {item['phone'][:4]}****  [{channel}] ({len(item['body'])} characters)"
        if not send:
            print(f"DRY RUN  {label}\n   {item['body']}")
            item["status"] = "dry-run"
            continue
        try:
            item["id"] = sender(item["phone"], item["body"], channel)
            sent[item["key"]] = item["id"]
            save_json(log_path, sent)                # saved after each message: a crash never causes a double send
            item["status"] = "sent"
            print(f"SENT     {label}")
        except NotifyError as error:
            item["status"] = f"failed: {error}"
            print(f"FAILED   {label}: {error}")
    if not todo:
        print("nothing to send (no general-advice alert with a phone number, or all already sent)")
    return todo


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="really send (default: dry run)")
    ap.add_argument("--channel", choices=["whatsapp", "sms"], default="whatsapp")
    ap.add_argument("--view", default="farmer_view.json")
    ap.add_argument("--phones", default="phones.json")
    args = ap.parse_args()
    run(args.view, args.phones, channel=args.channel, send=args.send)