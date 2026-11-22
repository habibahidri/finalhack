"""The agent graph (LangGraph): who proposes what, how conflicts are solved, and what the farmer is told.

  event + farm
      |
   [router]        which agents are needed for this cut and this farm
    /   |   \\
 [water][energy][crop]   each one PROPOSES an action per equipment, with a reason and a priority rank
    \\   |   /
  [reconcile]      same equipment, different actions -> the higher priority need wins
      |            shared battery budget -> highest priorities stay on, the rest prepare before
  [rules_check] --fail (once)--> back to reconcile with the forbidden choices --> still fail: plain rules plan
      |
  [explain]        final plan + one sentence per conflict (the farmer sees WHY)

Agents propose, code decides. No AI is called here, so the demo never depends on a provider.
The result has the same shape as farm._plan(), so farmer_view.json does not change.

Priority (1 = most important):  1 animals' water and ventilation | 2 cold chain | 3 crops, irrigation | 4 comfort, saving
"""
from __future__ import annotations

import operator
from functools import lru_cache
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from catalog import CATALOG
from farm import Equipment, Farm, _plan
from texts_ar import plan_reason

# item priority: change a number here to change the order (one line)
PRIORITY = {"animal_drinkers": 1, "poultry_fans": 1, "cold_room": 2, "milk_cooling_tank": 2, "incubator": 2,
            "milking_machine": 3, "greenhouse_fans": 3, "drip_irrigation": 3, "well_pump": 3, "shed_lighting": 4}
SAFETY = {"Generator": -1, "Before": 0, "Keep": 1, "Off": 2}            # tie-break: the safer action wins
AGENT_AR = {"water": "وكيل الماء", "energy": "وكيل الطاقة", "crop": "وكيل الزراعة"}
NAME_TO_ID = {v["ar"]: k for k, v in CATALOG.items()}


def cid(item: Equipment) -> str:
    return item.catalog_id or NAME_TO_ID.get(item.name, "")


def rank_of(item: Equipment) -> int:
    return PRIORITY.get(cid(item), {"essential": 2, "flexible": 3, "optional": 4}[item.role])


def _reserve(farm: Farm, utility: str) -> float:
    return (farm.water_autonomy() if utility == "water" else farm.power_autonomy()) or 0


def _base(item: Equipment, utility: str, reserve: float, cut: float) -> tuple[str, str, str]:
    """The plain rule for one item (same as farm._plan): action, English reason, Arabic reason."""
    if item.uses != utility:
        return "Keep", "not affected by this cut", plan_reason(item.role, False, reserve, cut)
    if item.role == "essential":
        if reserve >= cut:
            return "Keep", f"reserve {reserve:g} h covers the {cut:g} h cut", plan_reason("essential", True, reserve, cut)
        return "Before", f"reserve {reserve:g} h is shorter than the {cut:g} h cut: prepare before", plan_reason("essential", True, reserve, cut)
    if item.role == "flexible":
        return "Before", "run it before the window, restart after", plan_reason("flexible", True, reserve, cut)
    return "Off", "not needed during the cut", plan_reason("optional", True, reserve, cut)


def _prop(item, action, en, ar, rank, agent) -> dict:
    return {"equipment": item.name, "action": action, "en": en, "ar": ar, "rank": rank, "agent": agent}


# ----------------------------------------------------------------------------- the three agents (propose only)
def water_agent(farm: Farm, utility: str, cut: float, reserve: float) -> list[dict]:
    """Thinks about the animals' water first."""
    if not any(cid(i) == "animal_drinkers" for i in farm.equipment):
        return []
    out = []
    for item in farm.equipment:
        c = cid(item)
        if c == "animal_drinkers" and utility == "water":
            action, en, ar = _base(item, utility, reserve, cut)
            out.append(_prop(item, action, en, ar, 1, "water"))
        elif c == "well_pump" and utility == "electricity":
            out.append(_prop(item, "Before", "fill the tank before the cut: the animals need water",
                             "شغّله قبل الانقطاع لملء الخزان: الحيوانات تحتاج الماء", 1, "water"))
        elif c == "drip_irrigation" and utility == "water" and reserve < cut:
            out.append(_prop(item, "Off", "tank will not last: keep the water for the animals",
                             "الخزان لا يكفي: احتفظ بالماء للحيوانات", 1, "water"))
    return out


def energy_agent(farm: Farm, utility: str, cut: float, reserve: float) -> list[dict]:
    """Thinks about the battery: wants essential items on, and flexible items off when the battery is short."""
    if utility != "electricity":
        return []
    out = []
    for item in farm.equipment:
        if item.uses != utility:
            continue
        action, en, ar = _base(item, utility, reserve, cut)
        rank = rank_of(item)
        if item.role == "essential":
            if action == "Before" and "generator" in farm.backup:     # the farmer has a generator: use it, nothing to "prepare"
                action, en, ar = "Generator", "the battery is short: start the generator", "البطارية لا تكفي: شغّل المولّد"
            elif action == "Before":                     # the battery cannot carry everything: reconcile will pick who stays on
                action, en, ar = "Keep", "keep it running on the battery", "أبقِه يعمل على البطارية"
        elif item.role == "flexible" and reserve < cut:
            action, en, ar, rank = "Off", "battery is short: do not run it during the cut", "البطارية لا تكفي: لا تشغّله أثناء الانقطاع", 4
        out.append(_prop(item, action, en, ar, rank, "energy"))
    return out


def crop_agent(farm: Farm, utility: str, cut: float, reserve: float) -> list[dict]:
    """Thinks about the plants."""
    out = []
    for item in farm.equipment:
        c = cid(item)
        if c == "drip_irrigation" and utility == "water":
            out.append(_prop(item, "Before", "irrigate before the cut", "اسقِ قبل الانقطاع", 3, "crop"))
        elif c == "well_pump" and utility == "electricity":
            out.append(_prop(item, "Before", "irrigate before the cut", "اسقِ قبل الانقطاع", 3, "crop"))
        elif c == "greenhouse_fans" and utility == "electricity":
            if reserve < cut and "generator" in farm.backup:
                out.append(_prop(item, "Generator", "the battery is short: start the generator for the greenhouse air",
                                 "البطارية لا تكفي: شغّل المولّد لتهوية البيوت المحمية", 3, "crop"))
            else:
                out.append(_prop(item, "Keep", "plants in the greenhouse need air", "النباتات في البيوت المحمية تحتاج التهوية", 3, "crop"))
    return out


AGENT_FUNCS = {"water": water_agent, "energy": energy_agent, "crop": crop_agent}   # looked up at run time (tests can swap one)


# ----------------------------------------------------------------------------- state and nodes
class State(TypedDict, total=False):
    farm: Farm
    event: object
    cut: float
    utility: str
    reserve: float
    agents: list
    proposals: Annotated[list, operator.add]     # the agents run in parallel: their lists are added together
    trace: Annotated[list, operator.add]
    excluded: list                               # [equipment, action] pairs the rules check forbade
    retries: int
    rows: list
    conflicts: list
    violations: list
    fallback: bool
    plan: list


def router(state: State) -> dict:
    farm, utility = state["farm"], state["event"].utility
    if not farm.smart:
        return {"agents": [], "trace": ["router: no sensors -> no agents, general message only"]}
    has = lambda *ids: any(cid(i) in ids for i in farm.equipment)  # noqa: E731
    agents = []
    if utility == "electricity" and any(i.uses == "electricity" for i in farm.equipment):
        agents.append("energy")
    if has("animal_drinkers") or (utility == "water" and has("drip_irrigation")):
        agents.append("water")
    if farm.crops or has("drip_irrigation", "greenhouse_fans"):
        agents.append("crop")
    return {"agents": agents, "reserve": _reserve(farm, utility),
            "trace": [f"router: {utility} cut of {state['cut']:g} h -> agents: {', '.join(agents) or 'none'}"]}


def route_after_router(state: State) -> list[str]:
    if not state["farm"].smart:
        return ["explain"]
    return [f"{a}_node" for a in state["agents"]] or ["reconcile"]


def make_agent_node(name: str):
    def node(state: State) -> dict:
        props = AGENT_FUNCS[name](state["farm"], state["event"].utility, state["cut"], state["reserve"])
        return {"proposals": props, "trace": [f"{name} agent: {len(props)} proposals"]}
    return node


def _capacity_wh(farm: Farm):
    hours = farm.power_autonomy()
    load = sum(e.power_w for e in farm.equipment if e.uses == "electricity" and e.role == "essential")
    return hours * load if hours and load else None


def reconcile(state: State) -> dict:
    farm, utility, cut, reserve = state["farm"], state["event"].utility, state["cut"], state["reserve"]
    excluded = {tuple(x) for x in state.get("excluded", [])}
    by_item: dict[str, list[dict]] = {}
    for p in state.get("proposals", []):
        if (p["equipment"], p["action"]) not in excluded:
            by_item.setdefault(p["equipment"], []).append(p)

    rows, conflicts = [], []
    for item in farm.equipment:
        base_action, base_en, base_ar = _base(item, utility, reserve, cut)
        row = {"equipment": item.name, "action": base_action, "why": base_en, "why_ar": base_ar,
               "affected": item.uses == utility, "rank": rank_of(item), "item": item}
        if item.uses == utility:
            options = by_item.get(item.name, [])
            if options:
                winner = min(options, key=lambda p: (p["rank"], SAFETY[p["action"]]))
                row.update(action=winner["action"], why=winner["en"], why_ar=winner["ar"])
                losers = [p for p in options if p["action"] != winner["action"]]
                if losers:
                    lost = losers[0]
                    conflicts.append({"equipment": item.name, "kind": "disagreement", "chosen": winner["action"],
                                      "note_ar": f"{AGENT_AR[winner['agent']]} مقابل {AGENT_AR[lost['agent']]}. الأولوية: {_need_ar(winner['rank'])}",
                                      "note": f"{winner['agent']} ({winner['action']}) beat {lost['agent']} ({lost['action']}): "
                                              f"priority {winner['rank']} vs {lost['rank']}"})
            elif (item.name, base_action) in excluded:
                row.update(action="Before" if item.role != "optional" else "Off")
        rows.append(row)

    capacity = _capacity_wh(farm) if utility == "electricity" else None
    if capacity is None and reserve < cut:                # no budget can be computed: the plain rule applies, nobody stays on a short reserve
        for r in rows:
            if r["affected"] and r["item"].role == "essential" and r["action"] == "Keep":
                _, r["why"], r["why_ar"] = _base(r["item"], utility, reserve, cut)
                r["action"] = "Before"
    if capacity is not None:                              # shared battery: the highest priorities stay on, the rest prepare before
        used = 0.0
        keepers = sorted((r for r in rows if r["affected"] and r["action"] == "Keep"),
                         key=lambda r: (r["rank"], r["item"].power_w))
        demoted = []
        for r in keepers:
            need = r["item"].power_w * cut
            if used + need <= capacity:
                used += need
            else:
                demoted.append(r)
        for r in demoted:
            en, ar = ("the battery cannot run it for the whole cut: prepare before",
                      "البطارية لا تكفي لتشغيله طوال الانقطاع: حضّر قبل الانقطاع")
            r.update(action="Before", why=en, why_ar=ar)
            conflicts.append({"equipment": r["equipment"], "kind": "budget", "chosen": "Before", "note_ar": ar,
                              "note": f"battery budget {capacity:.0f} Wh: moved to Before"})
    trace = [f"reconcile: {len(conflicts)} conflicts solved" + (f" (retry {state.get('retries', 0)})" if state.get("retries") else "")]
    return {"rows": rows, "conflicts": conflicts, "trace": trace}


def _need_ar(rank: int) -> str:
    return {1: "ماء الحيوانات وتهويتها", 2: "سلسلة التبريد", 3: "الزراعة والريّ"}.get(rank, "التوفير")


def rules_check(state: State) -> dict:
    """The code verifies the plan. It never trusts an agent."""
    farm, cut, utility = state["farm"], state["cut"], state["event"].utility
    rows, problems, bad = state["rows"], [], []
    names = [i.name for i in farm.equipment]
    if sorted(r["equipment"] for r in rows) != sorted(names):
        problems.append("rows do not match the farm equipment")
    for r in rows:
        if r["affected"] and r["item"].role == "essential" and r["action"] == "Off":
            problems.append(f"{r['equipment']}: essential equipment cannot be switched off")
            bad.append([r["equipment"], "Off"])
    capacity = _capacity_wh(farm) if utility == "electricity" else None
    if capacity is None and state["reserve"] < cut:
        for r in rows:
            if r["affected"] and r["item"].role == "essential" and r["action"] == "Keep":
                problems.append(f"{r['equipment']}: kept on a reserve shorter than the cut")
                bad.append([r["equipment"], "Keep"])
    if capacity is not None:
        load = sum(r["item"].power_w for r in rows if r["affected"] and r["action"] == "Keep") * cut
        if load > capacity + 1e-6:
            problems.append(f"kept load {load:.0f} Wh is more than the battery {capacity:.0f} Wh")
    out: dict = {"violations": problems}
    if not problems:
        out["trace"] = ["rules check: pass"]
    elif state.get("retries", 0) == 0:
        out.update(retries=1, excluded=state.get("excluded", []) + bad,
                   trace=[f"rules check: FAIL ({'; '.join(problems)}) -> one retry with forbidden choices"])
    else:
        out.update(fallback=True, trace=[f"rules check: FAIL again ({'; '.join(problems)}) -> plain rules plan"])
    return out


def route_after_check(state: State) -> str:
    if state["violations"] and not state.get("fallback"):
        return "reconcile"
    return "explain"


def explain(state: State) -> dict:
    farm, event, cut = state["farm"], state["event"], state["cut"]
    if not farm.smart:
        return {"plan": [], "trace": ["explain: nothing to plan"]}
    if state.get("fallback"):
        return {"plan": _plan(farm, event, cut), "trace": ["explain: plain rules plan used"]}
    notes = {c["equipment"]: c for c in state.get("conflicts", []) if c["kind"] == "disagreement"}
    plan = []
    for r in state["rows"]:
        note = notes.get(r["equipment"])        # a conflict between agents: kept apart, the screen shows it under "how we decided"
        plan.append({"equipment": r["equipment"], "action": r["action"], "why": r["why"], "affected": r["affected"],
                     "why_ar": r["why_ar"], "decision_ar": note["note_ar"] if note else "", "decision": note["note"] if note else ""})
    return {"plan": plan, "trace": [f"explain: plan ready ({len(notes)} conflict notes)"]}


@lru_cache(maxsize=1)
def build_graph():
    g = StateGraph(State)
    g.add_node("router", router)
    for name in AGENT_FUNCS:
        g.add_node(f"{name}_node", make_agent_node(name))
        g.add_edge(f"{name}_node", "reconcile")
    g.add_node("reconcile", reconcile)
    g.add_node("rules_check", rules_check)
    g.add_node("explain", explain)
    g.add_edge(START, "router")
    g.add_conditional_edges("router", route_after_router, [f"{n}_node" for n in AGENT_FUNCS] + ["reconcile", "explain"])
    g.add_edge("reconcile", "rules_check")
    g.add_conditional_edges("rules_check", route_after_check, ["reconcile", "explain"])
    g.add_edge("explain", END)
    return g.compile()


def run_graph(farm: Farm, event, cut_hours: float):
    """Returns (plan, trace). Plan rows look exactly like farm._plan() rows."""
    result = build_graph().invoke({"farm": farm, "event": event, "cut": cut_hours, "proposals": [], "trace": [],
                                   "excluded": [], "retries": 0})
    return result["plan"], result["trace"]