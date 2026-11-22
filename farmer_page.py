"""The farmer's page: what the link in the message opens (served by server.py at /f/<farm id>).
One self-contained HTML page. It asks the same address the app uses (/api/farmer-view) and shows the complete dashboard:
status, sensors, each alert with the actions, 'why this alert?', assumptions and sources. Arabic, right to left, phone first.
All texts from the data are inserted as plain text (never as HTML)."""

_TEMPLATE = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>تنبيهات المزرعة</title>
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

  .banner { border-radius:24px; padding:18px 20px; color:#fff; font-size:1.3rem; font-weight:800; margin-bottom:16px; box-shadow:var(--shadow); }
  .s-clear { background:linear-gradient(135deg,#059669,#10b981); } .s-info { background:linear-gradient(135deg,#1d4ed8,#3b82f6); }
  .s-watch { background:linear-gradient(135deg,#d97706,#f59e0b); } .s-action { background:linear-gradient(135deg,#dc2626,#ef4444); }
  .card { background:var(--card); border:1px solid var(--line); border-radius:28px; padding:18px; margin-bottom:16px; box-shadow:var(--shadow); }
  .card h2 { font-size:1.05rem; font-weight:800; margin:0 0 6px; }
  .chip { display:inline-block; color:#fff; border-radius:999px; padding:2px 12px; font-size:.8rem; font-weight:700; margin-inline-start:6px; }
  .msg { background:var(--soft); border-radius:18px; padding:12px 14px; margin:10px 0; }
  .gauges { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  .bar { height:10px; border-radius:999px; background:var(--line); overflow:hidden; margin:6px 0; }
  .bar > i { display:block; height:100%; border-radius:999px; background:linear-gradient(90deg,var(--accent),var(--accent-2)); }
  .act { display:flex; gap:10px; padding:10px 0; border-top:1px solid var(--line); }
  .act b { min-width:104px; font-weight:800; } .act span { color:var(--muted); font-size:.92rem; }
  details { border-top:1px solid var(--line); padding-top:10px; margin-top:10px; }
  summary { cursor:pointer; font-weight:700; color:var(--accent); }
  .why { margin:10px 0; } .why b { display:block; font-size:.92rem; font-weight:800; } .why span { color:var(--muted); font-size:.92rem; }
  ul { margin:6px 0; padding-inline-start:20px; color:var(--muted); font-size:.92rem; }
  a { color:var(--accent); word-break:break-all; font-weight:600; }
  .tag { display:inline-block; background:var(--watch); color:#fff; border-radius:999px; padding:0 10px; font-size:.78rem; font-weight:700; }
  .err { color:var(--err); }
</style>
</head>
<body>
<main id="app"><p>جارٍ التحميل…</p></main>
<script>
(function () {
  var app = document.getElementById('app');
  var params = new URLSearchParams(location.search);
  var farmId = decodeURIComponent(location.pathname.split('/').filter(Boolean).pop() || '');
  var url = '__ENDPOINT__?farm=' + encodeURIComponent(farmId) + '&lang=ar' +
            (params.get('now') ? '&now=' + encodeURIComponent(params.get('now')) : '');

  function el(tag, text, cls) {
    var n = document.createElement(tag);
    if (text != null) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  }
  function safeUrl(u) { return /^https?:\/\//i.test(u) ? u : null; }

  function renderAlert(a, labels) {
    var card = el('section', null, 'card');
    var h = el('h2', a.headline);
    h.appendChild(el('span', a.status_label, 'chip s-' + a.status));
    card.appendChild(h);
    card.appendChild(el('div', a.summary, 'msg'));
    (a.actions || []).forEach(function (x) {
      var row = el('div', null, 'act');
      row.appendChild(el('b', x.action_label + ': ' + x.equipment));
      row.appendChild(el('span', x.reason));
      card.appendChild(row);
    });
    var d = el('details');
    d.appendChild(el('summary', 'لماذا هذا التنبيه؟'));
    (a.why || []).forEach(function (w) {
      var box = el('div', null, 'why');
      box.appendChild(el('b', w.title));
      box.appendChild(el('span', w.detail));
      d.appendChild(box);
    });
    if ((a.assumptions || []).length) {
      d.appendChild(el('b', 'افتراضاتنا'));
      var ul = el('ul');
      a.assumptions.forEach(function (t) { ul.appendChild(el('li', t)); });
      d.appendChild(ul);
    }
    if ((a.sources || []).length) {
      d.appendChild(el('b', 'المصادر'));
      var sl = el('ul');
      a.sources.forEach(function (s) {
        var li = el('li'), link = safeUrl(s.url);
        if (link) { var an = el('a', s.name); an.href = link; an.target = '_blank'; an.rel = 'noopener'; li.appendChild(an); }
        else li.textContent = s.name;
        sl.appendChild(li);
      });
      d.appendChild(sl);
    }
    card.appendChild(d);
    return card;
  }

  function gauge(title, pct, hours) {
    var g = el('div');
    g.appendChild(el('b', title));
    var bar = el('div', null, 'bar'), fill = el('i');
    fill.style.width = Math.max(0, Math.min(100, pct || 0)) + '%';
    bar.appendChild(fill); g.appendChild(bar);
    g.appendChild(el('span', (pct != null ? pct + '٪' : '') + (hours ? ' — تكفي نحو ' + hours + ' ساعة' : '')));
    return g;
  }

  function render(data) {
    var f = data.farm;
    app.textContent = '';
    app.appendChild(el('h1', f.farm));
    var sub = el('div', f.locality + (params.get('now') ? ' — ' : ''), 'sub');
    if (params.get('now')) sub.appendChild(el('span', 'عرض تجريبي: ' + params.get('now').replace('T', ' '), 'tag'));
    app.appendChild(sub);
    app.appendChild(el('div', f.overall_label, 'banner s-' + f.overall));
    if (f.sensors) {
      var box = el('section', null, 'card');
      box.appendChild(el('h2', 'حالة المزرعة (من الحساسات)'));
      var grid = el('div', null, 'gauges');
      grid.appendChild(gauge('الخزان', f.sensors.tank_pct, f.sensors.tank_hours));
      grid.appendChild(gauge('البطارية', f.sensors.battery_pct, f.sensors.battery_hours));
      box.appendChild(grid); app.appendChild(box);
    }
    if (!f.alerts.length) app.appendChild(el('div', f.all_clear_text, 'card'));
    f.alerts.forEach(function (a) { app.appendChild(renderAlert(a, data.status_labels)); });
  }

  fetch(url).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
    .then(function (res) {
      if (!res.ok) throw new Error(res.body.error || 'error');
      render(res.body);
    })
    .catch(function (e) {
      app.textContent = '';
      app.appendChild(el('p', e.message === 'unknown farm' ? 'هذا الرابط غير صالح: المزرعة غير موجودة.' : 'تعذّر تحميل البيانات. حاول لاحقا.', 'err'));
    });
})();
</script>
</body>
</html>
"""


def render(endpoint: str = "/api/farmer-view") -> str:
    """The page, told which address gives the farm data (the plain server and the FastAPI router differ)."""
    return _TEMPLATE.replace("__ENDPOINT__", endpoint)


PAGE = render()          # old name, kept so nothing else breaks
