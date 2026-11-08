"""ATANOR 모델 문지기 (5080 PC에서 실행).

HP 노트북은 SSH 터널을 통해 이 문지기(127.0.0.1:11435)에만 닿는다. 문지기는
- 허용된 경로만 통과: 대화(/api/chat, /v1/chat/completions), 임베딩(/api/embed), 버전·모델 목록
- 허용된 모델만 사용: ALLOWED_MODELS
- 요청 크기 제한, 초당 요청 수 제한
모델 다운로드·삭제·생성·복사(/api/pull, /api/delete, /api/create, /api/push, /api/copy, /api/blobs) 같은
관리 기능은 전부 거부한다. 노트북이 뚫려도 이 PC의 Ollama를 조작하거나 파일에 손댈 수 없게 하기 위함.
"""
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = "http://127.0.0.1:11434"
LISTEN = ("127.0.0.1", 11435)
ALLOWED_MODELS = {"dolphin24", "dolphin24:latest", "nomic-embed-text", "nomic-embed-text:latest", "gpt-oss:20b", "qwen2.5vl:7b"}
POST_PATHS = {"/api/chat", "/api/embed", "/v1/chat/completions"}
GET_PATHS = {"/api/version", "/api/tags", "/v1/models", "/api/ps"}
MAX_BODY = 4_000_000
RATE = 10  # 초당 최대 요청
LOG = None

_bucket = {"t": time.time(), "n": 0}
_lock = threading.Lock()


def log(msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
    if LOG:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def rate_ok():
    with _lock:
        now = time.time()
        if now - _bucket["t"] >= 1:
            _bucket.update(t=now, n=0)
        _bucket["n"] += 1
        return _bucket["n"] <= RATE


class Gate(BaseHTTPRequestHandler):
    server_version = "atanor-gate"

    def log_message(self, *a):
        pass

    def deny(self, code, why):
        log(f"DENY {self.command} {self.path} {why}")
        body = json.dumps({"error": why}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def relay(self, method, body=None):
        req = urllib.request.Request(UPSTREAM + self.path.split("?")[0], data=body, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                self.send_response(r.status)
                self.send_header("Content-Type", r.headers.get("Content-Type", "application/json"))
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                while True:
                    chunk = r.read1(65536) if hasattr(r, "read1") else r.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
        except urllib.error.HTTPError as e:
            self.deny(e.code, f"upstream {e.code}")
        except (urllib.error.URLError, OSError) as e:
            self.deny(502, f"upstream unavailable: {e}")

    def do_GET(self):
        if not rate_ok():
            return self.deny(429, "rate limit")
        path = self.path.split("?")[0]
        if path not in GET_PATHS:
            return self.deny(403, "path not allowed")
        self.relay("GET")

    def do_POST(self):
        if not rate_ok():
            return self.deny(429, "rate limit")
        path = self.path.split("?")[0]
        if path not in POST_PATHS:
            return self.deny(403, "path not allowed")
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BODY:
            return self.deny(413, "body size")
        raw = self.rfile.read(n)
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return self.deny(400, "bad json")
        if not isinstance(body, dict) or body.get("model") not in ALLOWED_MODELS:
            return self.deny(403, f"model not allowed: {str(body.get('model'))[:60] if isinstance(body, dict) else ''}")
        # 노트북이 모델 상주 시간 등을 조작하지 못하게 관리성 필드는 버린다
        for k in ("keep_alive",):
            body.pop(k, None)
        self.relay("POST", json.dumps(body).encode())

    def _reject(self):
        self.deny(405, "method not allowed")

    do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _reject


if __name__ == "__main__":
    LOG = sys.argv[1] if len(sys.argv) > 1 else None
    srv = ThreadingHTTPServer(LISTEN, Gate)
    srv.daemon_threads = True
    log(f"gate listening on {LISTEN[0]}:{LISTEN[1]}")
    srv.serve_forever()
