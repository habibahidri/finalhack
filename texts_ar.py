"""Arabic texts of the farm alerts (Modern Standard Arabic, simple words). Same facts as the French ones.

SMS note: Arabic goes in Unicode SMS: 70 characters in one message, 67 per part when it is split.
The general SMS is kept short (aim: 2 parts at most); sms_parts() tells how many parts a text needs.
"""
from __future__ import annotations

import os

LEVEL = {"low": "منخفض", "medium": "متوسط", "high": "مرتفع"}
ACTION = {"Generator": "شغّل المولّد", "Keep": "أبقِ", "Before": "قبل", "After": "بعد", "Off": "أطفئ"}
STATUS = {"info": "للعلم", "watch": "للمتابعة", "action": "تصرّف الآن", "clear": "لا شيء يستدعي الانتباه"}


def sms_parts(text: str) -> int:
    return 1 if len(text) <= 70 else -(-len(text) // 67)


def kind(event) -> str:
    if event.utility == "water":
        return "انقطاع الماء"
    return "انقطاع الكهرباء المتناوب" if event.event_type == "rotating_shedding" else "انقطاع الكهرباء"


def when(event) -> str:
    if not event.window_start:
        return "قريبا"
    day = f"{event.window_start:%d/%m}"
    if event.window_end:
        return f"يوم {day} من {event.window_start:%H} إلى {event.window_end:%H}"
    return f"يوم {day} ابتداء من {event.window_start:%H}"


def headline(farm, event) -> str:
    return f"{kind(event)} {when(event)} في {farm.locality}"


DETAILS_TEXT = "التفاصيل في التطبيق."


def details_line(farm=None) -> str:
    """The last line of the message. With DETAILS_URL set (the public address of our site), it is a link to THIS farm's
    page: <DETAILS_URL>/f/<farm id>. Without it: 'details in the app' (we never invent a link)."""
    base = os.environ.get("DETAILS_URL", "").strip().rstrip("/")
    farm_id = getattr(farm, "id", "") if farm is not None else ""
    if base and farm_id:
        return f"التفاصيل: {base}/f/{farm_id}"
    return f"التفاصيل: {base}" if base else DETAILS_TEXT


def general_message(farm, event, match: str) -> str:
    """One text message for farms without sensors (SMS or WhatsApp): same words for both channels.
    General advice only: we do not know the tank or battery level of this farm."""
    where = farm.locality + (" (محتمل)" if match == "possible" else "")
    daily = "، ويتكرر كل يوم" if event.recurrence == "daily" else ""
    no_notice = "، وقد يعود التيار دون إنذار" if event.utility == "electricity" and event.restoration_without_notice else ""
    if event.utility == "water":
        text = (f"الصوناد: {kind(event)} في {where} {when(event)}{daily}. "
                "املأ الخزانات والقوارير الآن، اسقِ قبل الانقطاع، واحتفظ بماء للماشية.")
    else:
        short = "انقطاع متناوب" if event.event_type == "rotating_shedding" else "انقطاع الكهرباء"
        text = (f"الستاغ: {short} في {where} {when(event)}{no_notice}. "
                "اشحن البطاريات الآن، لا تفتح غرفة التبريد، وأطفئ غير الضروري.")
    return f"{text} {details_line(farm)}"


general_sms = general_message          # old name, kept so nothing else breaks


def plan_reason(role: str, affected: bool, reserve: float, cut: float) -> str:
    if not affected:
        return "لا يتأثر بهذا الانقطاع"
    if role == "essential":
        if reserve >= cut:
            return f"الاحتياطي {reserve:g} ساعة يكفي لانقطاع {cut:g} ساعة"
        return f"الاحتياطي {reserve:g} ساعة أقل من {cut:g} ساعة: حضّر قبل الانقطاع"
    if role == "flexible":
        return "شغّله قبل الانقطاع وأعد تشغيله بعده"
    return "لا حاجة له أثناء الانقطاع"


def app_message(farm, event, level: str, cut: float, covered: bool, plan: list[dict], match: str,
                estimated: bool) -> str:
    lines = [f"{headline(farm, event)}. المدة المتوقعة: {cut:g} ساعة{' (تقدير)' if estimated else ''}. "
             f"الخطر: {LEVEL[level]}."]
    if match == "possible":
        lines.append("منطقتك غير مذكورة لكن قائمة الإعلان غير نهائية.")
    if event.event_type == "rotating_shedding":
        lines.append("هذا ليس انقطاعا متواصلا: الانقطاع يتناوب وقد يعود التيار دون إشعار.")
    if not covered:
        if event.utility == "water":
            lines.append(f"املأ الخزان قبل الانقطاع (يكفي {farm.water_autonomy():g} ساعة فقط).")
        else:
            lines.append(f"اشحن البطارية قبل الانقطاع (تكفي {farm.power_autonomy():g} ساعة فقط).")
    groups = {"Generator": "شغّل المولّد", "Before": "قبل الانقطاع", "Keep": "أبقِ", "Off": "أطفئ"}
    for action, label in groups.items():
        names = [r["equipment"] for r in plan if r["action"] == action and r["affected"]]
        if names:
            lines.append(f"{label}: " + "، ".join(names) + ".")
    return " ".join(lines)