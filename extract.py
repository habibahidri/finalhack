"""Block 4: text of an announcement -> validated structured notices, with a free LLM API.

Two providers are supported; the script picks the one whose key it finds:
  Gemini (Google AI Studio, free tier):  pip install google-genai   +  GEMINI_API_KEY
  Groq   (free plan):                    pip install groq           +  GROQ_API_KEY

PowerShell example:   $env:GEMINI_API_KEY="your-key"
Optional variables:
  LLM_PROVIDER    "gemini" or "groq" (to force one when both keys are set)
  GEMINI_MODEL    default: the newest Flash model your key can use (chosen automatically)
  GROQ_MODEL      default: openai/gpt-oss-120b
  GROQ_JSON_MODE  "1" (default) asks Groq for a JSON object; "0" turns that off
"""
import hashlib
import json
import os
import re
import time
from typing import Optional

from extraction_schema import ExtractionBatch, OutageExtraction, build_system_prompt

SYSTEM_PROMPT = build_system_prompt()   # rules + exact JSON schema + example
FAILED_REPLY_FILE = "last_failed_reply.txt"

MAX_TEXT_CHARS = 20000
MAX_OUTPUT_TOKENS = 16000        # a notice with 200 places needs several thousand tokens
RETRY_STATUS = (429, 503)        # rate limit / service busy: wait and try again
RETRIES = 3
REQUEST_TIMEOUT_S = 90            # one API call may take at most this long (long notices need time)


def _sleep(seconds: float) -> None:
    """Waits in 1-second steps so Ctrl+C works during a wait."""
    end = time.time() + seconds
    while time.time() < end:
        time.sleep(min(1.0, end - time.time()))


SLEEP = _sleep                   # replaced in tests
GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"
GEMINI_SKIP_WORDS = ("image", "tts", "audio", "live", "lite", "native", "embedding", "robotics", "computer")


class ExtractionError(Exception):
    pass


def parse_json(reply: str) -> dict:
    """Accepts a reply with or without ```json fences."""
    reply = re.sub(r"^```(?:json)?|```$", "", reply.strip(), flags=re.M).strip()
    start, end = reply.find("{"), reply.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in the reply")
    return json.loads(reply[start : end + 1])


def _status(error: Exception):
    return getattr(error, "status_code", None) or getattr(error, "code", None)


# ----------------------------------------------------------------- Groq
class GroqLLM:
    def __init__(self, client, model: Optional[str] = None):
        self.client = client
        self.model = model or os.environ.get("GROQ_MODEL", GROQ_DEFAULT_MODEL)

    def ask(self, messages: list[dict], system: Optional[str] = None) -> str:
        request = dict(
            model=self.model,
            messages=[{"role": "system", "content": system or SYSTEM_PROMPT}, *messages],
            temperature=0,
            max_tokens=MAX_OUTPUT_TOKENS,
        )
        if os.environ.get("GROQ_JSON_MODE", "1") == "1":
            request["response_format"] = {"type": "json_object"}
        response = self.client.chat.completions.create(**request)
        return response.choices[0].message.content or ""

    def models_help(self) -> str:
        try:
            ids = sorted(m.id for m in self.client.models.list().data)
            chat = [i for i in ids if not any(w in i for w in ("whisper", "guard", "orpheus", "tts"))]
            listing = ", ".join(chat) or "(none found)"
        except Exception as error:  # noqa: BLE001
            listing = f"(could not list models: {error})"
        return (f"Model '{self.model}' is not available for your key. Models your key can use: {listing}. "
                f'Pick one, for example in PowerShell:  $env:GROQ_MODEL="model-id"')


# --------------------------------------------------------------- Gemini
def _gemini_models(client) -> list[str]:
    names = []
    for model in client.models.list():
        actions = getattr(model, "supported_actions", None) or ["generateContent"]
        if "generateContent" in actions:
            names.append((model.name or "").removeprefix("models/"))
    return names


class GeminiLLM:
    def __init__(self, client, model: Optional[str] = None):
        self.client = client
        self.spare_models: list[str] = []      # other Flash models to try if this one stays overloaded
        self.model = model or os.environ.get("GEMINI_MODEL") or self._auto_model()

    def switch_model(self) -> bool:
        """Moves to the next model when the current one is overloaded (503). False if none is left."""
        if not self.spare_models:
            return False
        self.model = self.spare_models.pop(0)
        print(f"[extract] model overloaded, switching to {self.model}")
        return True

    def _auto_model(self) -> str:
        """Newest 'flash' model your key can use (fast, and the one meant for the free tier)."""
        candidates = [n for n in _gemini_models(self.client)
                      if "flash" in n and not any(w in n for w in GEMINI_SKIP_WORDS)]
        if not candidates:
            raise ExtractionError("No Gemini Flash model found for your key. "
                                  'Set one yourself:  $env:GEMINI_MODEL="model-id"')

        def rank(name: str):
            found = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
            stable = "preview" not in name and "exp" not in name
            return (float(found.group(1)) if found else 0.0, stable, -len(name))

        ranked = sorted(candidates, key=rank, reverse=True)
        best = ranked[0]
        self.spare_models = [n for n in ranked[1:] if rank(n)[1]][:2]    # stable models only
        print(f"[extract] Gemini model chosen automatically: {best}")
        return best

    def ask(self, messages: list[dict], system: Optional[str] = None) -> str:
        from google.genai import types

        contents = [
            types.Content(role="model" if m["role"] == "assistant" else "user",
                          parts=[types.Part(text=m["content"])])
            for m in messages
        ]
        config = types.GenerateContentConfig(
            system_instruction=system or SYSTEM_PROMPT, temperature=0,
            response_mime_type="application/json", max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        response = self.client.models.generate_content(model=self.model, contents=contents, config=config)
        return response.text or ""

    def models_help(self) -> str:
        try:
            listing = ", ".join(sorted(_gemini_models(self.client))) or "(none found)"
        except Exception as error:  # noqa: BLE001
            listing = f"(could not list models: {error})"
        return (f"Model '{self.model}' is not available for your key. Models your key can use: {listing}. "
                f'Pick one, for example in PowerShell:  $env:GEMINI_MODEL="model-id"')


# -------------------------------------------------------------- selection
_DEFAULT_LLM = None


def make_llm(client=None):
    """Wraps a ready client (tests) or builds one from the environment variables."""
    global _DEFAULT_LLM
    if client is not None:
        if hasattr(client, "ask"):
            return client
        return GroqLLM(client) if hasattr(client, "chat") else GeminiLLM(client)
    if _DEFAULT_LLM is None:   # built once: choosing the model costs one API call each time
        _DEFAULT_LLM = _build_llm_from_environment()
    return _DEFAULT_LLM


def _build_llm_from_environment():
    provider = os.environ.get("LLM_PROVIDER", "").lower()
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if provider == "gemini" or (not provider and gemini_key):
        if not gemini_key:
            raise ExtractionError("GEMINI_API_KEY is not set")
        from google import genai
        from google.genai import types

        # each call gives up after REQUEST_TIMEOUT_S seconds instead of hanging (Ctrl+C is slow during a hang)
        client = genai.Client(api_key=gemini_key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_S * 1000))
        return GeminiLLM(client)
    if provider == "groq" or os.environ.get("GROQ_API_KEY"):
        if not os.environ.get("GROQ_API_KEY"):
            raise ExtractionError("GROQ_API_KEY is not set")
        from groq import Groq

        return GroqLLM(Groq(api_key=os.environ["GROQ_API_KEY"], timeout=REQUEST_TIMEOUT_S))
    raise ExtractionError("No API key found. Set GEMINI_API_KEY (free, Google AI Studio) or GROQ_API_KEY.")


def _ask(llm, messages: list[dict], system: Optional[str] = None) -> str:
    for attempt in range(RETRIES + 1):
        try:
            return llm.ask(messages, system=system) if system else llm.ask(messages)
        except Exception as error:  # noqa: BLE001 - only rate limits and unknown models are handled
            status = _status(error)
            if status in RETRY_STATUS and attempt < RETRIES:
                wait = 20 * (attempt + 1)
                print(f"[extract] service busy ({status}), waiting {wait} s then trying again...")
                SLEEP(wait)
                continue
            if status == 503 and hasattr(llm, "switch_model") and llm.switch_model():
                return _ask(llm, messages, system)      # same request, another model
            if status in RETRY_STATUS:
                raise ExtractionError(f"The AI service is overloaded or rate-limited ({status}). "
                                      "This is on Google's side and temporary: wait a few minutes and run again "
                                      "(answers already received are saved, so nothing is lost).") from error
            if status == 404:
                raise ExtractionError(llm.models_help()) from error
            raise


def ungrounded_places(notice: OutageExtraction, text: str) -> list[str]:
    """Places the model wrote that do not appear in the article text (invented or reworded)."""
    from geocode import normalize

    haystack = normalize(text)
    return [p.text for p in notice.places if normalize(p.text) not in haystack]


REGION_NAMES = {"grandtunis", "nord", "nordouest", "nordest", "centre", "centreouest", "centreest", "sud", "sudouest",
                "sudest", "sfax", "capbon", "sahel", "grandsfax"}
LONG_TEXT_CHARS = 2500           # long notices list many places (real ones: about 1 place per 20 characters)
CHARS_PER_PLACE = 60


def incomplete_reason(notice: OutageExtraction, text: str) -> Optional[str]:
    """Detects an answer that only lists region headings, or forgets many places the text clearly contains."""
    from geocode import match_key

    if not notice.is_outage_notice or not notice.places:
        return None
    keys = {match_key(p.text) for p in notice.places}
    if len(keys) >= 3 and len(keys & REGION_NAMES) >= len(keys) / 2:
        return ("you listed region headings (Grand Tunis, Nord, Sud...) as places; "
                "list the localities written under each heading and use the heading as region_group")
    if len(text) > LONG_TEXT_CHARS and len(notice.places) < len(text) / CHARS_PER_PLACE:
        return (f"the text is long ({len(text)} characters) but you listed only {len(notice.places)} places; "
                "list every locality written in the text")
    return None


def _cache_key(llm, text: str, reference_date: Optional[str]) -> str:
    """Same text + same model + same prompt = same answer, so it can be reused."""
    raw = "\n".join([str(getattr(llm, "model", "")), SYSTEM_PROMPT, reference_date or "", text[:MAX_TEXT_CHARS]])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_cache(path: Optional[str]) -> dict:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}                                   # a damaged cache is just ignored


def _save_cache(path: str, cache: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except OSError:
        pass                                        # no cache is not a reason to fail


def extract_notices(
    text: str,
    reference_date: Optional[str] = None,
    client=None,
    max_retries: int = 1,
    cache_path: Optional[str] = None,
) -> list[OutageExtraction]:
    llm = make_llm(client)
    key = _cache_key(llm, text, reference_date)
    cache = _load_cache(cache_path)
    if key in cache:
        return ExtractionBatch.model_validate(cache[key]).notices
    date_line = reference_date or "not provided: use the dates written in the text"
    messages = [{"role": "user", "content": f"reference_date: {date_line}\n\nTEXT:\n{text[:MAX_TEXT_CHARS]}"}]
    last_error = None
    for attempt in range(max_retries + 1):
        reply = _ask(llm, messages)
        try:
            batch = ExtractionBatch.model_validate(parse_json(reply))
        except ValueError as error:  # JSON errors and pydantic validation errors
            last_error = error
            messages += [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": f"Your output was invalid: {error}\nReturn the corrected JSON only."},
            ]
            continue
        problem = next((r for n in batch.notices if (r := incomplete_reason(n, text))), None)
        if problem and attempt < max_retries:           # one more chance, with the precise reason
            last_error = ValueError(problem)
            messages += [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": f"Your answer is incomplete: {problem}\nReturn the corrected JSON only."},
            ]
            continue
        if problem:
            print(f"[extract] warning: answer may be incomplete: {problem}")
        if cache_path:
            cache[key] = batch.model_dump(mode="json")
            _save_cache(cache_path, cache)
        return batch.notices
    with open(FAILED_REPLY_FILE, "w", encoding="utf-8") as f:   # to see what the model really wrote
        f.write(reply)
    raise ExtractionError(f"extraction failed after retry: {last_error}\n"
                          f"The model's last answer was saved in {FAILED_REPLY_FILE}")
