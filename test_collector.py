"""Tests hors ligne du collecteur (aucun acces reseau). Lancer : python test_collector.py"""
from collector import (
    RawDoc, normalize_text, content_hash, is_relevant, extract_article, store,
)

# Textes synthetiques inspires du format des avis (pas de copie d'articles)
FR = ("La STEG informe ses clients que des coupures periodiques d'electricite pourraient etre "
      "effectuees ce lundi entre 13h00 et 17h00, a intervalles intermittents. Le courant pourra "
      "etre retabli sans preavis. Zones : Ezzahra, Le Kram, Borj Cedria.")
AR = ("أعلنت الشركة التونسية للكهرباء والغاز «الستاغ» إمكانية اللجوء إلى القطع الدوري للكهرباء "
      "اليوم بين الساعة الواحدة والخامسة مساءً في المناطق التالية: المروج، رادس، أريانة.")
NOISE = "Le Club Africain s'impose 2-1 contre l'Etoile du Sahel lors de la derniere journee."
PASSING = "Le ministre a cite la STEG lors d'une conference sur le tourisme."


def test_normalize():
    assert normalize_text("  Gabès  ÉLECTRICITÉ ") == "gabes electricite"
    assert normalize_text("الكَهرَبَاء") == normalize_text("الكهرباء")      # diacritiques arabes
    assert normalize_text("أريانة") == normalize_text("اريانة")              # variantes d'alef


def test_hash_stable_and_distinct():
    assert content_hash(FR) == content_hash("  " + FR.upper() + " ")        # casse/espaces ignores
    assert content_hash(FR) != content_hash(AR)


def test_relevance():
    assert is_relevant(FR) and is_relevant(AR)
    assert not is_relevant(NOISE)
    assert not is_relevant(PASSING)                                          # 1 seul mot-cle


def test_extract_article():
    html = f"""<html><head><title>Coupures STEG</title></head><body>
      <nav>Accueil | Sport | Contact</nav>
      <article><h1>Coupures d'electricite possibles</h1><p>{FR}</p><p>{FR}</p></article>
      <footer>Tous droits reserves</footer></body></html>"""
    res = extract_article(html, "https://example.test/a")
    assert res is not None
    title, text, _ = res
    assert "STEG" in text and "Tous droits reserves" not in text
    assert extract_article("<html><body><p>court</p></body></html>", "https://example.test/b") is None


class FakeCursor:
    """Simule ON CONFLICT DO NOTHING : fetchone() -> None si (source, hash) deja vu."""
    def __init__(self, seen): self.seen, self._row = seen, None
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, p):
        key = (p["source_name"], p["content_hash"])
        self._row = None if key in self.seen else (len(self.seen) + 1,)
        self.seen.add(key)
    def fetchone(self): return self._row


class FakeConn:
    def __init__(self): self.seen, self.committed = set(), False
    def cursor(self): return FakeCursor(self.seen)
    def commit(self): self.committed = True


def test_store_dedup():
    docs = [
        RawDoc("tunisienumerique", "https://x/1", "t", FR),
        RawDoc("tunisienumerique", "https://x/2", "t", FR.upper()),   # meme contenu, autre URL
        RawDoc("mosaiquefm_ar", "https://y/1", "t", AR),
        RawDoc("mosaiquefm_ar", "https://z/1", "t", FR),              # meme texte, autre source : garde
    ]
    conn = FakeConn()
    assert store(conn, docs) == (3, 1) and conn.committed


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(name, "OK")
