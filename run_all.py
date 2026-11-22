"""ONE command to run the whole outage watch.

  python run_all.py                 real mode: finds new announcements, reads them with the AI (needs GEMINI_API_KEY or
                                    GROQ_API_KEY for NEW articles only), checks the farms, sends messages (dry run by default)
  python run_all.py --demo          demo mode: the demo date 01/09/2026 08:00 and no AI needed (saved or hand-made answers)

Then, in a second window, enter a farmer:   python add_farmer.py
Everything else is automatic: the job runs at start and every 30 minutes (OUTAGE_EVERY_MIN).
Options: --port 8000   --public-url https://your-address/api/outage   --send (really send; needs the Twilio variables)
"""
import argparse
import json
import os


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="demo date and no AI needed")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to be reachable from other computers (deployment)")
    parser.add_argument("--public-url", default="", help="address used in the message links")
    parser.add_argument("--send", action="store_true", help="really send messages (default: dry run)")
    args = parser.parse_args()

    if args.demo:
        os.environ.setdefault("OUTAGE_NOW", "2026-09-01T08:00")
        os.environ.setdefault("OUTAGE_DISCOVER", "0")
        os.environ.setdefault("OUTAGE_EVERY_MIN", "2")        # a new farm gets its message within 2 minutes
    else:
        os.environ.setdefault("OUTAGE_DISCOVER", "1")
    base = f"http://localhost:{args.port}/api/outage"
    os.environ.setdefault("OUTAGE_PUBLIC_URL", args.public_url or base)
    if args.send:
        os.environ["OUTAGE_SEND"] = "1"

    try:
        import extraction_store
        saved = len(json.load(open(extraction_store.STORE_FILE, encoding="utf-8")).get("answers", {}))
    except (OSError, ValueError):
        saved = 0
    has_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GROQ_API_KEY"))
    print(f"mode: {'DEMO (date 01/09/2026 08:00)' if args.demo else 'REAL'} | AI key: {'yes' if has_key else 'no'} | "
          f"articles already read and saved: {saved} | discovery: {os.environ['OUTAGE_DISCOVER']} | "
          f"sending: {'REAL' if args.send else 'dry run'}")
    if os.environ.get("OUTAGE_OFFLINE") == "1":
        print("WARNING: OUTAGE_OFFLINE=1 is set in this window: only the 7 hand-made answers are used and it REWRITES events.json. "
              "To stop it:  Remove-Item Env:OUTAGE_OFFLINE")
    if not args.demo and os.environ.get("OUTAGE_NOW"):
        print(f"WARNING: OUTAGE_NOW={os.environ['OUTAGE_NOW']} is set: the app pretends it is that date. To stop it:  Remove-Item Env:OUTAGE_NOW")
    if not has_key:
        print("no AI key: saved answers are used; the 7 original articles fall back to the hand-made answers; "
              "NEW articles wait until a key is set.")
    print(f"health:  {base}/health\nfarmer pages: {base}/f/<farm id>\nsign-up page: {base}/join\nadd a farmer in the terminal instead (second window): python add_farmer.py"
          + (f" --base http://localhost:{args.port}" if args.port != 8000 else ""))

    import socket
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            raise SystemExit(f"\nport {args.port} is already used: a previous server is still running. Close that window "
                             f"(Ctrl+C) or use another port:  python run_all.py --port {args.port + 1}")
    import uvicorn
    uvicorn.run("example_app:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
