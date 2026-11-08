// ATANOR 배치 엔진 — AI가 고른 배치(또는 auto)에 따라 오브와 패널의 자리를 정한다.
// 배치: orbit | left | right | crown | focus | scatter | cascade | free | auto
// 기본은 orbit(오브가 가운데). auto는 패널 수에 맞는 배치들 중에서 구성이 바뀔 때마다 하나를 고른다 → 매번 다르게 보인다.
(function () {
  const GAP = 18, TOP = 64, BOTTOM = 112, SIDE = 28;
  const rnd = (seed) => () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;

  // 내용 종류에 따라 너비를 다르게: 표·앱·차트는 넓게, 버튼·계기는 좁게
  const WIDE = { table: 1.45, app: 1.7, chart: 1.35, html: 1.45, gallery: 1.4, text: 1.12, form: 1, log: 1.3, buttons: 0.85, meter: 0.72, kv: 0.92, steps: 1 };
  const wf = (el) => WIDE[el.dataset.type] || 1;
  function measure(els, width) { return els.map((el) => { el.style.width = width + "px"; return el.offsetHeight; }); }
  function measureEach(els, base, W) { return els.map((el) => { const w = Math.min(W - SIDE * 2, Math.round(base * wf(el))); el.style.width = w + "px"; return { w, h: el.offsetHeight }; }); }

  // 가장 짧은 열에 차곡차곡 (메이슨리)
  function masonry(els, x0, y0, w, cols) {
    const colW = (w - GAP * (cols - 1)) / cols, ys = Array(cols).fill(y0), out = [];
    const hs = measure(els, colW);
    els.forEach((el, i) => {
      const c = ys.indexOf(Math.min(...ys));
      out.push({ el, x: x0 + c * (colW + GAP), y: ys[c], w: colW, h: hs[i] });
      ys[c] += hs[i] + GAP;
    });
    return out;
  }

  function overlap(a, b, pad = GAP) { return a.x < b.x + b.w + pad && b.x < a.x + a.w + pad && a.y < b.y + b.h + pad && b.y < a.y + a.h + pad; }

  // 패널이 가운데 오브를 가리면 위·아래·옆 중 가장 조금 움직이는 쪽으로 비켜 준다
  // 원하는 자리가 오브·답글·다른 패널과 겹치면, 겹치지 않는 가장 가까운 빈자리로 옮긴다
  function settle(rc, blocks, W, H) {
    const free = (o) => blocks.every((b) => !overlap(o, b, b.pad ?? 10));
    if (free(rc)) return rc;
    const maxX = W - SIDE - rc.w, maxY = H - BOTTOM - rc.h;
    let best = null, bd = Infinity;
    for (let y = TOP; y <= Math.max(TOP, maxY); y += 16) {
      for (let x = SIDE; x <= Math.max(SIDE, maxX); x += 16) {
        const d = Math.hypot(x - rc.x, y - rc.y);
        if (d < bd) { const o = { ...rc, x, y }; if (free(o)) { best = o; bd = d; } }
      }
    }
    return best || rc;
  }

  const LAYOUTS = {
    idle(els, W, H) { return { orb: { cx: W / 2, cy: H * 0.42, s: Math.min(W, H) * 0.56 }, rects: [] }; },

    orbit(els, W, H, r) {
      const s = Math.min(W, H) * 0.36, cx = W / 2, cy = (TOP + H - BOTTOM) / 2;
      const base = Math.min(380, W * 0.23), ms = measureEach(els, base, W), n = els.length;
      const ry = (H - TOP - BOTTOM) / 2 - 40, a0 = -Math.PI / 2 + (r() - 0.5) * 0.6;
      // 오브 몸통과 그 아래 답글 줄은 비워 둔다
      const vw = Math.min(640, Math.max(260, s * 1.6));
      const blocks = [{ x: cx - s * 0.4, y: cy - s * 0.4, w: s * 0.8, h: s * 0.8, pad: 16 },
        { x: cx - vw / 2, y: cy + s * 0.4, w: vw, h: 56, pad: 8 }];
      const rects = [];
      // 큰 패널부터 자리를 잡아야 빈자리를 찾기 쉽다
      const order = els.map((el, i) => i).sort((i, j) => ms[j].w * ms[j].h - ms[i].w * ms[i].h);
      for (const i of order) {
        const el = els[i], { w, h } = ms[i], a = a0 + (i / n) * Math.PI * 2, rx = W / 2 - w / 2 - SIDE;
        const x = Math.max(SIDE, Math.min(W - w - SIDE, cx + Math.cos(a) * rx - w / 2));
        const y = Math.max(TOP, Math.min(H - BOTTOM - h, cy + Math.sin(a) * ry - h / 2));
        const rc = settle({ el, x, y, w, h }, blocks, W, H);
        rects.push(rc); blocks.push(rc);
      }
      return { orb: { cx, cy, s }, rects };
    },

    left(els, W, H) {
      const s = Math.min(W * 0.36, H * 0.62), x0 = W * 0.4;
      const cols = els.length <= 2 ? 1 : W - x0 > 900 ? 2 : 1;
      return { orb: { cx: W * 0.2, cy: H * 0.46, s }, rects: masonry(els, x0, TOP + 12, W - x0 - SIDE, cols) };
    },

    right(els, W, H) {
      const s = Math.min(W * 0.36, H * 0.62), w = W * 0.6 - SIDE;
      const cols = els.length <= 2 ? 1 : w > 900 ? 2 : 1;
      return { orb: { cx: W * 0.8, cy: H * 0.46, s }, rects: masonry(els, SIDE, TOP + 12, w - GAP, cols) };
    },

    crown(els, W, H) {
      const s = Math.min(H * 0.24, 220), cy = TOP + s / 2;
      const cols = Math.min(3, Math.max(1, els.length));
      return { orb: { cx: W / 2, cy, s }, rects: masonry(els, SIDE, cy + s / 2 + 8, W - SIDE * 2, cols) };
    },

    focus(els, W, H) {
      const [first, ...rest] = els, w = Math.min(920, W * 0.6), x = (W - w) / 2;
      const h = measure([first], w)[0];
      const rects = [{ el: first, x, y: TOP + 40, w, h }];
      if (rest.length) rects.push(...masonry(rest, SIDE, TOP + 40 + h + GAP * 2, W - SIDE * 2, Math.min(4, rest.length)));
      return { orb: { cx: 70, cy: 76, s: 110 }, rects };
    },

    cascade(els, W, H, r) {
      // 계단처럼 비스듬히 겹쳐 흐르는 배치 — 순서가 있는 작업에 어울린다
      const w = Math.min(460, W * 0.34), hs = measure(els, w), n = els.length;
      const stepX = n > 1 ? (W - w - SIDE * 2 - W * 0.18) / (n - 1) : 0;
      let y = TOP + 24;
      const rects = els.map((el, i) => { const rc = { el, x: SIDE + W * 0.18 + i * stepX, y, w, h: hs[i] }; y += Math.min(hs[i] * 0.55, 160); return rc; });
      return { orb: { cx: W * 0.1, cy: H - BOTTOM - 60, s: Math.min(W * 0.2, 200) }, rects };
    },

    scatter(els, W, H, r) {
      const side = r() < 0.5 ? -1 : 1;
      const s = Math.min(W, H) * (0.28 + r() * 0.12);
      const orb = { cx: W / 2 + side * W * (0.18 + r() * 0.12), cy: TOP + (H - TOP - BOTTOM) * (0.35 + r() * 0.3), s };
      const orbBox = { x: orb.cx - s * 0.42, y: orb.cy - s * 0.42, w: s * 0.84, h: s * 0.84 };
      const rects = [];
      for (const el of els) {
        const { w, h } = measureEach([el], Math.min(380, W * (0.19 + r() * 0.08)), W)[0];
        let best = null;
        for (let t = 0; t < 80 && !best; t++) {
          const c = { el, x: SIDE + r() * (W - w - SIDE * 2), y: TOP + r() * Math.max(1, H - TOP - BOTTOM - h), w, h };
          if (!overlap(c, orbBox) && rects.every((o) => !overlap(c, o))) best = c;
        }
        rects.push(best || { el, x: SIDE, y: TOP + rects.reduce((m, o) => Math.max(m, o.y + o.h + GAP), 0), w, h });
      }
      return { orb, rects };
    },

    free(els, W, H) {
      const rects = els.map((el) => {
        const p = JSON.parse(el.dataset.json || "{}");
        const w = W * Math.max(10, Math.min(100, p.w ?? 30)) / 100, h = measure([el], w)[0];
        return { el, x: W * (p.x ?? 5) / 100, y: TOP + (H - TOP - BOTTOM) * (p.y ?? 5) / 100, w, h };
      });
      return { orb: { cx: W - 80, cy: TOP + 50, s: 120 }, rects };
    },
  };

  const AUTO = { 1: ["focus", "left", "right", "crown"], 2: ["left", "right", "orbit", "crown"], 3: ["orbit", "left", "right", "scatter", "cascade"],
    4: ["orbit", "crown", "scatter", "left", "right"], 5: ["orbit", "crown", "scatter", "cascade"] };

  let lastSig = "", autoPick = "orbit", seed = Date.now() % 100000;

  window.Layout = {
    names: Object.keys(LAYOUTS).filter((k) => k !== "idle").concat("auto"),
    current: "idle",
    apply(stage, orbWrap, voice, mode, layoutSeed) {
      const els = [...stage.querySelectorAll(".panel")].sort((a, b) => (+a.style.order || 50) - (+b.style.order || 50));
      const W = innerWidth, H = innerHeight;
      const sig = els.map((e) => e.dataset.id).join("|") + mode;
      let m = !els.length ? "idle" : LAYOUTS[mode] && mode !== "idle" ? mode : mode === "auto" ? "auto" : "orbit";
      if (m === "auto") {
        if (sig !== lastSig) { // 구성이 바뀔 때마다 새로 고른다
          const opts = AUTO[Math.min(5, els.length)] || AUTO[5];
          let pick; do { pick = opts[Math.floor(Math.random() * opts.length)]; } while (opts.length > 1 && pick === autoPick);
          autoPick = pick; seed = Math.floor(Math.random() * 1e5);
        }
        m = autoPick;
      }
      if (sig !== lastSig && layoutSeed == null) seed = Math.floor(Math.random() * 1e5);
      lastSig = sig;
      const r = rnd((layoutSeed ?? seed) + 7);
      const { orb, rects } = (LAYOUTS[m] || LAYOUTS.orbit)(els, W, H, r);
      for (const rc of rects) {
        rc.el.style.width = rc.w + "px";
        rc.el.style.transform = `translate(${Math.round(rc.x)}px, ${Math.round(rc.y)}px)`;
      }
      const s = Math.round(orb.s);
      orbWrap.style.width = orbWrap.style.height = s + "px";
      orbWrap.style.transform = `translate(${Math.round(orb.cx - s / 2)}px, ${Math.round(orb.cy - s / 2)}px)`;
      // 목소리(마지막 답)는 오브 바로 아래에 붙는다. 화면 아래로 넘치면 오브 옆으로.
      const vw = Math.min(640, Math.max(260, s * 1.6));
      let vx = orb.cx - vw / 2, vy = orb.cy + s * 0.42;
      if (vy > H - BOTTOM - 40) { vy = orb.cy - 10; vx = orb.cx + s / 2 + 12; }
      voice.style.width = vw + "px";
      voice.style.transform = `translate(${Math.round(Math.max(SIDE, Math.min(W - vw - SIDE, vx)))}px, ${Math.round(vy)}px)`;
      voice.dataset.align = m === "idle" || m === "orbit" || m === "crown" ? "center" : "left";
      document.documentElement.dataset.layout = m;
      this.current = m;
      return m;
    },
  };
})();
