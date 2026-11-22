"""Exports what the FARMER screen needs, as one JSON file (the contract between our code and the design).

  python export_farmer_view.py events.json            -> farmer_view.json

Every alert carries its own explanation ("why"), the assumptions made, and the sources, so the screen can show
WHY we say something, not only WHAT. Texts are in French (the farmer's language); keys are English and stable.
"""
import json
import sys
from datetime import timedelta
from urllib.parse import urlparse

from events import status_at
import texts_ar
from farm import DEMO_FARMS, _is_estimated, farm_impacts, load_events
from geocode import PlaceRegistry

STATUS = {"high": "action", "medium": "watch", "low": "info"}       # what the screen should emphasise
STATUS_TEXT = {"action": "A faire maintenant", "watch": "A surveiller", "info": "Pour information",
               "clear": "Rien a signaler"}


def _source_name(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.")


def _headline(farm, event, cut_hours, lang="fr") -> str:
    if lang == "ar":
        return texts_ar.headline(farm, event)
    what = "Coupure d'eau" if event.utility == "water" else "Coupure d'electricite"
    if event.event_type == "rotating_shedding":
        what += " tournante"
    when = f"le {event.window_start:%d/%m} de {event.window_start:%Hh} a {event.window_end:%Hh}" \
        if event.window_start and event.window_end else (f"le {event.window_start:%d/%m} des {event.window_start:%Hh}"
                                                          if event.window_start else "bientot")
    return f"{what} {when} a {farm.locality}"


def _why_ar(farm, event, impact) -> list[dict]:
    estimated = _is_estimated(event)
    reasons = [
        {"key": "source", "title": "من أين جاءت المعلومة",
         "detail": f"إعلان منشور في {'، '.join(_source_name(u) for u in event.sources)}. "
                   f"قراءة آلية، درجة الثقة في الاستخراج: {round(event.confidence * 100)}٪."},
        {"key": "place", "title": "لماذا مزرعتك معنية",
         "detail": (f"«{farm.locality}» مذكورة في الإعلان." if impact.match == "listed" else
                    f"«{farm.locality}» غير مذكورة لكن قائمة الإعلان غير نهائية: قد تتأثر منطقتك أيضا.")},
        {"key": "duration", "title": "المدة المتوقعة",
         "detail": (f"{impact.cut_hours:g} ساعة (تقدير: الإعلان يعطي فترة واسعة وليس انقطاعا متواصلا)."
                    if estimated else f"{impact.cut_hours:g} ساعة حسب الإعلان.")},
    ]
    if impact.mode == "smart_plan":
        reserve = farm.water_autonomy() if event.utility == "water" else farm.power_autonomy()
        what = "الخزان يدوم" if event.utility == "water" else "البطارية تدوم"
        verdict = "يكفي" if impact.covered else "لا يكفي"
        reasons.append({"key": "reserve", "title": "احتياطيك",
                        "detail": f"حسب الحساسات، {what} نحو {reserve:g} ساعة: وهذا {verdict} لهذا الانقطاع."})
    else:
        reasons.append({"key": "reserve", "title": "احتياطيك",
                        "detail": "لا توجد حساسات: لا نعرف مستوى الخزان أو البطارية، لذلك نعطي نصائح عامة."})
    decided = [f"{r['equipment']}: {r['decision_ar']}" for r in impact.plan if r.get("decision_ar")]
    if decided:                       # the agents disagreed: the farmer can see who won and why
        reasons.append({"key": "decisions", "title": "كيف قررنا", "detail": " | ".join(decided)})
    reasons.append({"key": "probability", "title": "احتمال أن تتأثر",
                    "detail": f"نحو {round(impact.probability * 100)}٪. "
                              + ("منطقتك مذكورة لكن الانقطاع يتناوب: ليست كل المناطق في كل ساعة."
                                 if event.event_type == "rotating_shedding" and impact.match == "listed" else
                                 "حساب بسيط: المكان مذكور أم لا، نوع الانقطاع، وموثوقية المصدر.")})
    return reasons


def _uses_generator(impact) -> bool:
    return any(row.get("action") == "Generator" and row.get("affected") for row in impact.plan)


def _assumptions_ar(event, impact) -> list[str]:
    notes = []
    if _is_estimated(event):
        notes.append("مدة الانقطاع مقدّرة بساعتين: الإعلان لا يذكر حدا أقصى.")
    if event.restoration_without_notice:
        notes.append("قد يعود التيار دون إشعار.")
    if event.window_may_extend:
        notes.append("قد تتجاوز الانقطاعات الفترة المعلنة.")
    if not event.list_is_exhaustive:
        notes.append("قائمة المناطق غير نهائية.")
    if impact.mode == "general_sms":
        notes.append("مستوى الخزان والبطارية غير معروف (مزرعة بدون حساسات).")
    if _uses_generator(impact):
        notes.append("نفترض أن المولّد جاهز ووقوده كافٍ للأجهزة المذكورة.")
    return notes


def _why(farm, event, impact) -> list[dict]:
    estimated = _is_estimated(event)
    reasons = [
        {"key": "source", "title": "D'ou vient l'information",
         "detail": f"Avis publie par {', '.join(_source_name(u) for u in event.sources)}. "
                   f"Lecture automatique, fiabilite de l'extraction : {round(event.confidence * 100)} %."},
        {"key": "place", "title": "Pourquoi votre ferme est concernee",
         "detail": (f"« {farm.locality} » est cite dans l'avis." if impact.match == "listed" else
                    f"« {farm.locality} » n'est pas cite, mais la liste de l'avis n'est pas complete : "
                    "votre zone peut etre touchee aussi.")},
        {"key": "duration", "title": "Duree a prevoir",
         "detail": (f"{impact.cut_hours:g} h (estimation : l'avis donne un creneau large, pas une coupure continue)."
                    if estimated else f"{impact.cut_hours:g} h d'apres l'avis.")},
    ]
    if impact.mode == "smart_plan":
        reserve = farm.water_autonomy() if event.utility == "water" else farm.power_autonomy()
        what = "le reservoir" if event.utility == "water" else "la batterie"
        verdict = "suffit" if impact.covered else "ne suffit pas"
        reasons.append({"key": "reserve", "title": "Votre reserve",
                        "detail": f"Selon vos capteurs, {what} dure environ {reserve:g} h : cela {verdict} pour cette coupure."})
    else:
        reasons.append({"key": "reserve", "title": "Votre reserve",
                        "detail": "Pas de capteur : nous ne connaissons pas le niveau de votre reservoir ou batterie, "
                                  "donc nous donnons des conseils generaux."})
    decided = [f"{r['equipment']} : {r['decision']}" for r in impact.plan if r.get("decision")]
    if decided:
        reasons.append({"key": "decisions", "title": "Comment nous avons decide", "detail": " | ".join(decided)})
    reasons.append({"key": "probability", "title": "Chance d'etre touche",
                    "detail": f"Environ {round(impact.probability * 100)} %. "
                              + ("Votre zone est citee mais les coupures tournent : pas toutes les zones a toutes les heures."
                                 if event.event_type == "rotating_shedding" and impact.match == "listed" else
                                 "Calcul simple : lieu cite ou non, type de coupure, fiabilite de la source.")})
    return reasons


def _assumptions(event, impact) -> list[str]:
    notes = []
    if _is_estimated(event):
        notes.append("Duree de coupure estimee a 2 h : l'avis ne donne pas de maximum.")
    if event.restoration_without_notice:
        notes.append("Le courant peut revenir sans preavis.")
    if event.window_may_extend:
        notes.append("Les coupures peuvent depasser le creneau annonce.")
    if not event.list_is_exhaustive:
        notes.append("La liste des zones n'est pas definitive.")
    if impact.mode == "general_sms":
        notes.append("Niveaux du reservoir / de la batterie inconnus (ferme sans capteurs).")
    if _uses_generator(impact):
        notes.append("Nous supposons que le groupe electrogene est pret et a assez de carburant pour ces appareils.")
    return notes


def _plan_view(plan: list[dict], lang="fr") -> list[dict]:
    words = {"Generator": "Demarrer le groupe", "Keep": "Garder", "Before": "Faire avant", "After": "Faire apres",
             "Off": "Eteindre"}
    if lang == "ar":
        words = {"Generator": "شغّل المولّد", "Keep": "أبقِ", "Before": "قبل الانقطاع", "After": "بعد الانقطاع",
                 "Off": "أطفئ"}
    return [{"equipment": r["equipment"], "action": r["action"], "action_label": words[r["action"]],
             "reason": r["why_ar"] if lang == "ar" else r["why"]} for r in plan if r["affected"]]


def build(events_path: str, lang: str = "ar", farms_list=None, live_now=None) -> dict:
    events = load_events(events_path)
    registry = PlaceRegistry.seeded()
    for event in events:
        for name in event.place_names.values():
            registry.add(name)
    moments = [live_now] if live_now else sorted({e.window_start - timedelta(hours=5) for e in events if e.window_start})
    labels = texts_ar.STATUS if lang == "ar" else STATUS_TEXT
    result = {"generated_for": "farmer screen", "language": lang, "direction": "rtl" if lang == "ar" else "ltr",
              "status_labels": labels, "moments": []}
    for now in moments:
        farms = []
        for farm in (farms_list if farms_list is not None else DEMO_FARMS):
            alerts = []
            for imp in farm_impacts(farm, events, registry, now, lang):
                if not imp.notify:
                    continue
                e = imp.event
                status = STATUS[imp.level]
                alerts.append({
                    "event_id": e.id, "utility": e.utility, "status": status, "status_label": labels[status],
                    "headline": _headline(farm, e, imp.cut_hours, lang), "when_start": e.window_start.isoformat(),
                    "when_end": e.window_end.isoformat() if e.window_end else None,
                    "channel": imp.channel, "mode": imp.mode,
                    "summary": imp.message, "actions": _plan_view(imp.plan, lang),
                    "why": (_why_ar if lang == "ar" else _why)(farm, e, imp),
                    "assumptions": (_assumptions_ar if lang == "ar" else _assumptions)(e, imp),
                    "sources": [{"name": _source_name(u), "url": u} for u in e.sources],
                })
            alerts.sort(key=lambda a: ("action", "watch", "info").index(a["status"]))
            farms.append({
                "farm_id": farm.farm_id or farm.id, "farm": farm.name, "locality": farm.locality, "has_sensors": farm.smart,
                "sensors": ({"tank_pct": farm.tank_level_pct, "tank_hours": farm.water_autonomy(),
                            "battery_pct": farm.battery_pct, "battery_hours": farm.power_autonomy()}
                            if farm.smart else None),
                "overall": alerts[0]["status"] if alerts else "clear",
                "overall_label": labels[alerts[0]["status"] if alerts else "clear"],
                "alerts": alerts,
                "all_clear_text": None if alerts else (
                    f"لا يوجد انقطاع معلن أو جارٍ في {farm.locality}. نراقب {len(events)} إعلانات حديثة." if lang == "ar" else
                    f"Aucune coupure annoncee ou en cours pour {farm.locality}. Nous verifions {len(events)} avis recents."),
            })
        result["moments"].append({"label": f"{now:%d/%m/%Y %H:%M}", "iso": now.isoformat(), "farms": farms})
    return result


def write_view(events_path="events.json", view_out="farmer_view.json", lang="ar", farms_list=None, live_now=None):
    """Builds the farmer data and writes it in one step (a reader never sees a half-written file)."""
    import os
    data = build(events_path, lang, farms_list=farms_list, live_now=live_now)
    tmp = view_out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, view_out)
    return data


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "events.json"
    lang = sys.argv[2] if len(sys.argv) > 2 else "ar"                  # python export_farmer_view.py events.json fr
    data = build(path, lang)
    with open("farmer_view.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"farmer_view.json written: {len(data['moments'])} demo moments")