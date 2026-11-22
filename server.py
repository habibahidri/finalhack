"""The small server: the screens talk to the backend through these addresses (standard library only).

  python server.py                       starts on http://localhost:8000   (Ctrl+C to stop)
  python server.py --port 9000 --events events.json

Addresses (all answer JSON):
  GET  /api/health
  GET  /api/signup-options                          the icon form (same as signup_options.json)
  POST /api/signup        {answers, use_ai?}        -> estimated equipment to confirm
  POST /api/farms         {locality, confirmed:[{catalog_id,count}], answers?, name?, sensors?}  -> saves the farm, returns its id
  GET  /api/farmer-view?farm=<id>[&now=ISO][&lang=ar|fr]   -> the screen data for that farm (same shape as farmer_view.json)
  GET  /f/<farm id>[?now=ISO]                       the farmer's page (HTML): the link at the end of the message opens this

Options: --public-url https://...   address written in the message links (<url>/f/<farm id>)
         --now 2026-09-01T08:00     demo date used when a request has no date (the notices are from the past)

Safety: power / water numbers are never taken from the client, they are recomputed from the catalog;
unknown ids and wrong sizes are rejected; request size is limited.
"""
import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import outage_core as core
from farmer_page import render

MAX_BODY = 20_000
ApiError = core.ApiError                      # old name, kept so nothing else breaks


def make_handler(events_path: str, farms_path: str, llm_factory=None, default_now=None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "OutageWatch/1.0"

        # ---- helpers
        def _send(self, status: int, payload) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")          # demo: any front end; restrict in production
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, page: str) -> None:
            body = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise core.ApiError(413, "request too large")
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                raise core.ApiError(400, "body is not valid JSON")
            if not isinstance(data, dict):
                raise core.ApiError(400, "body must be a JSON object")
            return data

        def log_message(self, fmt, *args):            # quiet; one short line per request
            print(f"{self.command} {self.path.split('?')[0]} -> {args[1] if len(args) > 1 else ''}")

        def _run(self, action) -> None:
            try:
                self._send(200, action())
            except core.ERRORS as error:
                status, message = core.error_status(error)
                self._send(status, {"error": message})
            except Exception as error:  # noqa: BLE001 - never crash the server on one bad request
                self._send(500, {"error": f"server error: {type(error).__name__}"})

        # ---- routes
        def do_OPTIONS(self):
            self._send(204, {})

        def do_GET(self):
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path in ("/", "/api"):
                self._run(lambda: {"name": "Outage watch API", "status": "running", "try_these": [
                    "GET /api/health", "GET /api/signup-options", "POST /api/signup", "POST /api/farms",
                    "GET /api/farmer-view?farm=<farm_id>&now=2026-09-01T08:00"]})
            elif url.path == "/api/health":
                self._run(lambda: core.health(events_path))
            elif url.path == "/api/signup-options":
                self._run(core.options)
            elif url.path == "/api/farmer-view":
                self._run(lambda: core.farmer_view(query, events_path, farms_path, default_now))
            elif url.path.startswith("/f/"):
                self._send_html(render("/api/farmer-view"))      # the page asks the data itself; unknown ids show a clear message
            else:
                self._send(404, {"error": "unknown address", "try": "/api/health or /api/signup-options"})

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/api/signup":
                self._run(lambda: core.signup(self._body(), llm_factory))
            elif path == "/api/farms":
                self._run(lambda: core.create_farm(self._body(), farms_path))
            elif path == "/api/farms/phone":
                self._run(lambda: core.set_phone(self._body(), farms_path))
            else:
                self._send(404, {"error": "unknown address"})

    return Handler


def create_server(events_path="events.json", farms_path="farms.json", port=8000, llm_factory=None, default_now=None):
    return ThreadingHTTPServer(("0.0.0.0", port), make_handler(events_path, farms_path, llm_factory, default_now))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--events", default="events.json")
    parser.add_argument("--farms", default="farms.json")
    parser.add_argument("--public-url", default="", help="public address of this server, written in the message links")
    parser.add_argument("--now", default="", help="demo date for requests without one, e.g. 2026-09-01T08:00")
    args = parser.parse_args()
    if args.public_url:
        os.environ["DETAILS_URL"] = args.public_url          # texts_ar reads it: message link = <url>/f/<farm id>

    def llm_factory():                          # the AI is optional: only built when a sign-up asks for it
        from extract import make_llm
        return make_llm()

    server = create_server(args.events, args.farms, args.port, llm_factory, args.now or None)
    print(f"Server ready on http://localhost:{args.port}  (events: {args.events}, farms: {args.farms}). Ctrl+C to stop.")
    if args.public_url:
        print(f"Message links look like: {args.public_url.rstrip('/')}/f/<farm id>")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()