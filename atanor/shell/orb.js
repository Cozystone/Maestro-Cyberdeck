// ATANOR orb — HologramVoiceOrb (Cozystone/ATANOR-Demo) 의 기하·색·재질 상수를 그대로 옮기고,
// OS 상태(idle / listen / think / speak / alert)에 반응하도록 이었다.
(function () {
  const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;

  class Orb {
    constructor(host) {
      this.host = host; this.state = "idle"; this.energy = 0; this.target = 0; this.pulse = 0;
      if (typeof THREE === "undefined") { this.fallback(); return; }
      this.build();
    }

    fallback() { this.host.innerHTML = "<div style='width:40%;height:40%;margin:30%;border-radius:50%;box-shadow:0 0 60px #20f4ff'></div>"; }

    build() {
      const RIBBON_PARTICLES = 24000, SHELL_PARTICLES = 14000, AURA_PARTICLES = 5200;
      const SHAPE_COUNT = 7;
      const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
      const PALETTE = [new THREE.Color("#20f4ff"), new THREE.Color("#3aa8ff"), new THREE.Color("#bd6dff"), new THREE.Color("#ff4f9d")];
      const fract = (v) => v - Math.floor(v);
      const seeded = (i, salt = 0) => fract(Math.sin(i * 12.9898 + salt * 78.233) * 43758.5453123);

      function siriRibbonPoint(shape, t, seed) {
        const band = Math.floor(seed * 4), local = fract(seed * 4);
        const phase = shape * 0.58 + band * 1.72 + local * 0.8;
        const angle = t * Math.PI * (2.2 + band * 0.18) + phase;
        const ribbonWidth = (local - 0.5) * (0.26 + Math.sin(angle + shape) * 0.045);
        const radius = 1.04 + Math.sin(angle * 1.7 + phase) * 0.2 + Math.cos(angle * 0.67 + shape) * 0.05;
        const squash = 0.48 + band * 0.06;
        const x = Math.cos(angle + Math.sin(angle * 0.73 + phase) * 0.32) * radius;
        const z = Math.sin(angle + Math.cos(angle * 0.82 + phase) * 0.22) * radius * squash;
        const y = Math.sin(angle * 1.05 + phase) * (0.48 - band * 0.035) + ribbonWidth;
        const p = new THREE.Vector3(x, y, z);
        p.applyAxisAngle(new THREE.Vector3(0, 0, 1), -0.58 + band * 0.34 + Math.sin(shape * 0.9) * 0.1);
        p.applyAxisAngle(new THREE.Vector3(1, 0, 0), 0.38 + Math.cos(shape * 0.7) * 0.18);
        return p.multiplyScalar(1.08);
      }
      function ribbonGeo(n) {
        const pos = new Float32Array(n * 3), col = new Float32Array(n * 3);
        const morphs = Array.from({ length: SHAPE_COUNT }, () => new Float32Array(n * 3));
        for (let i = 0; i < n; i++) {
          const t = i / n, seed = seeded(i), band = Math.min(2, Math.floor(seed * 3));
          const c = PALETTE[band].clone().lerp(PALETTE[band + 1], 0.18 + seeded(i, 4) * 0.32);
          col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
          for (let s = 0; s < SHAPE_COUNT; s++) { const p = siriRibbonPoint(s, t, seed); morphs[s][i * 3] = p.x; morphs[s][i * 3 + 1] = p.y; morphs[s][i * 3 + 2] = p.z; }
          pos[i * 3] = morphs[0][i * 3]; pos[i * 3 + 1] = morphs[0][i * 3 + 1]; pos[i * 3 + 2] = morphs[0][i * 3 + 2];
        }
        const g = new THREE.BufferGeometry();
        g.setAttribute("position", new THREE.BufferAttribute(pos, 3)); g.setAttribute("color", new THREE.BufferAttribute(col, 3));
        return { g, morphs };
      }
      function shellGeo(n, radius, bias = 0) {
        const pos = new Float32Array(n * 3), col = new Float32Array(n * 3);
        const rim = new THREE.Color("#5ee7ff"), glass = new THREE.Color("#dcecff"), violet = new THREE.Color("#6557ff");
        for (let i = 0; i < n; i++) {
          const t = (i + 0.5) / n, th = i * GOLDEN_ANGLE, y = 1 - 2 * t, ring = Math.sqrt(Math.max(0, 1 - y * y));
          const r = radius + Math.sin(th * 1.7 + i * 0.003) * 0.01;
          const x = Math.cos(th) * ring * r, z = Math.sin(th) * ring * r;
          pos[i * 3] = x; pos[i * 3 + 1] = y * r; pos[i * 3 + 2] = z;
          const w = Math.min(1, Math.pow(Math.abs(x) / r, 2.2) + Math.pow(Math.abs(y) / r, 3) * 0.35 + bias);
          const c = glass.clone().lerp(rim, w * 0.65).lerp(violet, Math.max(0, z / r) * 0.22);
          col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
        }
        const g = new THREE.BufferGeometry();
        g.setAttribute("position", new THREE.BufferAttribute(pos, 3)); g.setAttribute("color", new THREE.BufferAttribute(col, 3));
        return g;
      }
      function auraGeo(n) {
        const pos = new Float32Array(n * 3), col = new Float32Array(n * 3);
        const cyan = new THREE.Color("#18e8ff"), rose = new THREE.Color("#ff3d85");
        for (let i = 0; i < n; i++) {
          const th = Math.PI * 2 * seeded(i, 2), ph = Math.acos(2 * seeded(i, 3) - 1), r = 1.96 + seeded(i, 8) * 0.5;
          pos[i * 3] = Math.sin(ph) * Math.cos(th) * r; pos[i * 3 + 1] = Math.cos(ph) * r; pos[i * 3 + 2] = Math.sin(ph) * Math.sin(th) * r;
          const c = cyan.clone().lerp(rose, seeded(i, 5) * 0.35);
          col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
        }
        const g = new THREE.BufferGeometry();
        g.setAttribute("position", new THREE.BufferAttribute(pos, 3)); g.setAttribute("color", new THREE.BufferAttribute(col, 3));
        return g;
      }
      const mat = (opacity, size) => new THREE.PointsMaterial({ blending: THREE.AdditiveBlending, depthWrite: false, opacity, size,
        sizeAttenuation: true, transparent: true, vertexColors: true });

      const d = 0.35; // 노트북 GPU(HD 530)에 맞춘 밀도 — 데모 랜딩과 같은 값
      const nRibbon = Math.max(4200, Math.round(RIBBON_PARTICLES * d)), nShell = Math.max(2600, Math.round(SHELL_PARTICLES * d));
      const nAura = Math.max(1100, Math.round(AURA_PARTICLES * d)), nCore = Math.max(600, Math.round(1800 * d));

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100); camera.position.set(0, 0, 7.2);
      const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false, powerPreference: "high-performance" });
      renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2)); renderer.setClearColor(0x000000, 0);
      renderer.domElement.style.cssText = "width:100%;height:100%;display:block;cursor:grab";
      this.host.appendChild(renderer.domElement);

      const root = new THREE.Group(); scene.add(root);
      const aura = new THREE.Points(auraGeo(nAura), mat(0.11, 0.024)); root.add(aura);
      const shell = new THREE.Points(shellGeo(nShell, 1.72, 0.06), mat(0.42, 0.013)); root.add(shell);
      const rim = new THREE.Points(shellGeo(Math.floor(nShell * 0.38), 1.76, 0.15), mat(0.55, 0.018)); root.add(rim);
      const built = ribbonGeo(nRibbon); const ribbons = new THREE.Points(built.g, mat(0.92, 0.027)); root.add(ribbons);
      const core = new THREE.Points(shellGeo(nCore, 0.16, 0.5), mat(0.72, 0.042)); root.add(core);
      const morphs = built.morphs;

      const clock = new THREE.Clock();
      const tr = { x: -0.08, y: 0.22 }, cr = { x: -0.08, y: 0.22 }, ptr = { on: false, x: 0, y: 0 };
      let active = 0, next = 1, morphStart = 0, lastMorph = -1, morphClock = 0;
      const self = this;

      const resize = () => {
        const r = this.host.getBoundingClientRect(); const w = Math.max(60, r.width), h = Math.max(60, r.height);
        renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
      };
      new ResizeObserver(resize).observe(this.host); resize();

      function morph(el) {
        // 생각 중에도 모양 변화는 차분하게 — 활력은 회전으로 드러낸다
        const hold = 4.4 - self.energy * 1.6, blend = 1.85 - self.energy * 0.7;
        if (el - morphStart > hold) {
          active = next; next = (next + 1 + Math.floor(el) % (SHAPE_COUNT - 1)) % SHAPE_COUNT;
          if (next === active) next = (next + 1) % SHAPE_COUNT; morphStart = el;
        }
        const k = Math.min(1, Math.max(0, (el - morphStart) / blend)), e = k * k * (3 - 2 * k);
        const P = built.g.getAttribute("position"), A = morphs[active], B = morphs[next];
        // 생각할수록 '안의 일렁거림'이 커진다 — 회전 속도는 건드리지 않는다
        const fluid = Math.sin(el * 1.35) * (0.022 + self.energy * 0.07);
        for (let i = 0; i < nRibbon * 3; i += 3) {
          const wave = Math.sin(el * (1.15 + self.energy * 0.45) + i * 0.0011) * fluid
                     + Math.sin(el * 0.7 + i * 0.0004) * self.energy * 0.012;
          P.array[i] = A[i] + (B[i] - A[i]) * e; P.array[i + 1] = A[i + 1] + (B[i + 1] - A[i + 1]) * e + wave; P.array[i + 2] = A[i + 2] + (B[i + 2] - A[i + 2]) * e;
        }
        P.needsUpdate = true;
      }

      const frame = () => {
        const el = clock.getElapsedTime();
        this.energy += (this.target - this.energy) * 0.04;
        morphClock = el;
        if (lastMorph < 0 || el - lastMorph >= 1 / 33) { morph(el); lastMorph = el; }
        this.pulse *= 0.94;
        const e = this.energy, pu = this.pulse;
        // 회전 속도는 상태와 무관하게 일정 — 생각·대답은 '안의 일렁거림'으로만 드러낸다. 펄떡임 없음.
        tr.y += 0.0018;
        cr.x += (tr.x - cr.x) * 0.055; cr.y += (tr.y - cr.y) * 0.055;
        root.rotation.x = cr.x + Math.sin(el * 0.23) * 0.025; root.rotation.y = cr.y; root.rotation.z = Math.sin(el * 0.31) * 0.05;
        root.scale.setScalar((1 + Math.sin(el * (1.0 + e * 0.5)) * (0.015 + e * 0.01)) * (1 + pu * 0.06));
        ribbons.material.size = 0.027 * (1 + pu * 0.3 + e * 0.18);
        core.material.opacity = Math.min(1, 0.72 * (1 + pu * 0.22 + e * 0.35));
        // 경고 상태에서는 코어가 호박색으로 물든다
        const alert = this.state === "alert" ? 1 : 0;
        core.material.color = core.material.color || new THREE.Color(1, 1, 1);
        ribbons.rotation.y = el * 0.12; shell.rotation.y = -el * 0.035; rim.rotation.y = el * 0.052;
        aura.rotation.y = -el * 0.018; core.rotation.y = el * 0.4;
        aura.material.opacity = 0.11 + e * 0.08 + alert * 0.1;
        renderer.render(scene, camera);
        if (!REDUCED) requestAnimationFrame(frame);
      };

      const cv = renderer.domElement;
      cv.addEventListener("pointerdown", (e) => { ptr.on = true; ptr.x = e.clientX; ptr.y = e.clientY; cv.setPointerCapture(e.pointerId); });
      cv.addEventListener("pointermove", (e) => {
        if (!ptr.on) return; tr.y += (e.clientX - ptr.x) * 0.006; tr.x = Math.max(-0.72, Math.min(0.72, tr.x + (e.clientY - ptr.y) * 0.004));
        ptr.x = e.clientX; ptr.y = e.clientY;
      });
      const rel = (e) => { ptr.on = false; try { cv.releasePointerCapture(e.pointerId); } catch {} };
      cv.addEventListener("pointerup", rel); cv.addEventListener("pointercancel", rel);
      frame();
    }

    set(state) {
      this.state = state;
      this.target = { idle: 0, listen: 0.2, think: 0.9, speak: 0.45, alert: 0.7 }[state] ?? 0;
      if (state === "alert") this.kick(0.9);
    }
    kick(k = 1) { this.pulse = Math.min(1.6, this.pulse + k); }
  }
  window.Orb = Orb;
})();
