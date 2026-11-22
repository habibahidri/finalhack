"""Discovery of NEW STEG / SONEDE announcements.

It opens a few listing pages (home page, site search), keeps the links that look like STEG or SONEDE cut
notices, downloads the ones we have not seen, and appends them to articles.txt in the same format as
read_articles.py. The normal job then reads, extracts and matches them like the first 7.

  python discover.py --dry-run      only print the candidate links (nothing is written): run this once to check
  python discover.py                download the new ones and append them to articles.txt

In the app: set OUTAGE_DISCOVER=1 (off by default, so the demo stays the same every run).
  OUTAGE_DISCOVER_SOURCES   comma-separated listing pages, to replace the defaults below
  OUTAGE_DISCOVER_MAX       new articles per run (default 5), so a bad page can never flood the AI

Safety: a page that fails is skipped; the function never raises; every link is judged once (accepted or
rejected) and remembered in discovery_seen.json, so it is not downloaded again on every run.
The listing addresses below were NOT checked from the author's sandbox: run --dry-run once and edit SOURCES
if a site changed its layout.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from urllib.parse import unquote, urljoin, urlparse

# Listing pages to look at. Edit freely.
SOURCES = [
    "https://www.tunisienumerique.com/?s=steg",
    "https://www.tunisienumerique.com/?s=sonede",
    "https://www.tunisienumerique.com/",
    "https://www.tuniscope.com/",
]
HEADERS = {"User-Agent": "student-project (contact: your.email@example.com)"}
MAX_NEW_DEFAULT = 5
MIN_TEXT = 200

# A link is a candidate when its address or title names STEG / SONEDE, or pairs "cut" with water / electricity.
STRONG = {"steg", "sonede", "delestage", "الستاغ", "الصوناد", "الشركة التونسية للكهرباء والغاز"}
CUT_WORDS = {"coupure", "coupures", "interruption", "interruptions", "perturbation", "perturbations",
             "انقطاع", "قطع", "انقطاعات"}
UTILITY_WORDS = {"electricite", "eau", "courant", "الكهرباء", "الماء", "المياه", "التيار"}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", unquote(text).lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^\w؀-ۿ]+", " ", text).strip()


# Words that mean "this is about something else" (plans, money, projects, crime...), even if STEG/SONEDE is named.
NOT_A_NOTICE = {"projet", "projets", "plan", "programme", "budget", "accords", "accord", "compteurs", "centrale",
                "prepayee", "jort", "audition", "auditionner", "pertes", "vol", "prison", "mesures", "capacites",
                "photovoltaique", "bct", "arp", "cmr", "site", "internet", "سجن", "السجون", "السجن"}


def looks_relevant(url: str, title: str = "") -> bool:
    """Cheap check on the link only (no download): it must name STEG/SONEDE/water/electricity AND a cut."""
    words = set(normalize(f"{url} {title}").split())
    if words & NOT_A_NOTICE:
        return False
    named = bool(words & (STRONG | UTILITY_WORDS)) or any(s in " ".join(words) for s in STRONG if " " in s)
    return named and bool(words & (CUT_WORDS | {"delestage", "zones", "concernees"}))


def find_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """[(absolute url, anchor text)] for the article-like links of a listing page, same site only."""
    from bs4 import BeautifulSoup

    host = urlparse(base_url).netloc.replace("www.", "")
    seen, found = set(), []
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        url = urljoin(base_url, a["href"]).split("#")[0]
        parts = urlparse(url)
        if parts.scheme not in ("http", "https") or parts.netloc.replace("www.", "") != host:
            continue
        if url in seen or not parts.path.strip("/") or "?s=" in url or "/tag/" in parts.path or "/category/" in parts.path:
            continue
        seen.add(url)
        found.append((url, a.get_text(" ", strip=True)))
    return found


def article_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    return "\n".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))


def text_is_outage_news(text: str) -> bool:
    """After download: long enough and at least two distinct outage keywords (the AI still decides later)."""
    if len(text) < MIN_TEXT:
        return False
    norm = normalize(text)
    hits = {w for w in (STRONG | CUT_WORDS | UTILITY_WORDS) if w in norm}
    return len(hits) >= 2


def http_get(url: str) -> str:
    import requests

    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.text


def _load_seen(path: str) -> set[str]:
    try:
        return set(json.load(open(path, encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def _save_seen(path: str, seen: set[str]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=0)
    os.replace(tmp, path)


def _known_urls_and_last_number(articles: str) -> tuple[set[str], int]:
    if not os.path.exists(articles):
        return set(), 0
    content = open(articles, encoding="utf-8").read()
    urls = set(re.findall(r"^URL: (\S+)", content, flags=re.M))
    numbers = [int(n) for n in re.findall(r"^=== ARTICLE (\d+) ===", content, flags=re.M)]
    return urls, max(numbers, default=0)


def discover(articles: str = "articles.txt", sources: list[str] | None = None, fetch=None,
             max_new: int = MAX_NEW_DEFAULT, dry_run: bool = False, seen_path: str | None = None,
             log=print) -> dict:
    """Finds new announcements and appends them to `articles`. Never raises."""
    result = {"candidates": [], "added": [], "pages_failed": 0}
    try:
        fetch = fetch or http_get
        sources = sources or SOURCES
        seen_path = seen_path or os.path.join(os.path.dirname(os.path.abspath(articles)), "discovery_seen.json")
        known, last_number = _known_urls_and_last_number(articles)
        seen = _load_seen(seen_path)

        candidates: list[tuple[str, str]] = []
        for source in sources:
            try:
                links = find_links(fetch(source), source)
            except Exception as error:  # noqa: BLE001 - one bad listing page must not stop the others
                result["pages_failed"] += 1
                log(f"discovery: listing page failed {source}: {type(error).__name__}: {' '.join(str(error).split())[:120]}")
                continue
            for url, title in links:
                if url not in known and url not in seen and url not in {c[0] for c in candidates} and looks_relevant(url, title):
                    candidates.append((url, title))
        result["candidates"] = [c[0] for c in candidates]
        if dry_run:
            return result

        blocks, new_urls = [], []
        for url, _title in candidates[:max_new]:
            try:
                text = article_text(fetch(url))
            except Exception as error:  # noqa: BLE001
                log(f"discovery: article failed {url}: {type(error).__name__}: {' '.join(str(error).split())[:120]}")
                continue                                   # not remembered: it may work next run
            seen.add(url)
            if not text_is_outage_news(text):
                log(f"discovery: not an outage notice, skipped {url}")
                continue
            last_number += 1
            blocks.append(f"=== ARTICLE {last_number} ===\nURL: {url}\n{text}\n\n")
            new_urls.append(url)
        if blocks:
            with open(articles, "a", encoding="utf-8") as f:
                f.write("".join(blocks))
        result["added"] = new_urls                         # reported only once the file really has them
        if candidates[:max_new] or blocks:
            _save_seen(seen_path, seen)
        log(f"discovery: {len(candidates)} candidate link(s), {len(result['added'])} new article(s) added")
    except Exception as error:  # noqa: BLE001 - discovery must never break the job
        log(f"discovery failed: {type(error).__name__}: {' '.join(str(error).split())[:160]}")
    return result


def sources_from_env() -> list[str] | None:
    raw = os.environ.get("OUTAGE_DISCOVER_SOURCES", "")
    return [s.strip() for s in raw.split(",") if s.strip()] or None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--articles", default="articles.txt")
    parser.add_argument("--dry-run", action="store_true", help="only print the candidate links, write nothing")
    parser.add_argument("--max", type=int, default=MAX_NEW_DEFAULT)
    parser.add_argument("--source", action="append", help="a listing page (repeat to give several)")
    args = parser.parse_args()
    result = discover(args.articles, args.source or sources_from_env(), max_new=args.max, dry_run=args.dry_run)
    for url in result["candidates"]:
        print(("candidate  " if args.dry_run else "found      ") + url)
    print(f"{len(result['candidates'])} candidate(s), {len(result['added'])} added, {result['pages_failed']} listing page(s) failed")


if __name__ == "__main__":
    main()
