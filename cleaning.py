"""Block 3: clean the text of a scraped page (remove repeats, ads, cookie and newsletter text)."""
import re

# Ads and footers written inside a paragraph. They are cut out with regular expressions.
AD_PATTERNS = [
    r"Décrivez votre projet.*?Démarrer ma recherche\s*→\s*x",
    r"Communiquez sur le journal.*?Demander une proposition\s*→\s*x",
    r"Recevez gratuitement la NewsLetter.*$",
    r"Abonnez-vous à notre newsletter pour obtenir.*$",
    r"Vous aimez nos contenus \? Ajouter TN.*$",
]

# Lines that start with one of these (lowercase) are page furniture, not news.
BOILERPLATE_STARTS = [
    "vous aimez nos contenus", "2026-2027", "que se passe-t-il en tunisie",
    "vous vous êtes bien abonné", "protection des données", "copyright",
    "pour offrir les meilleures", "cliquez ci-dessous", "abonnez-vous à la newsletter",
    "2026 © tuniscope", "abonnez-vous à notre newsletter",
]

MIN_LINE_LENGTH = 15


def clean_text(raw: str) -> str:
    kept: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        for pattern in AD_PATTERNS:
            line = re.sub(pattern, "", line, flags=re.S).strip()
        if len(line) < MIN_LINE_LENGTH:
            continue
        if any(line.lower().startswith(start) for start in BOILERPLATE_STARTS):
            continue
        # Web pages often repeat the same paragraph inside bigger ones: skip if already contained.
        if any(line in other for other in kept):
            continue
        kept.append(line)
    return "\n".join(kept)


def parse_articles(path: str) -> list[dict]:
    """Reads the file made by read_articles.py -> [{'number', 'url', 'text'}]."""
    content = open(path, encoding="utf-8").read()
    pattern = re.compile(r"=== ARTICLE (\d+) ===\nURL: (\S+)\n(.*?)(?=\n=== ARTICLE |\Z)", re.S)
    return [
        {"number": int(m.group(1)), "url": m.group(2), "text": m.group(3).strip()}
        for m in pattern.finditer(content)
    ]
