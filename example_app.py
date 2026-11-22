"""The smallest FastAPI app that uses the outage watch. Run:  uvicorn example_app:app --port 8000
Your own app only needs the same three lines (import, lifespan, mount).

CORS: a screen served from ANOTHER address (Antigravity's app, a preview) can only call the API if the origin is allowed.
OUTAGE_CORS = comma-separated origins, e.g. https://my-ui.example.com   (default "*" = any, fine for a demo, NOT for production).
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from outage_service import mount, outage_lifespan

app = FastAPI(lifespan=outage_lifespan)
origins = [o.strip() for o in os.environ.get("OUTAGE_CORS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
mount(app, "/api/outage")


@app.get("/")
def home():
    return {"my": "app", "outage_watch": "/api/outage/health", "sign_up": "/api/outage/join"}
