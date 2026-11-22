"""The farmer's SIGN-UP page, served at <prefix>/join (the same steps as add_farmer.py, in the browser).

One self-contained HTML page, Arabic, right to left, phone first. It only uses the public endpoints of the API
(GET /signup-options, POST /signup, POST /farms), so Antigravity can replace it later without any backend change.
Everything that comes from the server is inserted as plain text (never as HTML).
"""

_TEMPLATE = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>تسجيل المزرعة</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
  :root { --bg:#f8fafc; --card:#ffffff; --ink:#0f172a; --muted:#64748b; --line:#e6edf0; --navy:#0f172a; --on-navy:#ffffff;
          --accent:#059669; --accent-2:#10b981; --soft:#ecfdf5; --err:#dc2626;
          --clear:#059669; --info:#2563eb; --watch:#d97706; --action:#dc2626;
          --shadow:0 14px 34px -16px rgba(15,23,42,.18); --glow:0 10px 24px -8px rgba(5,150,105,.45); }
  @media (prefers-color-scheme: dark) { :root { --bg:#0a1120; --card:#111a2c; --ink:#e8eef6; --muted:#94a3b8; --line:#1e2b42;
          --navy:#e8eef6; --on-navy:#0a1120; --soft:#0f2a22; --shadow:0 14px 34px -16px rgba(0,0,0,.6); } }
  * { box-sizing:border-box; }
  body { margin:0; color:var(--ink); line-height:1.7;
         font-family:"Plus Jakarta Sans","Cairo","Segoe UI",Tahoma,Arial,sans-serif;
         background:radial-gradient(900px 420px at 88% -6%, rgba(16,185,129,.12), transparent 62%), var(--bg); background-attachment:fixed; }
  main { max-width:640px; margin:0 auto; padding:20px 16px 44px; }
  h1 { font-size:1.5rem; font-weight:800; margin:6px 0 2px; color:var(--ink); }
  .sub { color:var(--muted); font-size:.95rem; margin-bottom:16px; }

  .card { background:var(--card); border:1px solid var(--line); border-radius:28px; padding:18px; margin-bottom:16px; box-shadow:var(--shadow); }
  .card h2 { font-size:1.05rem; font-weight:800; margin:0 0 10px; }
  .chips { display:flex; flex-wrap:wrap; gap:8px; }
  .chip { border:1.5px solid var(--line); background:var(--card); color:var(--ink); border-radius:999px; padding:8px 16px; font-size:1rem; font-weight:600;
          cursor:pointer; min-height:46px; display:flex; align-items:center; gap:8px; font-family:inherit; transition:all .15s; }
  .chip:hover { border-color:var(--accent-2); }
  .chip[aria-pressed="true"] { border-color:var(--navy); background:var(--navy); color:var(--on-navy); font-weight:800; box-shadow:0 10px 22px -10px rgba(15,23,42,.55); }
  .sizes { display:flex; gap:6px; margin:10px 0 2px; align-items:center; flex-wrap:wrap; font-size:.92rem; color:var(--muted); }
  .sizes button { border:1.5px solid var(--line); background:var(--card); color:var(--ink); border-radius:999px; padding:4px 14px; cursor:pointer; font-family:inherit; font-weight:600; min-height:36px; }
  .sizes button[aria-pressed="true"] { background:var(--accent); color:#fff; border-color:var(--accent); }
  input[type=text], input[type=number], input[type=tel] { width:100%; padding:11px 14px; border:1.5px solid var(--line); border-radius:16px;
          font-size:1rem; background:var(--bg); color:var(--ink); font-family:inherit; min-height:46px; }
  input:focus { outline:none; border-color:var(--accent-2); box-shadow:0 0 0 4px rgba(16,185,129,.18); }
  label { display:block; font-size:.9rem; color:var(--muted); margin:10px 0 3px; font-weight:600; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  .go { width:100%; background:var(--accent); color:#fff; border:0; border-radius:999px; padding:14px; font-size:1.05rem; font-weight:800;
        cursor:pointer; min-height:52px; font-family:inherit; box-shadow:var(--glow); transition:transform .1s; }
  .go:active { transform:translateY(1px); } .go[disabled] { opacity:.55; cursor:wait; }
  .ghost { background:transparent; color:var(--accent); border:1.5px solid var(--accent); box-shadow:none; }
  .row { display:flex; align-items:center; gap:10px; padding:10px 0; border-top:1px solid var(--line); }
  .row:first-of-type { border-top:0; } .row .name { flex:1; font-weight:700; } .row .why { color:var(--muted); font-size:.85rem; font-weight:400; display:block; }
  .step { display:flex; align-items:center; gap:8px; font-weight:800; } .step button { width:38px; height:38px; border-radius:50%; border:1.5px solid var(--line);
          background:var(--card); color:var(--ink); font-size:1.1rem; cursor:pointer; }
  .step button:hover { border-color:var(--accent-2); color:var(--accent); }
  .del { border:0; background:transparent; color:var(--err); cursor:pointer; font-size:1.1rem; }
  .err { color:var(--err); margin:8px 0; min-height:1.4em; font-weight:600; } .hint { color:var(--muted); font-size:.85rem; }
  .done a.go { display:block; text-align:center; text-decoration:none; margin-top:12px; }
  [hidden] { display:none !important; }
</style>
</head>
<body>
<main>
  <h1>سجّل مزرعتك</h1>
  <div class="sub">أجب عن بضعة أسئلة لنقدّر معدّاتك وننبّهك قبل أي انقطاع للكهرباء أو الماء.</div>

  <div id="step1">
    <div id="sections"></div>
    <div class="card"><h2>أين توجد مزرعتك؟</h2>
      <input type="text" id="locality" placeholder="مثال: مرناق" autocomplete="off">
      <div class="hint">اكتب اسم المنطقة أو المعتمدية.</div></div>
    <div class="err" id="err1" role="alert"></div>
    <button class="go" id="estimate">تقدير المعدّات</button>
  </div>

  <div id="step2" hidden>
    <div class="card"><h2>معدّاتك (يمكنك التعديل)</h2><div id="equipment"></div>
      <div class="hint">هذه أرقام تقديرية. عدّل العدد أو احذف ما لا تملكه.</div></div>
    <div class="card"><h2>حسّاسات المزرعة (اختياري)</h2>
      <button class="chip" id="sensorsToggle" aria-pressed="false" type="button">📟 عندي حسّاسات للخزان والبطارية</button>
      <div id="sensorFields" hidden>
        <div class="grid">
          <div><label for="tank_litres">حجم الخزان (لتر)</label><input type="number" id="tank_litres" value="5000" min="0"></div>
          <div><label for="tank_level_pct">مستوى الخزان %</label><input type="number" id="tank_level_pct" value="70" min="0" max="100"></div>
          <div><label for="battery_kwh">سعة البطارية (kWh)</label><input type="number" id="battery_kwh" value="2" min="0" step="0.5"></div>
          <div><label for="battery_pct">شحن البطارية %</label><input type="number" id="battery_pct" value="90" min="0" max="100"></div>
        </div></div></div>
    <div class="card"><h2>رقم الهاتف (اختياري)</h2>
      <input type="tel" id="phone" placeholder="+216 22 345 678" inputmode="tel" autocomplete="tel">
      <div class="hint">للمزارع بدون حسّاسات: نرسل لك رسالة تنبيه. لا يظهر رقمك لأي شخص.</div></div>
    <div class="err" id="err2" role="alert"></div>
    <button class="go" id="save">سجّل مزرعتي</button>
    <button class="go ghost" id="back" style="margin-top:8px">رجوع</button>
  </div>

  <div id="step3" class="card done" hidden>
    <h2>تم تسجيل مزرعتك ✅</h2>
    <div id="doneText"></div>
    <a class="go" id="farmLink" href="#">افتح صفحة مزرعتي</a>
  </div>
</main>
<script>
const BASE = __BASE__;
const ICONS = {cow:"🐄", sheep:"🐑", goat:"🐐", chicken:"🐔", camel:"🐪", bee:"🐝", tomato:"🍅", olive:"🫒", palm:"🌴", fruit:"🍎",
  wheat:"🌾", well:"🪣", tap:"🚰", tank:"🛢️", generator:"⚙️", battery:"🔋", sun:"☀️", none:"🚫", snowflake:"❄️", greenhouse:"🏡", egg:"🥚"};
const state = { options:null, answers:{}, equipment:[], sensors:false };
const $ = (id) => document.getElementById(id);

async function api(method, path, body) {
  const response = await fetch(BASE + path, { method, headers:{"Content-Type":"application/json"}, body: body ? JSON.stringify(body) : undefined });
  let data = {};
  try { data = await response.json(); } catch (e) { /* not JSON */ }
  if (!response.ok) throw new Error(data.error || ("خطأ " + response.status));
  return data;
}
function el(tag, props, ...kids) {
  const node = document.createElement(tag);
  Object.assign(node, props || {});
  for (const kid of kids) node.append(kid);
  return node;
}

function renderSections() {
  const holder = $("sections");
  for (const section of state.options.sections) {
    if (!section.options) continue;                          // the place search is the plain field below
    const picked = (state.answers[section.id] = section.type === "multi_with_size" ? {} : []);
    const card = el("div", {className:"card"}, el("h2", {textContent:section.title_ar}));
    const chips = el("div", {className:"chips"}), sizes = el("div");
    const redraw = () => {
      for (const b of chips.children) {
        const id = b.dataset.id;
        b.setAttribute("aria-pressed", String(section.type === "multi_with_size" ? id in picked : picked.includes(id)));
      }
      if (section.type === "multi_with_size") {
        sizes.replaceChildren();
        for (const id of Object.keys(picked)) {
          const label = section.options.find((o) => o.id === id).label_ar;
          const row = el("div", {className:"sizes"}, el("span", {textContent:label + " — " + section.size_question_ar}));
          for (const size of section.sizes) {
            const b = el("button", {type:"button", textContent:size.label_ar, title:size.hint_ar});
            b.setAttribute("aria-pressed", String(picked[id] === size.id));
            b.onclick = () => { picked[id] = size.id; redraw(); };
            row.append(b);
          }
          sizes.append(row);
        }
      }
    };
    for (const option of section.options) {
      const b = el("button", {type:"button", className:"chip"}, el("span", {textContent:ICONS[option.icon] || "•"}), el("span", {textContent:option.label_ar}));
      b.dataset.id = option.id;
      b.onclick = () => {
        if (section.type === "multi_with_size") {
          if (option.id in picked) delete picked[option.id]; else picked[option.id] = "medium";
        } else if (picked.includes(option.id)) {
          picked.splice(picked.indexOf(option.id), 1);
        } else if (option.id === "none") {                   // "nothing" excludes the others, and the other way round
          picked.splice(0, picked.length, "none");
        } else {
          if (picked.includes("none")) picked.splice(picked.indexOf("none"), 1);
          picked.push(option.id);
        }
        redraw();
      };
      chips.append(b);
    }
    card.append(chips, sizes);
    holder.append(card);
  }
}

function renderEquipment() {
  const holder = $("equipment");
  holder.replaceChildren();
  state.equipment.forEach((item, index) => {
    const minus = el("button", {type:"button", textContent:"−", ariaLabel:"أنقص"});
    const plus = el("button", {type:"button", textContent:"+", ariaLabel:"زد"});
    const count = el("span", {textContent:String(item.count)});
    minus.onclick = () => { if (item.count > 1) { item.count--; renderEquipment(); } };
    plus.onclick = () => { item.count++; renderEquipment(); };
    const remove = el("button", {type:"button", className:"del", textContent:"✕", ariaLabel:"احذف"});
    remove.onclick = () => { state.equipment.splice(index, 1); renderEquipment(); };
    const name = el("div", {className:"name"}, el("span", {textContent:item.name_ar}), el("span", {className:"why", textContent:item.reason_ar || ""}));
    holder.append(el("div", {className:"row"}, name, el("div", {className:"step"}, minus, count, plus), remove));
  });
}

function normalizePhone(raw) {
  let phone = raw.replace(/[\s\-().]/g, "");
  if (!phone) return "";
  if (phone.startsWith("00")) phone = "+" + phone.slice(2);
  if (/^\d{8}$/.test(phone)) phone = "+216" + phone;       // a Tunisian number written without the country code
  if (/^216\d{8}$/.test(phone)) phone = "+" + phone;
  return phone;
}

function busy(button, on) { button.disabled = on; }

$("estimate").onclick = async () => {
  $("err1").textContent = "";
  const locality = $("locality").value.trim();
  if (!locality) { $("err1").textContent = "اكتب اسم المنطقة."; return; }
  busy($("estimate"), true);
  try {
    state.answers.locality = locality;
    const data = await api("POST", "/signup", {answers: state.answers});
    state.equipment = data.profile.equipment.map((i) => ({...i}));
    if (!state.equipment.length) throw new Error("اختر حيوانا أو محصولا أو تجهيزا واحدا على الأقل.");
    renderEquipment();
    $("step1").hidden = true; $("step2").hidden = false; window.scrollTo(0, 0);
  } catch (error) { $("err1").textContent = error.message; }
  busy($("estimate"), false);
};

$("back").onclick = () => { $("step2").hidden = true; $("step1").hidden = false; };
$("sensorsToggle").onclick = () => {
  state.sensors = !state.sensors;
  $("sensorsToggle").setAttribute("aria-pressed", String(state.sensors));
  $("sensorFields").hidden = !state.sensors;
};

$("save").onclick = async () => {
  $("err2").textContent = "";
  if (!state.equipment.length) { $("err2").textContent = "لا توجد معدّات. ارجع واختر على الأقل خيارا واحدا."; return; }
  const body = { locality: state.answers.locality, answers: state.answers,
                 confirmed: state.equipment.map((i) => ({catalog_id: i.catalog_id, count: i.count})) };
  if (state.sensors) {
    body.sensors = {};
    for (const key of ["tank_litres", "tank_level_pct", "battery_kwh", "battery_pct"]) body.sensors[key] = Number($(key).value);
  }
  const phone = normalizePhone($("phone").value);
  if (phone) {
    if (!/^\+\d{8,15}$/.test(phone)) { $("err2").textContent = "رقم الهاتف غير صحيح. مثال: +216 22 345 678"; return; }
    body.phone = phone;
  }
  busy($("save"), true);
  try {
    const farm = await api("POST", "/farms", body);
    $("step2").hidden = true; $("step3").hidden = false; window.scrollTo(0, 0);
    $("doneText").textContent = farm.has_sensors
      ? "ستجد خطة كل جهاز (أبقِ / قبل الانقطاع / أطفئ / شغّل المولّد) مع أسبابها في صفحة مزرعتك."
      : (farm.phone_saved ? "سنرسل لك رسالة عند أي انقطاع يخص منطقتك، وفيها رابط صفحة مزرعتك."
                          : "لم تُسجّل رقم هاتف: افتح صفحة مزرعتك لترى التنبيهات.");
    $("farmLink").href = BASE + "/f/" + encodeURIComponent(farm.farm_id);
  } catch (error) { $("err2").textContent = error.message; }
  busy($("save"), false);
};

api("GET", "/signup-options").then((options) => { state.options = options; renderSections(); })
  .catch((error) => { $("err1").textContent = "تعذّر تحميل النموذج: " + error.message; });
</script>
</body>
</html>
"""


def render(base: str) -> str:
    """`base` is the prefix the app is mounted under (e.g. /api/outage). It is written as a JS string, safely."""
    import json

    return _TEMPLATE.replace("__BASE__", json.dumps(base).replace("</", "<\\/"))
