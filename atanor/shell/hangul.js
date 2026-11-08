// ATANOR 한글 입력기 — 두벌식 자판을 브라우저 안에서 직접 조합한다.
// 시스템 입력기(IME)에 기대지 않으므로 어떤 화면 환경에서도 한글이 된다.
// 한/영 전환: 한/영 키, 오른쪽 Alt, Shift+Space
(function () {
  const CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ";
  const JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ";
  const JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ";
  const KEYS = {
    q: "ㅂ", w: "ㅈ", e: "ㄷ", r: "ㄱ", t: "ㅅ", y: "ㅛ", u: "ㅕ", i: "ㅑ", o: "ㅐ", p: "ㅔ",
    a: "ㅁ", s: "ㄴ", d: "ㅇ", f: "ㄹ", g: "ㅎ", h: "ㅗ", j: "ㅓ", k: "ㅏ", l: "ㅣ",
    z: "ㅋ", x: "ㅌ", c: "ㅊ", v: "ㅍ", b: "ㅠ", n: "ㅜ", m: "ㅡ",
    Q: "ㅃ", W: "ㅉ", E: "ㄸ", R: "ㄲ", T: "ㅆ", O: "ㅒ", P: "ㅖ",
  };
  const VCOMB = { "ㅗㅏ": "ㅘ", "ㅗㅐ": "ㅙ", "ㅗㅣ": "ㅚ", "ㅜㅓ": "ㅝ", "ㅜㅔ": "ㅞ", "ㅜㅣ": "ㅟ", "ㅡㅣ": "ㅢ" };
  const FCOMB = { "ㄱㅅ": "ㄳ", "ㄴㅈ": "ㄵ", "ㄴㅎ": "ㄶ", "ㄹㄱ": "ㄺ", "ㄹㅁ": "ㄻ", "ㄹㅂ": "ㄼ", "ㄹㅅ": "ㄽ",
    "ㄹㅌ": "ㄾ", "ㄹㅍ": "ㄿ", "ㄹㅎ": "ㅀ", "ㅂㅅ": "ㅄ" };
  const split = (m, c) => { for (const k in m) if (m[k] === c) return [k[0], k[1]]; return null; };
  const isVowel = (j) => JUNG.includes(j);

  function key(ch) {
    if (KEYS[ch]) return KEYS[ch];
    const lower = ch.toLowerCase();
    return /[a-z]/.test(ch) ? KEYS[lower] : null;
  }

  function render(s) {
    if (s.cho && s.jung) {
      return String.fromCharCode(0xac00 + (CHO.indexOf(s.cho) * 21 + JUNG.indexOf(s.jung)) * 28 +
        (s.jong ? JONG.indexOf(s.jong) : 0));
    }
    return (s.cho || "") + (s.jung || "");
  }

  class HangulInput {
    constructor(el, onMode) {
      this.el = el; this.on = true; this.s = {}; this.start = null; this.onMode = onMode;
      el.addEventListener("keydown", (e) => this.keydown(e));
      el.addEventListener("mousedown", () => this.commit());
      el.addEventListener("blur", () => this.commit());
      onMode && onMode(this.on);
    }
    toggle() { this.commit(); this.on = !this.on; this.onMode && this.onMode(this.on); }
    empty() { return !this.s.cho && !this.s.jung; }
    commit() { this.s = {}; this.start = null; }
    write() {
      const el = this.el, v = el.value;
      if (this.start === null) this.start = el.selectionStart;
      const end = el.selectionEnd;
      const text = render(this.s);
      el.value = v.slice(0, this.start) + text + v.slice(end);
      const pos = this.start + text.length;
      el.setSelectionRange(this.start, pos); // 조합 중인 글자를 선택 상태로 둔다(밑줄 효과)
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
    flush() { // 조합을 끝내고 커서를 글자 뒤로
      if (this.start !== null) { const p = this.el.selectionEnd; this.el.setSelectionRange(p, p); }
      this.commit();
    }
    feed(j) {
      const s = this.s;
      if (!isVowel(j)) {
        if (s.cho && s.jung && !s.jong && JONG.includes(j)) { s.jong = j; return this.write(); }
        if (s.jong && FCOMB[s.jong + j]) { s.jong = FCOMB[s.jong + j]; return this.write(); }
        this.flush(); this.s = { cho: j }; return this.write();
      }
      if (s.jong) { // 받침이 다음 글자 초성으로 넘어간다
        const parts = split(FCOMB, s.jong);
        let next;
        if (parts) { s.jong = parts[0]; next = parts[1]; } else { next = s.jong; s.jong = null; }
        this.write(); this.flush(); this.s = { cho: next, jung: j }; return this.write();
      }
      if (s.jung && VCOMB[s.jung + j]) { s.jung = VCOMB[s.jung + j]; return this.write(); }
      if (s.cho && !s.jung) { s.jung = j; return this.write(); }
      this.flush(); this.s = { jung: j }; return this.write();
    }
    back() {
      const s = this.s;
      if (s.jong) { const p = split(FCOMB, s.jong); s.jong = p ? p[0] : null; }
      else if (s.jung && s.cho) { const p = split(VCOMB, s.jung); s.jung = p ? p[0] : null; }
      else if (s.jung) { const p = split(VCOMB, s.jung); s.jung = p ? p[0] : null; }
      else if (s.cho) { s.cho = null; }
      if (this.empty()) {
        const el = this.el, v = el.value;
        el.value = v.slice(0, this.start) + v.slice(el.selectionEnd);
        el.setSelectionRange(this.start, this.start);
        this.commit();
        el.dispatchEvent(new Event("input", { bubbles: true }));
      } else this.write();
    }
    keydown(e) {
      const toggleKey = e.key === "HangulMode" || e.code === "Lang1" || e.key === "Hangul" ||
        e.code === "AltRight" || (e.code === "Space" && e.shiftKey);
      if (toggleKey) { e.preventDefault(); return this.toggle(); }
      if (e.isComposing) return; // 시스템 입력기가 동작 중이면 맡긴다
      if (!this.on || e.ctrlKey || e.altKey || e.metaKey) { if (!this.empty()) this.flush(); return; }
      if (e.key === "Backspace" && !this.empty()) { e.preventDefault(); return this.back(); }
      const j = e.key.length === 1 ? key(e.key) : null;
      if (j) { e.preventDefault(); return this.feed(j); }
      if (!this.empty()) this.flush(); // 스페이스·엔터·기호 등은 조합을 끝내고 그대로 처리
    }
  }
  window.HangulInput = HangulInput;
})();
