"""The whole project as one page you can send someone.

A drawing set is not much use as fifty-five files and a folder. This puts the
sheets, the views, a model you can turn, and the numbers into a single HTML
file with nothing loaded from anywhere else, so it works from a link, from an
email attachment, or from a memory stick on a site office laptop with no
internet.

Sheets are held in script tags and injected when they are asked for. Putting
fifty-five A1 drawings in the DOM at once is what makes a page like this take
ten seconds to open.
"""

import html
import json
import re

from . import openings as OP
from . import services as SV
from . import view as VW


def _svg_only(text):
    """Strip anything before the <svg> so it can sit inside a script tag."""
    i = text.find("<svg")
    return text[i:] if i >= 0 else text


def _fmt(v):
    return "{:,.0f}".format(v).replace(",", " ")


DISCIPLINE = {"A": "Architecture", "S": "Structure", "E": "Electrical",
              "M": "Mechanical", "P": "Public health", "FS": "Fire"}


def _facts(project):
    m = project.massing
    fp = project.floorplans[0]
    tot = OP.totals(project)
    st = SV.structure(project, 0)
    svc = {}
    for f in project.floorplans:
        for k, v in SV.totals(SV.for_floor(f)).items():
            svc[k] = svc.get(k, 0) + v
    esc = SV.escape(fp)
    return [
        ("Storeys", str(len(m.levels))),
        ("Gross internal area", "%s m²" % _fmt(m.gia())),
        ("Footprint", "%s m²" % _fmt(m.footprint().area)),
        ("Height to roof", "%.2f m" % m.height),
        ("Floor to floor", "%.2f m" % m.levels[0].to_ffl),
        ("Rooms", str(sum(len(f.rooms) for f in project.floorplans))),
        ("Doors", "%d in %d types" % (tot["doors"], tot["door_types"])),
        ("Glazed units", "%d, %s m²" % (tot["windows"],
                                        _fmt(tot["glazed_area_m2"]))),
        ("Structural grid", "%d × %d mm" % (int(st["spacing"][0] * 1000),
                                            int(st["spacing"][1] * 1000))),
        ("Design occupancy", "%d people" % svc.get("occupants", 0)),
        ("Worst escape route", "%.1f m of %.0f m" % (esc.worst, esc.limit)),
    ]


CSS = """
:root{--ink:#15181c;--grey:#6b7178;--line:#dfe1e4;--bg:#f6f6f4;--card:#fff;
      --blue:#1f6feb}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
header{background:var(--card);border-bottom:1px solid var(--line);padding:18px 24px}
h1{margin:0;font-size:20px;letter-spacing:.4px}
.sub{color:var(--grey);font-size:13px;margin-top:2px}
nav{display:flex;gap:2px;padding:0 24px;background:var(--card);
    border-bottom:1px solid var(--line)}
nav button{border:0;background:none;padding:11px 14px;font:inherit;
    color:var(--grey);cursor:pointer;border-bottom:2px solid transparent}
nav button[aria-selected=true]{color:var(--ink);border-bottom-color:var(--blue)}
main{padding:20px 24px 60px}
section[hidden]{display:none}
.wrap{display:grid;grid-template-columns:250px 1fr;gap:20px;align-items:start}
.list{background:var(--card);border:1px solid var(--line);border-radius:8px;
      overflow:hidden;max-height:78vh;overflow-y:auto}
.list h3{margin:0;padding:9px 12px;font-size:11px;letter-spacing:1px;
    text-transform:uppercase;color:var(--grey);background:#fafaf9;
    border-bottom:1px solid var(--line);position:sticky;top:0}
.list a{display:block;padding:7px 12px;color:var(--ink);text-decoration:none;
    border-bottom:1px solid #f0f0ee;font-size:13px}
.list a:hover{background:#f3f6fb}
.list a[aria-current=true]{background:#eaf1fd;box-shadow:inset 3px 0 var(--blue)}
.list .no{color:var(--grey);font-variant-numeric:tabular-nums;margin-right:7px}
.paper{background:var(--card);border:1px solid var(--line);border-radius:8px;
    padding:10px;min-height:60vh}
.paper svg{width:100%;height:auto;display:block}
.gal{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px}
.gal figure{margin:0;background:var(--card);border:1px solid var(--line);
    border-radius:8px;overflow:hidden}
.gal svg{width:100%;height:auto;display:block;background:#eef2f5}
.gal figcaption{padding:9px 12px;font-size:13px;border-top:1px solid var(--line)}
.gal small{color:var(--grey)}
.facts{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));
    gap:10px;margin-bottom:20px}
.fact{background:var(--card);border:1px solid var(--line);border-radius:8px;
    padding:11px 13px}
.fact b{display:block;font-size:17px;font-weight:600}
.fact span{color:var(--grey);font-size:11px;letter-spacing:.8px;
    text-transform:uppercase}
table{border-collapse:collapse;width:100%;background:var(--card);
    border:1px solid var(--line);border-radius:8px;overflow:hidden}
th,td{padding:7px 12px;text-align:left;border-bottom:1px solid #f0f0ee;
    font-size:13px}
th{font-size:11px;letter-spacing:.8px;text-transform:uppercase;color:var(--grey);
   background:#fafaf9}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.turn{background:var(--card);border:1px solid var(--line);border-radius:8px;
    padding:12px;text-align:center}
.turn .stage{position:relative}
.turn .stage svg{width:auto;max-width:100%;max-height:70vh;
    height:auto;display:none;margin:0 auto}
.turn .stage svg.on{display:block}
.turn input{width:min(560px,90%);margin-top:10px}
.hint{color:var(--grey);font-size:12px;margin-top:4px}
footer{color:var(--grey);font-size:12px;padding:0 24px 30px}
@media(max-width:820px){.wrap{grid-template-columns:1fr}}
"""

JS = """
const $=s=>document.querySelector(s);
let current = 'summary';
function tab(name, keep){
  if(!document.getElementById('tab-'+name)) name = 'summary';
  current = name;
  document.querySelectorAll('nav button').forEach(b=>
    b.setAttribute('aria-selected', b.dataset.tab===name));
  document.querySelectorAll('main > section').forEach(s=>
    s.hidden = s.id !== 'tab-'+name);
  if(!keep) hash();
}
function sheet(id, el, keep){
  const src = document.getElementById('svg-'+id);
  if(src) $('#paper').innerHTML = src.textContent;
  document.querySelectorAll('.list a').forEach(a=>
    a.setAttribute('aria-current', a === el));
  if(!keep) hash(id);
}
function hash(id){
  const a = document.querySelector('.list a[aria-current=true]');
  const sheetId = id || (a && a.dataset.id);
  history.replaceState(null, '',
    '#' + current + (current === 'drawings' && sheetId ? '/' + sheetId : ''));
}
function turn(i){
  document.querySelectorAll('.stage svg').forEach((s,k)=>
    s.classList.toggle('on', k === +i));
}
/* A link can point at one drawing: #drawings/A-100 opens that sheet. */
function open_from_hash(){
  const parts = location.hash.slice(1).split('/');
  const want = parts[1];
  const target = want && document.querySelector('[data-id="'+CSS.escape(want)+'"]');
  const first = document.querySelector('.list a');
  const el = target || first;
  if(el) sheet(el.dataset.id, el, true);
  tab(parts[0] || 'summary', true);
}
window.addEventListener('DOMContentLoaded', open_from_hash);
window.addEventListener('hashchange', open_from_hash);
"""


def build(project, out_path, sheets=None, views=None, turntable=8,
          title=None, subtitle=None):
    """One self-contained HTML file. `sheets` is the register `build` returns."""
    info = project.info
    m = project.massing
    sheets = list(sheets or [])
    views = list(views or [])

    parts = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
             "<meta name=\"viewport\" content=\"width=device-width,"
             "initial-scale=1\">",
             "<title>%s</title>" % html.escape(title or info.get("name", "Project")),
             "<style>%s</style></head><body>" % CSS]

    parts.append("<header><h1>%s</h1><div class=\"sub\">%s · %s · %s · "
                 "%d storeys · %s m² · revision %s</div></header>"
                 % (html.escape(info.get("name", "PROJECT")),
                    html.escape(subtitle or info.get("subtitle", "")),
                    html.escape(info.get("number", "")),
                    html.escape(info.get("date", "")),
                    len(m.levels), _fmt(m.gia()),
                    html.escape(info.get("rev", "P01"))))

    tabs = [("summary", "Summary"), ("drawings", "Drawings")]
    if views:
        tabs.append(("views", "Views"))
    if turntable:
        tabs.append(("model", "Model"))
    parts.append("<nav>" + "".join(
        "<button data-tab=\"%s\" onclick=\"tab('%s')\" aria-selected=\"%s\">%s"
        "</button>" % (k, k, "true" if i == 0 else "false", lab)
        for i, (k, lab) in enumerate(tabs)) + "</nav><main>")

    # -- summary ----------------------------------------------------------
    parts.append("<section id=\"tab-summary\"><div class=\"facts\">")
    for label, value in _facts(project):
        parts.append("<div class=\"fact\"><span>%s</span><b>%s</b></div>"
                     % (html.escape(label), html.escape(value)))
    parts.append("</div>")
    parts.append("<table><thead><tr><th>Level</th><th>FFL</th>"
                 "<th class=\"n\">Rooms</th><th class=\"n\">Circulation</th>"
                 "<th class=\"n\">Area</th></tr></thead><tbody>")
    for i, lv in enumerate(m.levels):
        fp = project.floorplans[i]
        parts.append("<tr><td>%s</td><td>%+.3f</td><td class=\"n\">%d</td>"
                     "<td class=\"n\">%s m²</td><td class=\"n\">%s m²</td></tr>"
                     % (html.escape(lv.name), lv.ffl, len(fp.rooms),
                        _fmt(fp.circulation_area), _fmt(lv.area)))
    parts.append("</tbody></table></section>")

    # -- drawings ---------------------------------------------------------
    parts.append("<section id=\"tab-drawings\" hidden><div class=\"wrap\">"
                 "<div class=\"list\">")
    groups = {}
    for entry in sheets:
        number, sheet_title = entry[0], entry[1]
        prefix = number.split("-")[0]
        groups.setdefault(DISCIPLINE.get(prefix, prefix), []).append(entry)
    for name in sorted(groups, key=lambda k: list(DISCIPLINE.values()).index(k)
                       if k in DISCIPLINE.values() else 99):
        parts.append("<h3>%s</h3>" % html.escape(name))
        for entry in groups[name]:
            number, sheet_title = entry[0], entry[1]
            parts.append("<a href=\"javascript:void 0\" data-id=\"%s\" "
                         "onclick=\"sheet('%s',this)\"><span class=\"no\">%s"
                         "</span>%s</a>"
                         % (number, number, html.escape(number),
                            html.escape(sheet_title)))
    parts.append("</div><div class=\"paper\" id=\"paper\"></div></div></section>")

    # -- views ------------------------------------------------------------
    if views:
        parts.append("<section id=\"tab-views\" hidden><div class=\"gal\">")
        for v in views:
            parts.append("<figure>%s<figcaption>%s<br><small>%s</small>"
                         "</figcaption></figure>"
                         % (_svg_only(v["svg"]), html.escape(v.get("title", "View")),
                            html.escape(v.get("note", ""))))
        parts.append("</div></section>")

    # -- turntable --------------------------------------------------------
    if turntable:
        frames = []
        for i in range(turntable):
            az = 360.0 * i / turntable
            frames.append(VW.render(project, "aerial-ne",
                                    addons=("ground", "sky", "shadow"),
                                    width=1000, height=620, azimuth=az))
        parts.append("<section id=\"tab-model\" hidden><div class=\"turn\">"
                     "<div class=\"stage\">")
        for i, svg in enumerate(frames):
            parts.append(_svg_only(svg).replace("<svg ", "<svg class=\"on\" ", 1)
                         if i == 0 else _svg_only(svg))
        parts.append("</div><input type=\"range\" min=\"0\" max=\"%d\" value=\"0\" "
                     "oninput=\"turn(this.value)\">"
                     "<div class=\"hint\">Drag to turn the building. Every frame "
                     "is drawn from the model, at the same sun.</div>"
                     "</div></section>" % (turntable - 1))

    parts.append("</main><footer>Generated by the ArchiAI building engine. "
                 "Every drawing on this page comes from one model; change a "
                 "dimension and the whole set redraws.</footer>")

    for entry in sheets:
        number, path = entry[0], entry[3] if len(entry) > 3 else None
        if not path:
            continue
        with open(path) as fh:
            parts.append("<script type=\"text/svg\" id=\"svg-%s\">%s</script>"
                         % (number, _svg_only(fh.read())))
    parts.append("<script>%s</script></body></html>" % JS)

    doc = "".join(parts)
    if hasattr(out_path, "write"):
        out_path.write(doc.encode("utf-8"))
        return out_path
    with open(out_path, "w") as fh:
        fh.write(doc)
    return out_path
