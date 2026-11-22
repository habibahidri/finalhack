"""Builds gold_extractions.json: the 7 real notices, extracted by hand (to be checked by you)."""
import json

def places(groups):
    out = []
    for region, names, sep in groups:
        out += [{"text": n.strip(), "region_group": region} for n in names.split(sep) if n.strip()]
    return out

U1 = "https://www.tunisienumerique.com/steg-des-coupures-delectricite-de-13h-a-18h-voici-les-zones-concernees/"
U2 = "https://www.tunisienumerique.com/coupures-delectricite-possibles-ce-mercredi-la-liste-des-zones-concernees/"
U3 = "https://www.tunisienumerique.com/sonede-coupure-deau-prevue-ce-vendredi-dans-ces-zones/"
U4 = "https://www.tunisienumerique.com/sonede-coupures-deau-programmees-dans-trois-gouvernorats/"
U5 = "https://www.tuniscope.com/article/435701/actualites/societe/sousse-sonede-534712"
U6 = "https://www.tuniscope.com/ar/article/436836/actu-arabe/arabe/steg-tunisie-051313"
U7 = "https://www.tuniscope.com/ar/article/437112/actu-arabe/arabe/steg-295314"

shedding = dict(is_outage_notice=True, utility="electricity", event_type="rotating_shedding",
                is_intermittent=True, list_is_exhaustive=False, restoration_without_notice=True,
                max_single_cut_hours=None, confidence=0.95)

g1 = [
 ("Grand Tunis", "Mornag, Borj Cedria, Radès, La Goulette, Ben Arous, Mégrine, El Ghazala, Mohamedia, Le Kram, Nouvelle Médina, Jardins d'El Menzah, Borj Touil, Sanhaja, Jedaida, Manouba, Aïn Zaghouan, Ennasr, La Soukra", ","),
 ("Nord - Cap Bon", "Hammam Ghezaz, Hammamet, Menzel Bouzelfa, Menzel Temime, Soliman, Takelsa, Béni Khalled, Béni Khiar, Somâa, Nabeul, Korba, Dar Chaâbane, Tazarka, Maâmoura, Kélibia", ","),
 ("Nord - Zaghouan", "Zaghouan Nord, El Fahs, Bou Achir, Zriba, Jebel Oust, Bir Mcherga, Nadhour", ","),
 ("Nord - Bizerte", "Ghar El Melh, Utique, Sejnane, El Khetmine, Mateur, Metline, Menzel Jemil, Menzel Bourguiba, Ghazala, Tinja, Zarzouna, Menzel Abderrahmane, Zouaouine, Aousja", ","),
 ("Nord-Ouest", "Ghardimaou, Nefza, Gaâfour, Chemtou, Oued Meliz, Nebeur, Touiref, Ouchtata, Rouhia, Bou Salem, Goubellat, Kalaat Khasba, Sidi Ismaïl, Makthar", ","),
 ("Centre", "Ksar Hellal, Sayada, Zaouiet Kontoch, Bou Hajla, Nasrallah, Menzel Mhiri, Sbiba, Chorbane, Souwassi, S'haylat, Bekalta, Rejiche, Zone industrielle d'El Jem, Enfidha, Sidi Bou Ali, Kalaa Kebira, Riadh, Ouled Achour, Jemmal, Bennane, Sahline, Msaken, Hergla, Bouficha, Kerker, El Ala, Zone industrielle d'Enfidha, Hammam Sousse, Cité universitaire Sousse, Akouda, Kalaa Seghira, Menzel Kamel, Moknine, Chebba, Khezama, Sahloul 3, Ouled Chamekh, Chtouine, Bouhjar", ","),
 ("Sfax", "Menzel Chaker, Sfax Sud, Sakiet Ezzit, Sakiet Eddaïer, Bir Ali, Mahres, Agareb, El Amra, Thyna, Sfax Ouest, Sfax Ville, Jebiniana, El Hencha", ","),
 ("Sud - Gabès", "Gabès-ville, El Menzel, Jara, Cité El Amal, Chamati, Chenini, Bouchema, El Hamma, Mareth, Oudhref, Métouia", ","),
 ("Sud - Djerba", "Houmt Souk, Midoun, El Tlalet, Jorf, Guellala, El May, Robbana, Sedouikech, Aghir", ","),
 ("Sud - Kébili", "Kébili, Nezla, Cité route de Gabès, Souk Lahad, Jemna, Douz, Faouar, Kalaa, Zaafrane, Nouil", ","),
 ("Sud - Tataouine", "Tataouine Nouvelle, Tataouine-ville, Cité El Mahrajene, Smar, Bir Lahmar, Ghomrassen, Remada, Zahra", ","),
 ("Sud - Zarzis-Ben Guerdane", "El Hicham, Mouensa, Souihel, Zaouia, Bsatine, Chehbaniya, Nefatia, Cité Mars, route de Ras Jedir", ","),
 ("Sud - Médenine", "Dergoulia, Hassi Amor, Médenine-ville, Béni Khedache, Bou Ghrara, Harich, Ragouba", ","),
 ("Sud-Ouest", "El Hamma, Lejred, Boudrias, Chebiba, Degueche, El Gallel, Souk Jedid, Chrayaa, Lahmar, Mekarem, Chkhar, Nouaiel, Majel Bel Abbès, Alanda, Nasrallah, Fouchana, Hichria, Ouled Haffouz, Laâyoune, Hazoua, Hassi El Ferid, Ouled Hamed, Oum Ladhame, El Haguene, Mazouna, Nefta", ","),
]
g2 = [
 ("Grand Tunis", "Ezzahra, Borj Cedria, Le Kram, Hammam-Lif, Jardins d'El Menzah, Les Berges du Lac, La Manouba, La Goulette, El Mourouj, Ben Arous, Mégrine, Aïn Zaghouan, Ennasr, La Soukra, Sidi Fredj, Nouvelle Médina, Borj Touil, Sanhaja, Jedeida", ","),
 ("Nord - Cap Bon", "Kélibia, Nabeul, Hammamet, Menzel Bouzelfa, Menzel Temime, Soliman, Takelsa, Somâa, Korba, Dar Chaâbane, Tazarka, Maâmoura, Béni Khalled, Béni Khiar, Hammam Ghezèze", ","),
 ("Nord - Zaghouan", "Jebel Oust, Zriba, Bir Mcherga, Nadhour, Zaghouan Nord, El Fahs, Bouachir", ","),
 ("Nord - Bizerte", "Zarzouna, Ghazala, Menzel Bourguiba, Tinja, Menzel Abderrahmane, Zaouaouine, Aousja, Ghar El Melh, Utique, Sejnane, Khetmine, Mateur, Menzel Jemil, Metline", ","),
 ("Nord-Ouest", "Ghardimaou, Nefza, Gaâfour, Chemtou, Oued Meliz, Nebeur, Téboursouk, Ouchtata, Rouhia, Bousalem, Goubellat, Kalaat Khasba, Sidi Ismaïl, Makthar", ","),
 ("Centre", "Ksar Hellal, Sayada, Zaouiet Kontoch, Bouhajla, Nasrallah, Menzel Mhiri, Sbiba, Cherbane, Souassi, Souehla, Bekalta, Rejiche, Zone industrielle d'El Jem, Enfidha, Sidi Bou Ali, Kalâa Kebira, Riadh, Ouled Achour, Jemmal, Bennane, Sahline, M'saken, Hergla, Bouficha, Kerker, El Alâa, Zone industrielle d'Enfidha, Hammam Sousse, Cité universitaire de Sousse, Akouda, Kalâa Seghira, Menzel Kamel, Moknine, Chebba, Khezama, Sahloul 3, Ouled Chamekh, Chetouine, Bouhjar", ","),
 ("Sfax", "Menzel Chaker, Sfax Sud, Sakiet Ezzit, Sakiet Eddaïer, Bir Ali Ben Khalifa, Mahrès, Agareb, El Amra, Thyna, Sfax Ouest, Sfax-ville, Jebeniana, El Hencha", ","),
 ("Sud - Gabès", "Cité El Izdehar, Cité Ezzouhour, El Menzel, Jara, Oudhref, Métouia, Menzel Habib, El Hamma, Mareth, Matmata", ","),
 ("Sud - Djerba", "Houmt Souk, Midoun, Aghir, Sedouikech, Sakia, Guellala, El Tlat, Robbana", ","),
 ("Sud - Kébili", "Nezla, Souk Lahad, Kébili, Jemna, Douz, El Golâa, Faouar, Zaafrane, Noueil", ","),
 ("Sud - Tataouine", "Tataouine Nouvelle, Cité El Mahrajène, Smar, Ghomrassen, Bir Lahmar, Remada, Dhehiba, Ezzahra", ","),
 ("Sud - Zarzis-Ben Guerdane", "Chammakh, Bassatine, Mouensa, Souihel, Jallel, Cité Mars, Neffatia, Chahbania", ","),
 ("Sud - Médenine", "Cité Ennour, Dergoulia, Boughrara, Hricha, Béni Khedache, Hassi Amor, Souitir", ","),
 ("Sud-Ouest", "El Hamma, Lejrad, Boudrias, Chebiba, Degueche, Gallel, Souk Jedid, Chrayâa, Lahmar, Mekarem, Chkhar, Nouaïel, Majel Bel Abbès, El Alenda, Nasrallah, Fouchana, Hichria, Ouled Haffouz, Laâyoune, Hazoua, Hassi El Ferid, Ouled Hamed, Oum Ladhame, Hagne, Mezzouna, Nefta", ","),
]
ar6 = "فوشانة، المغيرة، برج السدرية، حي التضامن، سكرة، المروج، مقرين، رادس، الزهراء، حمام الأنف، بومهل، بيرين، أريانة، دوار هيشر، المرسى، برج الطويل، المنازه، المنارات، عين زغوان، حدائق قرطاج، قصر السعيد، الكرم، حلق الوادي، طبربة، الجديدة، سيدي ثابت"
ar7 = "المروج، بن عروس، منوبة، عين زغوان، قمرت، صنهاجة، المحمدية، الجديدة، البحيرة"

gold = {
 U1: {"notices": [dict(shedding, places=places(g1), window_start="2026-09-01T13:00:00+01:00",
        window_end="2026-09-01T18:00:00+01:00", reason="equilibre production/consommation")]},
 U2: {"notices": [dict(shedding, places=places(g2), window_start="2026-09-02T12:00:00+01:00",
        window_end="2026-09-02T17:00:00+01:00", reason="equilibre production/consommation")]},
 U3: {"notices": [dict(is_outage_notice=True, utility="water", event_type="water_works", confidence=0.95,
        places=places([("Sousse - Enfidha", "Gremit El Gharbia, El Ghoualif, Sidi Saïdane, Ouled Blel, Al Smaïdia", ",")]),
        window_start="2026-07-10T06:00:00+01:00", expected_restoration="2026-07-10T16:00:00+01:00",
        reason="raccordement d'un nouveau reservoir")]},
 U4: {"notices": [dict(is_outage_notice=True, utility="water", event_type="water_regulation", confidence=0.95,
        places=[{"text": t, "region_group": "Sahel", "level_hint": "gouvernorat"} for t in ("Sousse", "Monastir", "Mahdia")],
        window_start="2026-07-05T00:00:00+01:00", window_end="2026-07-05T05:00:00+01:00", recurrence="daily",
        reason="remplissage des reservoirs, essais de la station de dessalement de Sousse")]},
 U5: {"notices": [dict(is_outage_notice=True, utility="water", event_type="water_works", confidence=0.95,
        places=places([("Sousse - Enfidha", "Grimita El Gharbia, Ghoualif, Sidi Saïdane, Ouled Blel, Essmaïdia", ",")]),
        window_start="2026-07-10T06:00:00+01:00", expected_restoration="2026-07-10T16:00:00+01:00",
        reason="raccordement d'un nouveau reservoir")]},
 U6: {"notices": [dict(shedding, places=places([("Grand Tunis", ar6, "،")]), window_may_extend=True,
        window_start="2026-07-23T11:00:00+01:00", window_end="2026-07-23T17:00:00+01:00",
        reason="التوازن بين الإنتاج والاستهلاك")]},
 U7: {"notices": [dict(shedding, places=places([("Grand Tunis", ar7, "،")]), window_may_extend=True,
        window_start="2026-07-27T13:00:00+01:00", window_end="2026-07-27T17:00:00+01:00",
        reason="التوازن بين الإنتاج والاستهلاك")]},
}
with open("gold_extractions.json", "w", encoding="utf-8") as f:
    json.dump(gold, f, ensure_ascii=False, indent=1)
print("gold_extractions.json written:", {u.split('/')[-1][:30]: sum(len(n['places']) for n in v['notices']) for u, v in gold.items()})
