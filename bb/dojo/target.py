#!/usr/bin/env python3
"""ATANOR 도장 — 훈련용 '허수아비' 웹앱. 의도적으로 취약하다.
오직 Kali 컨테이너 안 127.0.0.1에서만 돌며, ATANOR가 자기 자신을 상대로
뚫고(red)·탐지하고(blue)·고치는(patch) 자기대련의 표적이다. 외부에 절대 노출 금지.
심은 취약점: SQLi(로그인), 경로우회(download), 명령주입(ping), IDOR(profile), 노출파일(backup.db).
요청은 /root/dojo/access.log 에 남아 blue 팀이 공격 신호를 읽는다.
"""
import os, sqlite3, http.server, urllib.parse, datetime, html

D = "/root/dojo"; os.makedirs(D, exist_ok=True)
DB = os.path.join(D, "backup.db"); LOG = os.path.join(D, "access.log")
NOTES = os.path.join(D, "notes.txt")
open(NOTES, "w").write("훈련용 메모. 평범한 파일.")

def init_db():
    if os.path.exists(DB): os.remove(DB)
    c = sqlite3.connect(DB); c.executescript(
        "CREATE TABLE users(id INTEGER PRIMARY KEY, user TEXT, pass TEXT, secret TEXT);"
        "INSERT INTO users(user,pass,secret) VALUES"
        "('admin','S3cr3t!','플래그: admin 기밀 문서 열람 권한'),"
        "('alice','alicepw','플래그: alice 개인 메모'),"
        "('bob','bobpw','플래그: bob 급여 정보');")
    c.commit(); c.close()
init_db()

def logreq(path):
    with open(LOG, "a") as f:
        f.write(f"{datetime.datetime.now().isoformat()} {path}\n")

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def ok(self, body, ctype="text/html"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        logreq(self.path)
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        g = lambda k, d="": (q.get(k) or [d])[0]
        try:
            if u.path == "/":
                return self.ok("<h1>ACME 훈련 포털</h1><a href=/login?user=guest&pass=guest>login</a> "
                               "/download?file= /ping?host= /profile?id= /backup.db")
            if u.path == "/login":
                user, pw = g("user"), g("pass")
                con = sqlite3.connect(DB); cur = con.cursor()
                # 취약: 입력을 그대로 쿼리에 이어붙임 (SQLi)
                qy = f"SELECT user,secret FROM users WHERE user='{user}' AND pass='{pw}'"
                try: row = cur.execute(qy).fetchone()
                except Exception as e: row = None; qy += f"  -- ERROR {e}"
                con.close()
                if row: return self.ok(f"<p>welcome {html.escape(row[0])} — {html.escape(row[1])}</p>")
                return self.ok("<p>로그인 실패</p>")
            if u.path == "/download":
                # 취약: 경로 검증 없음 (path traversal)
                p = os.path.join(D, g("file", "notes.txt"))
                return self.ok(open(p, "rb").read(), "text/plain")
            if u.path == "/ping":
                # 취약: 셸로 넘김 (command injection)
                host = g("host", "127.0.0.1")
                out = os.popen(f"ping -c1 -W1 {host}").read()
                return self.ok("<pre>" + out + "</pre>")
            if u.path == "/profile":
                # 취약: 인증 없이 id로 남의 정보 (IDOR)
                con = sqlite3.connect(DB)
                row = con.execute("SELECT user,secret FROM users WHERE id=?", (g("id", "1"),)).fetchone()
                con.close()
                return self.ok(f"<p>{html.escape(str(row))}</p>" if row else "<p>없음</p>")
            if u.path == "/backup.db":
                # 취약: DB 파일 그대로 노출
                return self.ok(open(DB, "rb").read(), "application/octet-stream")
            self.send_response(404); self.end_headers()
        except Exception as e:
            self.ok(f"<pre>ERR {html.escape(str(e))}</pre>")

if __name__ == "__main__":
    print("dojo target on 127.0.0.1:8099", flush=True)
    http.server.HTTPServer(("127.0.0.1", 8099), H).serve_forever()
