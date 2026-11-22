"""Builds dashboard.html: one self-contained page (no internet needed) for the demo.

  python make_dashboard.py events.json          -> writes dashboard.html, then double-click it

It reads the events found by run_pipeline.py and, for several "demo moments", asks farm.py what each farm
should do. The page lets you pick the moment.
"""
import json
import sys
from datetime import timedelta

from events import status_at
from farm import DEMO_FARMS, TUNIS, farm_impacts, load_events
from geocode import PlaceRegistry


def build(events_path: str) -> dict:
    events = load_events(events_path)
    registry = PlaceRegistry.seeded()
    for event in events:
        for key, name in event.place_names.items():
            registry.add(name)
    moments = sorted({e.window_start - timedelta(hours=5) for e in events if e.window_start})
    out_moments = []
    for now in moments:
        rows = []
        for e in events:
            rows.append({"id": e.id, "status": status_at(e, now)})
        farms = []
        for farm in DEMO_FARMS:
            impacts = farm_impacts(farm, events, registry, now)
            farms.append({
                "name": farm.name, "locality": farm.locality, "smart": farm.smart,
                "water_hours": farm.water_autonomy(), "power_hours": farm.power_autonomy(),
                "tank_pct": farm.tank_level_pct, "battery_pct": farm.battery_pct,
                "impacts": [{
                    "event_id": i.event.id, "match": i.match, "probability": i.probability,
                    "level": i.level, "mode": i.mode, "channel": i.channel, "notify": i.notify,
                    "cut_hours": i.cut_hours, "plan": i.plan, "message": i.message,
                } for i in impacts],
            })
        out_moments.append({
            "label": f"{now:%d %b %Y, %H:%M}", "iso": now.isoformat(), "events": rows, "farms": farms,
        })
    event_rows = []
    for e in events:
        event_rows.append({
            "id": e.id, "utility": e.utility, "type": e.event_type,
            "start": e.window_start.strftime("%d %b %Y %H:%M") if e.window_start else "no date",
            "end": e.window_end.strftime("%H:%M") if e.window_end else None,
            "recurrence": e.recurrence, "intermittent": e.is_intermittent, "may_extend": e.window_may_extend,
            "restoration_without_notice": e.restoration_without_notice,
            "reason": e.reason, "confidence": e.confidence, "sources": e.sources,
            "places": sorted(e.place_names.values(), key=str.lower),
        })
    default = max(range(len(out_moments)),
                  key=lambda i: sum(len(f["impacts"]) for f in out_moments[i]["farms"])) if out_moments else 0
    return {"events": event_rows, "moments": out_moments, "default": default}


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "events.json"
    data = build(path)
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    with open("dashboard.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"dashboard.html written: {len(data['events'])} events, {len(data['moments'])} demo moments. "
          "Double-click it to open.")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Outage watch</title>
<style>
:root{--bg:#f6f7f4;--card:#fff;--ink:#1d2a22;--mute:#66746b;--line:#dfe4dc;--green:#2f7d4f;--greenbg:#e3f2e8;
--amber:#b26a00;--amberbg:#fdf0d8;--red:#b3261e;--redbg:#fbe4e1;--blue:#1f5f99;--bluebg:#e1eef9;--grey:#8a948d;--greybg:#eceeea}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#141a16;--card:#1c241f;--ink:#e8eee9;--mute:#9aa8a0;
--line:#2c3830;--green:#6cc58c;--greenbg:#1d3326;--amber:#f0b24d;--amberbg:#3a2d12;--red:#f08a82;--redbg:#3d1c19;
--blue:#7fb8ec;--bluebg:#1a2d3f;--grey:#8a948d;--greybg:#242c27}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,Segoe UI,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:20px 16px 48px}
header{display:flex;flex-wrap:wrap;gap:12px;align-items:end;justify-content:space-between;margin-bottom:16px}
h1{font-size:22px;margin:0}h1 small{display:block;font-size:13px;font-weight:400;color:var(--mute);margin-top:2px}
label{font-size:12px;color:var(--mute);display:block;margin-bottom:4px}
select{font:inherit;padding:8px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);max-width:100%}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:22px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.kpi b{display:block;font-size:26px;line-height:1.1}.kpi span{font-size:12px;color:var(--mute)}
h2{font-size:16px;margin:26px 0 10px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.row{display:flex;justify-content:space-between;gap:8px;align-items:center;flex-wrap:wrap}
.badge{font-size:11px;font-weight:600;padding:2px 8px;border-radius:99px;white-space:nowrap}
.announced{background:var(--bluebg);color:var(--blue)}.active{background:var(--redbg);color:var(--red)}
.expired{background:var(--greybg);color:var(--grey)}.low{background:var(--greenbg);color:var(--green)}
.medium{background:var(--amberbg);color:var(--amber)}.high{background:var(--redbg);color:var(--red)}
.water{background:var(--bluebg);color:var(--blue)}.electricity{background:var(--amberbg);color:var(--amber)}
.mute{color:var(--mute);font-size:13px}.ev{opacity:1}.ev.expired{opacity:.55}
.bar{height:6px;background:var(--greybg);border-radius:9px;overflow:hidden;margin-top:4px}.bar i{display:block;height:100%;background:var(--green)}
details summary{cursor:pointer;color:var(--blue);font-size:13px;margin-top:6px}
.places{font-size:12px;color:var(--mute);margin-top:6px;max-height:140px;overflow:auto}
.plan{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}.plan td{padding:5px 4px;border-top:1px solid var(--line);vertical-align:top}
.act{font-weight:700;font-size:11px;padding:2px 8px;border-radius:6px;display:inline-block;min-width:54px;text-align:center}
.Keep{background:var(--greenbg);color:var(--green)}.Before{background:var(--amberbg);color:var(--amber)}
.Off{background:var(--greybg);color:var(--grey)}.After{background:var(--bluebg);color:var(--blue)}
.msg{background:var(--greybg);border-radius:12px;padding:10px 12px;font-size:13px;margin-top:8px}
.sms{background:var(--greenbg);border-radius:16px 16px 16px 4px}
.note{font-size:12px;color:var(--mute);margin-top:30px;border-top:1px solid var(--line);padding-top:12px}
a{color:var(--blue)}
</style>
</head>
<body><div class="wrap">
<header>
  <h1>Outage watch: water and electricity<small>STEG / SONEDE notices, read by AI, matched to each farm</small></h1>
  <div><label for="moment">Pretend it is (demo moment)</label><select id="moment"></select></div>
</header>
<div class="kpis" id="kpis"></div>
<h2>Announced outages</h2><div class="grid" id="events"></div>
<h2>What each farm should do</h2><div class="grid" id="farms"></div>
<p class="note">Real: the announcements (linked sources) and their AI extraction. Simulated for the demo: the farms,
their sensors and equipment, and the moment chosen above. The SMS text is generated but not sent yet.</p>
</div>
<script>
const DATA = __DATA__;
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const TYPE = {maintenance:'Maintenance',rotating_shedding:'Rotating cuts',heatwave_incident:'Incident',
  water_works:'Works',water_regulation:'Daily regulation',water_incident:'Incident'};
DATA.moments.forEach((m,i)=>{const o=document.createElement('option');o.value=i;o.textContent=m.label;$('moment').appendChild(o)});
$('moment').value = DATA.default;
function render(){
  const m = DATA.moments[+$('moment').value] || {events:[],farms:[]};
  const status = Object.fromEntries(m.events.map(e=>[e.id,e.status]));
  const live = DATA.events.filter(e=>status[e.id]!=='expired').length;
  const impacts = m.farms.flatMap(f=>f.impacts);
  const sms = impacts.filter(i=>i.channel==='sms'&&i.notify).length;
  const concerned = m.farms.filter(f=>f.impacts.length).length;
  $('kpis').innerHTML = [[live,'announced or active outages'],[concerned+' / '+m.farms.length,'farms concerned'],
    [sms,'SMS to send'],[impacts.filter(i=>i.mode==='smart_plan').length,'full plans (farms with sensors)']]
    .map(([v,l])=>`<div class="kpi"><b>${v}</b><span>${l}</span></div>`).join('');
  $('events').innerHTML = DATA.events.map(e=>{
    const st = status[e.id]||'expired';
    const when = e.start + (e.end?' to '+e.end:'') + (e.recurrence==='daily'?' (every day)':'');
    const notes = [e.intermittent?'cuts on and off, not continuous':'', e.restoration_without_notice?'service returns without notice':'',
      e.may_extend?'may go beyond the window':''].filter(Boolean).join(' · ');
    const src = e.sources.map((u,i)=>`<a href="${esc(u)}" target="_blank" rel="noopener">source ${i+1}</a>`).join(' · ');
    return `<div class="card ev ${st}"><div class="row"><span><span class="badge ${e.utility}">${e.utility==='water'?'Water':'Electricity'}</span>
      <b> #${e.id} ${TYPE[e.type]||e.type}</b></span><span class="badge ${st}">${st}</span></div>
      <div class="mute" style="margin-top:6px">${esc(when)}</div>
      ${notes?`<div class="mute">${esc(notes)}</div>`:''}
      ${e.reason?`<div class="mute">Reason: ${esc(e.reason)}</div>`:''}
      <div class="mute" style="margin-top:6px">${e.places.length} places · ${src}</div>
      <div class="mute">AI confidence ${Math.round(e.confidence*100)}%</div><div class="bar"><i style="width:${e.confidence*100}%"></i></div>
      <details><summary>Show places</summary><div class="places">${e.places.map(esc).join(', ')}</div></details></div>`}).join('');
  $('farms').innerHTML = m.farms.map(f=>{
    const head = `<div class="row"><b>${esc(f.name)}</b><span class="badge ${f.smart?'low':'expired'}">${f.smart?'sensors':'no sensors'}</span></div>
      <div class="mute">${esc(f.locality)}${f.smart?` · tank ${f.tank_pct}% (${f.water_hours} h) · battery ${f.battery_pct}% (${f.power_hours} h)`:''}</div>`;
    if(!f.impacts.length) return `<div class="card">${head}<p class="mute">No announced or active outage concerns this farm.</p></div>`;
    const body = f.impacts.map(i=>{
      const top = `<div class="row" style="margin-top:10px"><span>Event #${i.event_id} · <span class="mute">${i.match==='listed'?'place is named in the notice':'place not named, list is incomplete'}</span></span>
        <span class="badge ${i.level}">risk ${i.level}</span></div>`;
      if(i.mode==='general_sms') return top+`<div class="msg sms">SMS: ${esc(i.message)}<div class="mute">${i.message.length} characters${i.notify?'':' · not sent (low chance)'}</div></div>
        <div class="mute">Tank and battery levels are unknown, so only general advice is sent.</div>`;
      const rows = i.plan.map(r=>`<tr><td><span class="act ${r.action}">${r.action}</span></td><td>${esc(r.equipment)}</td><td class="mute">${esc(r.why)}</td></tr>`).join('');
      return top+`<table class="plan">${rows}</table><div class="msg">App alert: ${esc(i.message)}</div>`}).join('');
    return `<div class="card">${head}${body}</div>`}).join('');
}
$('moment').onchange = render; render();
</script></body></html>"""


if __name__ == "__main__":
    main()
