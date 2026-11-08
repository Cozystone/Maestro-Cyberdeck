#!/usr/bin/env python3
"""일상 작업·UI 설정 시뮬레이션 — 실제 노트북에서 주인처럼 말을 걸고 결과를 기록한다.

python3 sim_daily.py [시작번호] [끝번호]
결과: ~/sim/report.jsonl, 각 장면 스크린샷 ~/sim/NN.png
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

U = "http://127.0.0.1:7700"
TOKEN = open(os.path.expanduser("~/.atanor/token")).read().strip()
OUT = os.path.expanduser("~/sim")
os.makedirs(OUT, exist_ok=True)

# (말, 확인할 것) — 확인은 사람이 결과를 읽을 때 쓰는 기준이다.
SCENARIOS = [
    ("지금 몇 시야?", "시간을 정확히 말한다"),
    ("배터리 얼마나 남았어?", "배터리 %"),
    ("소리 30으로 맞춰줘", "device.volume 30"),
    ("화면 좀 어둡게 해줘", "device.brightness 낮춤"),
    ("notes 폴더에 장보기.txt 만들고 우유, 계란, 두부 적어줘", "파일이 실제로 생김"),
    ("방금 만든 장보기 목록 보여줘", "파일 내용을 패널/답으로"),
    ("내일 아침 9시에 회의 있다고 알려줘", "schedule.add 내일 09:00"),
    ("5분 뒤에 스트레칭하라고 알려줘", "schedule.add 5분 뒤"),
    ("서울 오늘 날씨 어때?", "웹에서 실제 날씨 수치"),
    ("유튜브에서 lofi 음악 틀어줘", "브라우저로 유튜브 재생"),
    ("이제 브라우저 닫아줘", "창 닫히고 ATANOR 화면 복귀"),
    ("터미널 열어줘", "foot 창"),
    ("터미널 닫아줘", "창 닫힘, 화면 복귀"),
    ("와이파이 연결 상태 알려줘", "SSID/연결 여부(비밀번호 노출 금지)"),
    ("스크린샷 찍어줘", "파일 경로"),
    ("화면 밝은 테마로 바꿔줘", "ui.theme light"),
    ("다시 어둡게 해줘", "ui.theme dark (밝기 아님!)"),
    ("시계랑 오늘 할 일 패널 띄워줘", "패널 2개, 오브 가운데"),
    ("글씨 좀 크게 해줘", "UI 글자 크기"),
    ("패널 다 치워줘", "패널 0개"),
    ("화면 배치 기본으로 돌려줘", "layout orbit"),
    ("할 일에 빨래랑 운동 적어줘", "todo.add 빨래, 운동"),
    ("할 일 패널 띄워줘", "todo 패널(지어낸 항목 없음)"),
    ("빨래 다 했어", "todo.done 빨래"),
    ("글씨 원래대로 해줘", "scale 1"),
]


def call(path, body=None, timeout=900):
    req = urllib.request.Request(U + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-Atanor-Token": TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def shot(n):
    env = dict(os.environ, WAYLAND_DISPLAY="wayland-1", XDG_RUNTIME_DIR=f"/run/user/{os.getuid()}")
    subprocess.run(["grim", "-s", "0.5", f"{OUT}/{n:02d}.png"], env=env, capture_output=True)


def main():
    a = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    b = int(sys.argv[2]) if len(sys.argv) > 2 else len(SCENARIOS)
    call("/api/tool", {"name": "mind.autonomy", "args": {"level": "off"}, "source": "api"})
    if a == 1:
        call("/api/history/clear", {})
    rep = open(f"{OUT}/report.jsonl", "a")
    for n in range(a, b + 1):
        text, expect = SCENARIOS[n - 1]
        t0 = time.time()
        try:
            d = call("/api/ask", {"text": text, "source": "user", "wait": True})
        except Exception as e:  # noqa: BLE001
            d = {"reply": f"(요청 실패: {e})", "steps": []}
        secs = round(time.time() - t0)
        time.sleep(1.5)
        shot(n)
        st = call("/api/state")
        ui = st.get("ui", {})
        rec = {"n": n, "text": text, "expect": expect, "secs": secs, "reply": d.get("reply", ""),
               "steps": [{"tool": s.get("tool"), "args": s.get("args"), "ok": s.get("ok"),
                          "result": str(s.get("result", s.get("error", "")))[:300]} for s in d.get("steps", [])],
               "panels": {k: v.get("type") for k, v in (ui.get("panels") or {}).items()},
               "theme": ui.get("theme")}
        rep.write(json.dumps(rec, ensure_ascii=False) + "\n")
        rep.flush()
        print(f"\n#{n} {text}  ({secs}s)  기대: {expect}")
        for s in rec["steps"]:
            print(f"   - {s['tool']} {json.dumps(s['args'], ensure_ascii=False)[:140]} → {'OK' if s['ok'] is not False else 'ERR'} {s['result'][:140]}")
        print("   답:", rec["reply"][:300].replace("\n", " "))
        print("   패널:", rec["panels"], "테마:", rec["theme"])
    call("/api/tool", {"name": "mind.autonomy", "args": {"level": "quiet"}, "source": "api"})


if __name__ == "__main__":
    main()
