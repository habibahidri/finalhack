"""Simple scraper: 1) visit the page, 2) read the HTML, 3) extract announcements.

Install once:   pip install requests beautifulsoup4
Run:            python simple_scraper.py
"""
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# The page that lists news. Change it to any news site you want to try.
PAGE = "https://www.tunisienumerique.com/"

# A link is kept if its title contains one of these words.
WORDS = ["steg", "sonede", "coupure", "الستاغ", "انقطاع"]

# Tell the website who you are (put your real email).
HEADERS = {"User-Agent": "student-project (contact: your.email@example.com)"}


# 1. Visit the website (same as opening the page in your browser)
def get_html(url):
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.text


# 2 + 3. Read the HTML and extract titles and links
def find_announcements(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for link in soup.find_all("a", href=True):
        title = link.get_text(" ", strip=True)
        if any(word in title.lower() for word in WORDS):
            found[urljoin(base_url, link["href"])] = title
    return found


# Extract the text of one announcement page
def get_article_text(url):
    soup = BeautifulSoup(get_html(url), "html.parser")
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    return "\n".join(paragraphs)


if __name__ == "__main__":
    announcements = find_announcements(get_html(PAGE), PAGE)
    print(f"{len(announcements)} announcement(s) found\n")
    for url, title in announcements.items():
        print("TITLE:", title)
        print("LINK: ", url)
        print("TEXT: ", get_article_text(url)[:500], "...\n")
