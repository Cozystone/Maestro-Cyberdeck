// ATANOR Shell — Core(127.0.0.1:7700)의 이벤트를 받아 오브·패널·배치를 그린다.
(function () {
  const T = window.ATANOR_TOKEN;
  const $ = (s) => document.querySelector(s);
  const api = async (path, body) => (await fetch(path, { method: body ? "POST" : "GET",
    headers: { "X-Atanor-Token": T, "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined })).json();
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const md = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`(.+?)`/g, "<code>$1</code>").replace(/^#{1,3} (.*)$/gm, "<h2>$1</h2>");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const orb = new Orb($("#orb"));
  const stage = $("#stage"), orbWrap = $("#orb-wrap"), voice = $("#voice");
  let ui = { panels: {}, theme: {} };
  // ---------- 목소리: 듣기 · 말하기 ----------
  const VOX = new AtanorVoice({
    token: T, orb,
    onState: (st, info) => {
      const mic = $("#mic"); mic.dataset.state = st;
      if (st === "once") { orb.set("listen"); voice.classList.remove("murmur"); voice.classList.add("thinking"); voice.textContent = "듣고 있어요"; }
      else if (st === "hearing") voice.textContent = "듣고 있어요…";
      else if (st === "recognizing") voice.textContent = "알아듣는 중";
      else if (st === "nomic") toast("마이크를 쓸 수 없어요", info, true);
      else if (st === "error") toast("음성 인식", info, true);
      else if ((st === "wake" || st === "off") && voice.textContent.startsWith("듣고")) { voice.textContent = ""; voice.classList.remove("thinking"); orb.set("idle"); }
      mic.title = { wake: "부르면 대답합니다: '아타노르, …' (Ctrl+Space: 바로 말하기)", off: "말하기 (Ctrl+Space)", once: "듣는 중 — 다시 누르면 취소" }[st] || mic.title;
    },
    onText: (text, kind) => {
      if (kind === "busy") toast("아직 하던 일이 있어요", `들은 말: ${text}`);
      else if (kind === "none") { voice.classList.remove("thinking"); voice.textContent = text ? `"${text}"` : "잘 못 들었어요"; orb.set("idle"); }
    },
  });
  const speakOn = () => ui.theme.speak !== false;
  window.__vox = VOX;   // 진단용
  const relayout = () => Layout.apply(stage, orbWrap, voice, ui.theme.layout || "auto", ui.theme.layout_seed);
  let rl = null; const relayoutSoon = () => { clearTimeout(rl); rl = setTimeout(relayout, 30); };
  addEventListener("resize", relayoutSoon);

  // ---------- 글리프 비: 평소엔 거의 보이지 않고, 생각할 때 짙어진다 ----------
  (function rain() {
    if (reduced) return;
    const c = $("#rain"), ctx = c.getContext("2d"), fs = 15, G = "ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎㅏㅓㅗㅜㅡㅣアイウエオカキクケコサシスセソ01";
    let cols = [];
    const size = () => { c.width = innerWidth; c.height = innerHeight; cols = Array.from({ length: Math.ceil(innerWidth / fs) }, () => Math.random() * -innerHeight); };
    size(); addEventListener("resize", size);
    setInterval(() => {
      const e = orb.energy;
      ctx.fillStyle = "rgba(0,2,4,.2)"; ctx.fillRect(0, 0, c.width, c.height);
      ctx.font = `${fs}px "Noto Sans Mono CJK KR", monospace`;
      cols.forEach((y, i) => {
        if (Math.random() > 0.025 + e * 0.45) return;
        const head = Math.random() < 0.04;
        ctx.fillStyle = head ? `rgba(241,251,255,${0.25 + e * 0.4})` : (i % 7 === 0 ? `rgba(189,109,255,${0.05 + e * 0.18})` : `rgba(32,244,255,${0.05 + e * 0.2})`);
        ctx.fillText(G[(Math.random() * G.length) | 0], i * fs, y);
        cols[i] = y > c.height + 40 ? Math.random() * -240 : y + fs;
      });
    }, 70);
  })();

  // ---------- 시계 · 신호 ----------
  const DAYS = "일월화수목금토";
  function tick() { const d = new Date(); $("#time").textContent = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    $("#date").textContent = `${d.getMonth() + 1}월 ${d.getDate()}일 ${DAYS[d.getDay()]}요일`; }
  tick(); setInterval(tick, 5000);
  let lastStatus = null;
  async function pollStatus() {
    try { const s = await api("/api/status"); lastStatus = s;
      $("#s-net").textContent = (s.network || "").includes("UP") ? "연결됨" : "오프라인";
      $("#s-bat").textContent = s.battery ? "배터리 " + s.battery.split(" ")[0] : "";
      document.querySelectorAll(".panel[data-type=status] .body").forEach((b) => (b.innerHTML = statusHTML(s))); } catch {}
  }
  function statusHTML(s) {
    const rows = [["시간", s.time], ["가동", s.uptime], ["부하", (s.load || []).join(" ")], ["메모리", s.memory], ["디스크 여유", s.disk_free],
      ["배터리", s.battery], ["음량", s.volume], ["밝기", s.brightness], ["네트워크", (s.network || "").split("\n").filter((l) => /UP|ssid/.test(l)).join("\n")]];
    return `<div class="sg">${rows.filter((r) => r[1]).map((r) => `<b>${r[0]}</b><span>${esc(r[1])}</span>`).join("")}</div>`;
  }
  pollStatus(); setInterval(pollStatus, 15000);

  // ---------- 해독: 새 패널의 글자는 노이즈에서 떠오른다 ----------
  const NOISE = "ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎアイウエオ0123456789";
  const FINAL = new WeakMap();
  function decode(el) {
    if (reduced || !el) return;
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), nodes = []; let n;
    // 같은 글자에 해독 효과가 겹치면 두 번째가 '뒤섞인 글자'를 원문으로 착각한다 → 원문은 노드마다 한 번만 기억
    while ((n = w.nextNode())) if (n.nodeValue.trim()) { if (!FINAL.has(n)) FINAL.set(n, n.nodeValue); nodes.push([n, FINAL.get(n)]); }
    let step = 0; const steps = 12; el.classList.add("decoding");
    const iv = setInterval(() => {
      step++;
      for (const [node, fin] of nodes) { const k = Math.floor(fin.length * (step / steps)); node.nodeValue = fin.slice(0, k) + [...fin.slice(k)].map((ch) => (/\s/.test(ch) ? ch : NOISE[(Math.random() * NOISE.length) | 0])).join(""); }
      if (step >= steps) { clearInterval(iv); for (const [node, fin] of nodes) { node.nodeValue = fin; FINAL.delete(node); } el.classList.remove("decoding"); }
    }, 34);
  }

  // 시계 패널은 1초마다 스스로 간다
  setInterval(() => document.querySelectorAll(".clock").forEach((c) => {
    const o = c.dataset.tz ? { timeZone: c.dataset.tz } : {}, n = new Date();
    c.querySelector("b").textContent = n.toLocaleTimeString("ko-KR", { ...o, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
    c.querySelector("span").textContent = n.toLocaleDateString("ko-KR", { ...o, month: "long", day: "numeric", weekday: "long" });
  }), 1000);

  // ---------- 패널 ----------
  function render(next) {
    ui = next || ui; const th = ui.theme || {};
    document.documentElement.dataset.mode = th.mode === "light" ? "light" : "dark";
    const rs = document.documentElement.style, sc = Math.max(0.8, Math.min(1.6, +th.scale || 1));
    if (rs.getPropertyValue("--ui-scale") !== String(sc)) { rs.setProperty("--ui-scale", sc); setTimeout(relayout, 60); }
    if (/^#[0-9a-f]{6}$/i.test(th.accent || "")) rs.setProperty("--accent", th.accent); else rs.removeProperty("--accent");
    if (VOX.wake !== (th.wake !== false)) VOX.setWake(th.wake !== false);   // 기본: 부르면 대답
    const panels = Object.values(ui.panels || {}).sort((a, b) => (a.order ?? 50) - (b.order ?? 50));
    document.documentElement.dataset.state = panels.length ? "active" : "idle";
    const seen = new Set(), fresh = [];
    for (const p of panels) {
      seen.add(p.id);
      let el = stage.querySelector(`[data-id="${CSS.escape(p.id)}"]`);
      const json = JSON.stringify(p);
      if (el && el.dataset.json === json) continue;
      const isNew = !el;
      if (isNew) {
        el = document.createElement("section"); el.dataset.id = p.id; stage.appendChild(el);
        // 새 패널은 오브에서 태어난다
        const r = orbWrap.getBoundingClientRect(); el.style.transform = `translate(${r.left + r.width / 2 - 100}px, ${r.top + r.height / 2}px)`; el.style.width = "200px";
        el.className = "panel entering";
      }
      el.dataset.json = json; el.dataset.type = p.type; el.style.order = p.order ?? 50;
      el.className = `panel${isNew ? " entering" : ""}`;
      let inner; try { inner = body(p); } catch (err) { inner = `<span class="err">이 패널을 그리지 못했습니다: ${esc(err.message)}</span>`; }
      el.innerHTML = `<h3><span>${esc(p.title || p.id)}</span><span class="x" title="닫기">×</span></h3><div class="body">${inner}</div>`;
      el.querySelector(".x").onclick = () => api("/api/tool", { name: "ui.remove", args: { id: p.id }, source: "ui" });
      el.querySelectorAll("[data-prompt]").forEach((b) => (b.onclick = () => send(b.dataset.prompt)));
      el.querySelectorAll("form.aform").forEach((f) => (f.onsubmit = (ev) => { ev.preventDefault();
        const vals = Object.fromEntries(new FormData(f).entries());
        const tpl = f.dataset.promptTpl || Object.entries(vals).map(([k, v]) => `${k}: {${k}}`).join(", ");
        send(tpl.replace(/\{(\w+)\}/g, (_, k) => vals[k] ?? "")); }));
      if (isNew) fresh.push(el);
    }
    stage.querySelectorAll(".panel").forEach((el) => { if (!seen.has(el.dataset.id)) { el.style.opacity = 0; setTimeout(() => el.remove(), 400); el.dataset.id = "_gone"; } });
    requestAnimationFrame(() => {
      relayout();
      fresh.forEach((el, i) => setTimeout(() => { el.classList.remove("entering"); decode(el.querySelector(".body")); }, 80 * i));
      if (fresh.length) orb.kick(0.6);
    });
  }
  // ---------- live: 도구 결과를 그대로 그린다 (모델이 베끼지 않으니 지어낼 수 없다) ----------
  function view(res, how) {
    if (typeof res === "string") return how === "text" ? `<div class="text">${md(res)}</div>` : `<pre class="logbox">${esc(res)}</pre>`;
    if (Array.isArray(res)) {
      if (res.length && typeof res[0] === "object" && how !== "list") {
        const cols = Object.keys(res[0]);
        return `<table><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${res.map((r) => `<tr>${cols.map((c) => `<td>${esc(typeof r[c] === "object" ? JSON.stringify(r[c]) : r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
      }
      return `<ul>${res.map((i) => `<li>${esc(typeof i === "object" ? i.content || i.text || i["이름"] || JSON.stringify(i) : i)}</li>`).join("")}</ul>`;
    }
    if (res && typeof res === "object") return `<dl class="kv">${Object.entries(res).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${Array.isArray(v) ? v.map((x) => esc(typeof x === "object" ? JSON.stringify(x) : x)).join("<br>") : esc(typeof v === "object" ? JSON.stringify(v) : v)}</dd>`).join("")}</dl>`;
    return esc(res);
  }

  // ---------- 차트 (SVG, 외부 라이브러리 없이) ----------
  function chartSVG(d) {
    const W = 520, H = 200, P = 28, series = (d.series || []).filter((s) => Array.isArray(s.values)), labels = d.labels || [];
    if (!series.length) return "자료가 없습니다";
    const all = series.flatMap((s) => s.values.map(Number)), max = Math.max(...all, 0), min = Math.min(...all, 0), span = max - min || 1;
    const n = Math.max(...series.map((s) => s.values.length)), x = (i) => P + (i * (W - P * 2)) / Math.max(1, n - (d.kind === "bar" ? 0 : 1)), y = (v) => H - P - ((v - min) / span) * (H - P * 2);
    const colors = ["#20f4ff", "#bd6dff", "#ff4f9d", "#3aa8ff"];
    let g = `<line x1="${P}" y1="${y(0)}" x2="${W - P}" y2="${y(0)}" stroke="rgba(94,231,255,.2)"/>`;
    series.forEach((s, si) => {
      const c = colors[si % colors.length];
      if (d.kind === "bar") { const bw = (W - P * 2) / n / (series.length + 0.6); s.values.forEach((v, i) => { g += `<rect x="${x(i) + si * bw}" y="${Math.min(y(v), y(0))}" width="${bw * 0.9}" height="${Math.abs(y(v) - y(0))}" fill="${c}" opacity=".8"><title>${esc(labels[i] ?? i)}: ${esc(v)}</title></rect>`; }); }
      else g += `<polyline fill="none" stroke="${c}" stroke-width="1.6" points="${s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")}"/>` + s.values.map((v, i) => `<circle cx="${x(i)}" cy="${y(v)}" r="2.4" fill="${c}"><title>${esc(labels[i] ?? i)}: ${esc(v)}</title></circle>`).join("");
    });
    const step = Math.ceil(labels.length / 8) || 1;
    g += labels.map((l, i) => (i % step ? "" : `<text x="${x(i) + (d.kind === "bar" ? 8 : 0)}" y="${H - 8}" fill="#5d7d8f" font-size="10" text-anchor="middle">${esc(l)}</text>`)).join("");
    g += `<text x="${P}" y="14" fill="#5d7d8f" font-size="10">${esc(max)}</text>`;
    const legend = series.map((s, si) => `<span><i style="background:${colors[si % colors.length]}"></i>${esc(s.name || "")}</span>`).join("");
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${g}</svg>${series.length > 1 ? `<div class="legend">${legend}</div>` : ""}`;
  }

  // ---------- 미니 앱 다리: 격리된 앱이 비서·읽기 도구를 쓸 수 있게 ----------
  const APP_BRIDGE = `<script>(()=>{let n=0;const w=new Map();addEventListener("message",e=>{const m=e.data||{};if(m.atanorReply&&w.has(m.id)){w.get(m.id)(m.result);w.delete(m.id);}});
const call=(kind,payload)=>new Promise(r=>{const id=++n;w.set(id,r);parent.postMessage({atanor:kind,id,...payload},"*");});
window.atanor={ask:(text)=>call("ask",{text}),tool:(name,args)=>call("tool",{name,args})};})();<\/script>
<style>html,body{margin:0;background:transparent;color:#cfe6f2;font:13.5px "Noto Sans CJK KR",sans-serif}button,input,select{font:inherit;color:inherit;background:transparent;border:1px solid rgba(94,231,255,.25);padding:4px 10px}</style>`;
  addEventListener("message", async (e) => {
    const m = e.data || {}; if (!m.atanor) return;
    const frame = [...document.querySelectorAll("iframe.appframe")].find((f) => f.contentWindow === e.source); if (!frame) return;
    let result;
    if (m.atanor === "ask") { const r = await api("/api/ask", { text: String(m.text || ""), source: "app", wait: true }); result = r.reply; }
    else if (m.atanor === "tool") { const r = await api("/api/tool", { name: String(m.name || ""), args: m.args || {}, source: "app" }); result = r.result; }
    e.source.postMessage({ atanorReply: true, id: m.id, result }, "*");
  });

  function fill(id, html) { const el = stage.querySelector(`[data-id="${CSS.escape(id)}"] .body`); if (el) { el.innerHTML = html; decode(el); relayoutSoon(); } }
  function body(p) {
    const d = p.data || {};
    switch (p.type) {
      case "clock": return `<div class="clock" data-tz="${esc(d.tz || "")}"><b></b><span></span>${d.label ? `<small>${esc(d.label)}</small>` : ""}</div>`;
      case "text": return `<div class="text">${md(d.text || "")}</div>`;
      case "list": return `<ul>${(d.items || []).map((i) => `<li>${md(i)}</li>`).join("")}</ul>`;
      case "kv": return `<dl class="kv">${Object.entries(d.pairs || d).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(typeof v === "object" ? JSON.stringify(v) : v)}</dd>`).join("")}</dl>`;
      case "meter": { const v = Math.max(0, Math.min(100, +d.value || 0)); return `<div class="meter"><div class="val">${esc(d.display ?? v + "%")}</div><div class="bar"><i style="width:${v}%"></i></div><div class="lbl">${esc(d.label || "")}</div></div>`; }
      case "table": return `<table><thead><tr>${(d.columns || []).map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${(d.rows || []).map((r) => `<tr>${(Array.isArray(r) ? r : Object.values(r)).map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
      case "buttons": return `<div class="buttons">${(d.buttons || []).map((b) => `<button data-prompt="${esc(b.prompt || b.label)}">${esc(b.label)}</button>`).join("")}</div>`;
      case "image": { const src = /^https?:/.test(d.src) ? d.src : `/files/${String(d.src).replace(/^~\/|^\/home\/[^/]+\//, "")}?token=${T}`; return `<img src="${esc(src)}" alt="">`; }
      case "html": return `<iframe sandbox="allow-scripts" srcdoc="${esc(`<style>body{margin:0;font:13px 'Noto Sans CJK KR',sans-serif;color:#cfe6f2;background:transparent}</style>` + (d.html || ""))}"></iframe>`;
      case "live": api("/api/tool", { name: d.tool, args: d.args || {}, source: "app" }).then((r) => fill(p.id, r.ok ? view(r.result, d.view) : `<span class="err">${esc(r.result)}</span>`)); return "읽는 중";
      case "chart": return chartSVG(d);
      case "steps": return `<ol class="steps">${(d.steps || []).map((s) => { const o = typeof s === "string" ? { text: s } : s; return `<li class="${esc(o.state || "todo")}">${md(o.text)}</li>`; }).join("")}</ol>`;
      case "form": return `<form class="aform" data-prompt-tpl="${esc(d.prompt || "")}">${(d.fields || []).map((f) => `<label><span>${esc(f.label || f.name)}</span><input name="${esc(f.name)}" type="${esc(f.type || "text")}" autocomplete="off"></label>`).join("")}<button type="submit">${esc(d.submit || "보내기")}</button></form>`;
      case "log": return `<pre class="logbox">${esc((d.lines || []).join("\n"))}</pre>`;
      case "gallery": return `<div class="gallery">${(d.images || []).map((s) => `<img src="${esc(/^https?:/.test(s) ? s : `/files/${String(s).replace(/^~\/|^\/home\/[^/]+\//, "")}?token=${T}`)}" alt="">`).join("")}</div>`;
      case "app": api(`/api/app?name=${encodeURIComponent(d.name || p.id)}`).then((r) => { const box = stage.querySelector(`[data-id="${CSS.escape(p.id)}"] .body`); if (!box) return;
        const f = document.createElement("iframe"); f.setAttribute("sandbox", "allow-scripts allow-forms"); f.className = "appframe"; f.srcdoc = APP_BRIDGE + r.html; box.innerHTML = ""; box.appendChild(f); relayoutSoon(); }); return "불러오는 중";
      case "status": return lastStatus ? statusHTML(lastStatus) : "읽는 중";
      case "todo": api("/api/tool", { name: "todo.list", args: {}, source: "ui" }).then((r) => { const t = Array.isArray(r.result) ? r.result : [];
        fill(p.id, t.length ? `<ul class="todo">${t.map((x) => `<li class="${x.done ? "done" : ""}" data-todo="${esc(x.id)}">${esc(x.text)}</li>`).join("")}</ul>` : `<span class="dim">할 일이 없습니다. "우유 사기 적어줘"처럼 말해 보세요.</span>`);
        stage.querySelectorAll(`[data-id="${CSS.escape(p.id)}"] [data-todo]`).forEach((li) => (li.onclick = () => api("/api/tool", { name: "todo.done", args: { which: li.dataset.todo }, source: "ui" }))); }); return "읽는 중";
      case "windows": api("/api/tool", { name: "window.list", args: {}, source: "ui" }).then((r) => fill(p.id, (Array.isArray(r.result) ? r.result : []).map((w) => `<div class="win"><span class="app">${esc(w.app || "?")}</span><span>${esc(w.title || "")}</span><span class="ws">${esc(w.workspace || "")}</span></div>`).join("") || "열린 창이 없습니다")); return "읽는 중";
      case "memory": api("/api/memory").then((rows) => fill(p.id, rows.slice(0, 20).map((m) => `<div class="mem">${esc(m.content)}<small>${m.kind} ${Math.round(m.retention * 100)}%</small></div>`).join("") || "아직 기억이 없습니다")); return "읽는 중";
      default: return `<pre>${esc(JSON.stringify(d, null, 1))}</pre>`;
    }
  }

  // ---------- 목소리 · 기록 ----------
  const msgs = $("#messages"), say = $("#say");
  let speakIv = null, idleT = null;
  function speak(text) {
    clearInterval(speakIv); clearTimeout(idleT); voice.classList.remove("thinking"); orb.set("speak");
    if (speakOn()) VOX.say(text);
    if (reduced) voice.textContent = text;
    else { let i = 0; voice.textContent = ""; speakIv = setInterval(() => { voice.textContent = text.slice(0, (i += 2)); if (i >= text.length) clearInterval(speakIv); }, 22); }
    idleT = setTimeout(() => orb.set("idle"), 1800 + text.length * 25);
  }
  function thinking(text) { clearInterval(speakIv); voice.classList.add("thinking"); voice.classList.remove("murmur"); voice.textContent = text; }
  // 내면의 목소리: 주인이 없는 동안의 혼잣말. 옅게 비치고 사라진다.
  let murmurT = null;
  function murmur(text, settle) {
    clearInterval(speakIv); clearTimeout(murmurT);
    voice.classList.remove("thinking"); voice.classList.add("murmur"); voice.textContent = text;
    murmurT = setTimeout(() => { voice.classList.remove("murmur"); voice.textContent = ""; }, settle ? 20000 : 9000);
  }
  function addMsg(role, text, extra = {}) {
    const el = document.createElement("div"); el.className = `msg ${role}${extra.fail ? " fail" : ""}`;
    el.innerHTML = role === "thought" ? `${esc(text)} ${extra.tool ? `<code>${esc(extra.tool)}</code>` : ""}` : md(text);
    if (role === "user" || role === "assistant") el.innerHTML += `<time>${new Date(extra.t || Date.now()).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}</time>`;
    msgs.appendChild(el); msgs.scrollTop = msgs.scrollHeight;
  }
  // ---------- 마음 HUD: 지금 생각·하는 일·보는 대상 ----------
  const mind = $("#mind"), mindAct = $("#mind-act"), mindTgt = $("#mind-target"),
        mindThought = $("#mind-thought"), mindStream = $("#mind-stream");
  const TOOLPHRASE = {
    "bb.recon": "정찰", "kali.run": "보안 셸", "kali.msf": "Metasploit", "kali.gui": "도구 띄우기",
    "kali.install": "도구 설치", "net.tor": "Tor 전환", "web.fetch": "웹 읽기", "web.open": "웹 열기",
    "web.search": "웹 검색", "weather.get": "날씨", "screen.look": "화면 보기", "eye.see": "화면 보기",
    "eye.act": "화면 조작", "file.read": "파일 읽기", "file.write": "파일 쓰기", "file.search": "파일 찾기",
    "shell.run": "명령 실행", "memory.remember": "기억하기", "ui.panel": "화면 구성", "ui.app": "앱 만들기",
  };
  function mTarget(tool, a) {
    a = a || {};
    if (tool === "bb.recon") return a.scope || "";
    if (tool === "kali.msf") return ((a.commands || "").match(/RHOSTS\s+(\S+)/i) || [])[1] || "";
    if (tool === "kali.run" || tool === "shell.run") { const c = a.command || ""; return ((c.match(/\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?:\/\d+)?|[a-z0-9.-]+\.[a-z]{2,})\b/i) || [])[1]) || c.split(/\s+/)[0] || ""; }
    if (tool === "web.fetch" || tool === "web.open") return (a.url || "").replace(/^https?:\/\//, "").slice(0, 48);
    if (tool === "web.search") return a.query || "";
    if (tool === "weather.get") return a.place || "";
    if (tool === "file.read" || tool === "file.write" || tool === "file.search") return (a.path || a.name || "").split("/").pop();
    if (tool === "kali.gui" || tool === "kali.install") return a.app || a.names || "";
    if (tool === "net.tor") return a.action || "";
    return "";
  }
  let mindHideT = null;
  function mindShow(thought, tool, args) {
    if (!tool || tool === "reply") { if (thought) mindThought.textContent = thought; return; }
    clearTimeout(mindHideT);
    mind.hidden = false; document.documentElement.setAttribute("data-state", "working");
    mindAct.textContent = TOOLPHRASE[tool] || tool;
    const tg = mTarget(tool, args); mindTgt.textContent = tg ? "→ " + tg : "";
    mindThought.textContent = thought || "";
  }
  function mindStep(tool, result, ok) {
    if (mind.hidden) return;
    const li = document.createElement("li"); if (!ok) li.className = "fail";
    li.innerHTML = `<code>${esc(tool)}</code> ${esc(String(result).slice(0, 70))}`;
    mindStream.appendChild(li); while (mindStream.children.length > 6) mindStream.firstChild.remove();
  }
  function mindIdle() {
    clearTimeout(mindHideT);
    mindHideT = setTimeout(() => { mind.hidden = true; mindStream.innerHTML = ""; if (document.documentElement.getAttribute("data-state") === "working") document.documentElement.setAttribute("data-state", "idle"); }, 2600);
  }
  function setBusy(b) { say.classList.toggle("busy", b); if (b) { orb.set("think"); thinking("생각하는 중"); } }
  async function send(text) { text = (text || "").trim(); if (!text) return; prompt.value = ""; autosize(); orb.set("think"); await api("/api/ask", { text, source: "user" }); }

  // ---------- 입력 ----------
  const prompt = $("#prompt");
  const ime = new HangulInput(prompt, (on) => { $("#ime").textContent = on ? "한" : "A"; $("#ime").classList.toggle("ko", on); });
  $("#ime").onclick = () => { ime.toggle(); prompt.focus(); };
  function autosize() { prompt.style.height = "auto"; prompt.style.height = Math.min(160, prompt.scrollHeight) + "px"; }
  prompt.addEventListener("input", () => { autosize(); if (!say.classList.contains("busy")) orb.set(prompt.value ? "listen" : "idle"); });
  prompt.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); ime.flush(); if (!say.classList.contains("busy")) send(prompt.value); }
    if (e.key === "Escape") { api("/api/cancel", {}); VOX.stopSpeaking(); }
    if (e.key === "Tab") { e.preventDefault(); $("#log").hidden = !$("#log").hidden; }
  });
  $("#log-toggle").onclick = () => ($("#log").hidden = !$("#log").hidden);
  $("#log-clear").onclick = () => api("/api/history/clear", {});
  $("#mic").onclick = () => VOX.listenOnce();
  $("#orb-wrap").addEventListener("click", () => VOX.listenOnce());
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && (e.code === "Space" || e.key === " ")) { e.preventDefault(); e.stopImmediatePropagation(); VOX.listenOnce(); }
  }, true);
  document.addEventListener("keydown", (e) => { if (e.target !== prompt && !e.ctrlKey && !e.altKey && e.key.length === 1) prompt.focus(); });

  // ---------- 승인 · 알림 ----------
  const queue = [];
  function showConfirm() { const c = queue[0]; $("#confirm").hidden = !c; if (c) { $("#confirm-desc").textContent = `${c.source}: ${c.desc}`; orb.set("alert"); } }
  $("#confirm-yes").onclick = () => { const c = queue.shift(); api("/api/confirm", { id: c.id, approve: true }); showConfirm(); };
  $("#confirm-no").onclick = () => { const c = queue.shift(); api("/api/confirm", { id: c.id, approve: false }); showConfirm(); };
  function toast(title, body, alert, sticky) { const el = document.createElement("div"); el.className = "toast" + (alert ? " alert" : "") + (sticky ? " sticky" : ""); el.innerHTML = `<b>${esc(title)}</b><span>${esc(body || "")}</span>` + (sticky ? `<small>눌러서 닫기</small>` : ""); $("#toasts").appendChild(el); if (sticky) { el.onclick = () => el.remove(); speak(body || title); } else setTimeout(() => el.remove(), 8000); if (alert) orb.set("alert"); }

  // ---------- 실시간 ----------
  function connect() {
    const es = new EventSource(`/api/events?token=${T}`);
    es.onmessage = (e) => {
      const { kind, data } = JSON.parse(e.data);
      if (kind === "ui") render(data);
      else if (kind === "chat") { addMsg(data.role, data.text, data); if (data.role === "assistant") speak(data.text); }
      else if (kind === "thought") { addMsg("thought", data.text, { tool: data.tool !== "reply" ? data.tool : "" }); if (data.tool !== "reply") thinking(data.text); mindShow(data.text, data.tool, data.args); }
      else if (kind === "step") { addMsg("step", `${data.tool} → ${String(data.result).slice(0, 160)}`, { fail: !data.ok }); orb.kick(0.25); mindStep(data.tool, data.result, data.ok); }
      else if (kind === "busy") { if (data === "inner") { orb.set("listen"); } else setBusy(data); if (data === false) { orb.set("idle"); mindIdle(); if (voice.textContent === "생각하는 중") { voice.textContent = ""; voice.classList.remove("thinking"); } } }
      else if (kind === "inner") { addMsg("inner", data.text, { tool: data.tool !== "reply" ? data.tool : "" }); if (!say.classList.contains("busy")) murmur(data.text); }
      else if (kind === "inner_step") { addMsg("step", `${data.tool} → ${String(data.result).slice(0, 120)}`, { fail: !data.ok }); orb.kick(0.15); }
      else if (kind === "inner_done") { addMsg("inner", data.text); if (!say.classList.contains("busy")) murmur(data.text, true); }
      else if (kind === "confirm") { queue.push(data); showConfirm(); }
      else if (kind === "confirm_done") { const i = queue.findIndex((q) => q.id === data.id); if (i >= 0) queue.splice(i, 1); showConfirm(); }
      else if (kind === "notify") toast(data.title, data.body, /Sentinel|위협|승인/.test(data.title), data.sticky);
      else if (kind === "memory") $("#s-mem").textContent = "기억 " + Object.values(data.long_term || {}).reduce((a, b) => a + b, 0);
      else if (kind === "history_clear") msgs.innerHTML = "";
    };
    es.onerror = () => { es.close(); setTimeout(connect, 2000); };
  }
  async function init() {
    const s = await api("/api/state");
    msgs.innerHTML = ""; (s.history || []).forEach((h) => addMsg(h.role, h.text, h));
    const lastA = [...(s.history || [])].reverse().find((h) => h.role === "assistant"); voice.textContent = lastA ? lastA.text : "";
    render(s.ui); setBusy(s.busy);
    $("#s-brain").title = `${s.brain.model} @ ${s.brain.url}`;
    $("#s-mem").textContent = "기억 " + Object.values(s.memory.long_term || {}).reduce((a, b) => a + b, 0);
    (s.pending || []).forEach((p) => queue.push(p)); showConfirm(); connect();
    setTimeout(() => api("/api/greet", {}), 1500);   // 하루 한 번 먼저 인사·브리핑
    setBrain(s.brain.alive);
    watchBrain();
  }

  // ---------- 오프라인: 두뇌가 닿지 않으면 매트릭스 코드 비 ----------
  let brainAlive = true, misses = 0;
  const offline = $("#offline");
  function setBrain(alive) {
    $("#s-brain").className = alive ? "on" : "off";
    misses = alive ? 0 : misses + 1;
    const goDark = !alive && misses >= 2, goLight = alive && !brainAlive;
    if (goDark && offline.hidden) {
      offline.hidden = false;
      const f = document.createElement("iframe");
      f.src = "/static/vendor/matrix/index.html?version=classic&suppressWarnings=true&skipIntro=false&resolution=0.75";
      offline.prepend(f);
      requestAnimationFrame(() => offline.classList.add("on"));
      brainAlive = false;
    }
    if (goLight) {
      offline.classList.remove("on");
      setTimeout(() => { offline.hidden = true; offline.querySelector("iframe")?.remove(); }, 1700);
      brainAlive = true; orb.kick(1.2); speak("다시 연결됐어요.");
    }
  }
  function watchBrain() {
    const next = () => setTimeout(watchBrain, brainAlive ? 15000 : 4000); // 끊긴 동안엔 자주 확인
    api("/api/state").then((st) => setBrain(st.brain.alive)).catch(() => setBrain(false)).finally(next);
  }
  window.__atanorOffline = (on) => { misses = on ? 5 : 0; setBrain(!on); }; // 시험용
  init();
})();
