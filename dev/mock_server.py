"""Shell 개발용 가짜 Core. 노트북 없이 이 PC 브라우저에서 화면·배치를 다듬는다.

python dev/mock_server.py  →  http://127.0.0.1:7799/
?scene=idle|brief|focus|many|table  으로 장면을 고르고, ?layout=orbit 등으로 배치를 강제할 수 있다.
"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SHELL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "atanor", "shell")
MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".png": "image/png", ".ttf": "font/ttf"}

STATUS = {"time": "2026-11-08 09:12:03 Sun", "load": ["0.42", "0.51", "0.60"], "memory": "4.1/15.5 GB", "disk_free": "192 GB / 234 GB",
          "battery": "86% Discharging", "network": "wlo1 UP 192.168.0.149/24\nssid home-wifi", "uptime": "up 2 hours, 4 minutes",
          "volume": "Volume: 0.45", "brightness": "70%"}

P = {
    "status": {"id": "status", "title": "기기 상태", "type": "status", "order": 1},
    "todo": {"id": "todo", "title": "오늘 할 일", "type": "list", "order": 2,
             "data": {"items": ["ATANOR 화면 다듬기", "방화벽 기록 점검", "저녁 산책 30분"]}},
    "quick": {"id": "quick", "title": "바로 하기", "type": "buttons", "order": 3,
              "data": {"buttons": [{"label": "음악 틀기", "prompt": "음악"}, {"label": "유튜브", "prompt": "유튜브"}, {"label": "메모 열기", "prompt": "메모"}]}},
    "disk": {"id": "disk", "title": "디스크", "type": "meter", "order": 4, "data": {"value": 18, "display": "18%", "label": "234GB 중 42GB 사용"}},
    "note": {"id": "note", "title": "브리핑", "type": "text", "order": 0,
             "data": {"text": "## 좋은 아침이에요\n어젯밤 Sentinel이 막은 접속 시도는 없었어요. 배터리는 86%예요.\n오늘은 **ATANOR 화면**을 마저 다듬는 날이에요."}},
    "files": {"id": "files", "title": "홈 폴더", "type": "table", "order": 1,
              "data": {"columns": ["이름", "종류", "수정"], "rows": [["notes", "폴더", "11-08 02:05"], ["atanor-lab", "폴더", "11-08 02:50"],
                                                                 ["Pictures", "폴더", "11-08 02:26"], [".bashrc", "3.5 KB", "10-30 21:10"]]}},
    "sentinel": {"id": "sentinel", "title": "Sentinel", "type": "kv", "order": 5,
                 "data": {"pairs": {"위협도": "없음", "차단한 IP": "0", "열린 포트": "1 (ssh)", "마지막 점검": "09:11"}}},
}
P.update({
    "chart": {"id": "chart", "title": "배터리 (지난 6시간)", "type": "chart", "order": 1,
              "data": {"kind": "line", "labels": ["04", "05", "06", "07", "08", "09"], "series": [{"name": "배터리 %", "values": [100, 97, 93, 90, 88, 86]}]}},
    "steps": {"id": "steps", "title": "ATANOR 설치 진행", "type": "steps", "order": 2,
              "data": {"steps": [{"text": "그래픽 패키지 설치", "state": "done"}, {"text": "Core 서비스 시작", "state": "done"},
                                 {"text": "화면 다듬기", "state": "doing"}, {"text": "오프라인 연출", "state": "todo"}]}},
    "form": {"id": "form", "title": "알림 예약", "type": "form", "order": 3,
             "data": {"fields": [{"name": "time", "label": "언제", "type": "text"}, {"name": "what", "label": "무엇을"}],
                      "submit": "예약", "prompt": "{time}에 '{what}' 알려줘"}},
    "app": {"id": "app", "title": "포모도로", "type": "app", "order": 4, "data": {"name": "pomodoro"}},
})
SCENES = {
    "widgets": ["chart", "steps", "form", "app"],
    "idle": [], "brief": ["note", "status", "todo", "quick"], "focus": ["files"],
    "many": ["note", "status", "todo", "quick", "disk", "sentinel"], "table": ["files", "status"],
}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else (body.encode() if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode())
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def state(self):
        ref = parse_qs(urlparse(self.headers.get("Referer", "")).query)
        scene = (ref.get("scene") or ["brief"])[0]
        layout = (ref.get("layout") or ["orbit"])[0]
        panels = {k: P[k] for k in SCENES.get(scene, [])}
        hist = [{"role": "user", "text": "아침 브리핑 보여줘", "t": "2026-11-08T09:11:50"},
                {"role": "assistant", "text": "좋은 아침이에요. 오늘 필요한 것만 모아 뒀어요.", "t": "2026-11-08T09:12:01"}] if panels else []
        return {"ui": {"panels": panels, "theme": {"mode": "dark", "layout": layout}}, "history": hist, "busy": False, "pending": [],
                "brain": {"model": "dolphin24", "url": "mock", "alive": True},
                "memory": {"long_term": {"semantic": 12, "episodic": 5}}, "schedules": []}

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self.send(200, open(os.path.join(SHELL, "index.html"), encoding="utf-8").read().replace("__ATANOR_TOKEN__", "mock"), MIME[".html"])
        if u.path.startswith("/static/"):
            p = os.path.normpath(os.path.join(SHELL, u.path[8:]))
            return self.send(200, open(p, "rb").read(), MIME.get(os.path.splitext(p)[1], "application/octet-stream"))
        if u.path == "/api/state":
            return self.send(200, self.state())
        if u.path == "/api/status":
            return self.send(200, STATUS)
        if u.path == "/api/app":
            return self.send(200, {"html": """<div style="text-align:center;padding:20px">
<div id=t style="font:300 54px 'Noto Sans CJK KR';color:#f1fbff">25:00</div>
<button id=b>시작</button> <button id=s>상태 묻기</button><p id=o style="color:#5d7d8f"></p></div>
<script>let left=1500,iv;const f=()=>t.textContent=String(left/60|0).padStart(2,'0')+':'+String(left%60).padStart(2,'0');
b.onclick=()=>{clearInterval(iv);iv=setInterval(()=>{left--;f();},1000)};
s.onclick=async()=>{o.textContent=JSON.stringify(await atanor.tool('system.status',{})).slice(0,80)};</script>"""})
        if u.path == "/api/memory":
            return self.send(200, [{"content": "주인은 어두운 화면을 좋아한다", "kind": "semantic", "retention": .93}])
        if u.path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            try:
                while True:
                    time.sleep(15)
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except OSError:
                return
        self.send(404, {"error": "nf"})

    def do_POST(self):
        self.send(200, {"ok": True, "result": []})


if __name__ == "__main__":
    print("mock core on http://127.0.0.1:7799/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 7799), H).serve_forever()
