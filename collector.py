"""Collecteur (blocs 2 et 3) : sources -> documents bruts dedupliques.

Principes :
- un adaptateur par source (un changement de mise en page ne casse qu'une source) ;
- on garde le texte nettoye + l'URL (piste d'audit), pas le HTML complet ;
- hash SHA-256 du texte normalise pour eviter les doublons exacts ;
- filtre de pertinence FR/AR AVANT stockage (la presse parle de tout).

Dependances : httpx, feedparser, trafilatura, psycopg[binary]
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
import trafilatura

log = logging.getLogger("collector")

USER_AGENT = "OutageResearchBot/0.1 (projet etudiant ESPRIT; contact: a-renseigner)"
TIMEOUT = 20.0

# ---------------------------------------------------------------- pertinence
# Mots-cles (apres normalisation). Large volontairement : le LLM tranche ensuite.
KEYWORDS = [
    # francais
    "steg", "sonede", "coupure", "coupures", "delestage", "interruption",
    "perturbation", "electricite", "eau potable", "courant",
    # arabe (sans diacritiques)
    "الستاغ", "الصوناد", "انقطاع", "قطع الكهرباء", "القطع الدوري", "الكهرباء", "الماء الصالح للشرب",
]
_KEYWORDS_NORM: list[str] = []  # rempli apres definition de normalize_text


# ----------------------------------------------------------- normalisation
_AR_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")  # tachkil + tatwil
_WS = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Minuscules, sans accents latins, sans diacritiques arabes, espaces compactes.
    Sert au hash et au filtre, pas au stockage du texte affiche."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))  # accents latins
    text = _AR_DIACRITICS.sub("", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي")
    return _WS.sub(" ", text).strip().lower()


_KEYWORDS_NORM = [normalize_text(k) for k in KEYWORDS]


def is_relevant(text: str, min_hits: int = 2) -> bool:
    """Au moins `min_hits` mots-cles distincts : evite les articles qui citent la STEG en passant."""
    norm = normalize_text(text)
    return sum(1 for k in _KEYWORDS_NORM if k in norm) >= min_hits


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------- modele
@dataclass
class RawDoc:
    source_name: str
    url: str
    title: Optional[str]
    body_text: str
    published_at: Optional[datetime] = None
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.content_hash = content_hash(self.body_text)


@dataclass
class SourceConfig:
    """Configuration d'une source. `feed_urls` et `list_urls` sont a VERIFIER a la main
    pour chaque site avant la mise en production (ouvrir la page, chercher le flux)."""
    name: str
    base_url: str
    feed_urls: list[str] = field(default_factory=list)   # flux RSS/Atom connus
    list_urls: list[str] = field(default_factory=list)   # pages de listing (secours sans RSS)
    article_url_regex: Optional[str] = None              # filtre des liens d'articles
    max_articles_per_run: int = 30


# ------------------------------------------------------------------ reseau
def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=True)


def fetch_html(client: httpx.Client, url: str) -> Optional[str]:
    try:
        r = client.get(url)
        r.raise_for_status()
        return r.text
    except httpx.HTTPError as e:
        log.warning("fetch failed %s: %s", url, e)
        return None


def extract_article(html: str, url: str) -> Optional[tuple[Optional[str], str, Optional[datetime]]]:
    """HTML -> (titre, texte, date). Trafilatura retire menus, pubs, commentaires."""
    data = trafilatura.bare_extraction(html, url=url, with_metadata=True, favor_precision=True)
    if not data:
        return None
    d = data if isinstance(data, dict) else data.as_dict()
    text = (d.get("text") or "").strip()
    if len(text) < 80:
        return None
    published = None
    if d.get("date"):
        try:
            published = datetime.fromisoformat(d["date"]).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return d.get("title"), text, published


# ---------------------------------------------------------------- adaptateurs
def discover_article_urls(client: httpx.Client, cfg: SourceConfig) -> list[str]:
    urls: list[str] = []
    for feed in cfg.feed_urls:
        parsed = feedparser.parse(feed, agent=USER_AGENT)
        urls += [e.link for e in parsed.entries if getattr(e, "link", None)]
    if not urls:  # secours : page de listing
        pattern = re.compile(cfg.article_url_regex) if cfg.article_url_regex else None
        for page in cfg.list_urls:
            html = fetch_html(client, page)
            if not html:
                continue
            for href in re.findall(r'href=["\']([^"\']+)["\']', html):
                full = urljoin(page, href)
                if urlparse(full).netloc != urlparse(cfg.base_url).netloc:
                    continue
                if pattern is None or pattern.search(full):
                    urls.append(full)
    seen, out = set(), []
    for u in urls:  # dedup en gardant l'ordre
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[: cfg.max_articles_per_run]


def collect(cfg: SourceConfig, known_urls: Optional[set[str]] = None) -> Iterable[RawDoc]:
    """Collecte une source. `known_urls` evite de re-telecharger ce qu'on a deja."""
    known_urls = known_urls or set()
    with _client() as client:
        for url in discover_article_urls(client, cfg):
            if url in known_urls:
                continue
            html = fetch_html(client, url)
            if not html:
                continue
            parsed = extract_article(html, url)
            if not parsed:
                continue
            title, text, published = parsed
            if not is_relevant(f"{title or ''}\n{text}"):
                continue
            yield RawDoc(cfg.name, url, title, text, published)


# ------------------------------------------------------------------- stockage
INSERT_SQL = """
INSERT INTO raw_documents (source_id, url, title, body_text, published_at, content_hash)
SELECT s.id, %(url)s, %(title)s, %(body_text)s, %(published_at)s, %(content_hash)s
FROM sources s WHERE s.name = %(source_name)s
ON CONFLICT (source_id, content_hash) DO NOTHING
RETURNING id;
"""


def store(conn, docs: Iterable[RawDoc]) -> tuple[int, int]:
    """Insere les documents. Retourne (nouveaux, doublons ignores)."""
    new = dup = 0
    with conn.cursor() as cur:
        for d in docs:
            cur.execute(INSERT_SQL, {
                "url": d.url, "title": d.title, "body_text": d.body_text,
                "published_at": d.published_at, "content_hash": d.content_hash,
                "source_name": d.source_name,
            })
            if cur.fetchone():
                new += 1
            else:
                dup += 1
    conn.commit()
    return new, dup


# --------------------------------------------------------------------- sources
# URLs de flux volontairement VIDES : a renseigner apres verification manuelle.
SOURCES: list[SourceConfig] = [
    SourceConfig("tunisienumerique", "https://www.tunisienumerique.com"),
    SourceConfig("mosaiquefm_ar", "https://www.mosaiquefm.net"),
    SourceConfig("tuniscope", "https://www.tuniscope.com"),
    SourceConfig("businessnews", "https://businessnews.com.tn"),
    SourceConfig("lapresse", "https://www.lapresse.tn"),
]


if __name__ == "__main__":
    import os
    import psycopg

    logging.basicConfig(level=logging.INFO)
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for cfg in SOURCES:
            if not (cfg.feed_urls or cfg.list_urls):
                log.warning("source %s sans feed_urls/list_urls : ignoree", cfg.name)
                continue
            n, d = store(conn, collect(cfg))
            log.info("%s : %d nouveaux, %d doublons", cfg.name, n, d)
