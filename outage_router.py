"""The outage watch as a FastAPI router: the same endpoints as server.py, inside your app.

  app.include_router(router, prefix="/api/outage")      (outage_service.mount does this for you and loads the settings)

Answers keep the same shape as the standard-library server: errors are {"error": "..."}.
Endpoints (relative to the prefix):
  GET  /health                       GET  /signup-options
  POST /signup                       POST /farms            (optional "phone")
  POST /farms/phone                  GET  /farmer-view?farm=<id>[&now=ISO][&lang=ar|fr]
  GET  /f/<farm id>                  the farmer's page (the link at the end of the message)
  GET  /join                         the sign-up page (the form, in the browser)
Login, rate limits and CORS belong to your app: this router adds none.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse

import outage_core as core
from farmer_page import render
from signup_page import render as render_signup

router = APIRouter()


def _settings(request: Request):
    settings = getattr(request.app.state, "outage", None)
    if settings is None:
        raise core.ApiError(500, "outage watch is not mounted: call outage_service.mount(app)")
    return settings


def _llm():
    from extract import make_llm                  # the AI is optional: only built when a sign-up asks for it
    return make_llm()


def _answer(action) -> JSONResponse:
    try:
        return JSONResponse(action())
    except core.ERRORS as error:
        status, message = core.error_status(error)
        return JSONResponse({"error": message}, status_code=status)
    except Exception as error:  # noqa: BLE001 - never crash the app on one bad request
        return JSONResponse({"error": f"server error: {type(error).__name__}"}, status_code=500)


@router.get("/health")
def health(request: Request):
    def action():
        settings = _settings(request)
        return {**core.health(settings.events), "job": settings.status or {"state": "not run yet"}}
    return _answer(action)


@router.get("/signup-options")
def signup_options():
    return _answer(core.options)


@router.post("/signup")
def signup(request: Request, body: dict = Body(...)):
    return _answer(lambda: core.signup(body, _llm))


@router.post("/farms")
def create_farm(request: Request, body: dict = Body(...)):
    return _answer(lambda: core.create_farm(body, _settings(request).db))


@router.post("/farms/phone")
def set_phone(request: Request, body: dict = Body(...)):
    return _answer(lambda: core.set_phone(body, _settings(request).db))


@router.get("/farmer-view")
def farmer_view(request: Request):
    def action():
        settings = _settings(request)
        return core.farmer_view(dict(request.query_params), settings.events, settings.db, settings.now)
    return _answer(action)


@router.get("/f/{farm_id}", response_class=HTMLResponse)
def farmer_page(request: Request, farm_id: str):
    base = request.url.path.rsplit("/f/", 1)[0]          # the prefix the app mounted us under
    return HTMLResponse(render(f"{base}/farmer-view"))


@router.get("/join", response_class=HTMLResponse)
def join_page(request: Request):
    base = request.url.path.rsplit("/join", 1)[0]        # the prefix the app mounted us under
    return HTMLResponse(render_signup(base))
