"""ATANOR Sentinel — AI 경비. 방화벽을 백신처럼 쓴다.

흐름 (30초마다)
  감지 → 1차 판단(규칙, 즉시) → 2차 판단(모델이 사건을 읽고 위협 분석) → 대응 → 기록 → 화면 알림

감지하는 것
- 방화벽이 막은 패킷(nft 로그 'atanor-lan-block', dropped 카운터)
- SSH 로그인 시도·실패 (journal)
- 새로 열린 수신 포트, 새 프로세스가 네트워크를 쓰기 시작함
- sudo 사용, /etc 변경(SSH·방화벽·sudoers), authorized_keys 변경, 새 cron/systemd 서비스
- 모르는 바깥 주소로의 지속 연결

권한 원칙
- 막기(차단 목록에 IP 추가, 의심 프로세스 중지, 바깥 연결 끊기)는 AI가 바로 한다 — 되돌릴 수 있다.
- 열기(방화벽 규칙 완화, 차단 해제)는 주인 승인이 필요하다 — Core의 승인 흐름을 쓴다.
- 모든 판단과 대응은 ~/.atanor/logs 와 journal(atanor-sentinel)에 남는다.
"""
import json
import os
import re
import subprocess
import threading
import time

INTERVAL = 30
BLOCK_TTL = "24h"
TRUSTED = {"192.168.0.1", "192.168.0.125", "127.0.0.1"}

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "위협도": {"type": "string", "enum": ["없음", "낮음", "중간", "높음", "긴급"]},
        "요약": {"type": "string"},
        "근거": {"type": "string"},
        "대응": {"type": "array", "items": {"type": "object", "properties": {
            "행동": {"type": "string", "enum": ["block_ip", "kill_process", "watch", "none"]},
            "대상": {"type": "string", "description": "block_ip면 IPv4 주소, kill_process면 PID 숫자 또는 정확한 프로세스 이름"},
            "이유": {"type": "string"}}, "required": ["행동"]}},
    },
    "required": ["위협도", "요약", "대응"],
}

PROMPT = """너는 ATANOR Sentinel, 이 노트북(Debian 13, 집 Wi-Fi 192.168.0.0/24)의 보안 경비다.
신뢰하는 주소: 192.168.0.1(공유기), 192.168.0.125(주인의 메인 PC — SSH 터널로 모델을 제공한다).
이 노트북은 설계상 집 안 다른 기기로 나가는 연결이 전부 차단된다("lan_egress_block"). 그 차단 기록 자체는 정상이다.
그러나 노트북 안의 어떤 프로세스가 집 안 기기(특히 192.168.0.125)로 '계속' 나가려 한다면 침해 신호다.

아래 사건 묶음을 읽고 위협을 판단하라. 과잉 반응하지 말고, 근거 없는 추측도 하지 말라.
- 집 밖(인터넷)에서 들어오는 접속 시도가 여러 번이면 그 IP를 block_ip.
- 모르는 프로세스가 바깥으로 데이터를 보내거나, 새 수신 포트를 열거나, SSH 키·sudoers·방화벽을 바꾸면 '높음' 이상, 필요하면 kill_process.
- 주인(192.168.0.125)이나 ATANOR 자신(atanor, sshd, sway, chromium, apt)의 정상 활동은 위협이 아니다.
한국어로, JSON만 출력하라.

사건:
{events}
"""


def sh(cmd, timeout=20):
    r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


class Sentinel:
    def __init__(self, core):
        self.core = core
        self.state_path = os.path.join(core.log_path, "..", "sentinel.json")
        self.state = self._load()
        self.last_journal = time.strftime("%Y-%m-%d %H:%M:%S")

    def _load(self):
        try:
            with open(self.state_path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"ports": [], "listeners": {}, "counters": {}, "incidents": [], "blocked": {}, "baseline_done": False}

    def _save(self):
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=1)

    # ---------- 감지 ----------
    def collect(self):
        ev = []
        # 1) 방화벽 카운터와 로그
        counters = {}
        for line in sh("sudo -n nft list ruleset 2>/dev/null | grep -E 'counter packets' ").splitlines():
            m = re.search(r"counter packets (\d+) bytes \d+ comment \"([^\"]+)\"", line)
            if m:
                counters[m.group(2)] = int(m.group(1))
        for k, v in counters.items():
            prev = self.state["counters"].get(k, v)
            if v - prev > 0:
                ev.append(f"방화벽 {k}: 새로 {v - prev}개 패킷 차단")
        self.state["counters"] = counters
        lan_log = sh(f"sudo -n journalctl -k --since '{self.last_journal}' --no-pager -q 2>/dev/null | grep 'atanor-lan-block' | "
                     "grep -oE 'SRC=[0-9.]+ DST=[0-9.]+ .*DPT=[0-9]+' | sort | uniq -c | sort -rn | head -8")
        if lan_log:
            ev.append("LAN으로 나가려다 차단된 연결(횟수 SRC DST 포트):\n" + lan_log)
            # 어떤 프로세스가 LAN으로 나가려 하는지 찾는다
            procs = sh("sudo -n ss -tanp 2>/dev/null | grep -E '192\\.168\\.|10\\.|172\\.(1[6-9]|2[0-9]|3[01])\\.' | grep -vE ':22 |192.168.0.1:53' | head -8")
            if procs:
                ev.append("LAN 쪽 소켓을 가진 프로세스:\n" + procs)
        # 2) SSH
        ssh_log = sh(f"sudo -n journalctl -u ssh --since '{self.last_journal}' --no-pager -q 2>/dev/null | "
                     "grep -iE 'Failed|Invalid|Accepted|refused|Disconnected from authenticating' | tail -15")
        if ssh_log:
            ev.append("SSH:\n" + ssh_log)
        # 3) 수신 포트·연결 프로세스
        listeners = {}
        for line in sh("sudo -n ss -tulnpH 2>/dev/null").splitlines():
            parts = line.split()
            if len(parts) >= 5:
                proc = re.search(r'users:\(\("([^"]+)"', line)
                listeners[f"{parts[0]} {parts[4]}"] = proc.group(1) if proc else "?"
        new = {k: v for k, v in listeners.items() if k not in self.state["listeners"]}
        if new and self.state["baseline_done"]:
            ev.append("새로 열린 수신 포트: " + ", ".join(f"{k} ({v})" for k, v in new.items()))
        self.state["listeners"] = listeners
        ext = sh("sudo -n ss -tanpH state established 2>/dev/null | awk '{print $4, $5}' | "
                 "grep -vE ' (127\\.|192\\.168\\.|::1|\\[::ffff:127)' | head -12")
        ext_procs = sh("sudo -n ss -tanpH state established 2>/dev/null | grep -vE ' (127\\.|192\\.168\\.|::1)' | "
                       "grep -oE 'users:\\(\\(\"[^\"]+\"' | sort | uniq -c | sort -rn | head -8")
        if ext_procs:
            ev.append("바깥(인터넷)과 연결 중인 프로세스:\n" + ext_procs + ("\n" + ext if ext else ""))
        # 4) 권한·설정 변경
        sudo_log = sh(f"sudo -n journalctl _COMM=sudo --since '{self.last_journal}' --no-pager -q 2>/dev/null | "
                      "grep -E 'COMMAND=' | grep -vE 'COMMAND=/usr/(s)?bin/(nft list|journalctl|ss |snapper|brightnessctl|true)' | tail -10")
        if sudo_log:
            ev.append("sudo 사용:\n" + sudo_log)
        changed = sh("find /etc/ssh /etc/sudoers /etc/sudoers.d /etc/nftables.conf /etc/cron.d /etc/systemd/system "
                     "/home/*/.ssh/authorized_keys /home/*/.config/autostart -mmin -1 -type f 2>/dev/null")
        if changed:
            ev.append("최근 1분 안에 바뀐 보안 설정 파일:\n" + changed)
        self.last_journal = time.strftime("%Y-%m-%d %H:%M:%S")
        self.state["baseline_done"] = True
        return ev

    # ---------- 1차: 규칙 ----------
    def quick_rules(self, events):
        actions = []
        text = "\n".join(events)
        # 인터넷에서 SSH 무차별 시도
        fails = re.findall(r"(?:Failed|Invalid).*?from ([0-9.]+)", text)
        for ip in set(fails):
            if fails.count(ip) >= 3 and ip not in TRUSTED and not ip.startswith("192.168.0."):
                actions.append(("block_ip", ip, f"SSH 실패 {fails.count(ip)}회"))
        return actions

    # ---------- 2차: 모델 ----------
    def analyze(self, events):
        try:
            raw = self.core.brain.chat([{"role": "user", "content": PROMPT.replace("{events}", "\n\n".join(events)[:6000])}],
                                       schema=ANALYSIS_SCHEMA, temperature=0.1)
            return json.loads(raw)
        except Exception as e:  # noqa: BLE001
            return {"위협도": "알 수 없음", "요약": f"분석 실패: {e}", "대응": []}

    # ---------- 대응 ----------
    def block_ip(self, ip, why):
        if ip in TRUSTED or not re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
            return f"차단 거부: {ip}는 신뢰 주소"
        sh(f"sudo -n nft add element inet atanor blocklist {{ {ip} timeout {BLOCK_TTL} }}")
        self.state["blocked"][ip] = {"t": time.strftime("%Y-%m-%d %H:%M"), "why": why}
        subprocess.run(["logger", "-t", "atanor-sentinel", f"BLOCK {ip}: {why}"], check=False)
        return f"{ip} 차단 ({BLOCK_TTL})"

    PROTECTED = {"sshd", "sway", "swaybg", "python3", "systemd", "chromium", "apt", "apt-get", "dpkg", "bash", "sudo",
                 "init", "dbus-daemon", "wpa_supplicant", "dhcpcd", "pipewire", "wireplumber", "fcitx5", "mako", "login"}

    def kill_process(self, target, why):
        """대상은 PID(숫자) 또는 정확한 프로세스 이름만 받는다. 설명 문장이나 패턴은 거부한다."""
        target = (target or "").strip()
        if target.isdigit():
            pid = int(target)
            try:
                name = open(f"/proc/{pid}/comm").read().strip()
            except OSError:
                return f"중지 거부: PID {pid} 없음"
            if pid < 300 or name in self.PROTECTED:
                return f"중지 거부: {name}({pid})는 보호 대상"
            cmd = ["sudo", "-n", "kill", "-TERM", str(pid)]
        elif re.fullmatch(r"[A-Za-z0-9._+-]{1,15}", target):
            if target in self.PROTECTED:
                return f"중지 거부: {target}는 보호 대상"
            if not sh(f"pgrep -x {target}"):
                return f"중지 거부: 실행 중인 {target} 없음"
            cmd = ["sudo", "-n", "pkill", "-TERM", "-x", target]
        else:
            return f"중지 거부: 대상은 PID나 정확한 프로세스 이름이어야 한다 ({target[:40]})"
        r = subprocess.run(cmd, capture_output=True, text=True)
        out = "killed" if r.returncode == 0 else "failed"
        subprocess.run(["logger", "-t", "atanor-sentinel", f"KILL {target}: {why} -> {out}"], check=False)
        return f"{target} 중지: {out}"

    def act(self, actions, source):
        done = []
        for kind, target, why in actions:
            if kind == "block_ip":
                done.append(self.block_ip(target, why))
            elif kind == "kill_process":
                done.append(self.kill_process(target, why))
        if done:
            self.core.log("sentinel_action", source=source, actions=done)
        return done

    def unblock(self, ip):
        """차단 해제는 주인 승인이 있어야 한다 (Core 승인 흐름)."""
        if not self.core.request_confirm(f"Sentinel: {ip} 차단 해제", "sentinel"):
            return "주인이 승인하지 않음"
        sh(f"sudo -n nft delete element inet atanor blocklist {{ {ip} }}")
        self.state["blocked"].pop(ip, None)
        return f"{ip} 차단 해제"

    # ---------- 루프 ----------
    def tick(self):
        events = self.collect()
        if not events:
            self._save()
            return
        quick = self.quick_rules(events)
        done = self.act(quick, "rule")
        # 모델은 '신호가 있을 때만' 깨운다. 평범한 차단 카운터, 주인 PC의 SSH, ATANOR 자신의 sudo는 신호가 아니다.
        def signal(e):
            if e.startswith("방화벽 ") or e.startswith("바깥(인터넷)과 연결 중"):
                return False
            if e.startswith("SSH:"):
                return any(("192.168.0.125" not in line) for line in e.splitlines()[1:] if line.strip())
            if e.startswith("sudo 사용:"):
                return any("COMMAND=" in l and not re.search(r"(snapper|nft (list|add element)|ss -|journalctl|kill|pkill|tee /etc/nftables|install|apt|rsync|systemctl|chown|chmod|cp /opt|mkdir|loginctl|usermod)", l)
                           for l in e.splitlines()[1:])
            return True
        noisy = [e for e in events if signal(e)]
        if not noisy and not quick:
            self._save()
            return
        # 같은 종류의 신호로 모델을 너무 자주 깨우지 않는다 (최소 5분 간격, 긴급 규칙 대응은 예외)
        if not quick and time.time() - self.state.get("last_ai", 0) < 300:
            self._save()
            return
        self.state["last_ai"] = time.time()
        if self.core.busy or not self.core.brain.alive():
            self._save()
            return
        verdict = self.analyze(events)
        level = verdict.get("위협도", "없음")
        acts = [(a.get("행동"), a.get("대상", ""), a.get("이유", "")) for a in verdict.get("대응", [])
                if a.get("행동") in ("block_ip", "kill_process")]
        done += self.act(acts, "ai")
        incident = {"t": time.strftime("%Y-%m-%d %H:%M"), "level": level, "summary": verdict.get("요약", ""),
                    "evidence": verdict.get("근거", ""), "actions": done, "events": events[:6]}
        self.state["incidents"] = (self.state["incidents"] + [incident])[-200:]
        self.core.log("sentinel", **incident)
        self._save()
        if level in ("중간", "높음", "긴급") or done:
            self.core.emit("notify", {"title": f"🛡 Sentinel · 위협 {level}", "body": verdict.get("요약", "")[:160]})
            self.core.memory.log_event("sentinel", f"[{level}] {verdict.get('요약', '')} / 대응: {', '.join(done) or '없음'}")
        self.core.emit("sentinel", self.summary())

    def summary(self):
        inc = self.state["incidents"][-8:]
        return {"blocked": self.state["blocked"], "recent": inc, "listeners": len(self.state["listeners"]),
                "counters": self.state["counters"]}

    def loop(self):
        while True:
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001
                self.core.log("sentinel_error", error=str(e))
            time.sleep(INTERVAL)


def start(core):
    s = Sentinel(core)
    core.sentinel = s
    threading.Thread(target=s.loop, daemon=True, name="sentinel").start()

    # 도구로도 연다: 비서와 외부 AI가 경비 현황을 묻고 조치할 수 있게
    from atanor import tools as T

    @T.tool("sentinel.status", "AI 경비 현황: 차단된 IP, 최근 사건, 열린 포트 수.")
    def sentinel_status(a, ctx):
        return s.summary()

    @T.tool("sentinel.block", "IP를 24시간 차단한다(바로 실행, 되돌릴 수 있음).",
            {"ip": {"type": "string"}, "reason": {"type": "string"}}, risk="write", required=["ip"])
    def sentinel_block(a, ctx):
        return s.block_ip(a["ip"], a.get("reason", "manual"))

    @T.tool("sentinel.unblock", "차단을 푼다(주인 승인 필요).", {"ip": {"type": "string"}}, risk="danger", required=["ip"])
    def sentinel_unblock(a, ctx):
        sh(f"sudo -n nft delete element inet atanor blocklist {{ {a['ip']} }}")
        s.state["blocked"].pop(a["ip"], None)
        s._save()
        return f"{a['ip']} 차단 해제"

    @T.tool("sentinel.scan", "지금 바로 한 번 점검하고 결과를 돌려준다.", risk="write")
    def sentinel_scan(a, ctx):
        s.tick()
        return s.summary()
