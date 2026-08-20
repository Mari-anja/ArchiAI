// The local test page. Talks to the same service that Arqio will talk to, by
// the same routes, so what you try here is what you get there.
const $ = s => document.querySelector(s);
let MODE = "brief";
let LAST = null;          // the last response, so a revision has a source
let RINGS = [];           // drawn outline: [[ [x,y], ... ], ...]
let CUR = [];
let IMAGE = null;         // base64 of the uploaded picture
let TRACED = null;
let PENDING = null;       // a trace still in flight, so Generate can wait for it

function mode(m) {
  MODE = m;
  document.querySelectorAll(".tabs button").forEach(b =>
    b.setAttribute("aria-selected", b.dataset.mode === m));
  for (const k of ["brief", "draw", "image"]) $("#m-" + k).hidden = k !== m;
}

function ex(btn) { $("#brief").value = btn.textContent.trim(); parse(); }

// --- describe ---------------------------------------------------------------
let parseTimer = null;
$("#brief").addEventListener("input", () => {
  clearTimeout(parseTimer);
  parseTimer = setTimeout(parse, 400);
});

async function parse() {
  const brief = $("#brief").value.trim();
  const box = $("#parsed");
  box.classList.remove("err");
  if (!brief) { box.textContent = "Type a brief and it will tell you what it understood."; return; }
  try {
    const r = await fetch("/v1/parse", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ brief })
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "could not read that");
    const s = d.spec;
    let html = `<b>Understood:</b> ${s.storeys} storey ${s.use}` +
      (s.area_m2 ? `, ${(+s.area_m2).toLocaleString()} m²` : "") +
      `, ${s.shape} shaped. About ${d.estimated_sheets} sheets.`;
    if (d.assumptions.length)
      html += `<br><b>Assumed:</b> ${d.assumptions.join(" ")}`;
    box.innerHTML = html;
    $("#storeys").value = s.storeys;
    if (s.use) $("#use").value = s.use;
  } catch (e) {
    box.classList.add("err");
    box.textContent = e.message;
  }
}

// --- draw -------------------------------------------------------------------
const pad = $("#pad"), pctx = pad.getContext("2d");
pad.addEventListener("click", e => {
  const r = pad.getBoundingClientRect();
  const p = [(e.clientX - r.left) * pad.width / r.width,
             (e.clientY - r.top) * pad.height / r.height];
  if (CUR.length > 2) {
    const d = Math.hypot(p[0] - CUR[0][0], p[1] - CUR[0][1]);
    if (d < 14) { padClose(); return; }
  }
  CUR.push(p); drawPad();
});
function padUndo() { CUR.pop(); drawPad(); }
function padClose() { if (CUR.length > 2) { RINGS.push(CUR); CUR = []; } drawPad(); }
function padClear() { RINGS = []; CUR = []; drawPad(); }

function drawPad() {
  pctx.clearRect(0, 0, pad.width, pad.height);
  pctx.fillStyle = "#fcfcfb"; pctx.fillRect(0, 0, pad.width, pad.height);
  RINGS.forEach((ring, i) => {
    pctx.beginPath();
    ring.forEach((p, k) => k ? pctx.lineTo(...p) : pctx.moveTo(...p));
    pctx.closePath();
    pctx.fillStyle = i === 0 ? "#e7eefb" : "#fcfcfb";
    pctx.fill();
    pctx.strokeStyle = i === 0 ? "#1f6feb" : "#8a93a0";
    pctx.lineWidth = 2; pctx.stroke();
  });
  if (CUR.length) {
    pctx.beginPath();
    CUR.forEach((p, k) => k ? pctx.lineTo(...p) : pctx.moveTo(...p));
    pctx.strokeStyle = "#1f6feb"; pctx.lineWidth = 2; pctx.stroke();
    CUR.forEach(p => {
      pctx.beginPath(); pctx.arc(p[0], p[1], 3.5, 0, 7); 
      pctx.fillStyle = "#1f6feb"; pctx.fill();
    });
  }
}
drawPad();

function drawnFootprint() {
  if (!RINGS.length) throw new Error("Draw a shape first, and close it.");
  // canvas pixels to metres, from the width the user gave
  const all = RINGS.flat();
  const xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const span = Math.max(Math.max(...xs) - Math.min(...xs),
                        Math.max(...ys) - Math.min(...ys)) || 1;
  const k = (+$("#width_m").value || 70) / span;
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const conv = ring => ring.map(p => [ +(((p[0] - cx) * k).toFixed(3)),
                                       +(((cy - p[1]) * k).toFixed(3)) ]);
  return { outer: conv(RINGS[0]), holes: RINGS.slice(1).map(conv) };
}

// --- upload -----------------------------------------------------------------
$("#file").addEventListener("change", e => {
  const f = e.target.files[0];
  if (!f) return;
  PENDING = trace(f);
});

// Reading the picture and tracing it takes a moment. If Generate is pressed
// in that moment, wait for it rather than saying no picture was chosen.
async function trace(f) {
  const note = $("#trace-note");
  note.classList.remove("err");
  note.textContent = "Reading the outline…";
  IMAGE = await new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(String(r.result).split(",")[1]);
    r.onerror = rej;
    r.readAsDataURL(f);
  });
  try {
    const r = await fetch("/v1/trace", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ image: { data: IMAGE, area_m2: +$("#area_m2").value } })
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "could not read that picture");
    TRACED = d;
    showTrace(d);
    note.innerHTML = `<b>Read:</b> ${d.vertices} corners, ` +
      `${d.width_m} × ${d.depth_m} m, ${d.area_m2.toLocaleString()} m²` +
      (d.holes.length ? `, ${d.holes.length} courtyard` : "") +
      (d.notes.length ? `<br>${d.notes.join(" ")}` : "");
  } catch (err) {
    note.classList.add("err");
    note.textContent = err.message;
    TRACED = null;
  }
}

function showTrace(d) {
  const c = $("#traced"), ctx = c.getContext("2d");
  ctx.clearRect(0, 0, c.width, c.height);
  ctx.fillStyle = "#fcfcfb"; ctx.fillRect(0, 0, c.width, c.height);
  const pts = d.outer.concat(...d.holes);
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const w = Math.max(...xs) - Math.min(...xs), h = Math.max(...ys) - Math.min(...ys);
  const k = Math.min((c.width - 40) / (w || 1), (c.height - 40) / (h || 1));
  const mx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const my = (Math.min(...ys) + Math.max(...ys)) / 2;
  const P = p => [c.width / 2 + (p[0] - mx) * k, c.height / 2 - (p[1] - my) * k];
  const ring = (r, fill, stroke) => {
    ctx.beginPath();
    r.forEach((p, i) => i ? ctx.lineTo(...P(p)) : ctx.moveTo(...P(p)));
    ctx.closePath(); ctx.fillStyle = fill; ctx.fill();
    ctx.strokeStyle = stroke; ctx.lineWidth = 2; ctx.stroke();
  };
  ring(d.outer, "#e7eefb", "#1f6feb");
  d.holes.forEach(hh => ring(hh, "#fcfcfb", "#8a93a0"));
}

// --- generate ---------------------------------------------------------------
async function body() {
  if (MODE === "image" && PENDING) { await PENDING; PENDING = null; }
  const b = {
    storeys: +$("#storeys").value,
    disciplines: $("#disciplines").value ? [$("#disciplines").value] : null,
    views: [{ name: "aerial-ne", width: 1100, height: 690 },
            { name: "entrance", width: 1100, height: 690 }],
    turntable: 6
  };
  const use = $("#use").value, ent = +$("#entrance").value;
  if (MODE === "brief") {
    const brief = $("#brief").value.trim();
    if (!brief) throw new Error("Write a brief first, or pick an example.");
    return { brief, ...strip(b) };
  }
  if (MODE === "draw") {
    const f = drawnFootprint();
    return { footprint: { ...f, storeys: b.storeys, use, entrance_azimuth: ent },
             ...strip(b) };
  }
  if (!IMAGE) throw new Error("Choose a picture first.");
  return { image: { data: IMAGE, area_m2: +$("#area_m2").value,
                    storeys: b.storeys, use, entrance_azimuth: ent },
           ...strip(b) };
}
function strip(b) { const { storeys, ...rest } = b; return rest; }

async function generate() {
  const btn = $("#go"), st = $("#status");
  st.hidden = false; st.classList.remove("err");
  btn.disabled = true;
  btn.innerHTML = '<span class="spin"></span>Generating…';
  let payload;
  try { payload = await body(); }
  catch (e) {
    st.classList.add("err"); st.textContent = e.message;
    btn.disabled = false; btn.textContent = "Generate the project";
    return;
  }
  st.textContent = "Drawing every sheet, the model and the views. A few seconds.";
  const t0 = performance.now();
  try {
    const r = await fetch("/v1/generate", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "generation failed");
    LAST = d;
    show(d, Math.round(performance.now() - t0));
    st.hidden = true;
  } catch (e) {
    st.classList.add("err"); st.textContent = e.message;
  } finally {
    btn.disabled = false; btn.textContent = "Generate the project";
  }
}

function asset(d, pred) { return d.assets.find(pred); }

function show(d, ms, changes) {
  const p = d.manifest.project;
  const sheets = d.assets.filter(a => a.kind === "drawing");
  const views = d.assets.filter(a => a.kind === "view");
  const page = asset(d, a => a.meta && a.meta.format === "html");
  const pdf = asset(d, a => a.meta && a.meta.format === "pdf");
  const el = $("#out");
  el.innerHTML = `
    <div class="strip">
      <div class="stat"><span>Storeys</span><b>${p.storeys}</b></div>
      <div class="stat"><span>Floor area</span><b>${Math.round(p.gia_m2).toLocaleString()} m²</b></div>
      <div class="stat"><span>Footprint</span><b>${Math.round(p.footprint_m2).toLocaleString()} m²</b></div>
      <div class="stat"><span>Height</span><b>${p.height_m.toFixed(1)} m</b></div>
      <div class="stat"><span>Drawings</span><b>${sheets.length}</b></div>
      <div class="stat"><span>Took</span><b>${(ms / 1000).toFixed(1)} s</b></div>
      ${p.revision ? `<div class="stat"><span>Revision</span><b>${p.revision}</b></div>` : ""}
    </div>
    ${changes ? `<ul class="changes">${changes.map(c => `<li>${c}</li>`).join("")}</ul>` : ""}
    <div class="acts">
      ${page ? `<a class="primary" href="${page.url}" target="_blank">Open the project page</a>` : ""}
      ${pdf ? `<a href="${pdf.url}" target="_blank">Download the PDF (${sheetCount(pdf)} pages)</a>` : ""}
    </div>
    <div class="gal">
      ${views.map(v => `<a href="${v.url}" target="_blank">
         <img src="${v.url}" alt="${v.title}"><small>${v.title}</small></a>`).join("")}
    </div>
    <div class="edit">
      <h2>Change your mind</h2>
      <div class="chips">
        <button onclick='revise({"storeys":"+1"})'>One more storey</button>
        <button onclick='revise({"storeys":"-1"})'>One fewer</button>
        <button onclick='revise({"area_m2":"+20%"})'>20% bigger</button>
        <button onclick='revise({"courtyard":"bigger"})'>Bigger courtyard</button>
        <button onclick='revise({"courtyard":"none"})'>No courtyard</button>
        <button onclick='revise({"entrance":"north"})'>Entrance north</button>
      </div>
      <div class="note" id="rev-note" hidden></div>
    </div>
    <div class="sheets">
      ${sheets.map(s => `<div><span>${s.number}</span>${s.title}</div>`).join("")}
    </div>`;
}
function sheetCount(pdf) { return (pdf.meta && pdf.meta.pages) || "?"; }

async function revise(changes) {
  if (!LAST) return;
  const note = $("#rev-note");
  note.hidden = false; note.classList.remove("err");
  note.innerHTML = '<span class="spin" style="border-color:#6b7178;border-top-color:transparent"></span>Rebuilding…';
  const t0 = performance.now();
  try {
    const r = await fetch("/v1/revise", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({
        source: LAST.manifest.source, changes,
        parent_generation_id: LAST.generation_id,
        disciplines: $("#disciplines").value ? [$("#disciplines").value] : null,
        views: [{ name: "aerial-ne", width: 1100, height: 690 },
                { name: "entrance", width: 1100, height: 690 }],
        turntable: 6
      })
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "could not make that change");
    LAST = d;
    show(d, Math.round(performance.now() - t0), d.manifest.revision.changed);
  } catch (e) {
    note.classList.add("err"); note.textContent = e.message;
  }
}
