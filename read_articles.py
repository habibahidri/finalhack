"""Reads a list of announcement pages and saves their text in articles.txt.

Run:   python read_articles.py
Then open articles.txt and paste its content to Claude.
"""
import requests
from bs4 import BeautifulSoup

# Real STEG / SONEDE announcements (French and Arabic). Add or remove lines freely.
URLS = [
    "https://www.tunisienumerique.com/steg-des-coupures-delectricite-de-13h-a-18h-voici-les-zones-concernees/",
    "https://www.tunisienumerique.com/coupures-delectricite-possibles-ce-mercredi-la-liste-des-zones-concernees/",
    "https://www.tunisienumerique.com/sonede-coupure-deau-prevue-ce-vendredi-dans-ces-zones/",
    "https://www.tunisienumerique.com/sonede-coupures-deau-programmees-dans-trois-gouvernorats/",
    "https://www.tuniscope.com/article/435701/actualites/societe/sousse-sonede-534712",
    "https://www.tuniscope.com/ar/article/436836/actu-arabe/arabe/steg-tunisie-051313",
    "https://www.tuniscope.com/ar/article/437112/actu-arabe/arabe/steg-295314",
]

# Put your real email so the website can contact you.
HEADERS = {"User-Agent": "student-project (contact: your.email@example.com)"}


def get_article_text(url):
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    return "\n".join(paragraphs)


def download(path="articles.txt", urls=None):
    urls = urls or URLS
    with open(path, "w", encoding="utf-8") as f:   # utf-8 keeps Arabic readable
        for number, url in enumerate(urls, start=1):
            try:
                text = get_article_text(url)
            except requests.RequestException as error:
                text = f"(could not download: {error})"
            f.write(f"=== ARTICLE {number} ===\nURL: {url}\n{text}\n\n")
            print(f"{number}/{len(urls)} done")


if __name__ == "__main__":
    download()
