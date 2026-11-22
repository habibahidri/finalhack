# PROJECT NOTES: Outage watch for PlantDNA (agriculteur part)

Purpose of this file: a new chat (or Antigravity) that knows nothing can read this and continue. Last update: 2026-11-21.
Rule of the project: **code decides, the AI interprets and proposes.** The AI never produces a number that the
farmer's safety depends on without a check.

## 1. The idea in one paragraph
STEG / SONEDE announce water and electricity cuts in the press. We read those notices automatically, extract
(utility, places, time window, type), merge duplicates into events, and match them to registered farms. At sign-up the
farmer taps icons (animals, crops, water source, backup energy); an AI estimates the farm's equipment from a fixed
catalog. When a cut concerns the farm, the farmer gets simple advice in Arabic: by SMS (general advice) if the farm has
no sensors, or a full plan (Keep / Before / Off per equipment) in the app if sensors give the tank and battery levels.
Every alert is explainable (why, assumptions, sources).

## 2. Decisions already taken (do not reopen without a reason)
- Simple stack: Python, requests + BeautifulSoup, pydantic, rapidfuzz. No heavy infrastructure for the demo.
- Free LLMs: Gemini (free tier, model chosen automatically) or Groq (default `openai/gpt-oss-120b`). Keys only in
  environment variables (`GEMINI_API_KEY`, `GROQ_API_KEY`, `LLM_PROVIDER`). Never paste keys in chats or files.
- Farm WITHOUT sensors: general advice only (SMS), never specific numbers. Farm WITH sensors: full plan.
- Farm without sensors gets ONE text message (SMS or WhatsApp, same words, channel value `sms` in the data). Wording: full version
  (what, where, when, may return without notice, 3 short actions, "التفاصيل في التطبيق."). About 160 characters = 3 SMS parts
  in Arabic; WhatsApp has no such limit. If env var `DETAILS_URL` is set, that real link replaces the app mention (never invented).
- Language of the form and of the advice: **Arabic** (right-to-left). French kept as secondary.
- The AI picks equipment only from `catalog.py`; power / water numbers come from the catalog, not from the AI.
- A rotating-cut window (e.g. 13h-18h) is NOT one continuous cut: plan with an assumed 2 h cut, shown as "estimation".
- Antigravity does the UI design and the UI code; our Python produces data files it reads (contracts below).
- Hackathon demo: use saved results (`events.json`), never depend on a live API on stage; `--offline` mode exists.

## 3. Pipeline blocks: status
| # | Block | Status | File(s) |
|---|-------|--------|---------|
| 1 | Source list | partial: 7 real article URLs, a few press sites; no Facebook / citizen sources | read_articles.py, sources_seed.sql |
| 2 | Raw store | simple text file only (SQL schema written, never run) | articles.txt, schema.sql |
| 3 | Cleaning | done | cleaning.py |
| 4 | AI extraction | done, with checks (invented places, incomplete answers, 503 retry + model switch, cache) | extraction_schema.py, extract.py |
| 5 | Place matching | done for French + Arabic; ~65 Arabic names; no coordinates; full Tunisia list missing | geocode.py |
| 6 | Event merging | done (overlap + shared places, combined confidence, status announced/active/expired) | events.py |
| 7 | Farm impact | done (listed / possible, probability, risk, cut duration) | farm.py |
| 7b | Equipment prioritizer | done (Keep / Before / Off) | farm.py |
| 7c | Sign-up -> equipment estimate | done (rules + optional AI, validated) | catalog.py, profile_estimator.py |
| 8 | LangGraph agents (Water, Energy, Crop, Simulation) | NOT started | |
| 9 | Notification | texts done (Arabic + French); real SMS sending NOT done (needs a provider account) | farm.py, texts_ar.py |
| 10 | Dashboard / farmer screen | internal demo page done; farmer UI = Antigravity | make_dashboard.py, export_farmer_view.py |
| 11 | Feedback loop | NOT started | |
| - | Automatic job | done: one command builds events + farmer view for all registered farms, repeats every N min, keeps old files if everything fails. Article list is still fixed (7 URLs); no server/API yet | pipeline_job.py, farms_store.py |

## 4. File map (what each file is)
Data in -> events:
- `read_articles.py`: downloads the 7 article pages into `articles.txt`. `simple_scraper.py`: first scraper test.
- `collector.py`, `test_collector.py`, `sources_seed.sql`: the earlier heavier collector (feeds, trafilatura). Kept, not used by the demo.
- `cleaning.py`: removes ads/boilerplate, splits `articles.txt`.
- `extraction_schema.py`: what the AI must return (pydantic) + the prompt (rules, JSON schema, example). Uses compact `place_groups`.
- `extract.py`: calls Gemini/Groq, retries, switches model on 503, caches answers, checks answers (invented or missing places).
- `geocode.py`: place-name normalization and matching (French + Arabic, fuzzy), ambiguous names flagged.
- `events.py`: merges notices into events, confidence, status.
- `run_pipeline.py`: runs 3 to 6 on `articles.txt` -> `events.json`. Options: `--offline` (hand-made answers), `--fresh`.
- `make_gold.py`, `gold_extractions.json`: hand-made correct answers for the 7 articles (the reference for checks and offline mode).
- `compare_runs.py`: compares two `events.json` files (AI vs hand-made).
- `old_working/`: the first version that worked (kept as a safe fallback).
Farm side:
- `catalog.py`: sign-up choices, equipment catalog with typical values, answer validation, `signup_options()`.
- `profile_estimator.py`: sign-up answers -> equipment list (rules, optional AI, validation) -> `Farm`.
- `farm.py`: Farm / Equipment, autonomy from sensor levels, matching, risk, plan, alert texts, pre-filter (`mentions_a_farm`).
- `texts_ar.py`: Arabic alert texts and SMS length helper.
- `signup_demo.py`: the whole sign-up -> advice flow in one run (`--save` stores the farm in `farms.json`).
- `farms_store.py`: where registered farms are kept (`farms.json`; demo farms if the file does not exist yet).
- `pipeline_job.py`: THE AUTOMATIC JOB: articles -> events -> `farmer_view.json` for all farms. `--every 30`, `--refresh`, `--offline`.
Outputs for screens:
- `export_farmer_view.py` -> `farmer_view.json`: data for the farmer screen (Arabic by default).
- `signup_options.json`: the sign-up form as data (made by `python catalog.py`).
- `make_dashboard.py` -> `dashboard.html`: our internal demo page (not the final UI).
- `design_brief_antigravity.md`: the brief for Antigravity.
Tests: `test_pipeline.py` (21), `test_farm.py` (11), `test_profile.py` (6), `test_job.py` (4), `test_collector.py`. Run each with `python <file>`.

## 5. Data contracts (UI must not rename keys)
- **Sign-up form**: `signup_options.json` (sections: animals with size, crops, water_source, backup_energy, extras, locality).
  Answer shape: `{"animals":{"poultry":"medium"},"crops":["vegetables"],"water_source":["well"],"backup_energy":["generator"],"extras":["cold_room"],"locality":"مرناق"}`
- **Equipment confirmation**: backend returns `{"equipment":[{catalog_id,name_ar,count,power_w,flow_lph,reason_ar,source,confirm}],"questions_ar":[],"ai_used":bool}`;
  UI returns the kept `catalog_id` list (and counts).
- **Farmer screen**: `farmer_view.json` -> moments -> farms -> alerts (headline, actions, why, assumptions, sources, summary, mode, channel).
  Status values: clear | info | watch | action.
- Today the UI reads files; later the same shapes come from an API endpoint (one `load` function to switch).

## 6. How to run (PowerShell, in the project folder)
- Real extraction: `$env:GEMINI_API_KEY="..."` (or Groq + `$env:LLM_PROVIDER="groq"`), then `python run_pipeline.py articles.txt`.
- No key: `python run_pipeline.py articles.txt --offline`.
- Automatic: `python pipeline_job.py --every 30` (add `--offline` without a key). The UI just re-reads `farmer_view.json`.
- Farm demo: `python farm.py events.json --now 2026-09-01T08:00`. Sign-up demo: `python signup_demo.py events.json`.
- Screen data: `farmer_view.json` is written by the run itself: `run_pipeline.py` and `farm.py` (and `pipeline_job.py`) all end by writing it (`--no-view` to skip, `--now` to pretend a date). `python export_farmer_view.py events.json` still works alone. Sign-up form data: `python catalog.py`.
- Before the demo: back up the folder with the good `events.json`.

## 7. Still to do (suggested order)
1. LangGraph decision graph: Water / Energy / Crop agents propose, rules verify (the code decides), Simulation agent tests the plan; explain each step.
2. Full list of Tunisian places (governorate / delegation, Arabic + French) for sign-up place search and better matching.
3. Real SMS / WhatsApp sending (provider account needed); a small server (API) so the UI gets `farmer_view` over HTTP and sign-up is saved by the backend; discovery of NEW articles (today a fixed list of 7 URLs).
4. Feedback loop: farmer says how long the cut / reserve really lasted; adjust probabilities and typical values.
5. Measure accuracy on 30 to 50 real notices (only 7 so far).
6. Coordinates + map; Facebook / citizen sources.
7. Connect Antigravity UI to the JSON files above.

## 8. Honest limits (say them in the demo)
- Farms, sensor readings and the "pretend it is" date are simulated. SMS is generated, not sent.
- Probabilities (0.6 rotating cut, 0.25 possible) and typical equipment / herd values are estimates, to be confirmed by farmers.
- Arabic wording was written by Claude: have a native reader review it.
- Free LLMs can be overloaded (503) or make mistakes (e.g. Groq listed region headings as places): the checks and the saved results protect the demo.
- Accuracy checked on 7 articles only.
