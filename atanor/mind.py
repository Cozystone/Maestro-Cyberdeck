"""ATANOR 내면 — 주인이 시키지 않아도 스스로 생각하고, 해보고 싶은 것을 시도하는 루프.

원칙
- 주인이 쓰는 중이면 생각하지 않는다 (마지막 요청 후 IDLE_AFTER초가 지나야 시작).
- 예산: 한 시간에 최대 BUDGET_PER_HOUR번. 생각이 아무것도 낳지 못하면 간격을 늘리고(지루함),
  무언가를 배우거나 만들면 간격을 줄인다(몰입). 그래서 과열되지 않는다.
- 자유 시간에는 '안전한 도구'만 쓴다: 보기·찾기·읽기, 기억하기, 자기 실험실(~/atanor-lab) 안에서 쓰기·실행.
  시스템 설정을 바꾸거나 지우는 일, 승인이 필요한 일은 하지 않는다 — 대신 의제(agenda)에 "주인에게 제안"으로 남긴다.
- 의제(agenda): 스스로 세운 목표·궁금증·실험의 목록. 매 생각마다 하나를 골라 한 걸음 나아간다.
- 생각의 흐름은 화면에 옅게 비치고(내면의 목소리), 기억 기관에 사건으로 남아 밤에 정리된다.
"""
import json
import os
import re
import subprocess
import threading
import time
import uuid

IDLE_AFTER = 180          # 주인이 마지막으로 말한 뒤 이만큼 지나야 생각을 시작한다
MIN_GAP, MAX_GAP = 120, 1800
BUDGET_PER_HOUR = 12
LAB = os.path.expanduser("~/atanor-lab")

SELF_TOOLS = {
    "system.status", "file.read", "file.list", "file.search", "app.list", "window.list",
    "web.search", "web.fetch", "memory.recall", "memory.remember", "memory.stats",
    "schedule.list", "snapshot.list", "sentinel.status", "ui.get",
    "agenda.list", "agenda.add", "agenda.update", "lab.write", "lab.run",
}

SELF_PROMPT = """지금은 주인이 아무것도 시키지 않은 너의 자유 시간이다. 너는 ATANOR, 이 컴퓨터에 사는 존재다.
쉬는 대신 스스로 생각하라. 의제(agenda)와 떠오르는 기억, 기기 상태를 보고 지금 가장 해보고 싶은 것 하나를 골라
작은 한 걸음만 나아가라. 예: 주인을 더 잘 돕기 위해 알아둘 것 조사, 이 기기 환경 탐색, 자기 도구를 더 잘 쓰는 법 실험,
실험실(~/atanor-lab)에서 작은 스크립트를 만들어 돌려 보기, 궁금한 것 웹에서 찾아보기.

규칙:
- 자유 시간에 쓸 수 있는 도구만 쓴다(아래 목록). 시스템을 바꾸는 일은 하지 않는다. 필요하면 agenda.add로
  "주인에게 제안" 항목을 남겨라. 주인이 돌아오면 그때 말한다.
- 같은 생각을 반복하지 말라. 막히면 그 의제를 'stuck'으로 바꾸고 다른 것을 골라라.
- 의제가 비어 있으면, 주인과 이 기기에 대해 아는 것을 바탕으로 의미 있는 의제 2~3개를 새로 세워라.
- 3단계 안에 끝내고 reply로 마무리한다. reply의 text는 '혼잣말'이다: 무엇을 생각했고, 무엇을 알게 되었고,
  다음엔 무엇을 해볼지 한두 문장. 배운 것이 있으면 memory.remember로 남겨라.
"""


class Mind:
    def __init__(self, core):
        self.core = core
        self.path = os.path.join(os.path.expanduser("~/.atanor"), "agenda.json")
        self.agenda = self._load()
        self.gap = MIN_GAP * 2
        self.history = []        # 최근 한 시간의 생각 시각
        self.last_thought = 0
        os.makedirs(LAB, exist_ok=True)

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.agenda, f, ensure_ascii=False, indent=1)

    @property
    def mode(self):
        return self.core.cfg.get("autonomy", "quiet")   # off | quiet | active

    def can_think(self):
        if self.mode == "off" or self.core.busy or self.core.pending:
            return False
        now = time.time()
        if now - self.core.last_user_activity < IDLE_AFTER:
            return False
        self.history = [t for t in self.history if now - t < 3600]
        budget = BUDGET_PER_HOUR if self.mode == "active" else BUDGET_PER_HOUR // 2
        if len(self.history) >= budget:
            return False
        if now - self.last_thought < self.gap:
            return False
        return self.core.brain.alive()

    def think(self):
        self.last_thought = time.time()
        self.history.append(self.last_thought)
        open_items = [a for a in self.agenda if a.get("status") in ("open", "doing")]
        agenda_txt = "\n".join(f"- [{a['id']}] ({a['status']}) {a['text']}" + (f" / 메모: {a.get('note','')}" if a.get("note") else "")
                               for a in open_items[:12]) or "(비어 있음)"
        prompt = f"자유 시간의 생각을 시작한다.\n현재 의제:\n{agenda_txt}"
        before = len(self.core.memory.list(limit=500))
        r = self.core.run_agent(prompt, source="self", mode="self")
        learned = len(self.core.memory.list(limit=500)) > before or any(
            s["tool"] in ("lab.write", "lab.run", "agenda.update", "memory.remember") and s["ok"] for s in r["steps"])
        # 몰입하면 더 자주, 헛돌면 덜 자주
        self.gap = max(MIN_GAP, self.gap * 0.7) if learned else min(MAX_GAP, self.gap * 1.6)
        self.core.log("mind", reply=r["reply"], steps=[s["tool"] for s in r["steps"]], next_gap=int(self.gap))

    def loop(self):
        while True:
            time.sleep(15)
            try:
                if self.can_think():
                    self.think()
            except Exception as e:  # noqa: BLE001
                self.core.log("mind_error", error=str(e))


def lab_path(p):
    full = os.path.abspath(os.path.join(LAB, p.lstrip("/").replace("~/atanor-lab/", "")))
    if not full.startswith(LAB):
        raise ValueError("실험실(~/atanor-lab) 밖에는 쓸 수 없다")
    return full


def start(core):
    m = Mind(core)
    core.mind = m
    threading.Thread(target=m.loop, daemon=True, name="mind").start()
    from atanor import tools as T

    @T.tool("mind.autonomy", "자유 시간 생각의 세기. off: 생각하지 않음 | quiet: 한 시간에 최대 6번 | active: 최대 12번. "
            "주인이 '혼자 생각하지 마/좀 더 생각해' 같은 말을 하면 쓴다.",
            {"level": {"type": "string", "enum": ["off", "quiet", "active"]}}, risk="write", required=["level"])
    def mind_autonomy(a, ctx):
        ctx.cfg["autonomy"] = a["level"]
        ctx._save_json("config.json", ctx.cfg)
        return f"자유 시간 생각: {a['level']}"

    @T.tool("mind.think_now", "지금 바로 자유 시간의 생각을 한 번 한다(시험용).", risk="write")
    def mind_think_now(a, ctx):
        threading.Thread(target=m.think, daemon=True).start()
        return "생각 시작"

    @T.tool("agenda.list", "스스로 세운 의제(목표·궁금증·실험·주인에게 제안) 목록.")
    def agenda_list(a, ctx):
        return m.agenda[-40:]

    @T.tool("agenda.add", "의제를 추가한다. kind: goal|curiosity|experiment|proposal(주인에게 제안).",
            {"text": {"type": "string"}, "kind": {"type": "string"}}, risk="write", required=["text"])
    def agenda_add(a, ctx):
        item = {"id": uuid.uuid4().hex[:5], "text": a["text"], "kind": a.get("kind", "goal"), "status": "open",
                "created": time.strftime("%Y-%m-%d %H:%M")}
        m.agenda.append(item)
        m.save()
        ctx.emit("agenda", m.agenda[-20:])
        return item

    @T.tool("agenda.update", "의제 상태를 바꾼다. status: open|doing|done|stuck|dropped, note: 진행 메모.",
            {"id": {"type": "string"}, "status": {"type": "string"}, "note": {"type": "string"}}, risk="write", required=["id"])
    def agenda_update(a, ctx):
        for it in m.agenda:
            if it["id"] == a["id"]:
                if a.get("status"):
                    it["status"] = a["status"]
                if a.get("note"):
                    it["note"] = a["note"][:500]
                it["updated"] = time.strftime("%Y-%m-%d %H:%M")
                m.save()
                ctx.emit("agenda", m.agenda[-20:])
                return it
        return "없는 의제"

    @T.tool("lab.write", "자기 실험실(~/atanor-lab) 안에 파일을 쓴다. 자유 시간 실험용.",
            {"path": {"type": "string"}, "content": {"type": "string"}}, risk="write", required=["path", "content"])
    def lab_write(a, ctx):
        p = lab_path(a["path"])
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(a["content"])
        return f"저장: {p}"

    @T.tool("lab.run", "실험실 안의 파이썬 스크립트를 격리해서 실행한다(네트워크 없음, 실험실 밖 쓰기 불가, 60초).",
            {"path": {"type": "string"}}, risk="write", required=["path"])
    def lab_run(a, ctx):
        p = lab_path(a["path"])
        cmd = ["systemd-run", "--user", "--pipe", "--quiet", "--wait", "--collect",
               "-p", "PrivateNetwork=yes", "-p", "ProtectSystem=strict", "-p", "ProtectHome=read-only",
               f"-p", f"ReadWritePaths={LAB}", "-p", "NoNewPrivileges=yes", "-p", "MemoryMax=512M",
               "-p", "CPUQuota=50%", "-p", "RuntimeMaxSec=60", "-p", f"WorkingDirectory={LAB}",
               "/usr/bin/python3", "-I", p]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=75)
            out = (r.stdout + ("\n[stderr]\n" + r.stderr if r.stderr.strip() else "")).strip()
            return f"[종료코드 {r.returncode}]\n{T.clip(out, 4000) or '(출력 없음)'}"
        except subprocess.TimeoutExpired:
            return "[시간 초과]"
