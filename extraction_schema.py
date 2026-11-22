"""Schema d'extraction (bloc 4) : un avis de coupure -> donnees structurees.

Le LLM remplit ce modele ; Pydantic le valide. Les dates relatives
("ce lundi", "demain") sont resolues par rapport a `reference_date`
(date de publication de l'article), fuseau Africa/Tunis (UTC+1).
"""
from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class Utility(str, Enum):
    electricity = "electricity"
    water = "water"


class EventType(str, Enum):
    maintenance = "maintenance"              # travaux planifies, heures precises
    rotating_shedding = "rotating_shedding"  # delestage tournant, creneau large
    heatwave_incident = "heatwave_incident"  # coupure non annoncee (charge/canicule)
    water_works = "water_works"              # travaux SONEDE
    water_regulation = "water_regulation"    # regulation quotidienne SONEDE
    water_incident = "water_incident"        # panne


ELECTRICITY_TYPES = {EventType.maintenance, EventType.rotating_shedding, EventType.heatwave_incident}
WATER_TYPES = {EventType.water_works, EventType.water_regulation, EventType.water_incident}


class PlaceMention(BaseModel):
    """Un nom de lieu tel qu'ecrit dans l'avis. Jamais de coordonnees :
    le geocodage (bloc 5) se fait uniquement avec le gazetteer."""
    text: str = Field(description="Nom exact du lieu dans le texte (arabe ou francais)")
    region_group: Optional[str] = Field(
        default=None,
        description="Groupe de region si l'avis en donne un : Grand Tunis, Nord, Nord-Ouest, "
                    "Centre, Sfax, Sud, Sud-Ouest, Cap Bon, etc.",
    )
    level_hint: Optional[str] = Field(
        default=None, description="gouvernorat | delegation | locality, si deductible du texte"
    )
    exclusions: list[str] = Field(
        default_factory=list,
        description="Sous-zones explicitement exclues (ex. 'sauf Menzel Hayet')",
    )


class PlaceGroup(BaseModel):
    """Un groupe de lieux d'une meme region : le nom de la region est ecrit une seule fois."""
    region_group: Optional[str] = Field(
        default=None, description="Nom de la region/zone tel que donne par l'avis (en francais)"
    )
    names: list[str] = Field(description="Noms des localites de cette region, recopies tels qu'ecrits")
    level_hint: Optional[str] = Field(
        default=None, description="gouvernorat | delegation | locality, si tous les noms sont du meme niveau"
    )
    exclusions: list[str] = Field(default_factory=list, description="Sous-zones explicitement exclues")


class OutageExtraction(BaseModel):
    is_outage_notice: bool = Field(
        description="False si le texte ne contient aucun avis de coupure (commentaire, politique...)"
    )
    utility: Optional[Utility] = None
    event_type: Optional[EventType] = None

    places: list[PlaceMention] = Field(default_factory=list)          # filled from place_groups
    place_groups: list[PlaceGroup] = Field(
        default_factory=list, description="Les lieux touches, groupes par region (une entree par region)"
    )

    window_start: Optional[datetime] = Field(
        default=None, description="Debut du creneau, ISO 8601 avec fuseau +01:00"
    )
    window_end: Optional[datetime] = Field(
        default=None,
        description="Fin de la periode de coupure annoncee. Null si l'avis ne donne que l'heure de retour du service",
    )
    max_single_cut_hours: Optional[float] = Field(
        default=None, ge=0, description="Duree max d'une coupure (ex. 2 pour 'ne depassant pas deux heures')"
    )
    is_intermittent: bool = Field(
        default=False, description="True si 'par intermittence' / 'a intervalles intermittents'"
    )
    list_is_exhaustive: bool = Field(
        default=False, description="True seulement si le texte dit que la liste est complete"
    )
    expected_restoration: Optional[datetime] = Field(
        default=None, description="Heure de retour du service si elle est donnee (ex. 'des 16h00')"
    )
    restoration_without_notice: bool = Field(
        default=False, description="True si 'retablissement sans preavis'"
    )
    window_may_extend: bool = Field(
        default=False, description="True si l'avis dit que les coupures peuvent depasser le creneau annonce"
    )
    recurrence: Optional[str] = Field(
        default=None, description="'daily' si la coupure se repete chaque jour (regulation), sinon null"
    )
    reason: Optional[str] = Field(default=None, description="Motif en une phrase courte, langue du texte")

    confidence: float = Field(ge=0, le=1, description="Certitude de l'extraction, pas de la coupure")
    notes: Optional[str] = Field(default=None, description="Ambiguites rencontrees")

    @model_validator(mode="after")
    def _coherence(self) -> "OutageExtraction":
        if self.place_groups:                                   # expand the compact format
            seen = {(p.text, p.region_group) for p in self.places}
            for group in self.place_groups:
                for name in group.names:
                    name = name.strip()
                    if name and (name, group.region_group) not in seen:   # no duplicates
                        seen.add((name, group.region_group))
                        self.places.append(PlaceMention(
                            text=name, region_group=group.region_group,
                            level_hint=group.level_hint, exclusions=group.exclusions,
                        ))
            self.place_groups = []
        if not self.is_outage_notice:
            return self
        if self.utility is None or self.event_type is None:
            raise ValueError("utility et event_type sont obligatoires pour un avis de coupure")
        allowed = ELECTRICITY_TYPES if self.utility == Utility.electricity else WATER_TYPES
        if self.event_type not in allowed:
            raise ValueError(f"event_type {self.event_type.value} incompatible avec {self.utility.value}")
        if not self.places:
            raise ValueError("au moins un lieu est requis")
        if self.window_start and self.window_end and self.window_end < self.window_start:
            raise ValueError("window_end avant window_start")
        return self


class ExtractionBatch(BaseModel):
    """Sortie attendue du LLM : un article peut contenir plusieurs avis distincts."""
    notices: list[OutageExtraction]


SYSTEM_PROMPT = """Tu extrais des avis de coupure d'electricite (STEG) et d'eau (SONEDE) en Tunisie.
Les textes sont en arabe ou en francais. Reponds uniquement avec le JSON demande.

Regles :
- Resous les dates relatives avec reference_date. Fuseau Africa/Tunis (+01:00).
- N'invente jamais un lieu, une heure ou une duree absents du texte : laisse null.
- Ne donne jamais de coordonnees. Recopie les noms de lieux tels qu'ecrits.
- Types electricite : maintenance (travaux, heures et quartiers precis) ; rotating_shedding
  (coupures periodiques/tournantes sur un creneau large, liste non definitive) ;
  heatwave_incident (coupure non annoncee a l'avance).
- Types eau : water_works (travaux, debut et retour prevus) ; water_regulation (programme
  quotidien recurrent) ; water_incident (panne soudaine).
- Un creneau comme "13h-17h" n'est PAS une coupure continue : renseigne max_single_cut_hours
  et is_intermittent si le texte le dit.
- window_may_extend=true si le texte dit que la periode peut etre depassee ; recurrence="daily"
  si la coupure se repete chaque jour.
- Si le texte n'est pas un avis de coupure, mets is_outage_notice=false.
- Renvoie {"notices": [...]} : un objet par avis distinct (un seul si l'article n'en contient qu'un).
  Toujours renseigner utility et event_type pour un avis de coupure.
- Lieux : utilise place_groups, UNE entree par region : {"region_group": "Grand Tunis",
  "names": ["Ezzahra", "Le Kram", ...]}. Ecris le nom de la region une seule fois, pas pour chaque lieu.
  region_group en francais (Grand Tunis, Cap Bon, Nord-Ouest, Centre, Sfax, Sud, Sud-Ouest...).
- Chaque nom est une localite precise, recopiee telle qu'ecrite : n'en oublie aucune, ne repete aucun nom.
  Si des localites precises sont donnees, n'ajoute PAS la delegation ou le gouvernorat cite comme cadre
  geographique (par exemple "Enfidha" ou "Sousse") : mets-le dans region_group.
  Si l'avis ne donne que des gouvernorats (par exemple Sousse, Monastir, Mahdia), ce sont les noms.
- window_start / window_end = debut et fin de la periode de coupure annoncee. Si l'avis donne un debut et
  seulement une heure de retour du service ("reprise a partir de 16h00"), mets cette heure dans
  expected_restoration et laisse window_end a null.
"""

EXAMPLE_ANSWER = {
    "notices": [{
        "is_outage_notice": True,
        "utility": "electricity",
        "event_type": "rotating_shedding",
        "place_groups": [
            {"region_group": "Grand Tunis", "names": ["Ezzahra", "Le Kram"]},
            {"region_group": "Sfax", "names": ["Sfax Sud", "Mahres"]},
        ],
        "window_start": "2026-09-01T13:00:00+01:00",
        "window_end": "2026-09-01T18:00:00+01:00",
        "max_single_cut_hours": None,
        "is_intermittent": True,
        "list_is_exhaustive": False,
        "expected_restoration": None,
        "restoration_without_notice": True,
        "window_may_extend": False,
        "recurrence": None,
        "reason": "equilibre production/consommation",
        "confidence": 0.95,
        "notes": None,
    }]
}


def build_system_prompt() -> str:
    """Rules + the exact JSON Schema + one example, so the model uses our field names."""
    schema_dict = ExtractionBatch.model_json_schema()
    # The model fills place_groups only; "places" is built by our code from them.
    schema_dict["$defs"]["OutageExtraction"]["properties"].pop("places", None)
    schema_dict["$defs"].pop("PlaceMention", None)
    schema = json.dumps(schema_dict, ensure_ascii=False, separators=(",", ":"))
    example = json.dumps(EXAMPLE_ANSWER, ensure_ascii=False)
    return (
        SYSTEM_PROMPT
        + "\nFormat de reponse : un objet JSON qui respecte exactement ce JSON Schema "
        + "(memes noms de champs, aucun champ en plus) :\n"
        + schema
        + "\n\nExemple de reponse valide :\n"
        + example
        + "\n"
    )
