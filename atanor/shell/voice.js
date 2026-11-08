// ATANOR 목소리(화면 쪽): 마이크 → 말소리 구간만 잘라 Core(/api/listen)로, 답은 /api/tts mp3로 재생.
// 상시 듣기(wake): 계속 듣다가 "아타노르…"로 시작하는 말만 처리한다(판정은 Core가 음성 인식 뒤에 한다).
// 한 번 듣기(once): 마이크 버튼·오브 클릭·Ctrl+Space. 깨우는 말 없이 바로 명령.
(function () {
  const RATE = 16000;
  class AtanorVoice {
    constructor({ token, orb, onState, onText }) {
      Object.assign(this, { token, orb, onState: onState || (() => {}), onText: onText || (() => {}) });
      this.mode = "off";          // off | wake | once
      this.wake = false;          // 상시 듣기 설정
      this.speaking = false;
      this.sending = false;
      this.nf = 0.006;            // 주변 소음 바닥
      this.reset();
    }
    reset() { this.buf = []; this.pre = []; this.inSpeech = false; this.voiced = 0; this.silent = 0; this.total = 0; }

    async ensureMic() {
      if (this.ctx) return true;
      try {
        this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: false } });
      } catch (e) { this.onState("nomic", String(e && e.name || e)); return false; }
      this.ctx = new AudioContext({ sampleRate: RATE });
      const src = this.ctx.createMediaStreamSource(this.stream);
      const proc = this.ctx.createScriptProcessor(1024, 1, 1);
      proc.onaudioprocess = (e) => this.frame(e.inputBuffer.getChannelData(0));
      src.connect(proc); proc.connect(this.ctx.destination); // 출력은 비워 둔다(소리 안 남)
      return true;
    }

    setWake(on) { this.wake = !!on; if (this.mode !== "once") this.go(on ? "wake" : "off"); }
    async go(mode) {
      if (mode !== "off" && !(await this.ensureMic())) return;
      this.mode = mode; this.reset();
      clearTimeout(this.onceT);
      if (mode === "once") this.onceT = setTimeout(() => { if (this.mode === "once" && !this.inSpeech) this.back(); }, 7000);
      if (this.ctx && this.ctx.state === "suspended") this.ctx.resume();
      this.onState(mode);
    }
    back() { this.go(this.wake ? "wake" : "off"); }
    listenOnce() { if (this.mode === "once") return this.back(); this.stopSpeaking(); this.go("once"); }

    frame(f) {
      if (this.mode === "off" || this.sending || this.speaking) return;   // 제 목소리를 듣지 않는다
      let s = 0; for (let i = 0; i < f.length; i++) s += f[i] * f[i];
      const rms = Math.sqrt(s / f.length), ms = (f.length / RATE) * 1000;
      const on = rms > Math.max(0.014, this.nf * 3.2), off = rms < Math.max(0.009, this.nf * 2.2);
      if (!this.inSpeech && rms < this.nf * 3) this.nf = this.nf * 0.97 + rms * 0.03;
      const chunk = new Float32Array(f);
      if (this.mode === "once") this.orb.kick(Math.min(0.3, rms * 6));
      if (!this.inSpeech) {
        this.pre.push(chunk); if (this.pre.length > 6) this.pre.shift();      // 말 시작 직전 0.4초
        if (on) { this.voiced += ms; if (this.voiced > 120) { this.inSpeech = true; this.buf = this.pre.slice(); this.silent = 0; this.total = 0; if (this.mode === "once") this.onState("hearing"); } }
        else this.voiced = 0;
        return;
      }
      this.buf.push(chunk); this.total += ms;
      this.silent = off ? this.silent + ms : 0;
      const endSil = this.mode === "once" ? 900 : 700;
      if (this.silent > endSil || this.total > 15000) this.finish();
    }

    async finish() {
      const parts = this.buf, total = this.total - this.silent, mode = this.mode;
      this.reset();
      if (total < 350) return;              // 너무 짧은 소리(기침·딸깍)는 버린다
      const n = parts.reduce((a, p) => a + p.length, 0), pcm = new Int16Array(n);
      let o = 0; for (const p of parts) for (let i = 0; i < p.length; i++) pcm[o++] = Math.max(-1, Math.min(1, p[i])) * 32767;
      this.sending = true; if (mode === "once") this.onState("recognizing");
      try {
        const r = await (await fetch(`/api/listen?mode=${mode === "once" ? "once" : "wake"}`, { method: "POST", headers: { "X-Atanor-Token": this.token, "Content-Type": "application/octet-stream" }, body: pcm.buffer })).json();
        this.sending = false;
        if (r.error) { this.onState("error", r.error); return this.back(); }
        if (r.wake && !r.heard) { await this.go("once"); return this.say("네?"); }    // 이름만 불렀으면 이어서 듣는다
        if (r.busy) this.onText(r.text, "busy");
        else if (r.heard) this.onText(r.text, "heard");
        else if (mode === "once") this.onText(r.text, "none");
      } catch (e) { this.sending = false; this.onState("error", String(e)); }
      if (this.mode === mode) this.back();
    }

    // ---------- 말하기 ----------
    async say(text) {
      text = String(text || "").trim(); if (!text) return;
      const my = (this.sayN = (this.sayN || 0) + 1);
      let blob;
      try {
        const res = await fetch("/api/tts", { method: "POST", headers: { "X-Atanor-Token": this.token, "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
        if (!res.ok || my !== this.sayN) return; blob = await res.blob();
      } catch (e) { return; }
      this.stopSpeaking(true);
      const a = (this.audio = new Audio(URL.createObjectURL(blob)));
      if (!this.outCtx) { this.outCtx = new AudioContext(); }
      const an = this.outCtx.createAnalyser(); an.fftSize = 512; const data = new Uint8Array(an.fftSize);
      const node = this.outCtx.createMediaElementSource(a); node.connect(an); an.connect(this.outCtx.destination);
      this.speaking = true; this.onState("speaking");
      const tick = () => { if (this.audio !== a || a.paused) return; an.getByteTimeDomainData(data); let m = 0; for (const v of data) m = Math.max(m, Math.abs(v - 128)); this.orb.kick(m / 400); requestAnimationFrame(tick); };
      a.onplay = () => requestAnimationFrame(tick);
      a.onended = a.onerror = () => { if (this.audio === a) { this.audio = null; this.speaking = false; this.onState("spoke"); } URL.revokeObjectURL(a.src); };
      try { if (this.outCtx.state === "suspended") await this.outCtx.resume(); await a.play(); } catch (e) { this.speaking = false; }
    }
    stopSpeaking(keepCounter) {
      if (!keepCounter) this.sayN = (this.sayN || 0) + 1;
      if (this.audio) { this.audio.pause(); this.audio = null; }
      this.speaking = false;
    }
  }
  window.AtanorVoice = AtanorVoice;
})();
