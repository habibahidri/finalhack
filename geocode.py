"""Block 5: place names -> canonical places.

No GIS and no database: names are normalized (accents, Arabic marks, "El/Al/La/Le" prefixes,
spaces and hyphens) and matched with fuzzy matching. The same place written in different ways
("Gremit El Gharbia" / "Grimita El Gharbia") or in Arabic and French ends up with the same key.

Limits (to improve later with an official list of governorates / delegations / localities):
- no hierarchy yet (governorate > delegation > locality);
- two different places can share a name (for example "El Hamma" in Gabès and in the Sud-Ouest):
  we keep every region where a name was seen and flag the name as ambiguous.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Optional

from rapidfuzz import fuzz, process

_ARABIC_MARKS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_LEADING_ARTICLES = ("el ", "al ", "la ", "le ", "les ", "l ")
FUZZY_THRESHOLD = 90
MIN_FUZZY_LENGTH = 5  # very short names are only matched exactly

# Arabic name -> French display name (only the ones I am sure about; others stay unresolved).
ARABIC_SEED = {
    "فوشانة": "Fouchana", "المغيرة": "El Mghira", "برج السدرية": "Borj Sedria",
    "حي التضامن": "Hay Ettadhamen", "سكرة": "La Soukra", "المروج": "El Mourouj",
    "مقرين": "Mokrine", "رادس": "Radès", "الزهراء": "Ezzahra", "حمام الأنف": "Hammam Lif",
    "بومهل": "Boumhel", "أريانة": "Ariana", "دوار هيشر": "Douar Hicher", "المرسى": "La Marsa",
    "برج الطويل": "Borj Touil", "المنازه": "El Menzah", "عين زغوان": "Aïn Zaghouan",
    "حدائق قرطاج": "Jardins de Carthage", "قصر السعيد": "Ksar Saïd", "الكرم": "Le Kram",
    "حلق الوادي": "La Goulette", "طبربة": "Tebourba", "الجديدة": "Jedaida",
    "سيدي ثابت": "Sidi Thabet", "بن عروس": "Ben Arous", "منوبة": "Manouba",
    "قمرت": "Gammarth", "صنهاجة": "Sanhaja", "المحمدية": "Mohamedia",
    "البحيرة": "Les Berges du Lac", "سوسة": "Sousse", "صفاقس": "Sfax", "قابس": "Gabès",
    "مدنين": "Médenine", "المنستير": "Monastir", "المهدية": "Mahdia", "جربة": "Djerba",
    # more well-known names (sign-up place search needs a full list later)
    "مرناق": "Mornag", "حمام سوسة": "Hammam Sousse", "نابل": "Nabeul", "الحمامات": "Hammamet",
    "قليبية": "Kélibia", "قربة": "Korba", "نفطة": "Nefta", "دوز": "Douz", "ميدون": "Midoun",
    "حومة السوق": "Houmt Souk", "قبلي": "Kébili", "مارث": "Mareth", "مطماطة": "Matmata",
    "المكنين": "Moknine", "الشابة": "Chebba", "مساكن": "M’saken", "أكودة": "Akouda",
    "النفيضة": "Enfidha", "تازركة": "Tazarka", "منزل تميم": "Menzel Temime",
    "منزل بورقيبة": "Menzel Bourguiba",
}

# Spelling variants that are too different for fuzzy matching (name written in the notices).
EXTRA_ALIASES = {
    "El Tlalet": ["El Tlat"],
    "El Haguene": ["Hagne"],
    "Mazouna": ["Mezzouna"],
    "Hammam Ghezaz": ["Hammam Ghezèze"],
    "Harich": ["Hricha"],
    "Ouled Blel": ["Ouled Belel"],
    "Essmaïdia": ["Al Smaïdia", "Smaïdia"],
    "Gremit El Gharbia": ["Grimita El Gharbia"],
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _ARABIC_MARKS.sub("", text)
    text = text.replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"[-'’`.]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def match_key(text: str) -> str:
    words = [w[2:] if re.match(r"^ال\w", w) else w for w in normalize(text).split(" ")]
    text = " ".join(words)
    for article in _LEADING_ARTICLES:
        if text.startswith(article):
            text = text[len(article):]
            break
    return text.replace(" ", "")


class PlaceRegistry:
    def __init__(self, threshold: int = FUZZY_THRESHOLD):
        self.threshold = threshold
        self.places: dict[str, dict] = {}   # canonical key -> {name, aliases, regions}
        self.index: dict[str, str] = {}     # match key -> canonical key

    @classmethod
    def seeded(cls) -> "PlaceRegistry":
        registry = cls()
        for arabic, french in ARABIC_SEED.items():
            registry.add(french, aliases=[arabic])
        for name, aliases in EXTRA_ALIASES.items():
            registry.add(name, aliases=aliases)
        return registry

    def add(self, name: str, aliases=(), region: Optional[str] = None) -> str:
        key = self.index.get(match_key(name)) or match_key(name)
        place = self.places.setdefault(key, {"name": name, "aliases": [], "regions": []})
        for alias in (name, *aliases):
            self.index[match_key(alias)] = key
            if alias not in place["aliases"]:
                place["aliases"].append(alias)
        if region and region not in place["regions"]:
            place["regions"].append(region)
        return key

    def lookup(self, text: str) -> Optional[str]:
        """Finds the canonical key of a name without creating anything."""
        key = match_key(text)
        if key in self.index:
            return self.index[key]
        if len(key) >= MIN_FUZZY_LENGTH:
            best = process.extractOne(key, list(self.index), scorer=fuzz.ratio, score_cutoff=self.threshold)
            if best:
                return self.index[best[0]]
        return None

    def resolve(self, text: str, region: Optional[str] = None) -> dict:
        found = self.lookup(text)
        if found is None:
            key, is_new = self.add(text, region=region), True
        else:
            key, is_new = found, False
            self.add(self.places[key]["name"], aliases=[text], region=region)
            self.index[match_key(text)] = key
        place = self.places[key]
        return {
            "raw": text, "key": key, "name": place["name"], "region": region, "new": is_new,
            "ambiguous": len(place["regions"]) > 1,
        }

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"places": self.places}, f, ensure_ascii=False, indent=1)
