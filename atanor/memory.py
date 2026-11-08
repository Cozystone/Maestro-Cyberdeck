"""ATANOR 기억 기관 — 사람의 기억 구조를 본뜬 장·단기 기억.

층 구조
- 작업기억(working): 요청마다 관련 기억 몇 개만 골라 모델 문맥에 넣는다 (recall()).
- 단기기억(events): 대화·행동을 사건 단위로 그대로 적는다. 정리(consolidate) 후 비워진다.
- 장기기억(memories): semantic(사실·취향) / episodic(요약된 경험) / procedural(성공한 작업 방법).

가소성
- 기억마다 importance(중요도)와 stability(안정도, 시간 단위)를 가진다.
- 보존율 R = exp(-경과시간 / stability)  (에빙하우스 망각 곡선)
- 떠올릴 때마다(recall) stability가 커진다 → 자주 쓰는 기억일수록 덜 잊힌다 (간격 반복 효과).
- 함께 떠올린 기억끼리는 연결(links) 가중치가 커진다 (헤브 규칙: 함께 발화하면 함께 연결된다).
- 연상: 검색된 기억과 연결된 이웃 기억도 활성화가 퍼진다 (spreading activation).

수면 정리(consolidate)
- 단기기억을 모델로 요약해 장기기억으로 옮긴다. 비슷한 기억이 있으면 새로 만들지 않고 합치며 강화한다.
- 보존율과 중요도가 모두 낮은 기억은 보관함(archived)으로 보낸다 — 지우지 않는다.
"""
import json
import math
import sqlite3
import struct
import threading
import time
import urllib.request

HOUR = 3600.0
KINDS = ("semantic", "episodic", "procedural")


def _pack(vec):
    return struct.pack(f"{len(vec)}f", *vec) if vec else None


def _unpack(blob):
    return list(struct.unpack(f"{len(blob) // 4}f", blob)) if blob else None


def _cos(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _keywords(text):
    import re
    return {w for w in re.findall(r"[\w가-힣]{2,}", text.lower())}


class Memory:
    def __init__(self, path, embed_url=None, embed_model=None):
        self.path = path
        self.embed_url = embed_url
        self.embed_model = embed_model
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY, t REAL, kind TEXT, content TEXT, session TEXT, consolidated INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS memories(
            id INTEGER PRIMARY KEY, kind TEXT, content TEXT, embedding BLOB,
            importance REAL, stability REAL, created REAL, last_access REAL,
            access_count INTEGER DEFAULT 0, archived INTEGER DEFAULT 0, source TEXT);
        CREATE TABLE IF NOT EXISTS links(a INTEGER, b INTEGER, weight REAL, PRIMARY KEY(a, b));
        CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
        """)
        self.db.commit()

    # ---------- 임베딩 ----------
    def embed(self, text):
        if not self.embed_url or not self.embed_model:
            return None
        try:
            body = json.dumps({"model": self.embed_model, "input": [text[:2000]],
                               "options": {"num_gpu": 0}}).encode()  # CPU로 돌려 큰 모델을 GPU에서 밀어내지 않는다
            req = urllib.request.Request(self.embed_url + "/api/embed", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())["embeddings"][0]
        except Exception:  # noqa: BLE001 — 두뇌가 꺼져 있어도 기억은 키워드로 동작한다
            return None

    # ---------- 단기기억 ----------
    def log_event(self, kind, content, session=""):
        with self.lock:
            self.db.execute("INSERT INTO events(t, kind, content, session) VALUES(?,?,?,?)",
                            (time.time(), kind, content[:4000], session))
            self.db.commit()

    def recent_events(self, n=20):
        with self.lock:
            rows = self.db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def pending_event_count(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM events WHERE consolidated=0").fetchone()[0]

    # ---------- 장기기억 ----------
    def retention(self, row, now=None):
        now = now or time.time()
        dt_h = max(0.0, (now - (row["last_access"] or row["created"])) / HOUR)
        return math.exp(-dt_h / max(row["stability"], 0.1))

    def remember(self, content, kind="semantic", importance=0.5, source="agent"):
        """새 기억을 넣는다. 거의 같은 기억이 있으면 합치고 강화한다."""
        kind = kind if kind in KINDS else "semantic"
        vec = self.embed(content)
        with self.lock:
            dup = self._find_similar(content, vec, threshold=0.92)
            now = time.time()
            if dup:
                self.db.execute(
                    "UPDATE memories SET content=?, importance=MAX(importance, ?), stability=stability*1.5,"
                    " last_access=?, access_count=access_count+1, archived=0,"
                    " embedding=COALESCE(?, embedding) WHERE id=?",
                    (content, importance, now, _pack(vec), dup))
                self.db.commit()
                return {"id": dup, "merged": True}
            # 중요한 기억일수록 처음부터 안정도가 높다 (24시간 ~ 2주)
            stability = 24 + importance * 300
            cur = self.db.execute(
                "INSERT INTO memories(kind, content, embedding, importance, stability, created, last_access, source)"
                " VALUES(?,?,?,?,?,?,?,?)", (kind, content, _pack(vec), importance, stability, now, now, source))
            self.db.commit()
            return {"id": cur.lastrowid, "merged": False}

    def _find_similar(self, content, vec, threshold):
        rows = self.db.execute("SELECT id, content, embedding FROM memories WHERE archived=0").fetchall()
        best, best_sim = None, 0.0
        kw = _keywords(content)
        for r in rows:
            if vec and r["embedding"]:
                sim = _cos(vec, _unpack(r["embedding"]))
            else:
                other = _keywords(r["content"])
                sim = len(kw & other) / max(1, len(kw | other))
            if sim > best_sim:
                best, best_sim = r["id"], sim
        return best if best_sim >= threshold else None

    def recall(self, query, k=6, kinds=None, touch=True):
        """질문과 관련된 기억을 꺼낸다. 꺼낸 기억은 강해지고, 함께 꺼낸 기억끼리는 연결된다."""
        vec = self.embed(query)
        kw = _keywords(query)
        now = time.time()
        with self.lock:
            rows = self.db.execute("SELECT * FROM memories WHERE archived=0").fetchall()
            scored = {}
            for r in rows:
                if kinds and r["kind"] not in kinds:
                    continue
                other = _keywords(r["content"])
                kw_sim = len(kw & other) / max(1, len(kw)) if kw else 0.0
                emb_sim = _cos(vec, _unpack(r["embedding"])) if vec and r["embedding"] else 0.0
                relevance = max(emb_sim, kw_sim) if vec else kw_sim
                score = 0.65 * relevance + 0.2 * self.retention(r, now) + 0.15 * r["importance"]
                scored[r["id"]] = (score, relevance, r)
            # 연상: 관련도가 높은 기억의 이웃에게 활성화를 나눠준다
            top_ids = [i for i, (s, rel, _) in sorted(scored.items(), key=lambda x: -x[1][0])[:k] if rel > 0.15]
            if top_ids:
                q = ",".join("?" * len(top_ids))
                for ln in self.db.execute(f"SELECT a, b, weight FROM links WHERE a IN ({q})", top_ids):
                    if ln["b"] in scored:
                        s, rel, r = scored[ln["b"]]
                        scored[ln["b"]] = (s + 0.15 * min(ln["weight"], 1.0), max(rel, 0.16), r)
            ranked = sorted(scored.values(), key=lambda x: -x[0])
            picked = [(s, r) for s, rel, r in ranked if rel > 0.15][:k]
            if touch and picked:
                ids = [r["id"] for _, r in picked]
                for _, r in picked:
                    # 간격 반복: 잊혀 가던 기억을 떠올릴수록 안정도가 크게 오른다
                    gain = 1.0 + 0.8 * (1.0 - self.retention(r, now))
                    self.db.execute("UPDATE memories SET stability=MIN(stability*?, 24*365), last_access=?,"
                                    " access_count=access_count+1 WHERE id=?", (gain, now, r["id"]))
                for a in ids:  # 헤브 규칙
                    for b in ids:
                        if a != b:
                            self.db.execute("INSERT INTO links(a,b,weight) VALUES(?,?,0.1) ON CONFLICT(a,b)"
                                            " DO UPDATE SET weight=MIN(weight+0.1, 2.0)", (a, b))
                self.db.commit()
        return [{"id": r["id"], "kind": r["kind"], "content": r["content"], "score": round(s, 3),
                 "retention": round(self.retention(r, now), 3)} for s, r in picked]

    def forget(self, memory_id):
        with self.lock:
            self.db.execute("UPDATE memories SET archived=1 WHERE id=?", (memory_id,))
            self.db.commit()

    def stats(self):
        with self.lock:
            c = self.db.execute("SELECT kind, COUNT(*) n FROM memories WHERE archived=0 GROUP BY kind").fetchall()
            arch = self.db.execute("SELECT COUNT(*) FROM memories WHERE archived=1").fetchone()[0]
            last = self.db.execute("SELECT v FROM meta WHERE k='last_consolidation'").fetchone()
        return {"long_term": {r["kind"]: r["n"] for r in c}, "archived": arch,
                "short_term_pending": self.pending_event_count(), "last_consolidation": last[0] if last else None}

    def list(self, kind=None, limit=50):
        with self.lock:
            sql = "SELECT * FROM memories WHERE archived=0" + (" AND kind=?" if kind else "") + \
                  " ORDER BY last_access DESC LIMIT ?"
            rows = self.db.execute(sql, ((kind, limit) if kind else (limit,))).fetchall()
            now = time.time()
        return [{"id": r["id"], "kind": r["kind"], "content": r["content"], "importance": r["importance"],
                 "retention": round(self.retention(r, now), 3), "access_count": r["access_count"]} for r in rows]

    # ---------- 수면 정리 ----------
    def consolidate(self, llm):
        """llm(prompt) -> str(JSON). 단기기억을 장기기억으로 옮기고, 약한 기억을 보관함으로 보낸다."""
        with self.lock:
            rows = self.db.execute("SELECT * FROM events WHERE consolidated=0 ORDER BY id LIMIT 300").fetchall()
        result = {"events": len(rows), "added": 0, "merged": 0, "archived": 0}
        if rows:
            transcript = "\n".join(
                f"[{time.strftime('%m-%d %H:%M', time.localtime(r['t']))}] {r['kind']}: {r['content'][:500]}"
                for r in rows)
            prompt = (
                "다음은 AI 비서와 주인 사이에 있었던 일의 기록이다. 오래 기억할 가치가 있는 것만 뽑아라.\n"
                "- semantic: 주인에 대한 사실, 취향, 기기·환경 정보 (예: '주인은 어두운 화면을 좋아한다')\n"
                "- episodic: 있었던 일의 요약 (날짜 포함, 한 문장)\n"
                "- procedural: 성공한 작업 방법 (예: '배터리 확인은 cat /sys/class/power_supply/BAT0/capacity')\n"
                "사소한 잡담, 실패한 시도, 일시적 수치는 버린다. importance는 0~1.\n"
                'JSON으로만 답하라: {"memories": [{"kind": "...", "content": "...", "importance": 0.5}]}\n\n'
                + transcript)
            try:
                data = json.loads(llm(prompt))
                for m in data.get("memories", [])[:30]:
                    if m.get("content"):
                        r = self.remember(m["content"], m.get("kind", "semantic"),
                                          float(m.get("importance", 0.5)), source="consolidation")
                        result["merged" if r["merged"] else "added"] += 1
            except Exception as e:  # noqa: BLE001
                result["error"] = str(e)
                return result
            with self.lock:
                self.db.execute(f"UPDATE events SET consolidated=1 WHERE id <= ?", (rows[-1]["id"],))
                # 정리된 단기기억은 7일 지나면 지운다 (장기기억에 요약이 남아 있다)
                self.db.execute("DELETE FROM events WHERE consolidated=1 AND t < ?", (time.time() - 7 * 86400,))
        with self.lock:
            now = time.time()
            for r in self.db.execute("SELECT * FROM memories WHERE archived=0").fetchall():
                if self.retention(r, now) < 0.05 and r["importance"] < 0.4:
                    self.db.execute("UPDATE memories SET archived=1 WHERE id=?", (r["id"],))
                    result["archived"] += 1
            self.db.execute("DELETE FROM links WHERE weight < 0.05")
            self.db.execute("UPDATE links SET weight = weight * 0.9")  # 연결도 쓰지 않으면 약해진다
            self.db.execute("INSERT INTO meta(k, v) VALUES('last_consolidation', ?) ON CONFLICT(k) DO UPDATE"
                            " SET v=excluded.v", (time.strftime("%Y-%m-%d %H:%M"),))
            self.db.commit()
        return result
