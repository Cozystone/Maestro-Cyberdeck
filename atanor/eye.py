"""ATANOR 눈 — 사람의 시각을 본뜬 화면 지각 기관 (ATANOR-Demo perception v0의 다음 세대).

Demo의 시각 기관이 지킨 원칙을 그대로 잇는다:
  · 지어내지 않고 '측정'한다 — 밝기·색·변화는 픽셀에서 잰 값, 글자는 OCR이 읽은 값만 쓴다.
  · 본 것마다 출처가 있다 — 요소마다 어디서 왔는지(접근성 트리 / 글자 판독 / 눈 모델 추정) 붙인다.
  · 본 것을 장면 그래프로 바꾼다 — 창 → 줄 → 요소, 번호가 붙은 구조로.
  · 민감한 것은 남기지 않는다 — 비밀번호 칸의 값은 가린다.

사람의 눈처럼 나뉘어 일한다:
  망막(retina)   화면 전체를 저해상도로 훑어 밝기·색·변화 지도를 잰다. 바뀐 곳에 주의가 간다.
  주변시(periphery) 창들의 배치(어느 앱이 어디, 무엇에 포커스)를 잡는다.
  중심와(fovea)  바뀐 창만 고해상도로 글자를 읽는다(OCR). 어두운 화면은 반전해서 읽는다(암순응).
  배측 경로(where) 접근성 트리로 버튼·입력칸의 정확한 자리와 역할을 안다.
  복측 경로(what) 글자와 역할을 합쳐 '무엇'인지 이름 붙인다.
  주의(attention) 직전 장면과 비교해 새로 나타난 것·사라진 것을 먼저 알린다.
결과는 글로 된 장면이라, 그림을 못 보는 두뇌(mistral)도 사람처럼 화면을 읽고 번호로 조작한다.
"""
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "atspi_helper.py")
ROLE_KO = {"push button": "버튼", "toggle button": "토글", "check box": "체크칸", "radio button": "선택칸",
           "menu item": "메뉴항목", "menu": "메뉴", "check menu item": "메뉴항목", "radio menu item": "메뉴항목",
           "text": "입력칸", "entry": "입력칸", "password text": "비밀번호칸", "combo box": "선택상자",
           "list item": "목록", "table cell": "칸", "page tab": "탭", "link": "링크", "icon": "아이콘",
           "spin button": "숫자칸", "slider": "슬라이더", "tree item": "항목", "terminal": "터미널",
           "document text": "문서", "paragraph": "문단"}


class Eye:
    def __init__(self, core):
        self.core = core
        self.prev_small = None          # 망막: 직전 저해상도 화면
        self.ocr_cache = {}             # 창 id → (픽셀 지문, 판독 결과)
        self.scene = {"elements": {}, "labels": set()}
        self.next_id = 1
        self.lock = threading.Lock()

    # ───────── 망막 ─────────
    def retina(self, img):
        """저해상도로 측정: 밝기, 주조색, 변화 지도(어느 칸이 바뀌었나)."""
        import numpy as np
        small = img.resize((192, 108)).convert("RGB")
        px = np.asarray(small, dtype=np.float32) / 255.0
        gray = px.mean(axis=2)
        q = (px.reshape(-1, 3) * 3.999).astype(int)
        keys, counts = np.unique(q[:, 0] * 16 + q[:, 1] * 4 + q[:, 2], return_counts=True)
        top = int(keys[np.argmax(counts)])
        dominant = [round((top // 16) / 3, 2), round(((top % 16) // 4) / 3, 2), round((top % 4) / 3, 2)]
        changed = []
        if self.prev_small is not None and self.prev_small.shape == gray.shape:
            diff = np.abs(gray - self.prev_small) > 0.06
            for ty in range(0, 108, 12):          # 16x9 칸으로 나눠 바뀐 칸을 센다
                for tx in range(0, 192, 12):
                    if diff[ty:ty + 12, tx:tx + 12].mean() > 0.02:
                        changed.append((tx * img.width // 192, ty * img.height // 108))
        self.prev_small = gray
        return {"밝기": round(float(gray.mean()), 2), "주조색": dominant, "바뀐칸": changed}

    # ───────── 주변시: 창 배치 ─────────
    def windows(self, ctx):
        from atanor import tools as T
        tree = json.loads(T.swaymsg(ctx, "-t", "get_tree"))
        out, ws_name = [], None

        def walk(n, ws):
            if n.get("type") == "workspace":
                ws = n.get("name")
            if n.get("pid") and n.get("visible"):
                r, wr = n["rect"], n.get("window_rect") or {"x": 0, "y": 0, "width": n["rect"]["width"], "height": n["rect"]["height"]}
                out.append({"id": n["id"], "pid": n["pid"], "app": n.get("app_id") or (n.get("window_properties") or {}).get("class") or "?",
                            "title": n.get("name") or "", "focused": n.get("focused", False), "ws": ws,
                            "x": r["x"] + wr["x"], "y": r["y"] + wr["y"], "w": wr["width"], "h": wr["height"]})
            for c in n.get("nodes", []) + n.get("floating_nodes", []):
                walk(c, ws)
        walk(tree, ws_name)
        return out

    # ───────── 중심와: 글자 읽기 ─────────
    def read_text(self, img, win):
        """창 하나를 고해상도로 읽는다. 픽셀이 그대로면 예전 판독을 다시 쓴다(주의가 안 가는 곳은 다시 안 본다)."""
        import numpy as np
        from PIL import Image, ImageOps
        crop = img.crop((win["x"], win["y"], win["x"] + win["w"], win["y"] + win["h"]))
        fp = hashlib.md5(np.asarray(crop.resize((96, 54)).convert("L")).tobytes()).hexdigest()
        hit = self.ocr_cache.get(win["id"])
        if hit and hit[0] == fp:
            return hit[1], True
        g = crop.convert("L")
        if np.asarray(g.resize((64, 36)), dtype=np.float32).mean() < 110:   # 어두운 화면 → 반전해서 읽기(암순응)
            g = ImageOps.invert(g)
        S = 2
        g = g.resize((g.width * S, g.height * S), Image.LANCZOS)
        path = f"/tmp/atanor-eye-{win['id']}.png"
        g.save(path)
        p = subprocess.run(["tesseract", path, "stdout", "-l", "kor+eng", "--psm", "11", "tsv"],
                           capture_output=True, text=True, timeout=60)
        words = []
        for line in p.stdout.splitlines()[1:]:
            c = line.split("\t")
            if len(c) < 12 or not c[11].strip():
                continue
            try:
                conf = float(c[10])
            except ValueError:
                continue
            if conf < 45:
                continue
            x, y, w, h = (int(v) // S for v in c[6:10])
            words.append({"t": c[11].strip(), "x": win["x"] + x, "y": win["y"] + y, "w": w, "h": h, "c": conf})
        phrases = self.group(words)
        self.ocr_cache[win["id"]] = (fp, phrases)
        return phrases, False

    @staticmethod
    def group(words):
        """낱말을 사람 눈처럼 덩어리(구절)로 묶는다: 같은 줄에 있고 간격이 좁으면 한 덩어리."""
        words.sort(key=lambda w: (w["y"] + w["h"] / 2, w["x"]))
        lines = []
        for w in words:
            cy = w["y"] + w["h"] / 2
            for ln in lines:
                if abs(ln["cy"] - cy) < max(ln["h"], w["h"]) * 0.6:
                    ln["ws"].append(w)
                    break
            else:
                lines.append({"cy": cy, "h": w["h"], "ws": [w]})
        out = []
        for ln in lines:
            ws = sorted(ln["ws"], key=lambda w: w["x"])
            cur = [ws[0]]
            for w in ws[1:]:
                prev = cur[-1]
                if w["x"] - (prev["x"] + prev["w"]) < max(prev["h"], w["h"]) * 0.8:
                    cur.append(w)
                else:
                    out.append(cur)
                    cur = [w]
            out.append(cur)
        res = []
        for ph in out:
            x1, y1 = min(w["x"] for w in ph), min(w["y"] for w in ph)
            x2, y2 = max(w["x"] + w["w"] for w in ph), max(w["y"] + w["h"] for w in ph)
            text = " ".join(w["t"] for w in ph)
            if len(text) == 1 and not re.match(r"[0-9A-Za-z가-힣]", text):
                continue                                   # 홀로 떨어진 기호 하나는 잡음일 가능성이 크다
            res.append({"text": text, "box": [x1, y1, x2 - x1, y2 - y1], "conf": round(sum(w["c"] for w in ph) / len(ph))})
        return res

    # ───────── 배측 경로: 접근성 트리 ─────────
    def a11y(self, ctx, wins):
        from atanor import tools as T
        env = T.need_gui(ctx)
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={env['XDG_RUNTIME_DIR']}/bus")
        try:
            p = subprocess.run(["python3", HELPER, "scan", *[str(w["pid"]) for w in wins]],
                               capture_output=True, text=True, timeout=20, env=env)
            els = json.loads(p.stdout or "[]")
        except Exception:  # noqa: BLE001
            return []
        by_pid = {w["pid"]: w for w in wins}
        for e in els:
            w = by_pid.get(e["pid"])
            if w:
                x, y, bw, bh = e["box"]
                e["box"] = [w["x"] + x, w["y"] + y, bw, bh]
                e["win"] = w["id"]
        return [e for e in els if "win" in e]

    # ───────── 보기 ─────────
    def see(self, ctx, scope="screen", gist=False):
        from atanor import tools as T
        t0 = time.time()
        code, _, err = T.run(["grim", "/tmp/atanor-eye.png"], env=T.need_gui(ctx))
        if code != 0:
            raise RuntimeError(err)
        from PIL import Image
        img = Image.open("/tmp/atanor-eye.png").convert("RGB")
        ret = self.retina(img)
        wins = self.windows(ctx)
        if scope == "focused":
            wins = [w for w in wins if w["focused"]] or wins
        with ThreadPoolExecutor(max_workers=4) as ex:
            reads = list(ex.map(lambda w: self.read_text(img, w), wins))
        acc = self.a11y(ctx, wins)

        elements, n = [], 0
        for w, (phrases, cached) in zip(wins, reads):
            used = set()
            items = []
            for e in (x for x in acc if x["win"] == w["id"]):
                # 이름이 같은 글을 눈이 실제로 본 곳이 있으면, 그 자리가 진짜다(측정 우선).
                # 팝업 메뉴처럼 접근성 좌표가 팝업 기준으로 어긋나는 경우를 바로잡는다.
                nm = _norm(e["name"])
                if nm:
                    cands = [i for i, ph in enumerate(phrases) if i not in used and _same(nm, _norm(ph["text"]))]
                    if cands:
                        bx, by = e["box"][0], e["box"][1]
                        best = min(cands, key=lambda i: abs(phrases[i]["box"][0] - bx) + abs(phrases[i]["box"][1] - by))
                        pb = phrases[best]["box"]
                        if abs(pb[0] - bx) > 24 or abs(pb[1] - by) > 12 or not _inside(pb, e["box"]):
                            e["box"] = [pb[0] - 6, pb[1] - 4, pb[2] + 12, pb[3] + 8]
                ex_, ey, ew, eh = e["box"]
                inside = [i for i, ph in enumerate(phrases)
                          if ph["box"][0] >= ex_ - 3 and ph["box"][1] >= ey - 3
                          and ph["box"][0] + ph["box"][2] <= ex_ + ew + 3 and ph["box"][1] + ph["box"][3] <= ey + eh + 3]
                label = e["name"] or " ".join(phrases[i]["text"] for i in inside)
                if not label and not e["value"] and e["role"] not in ("text", "entry", "password text"):
                    continue
                used.update(inside)
                items.append({"kind": ROLE_KO.get(e["role"], e["role"]), "label": label[:70], "value": e["value"],
                              "box": e["box"], "src": "접근성", "focused": e["focused"], "checked": e["checked"],
                              "selected": e["selected"], "pid": e["pid"], "path": e["path"],
                              "secret": e["role"] == "password text"})
            for i, ph in enumerate(phrases):
                if i in used:
                    continue
                if any(it.get("secret") and _inside(ph["box"], it["box"]) for it in items):
                    continue
                # 접근성 요소들과 대부분 겹치는 글은 그 요소들이 이미 말해 준 것 — 두 번 세지 않는다
                if items and _covered(ph["box"], [it["box"] for it in items if it["src"] == "접근성"]) > 0.5:
                    continue
                # 글자가 아닌 그림 조각(아이콘 화살표 등)을 글로 잘못 읽은 것 걸러내기
                if ph["conf"] < 70 and len(re.findall(r"[0-9A-Za-z가-힣]", ph["text"])) < 3:
                    continue
                items.append({"kind": "글", "label": ph["text"][:70], "value": "", "box": ph["box"], "src": "글자판독",
                              "focused": False, "checked": False, "selected": False, "conf": ph["conf"]})
            items.sort(key=lambda it: (it["box"][1] // 14, it["box"][0]))
            for it in items:
                it["win"] = w
                elements.append(it)

        # 대상 영속성: 직전 장면에 있던 같은 것(같은 창·같은 글·거의 같은 자리)은 같은 번호를 지킨다.
        # 화면 일부가 바뀌어도 번호가 밀리지 않아, 두뇌가 본 번호를 그대로 쓸 수 있다.
        prev = list(self.scene.get("elements", {}).values())
        taken, fresh = set(), []
        for it in elements:
            cx, cy = it["box"][0] + it["box"][2] / 2, it["box"][1] + it["box"][3] / 2
            match = None
            for p in prev:
                if p["id"] in taken or p["win"]["id"] != it["win"]["id"] or p["label"] != it["label"]:
                    continue
                px, py = p["box"][0] + p["box"][2] / 2, p["box"][1] + p["box"][3] / 2
                if abs(px - cx) < 40 and abs(py - cy) < 40:
                    match = p["id"]
                    break
            if match:
                it["id"] = match
                taken.add(match)
            else:
                fresh.append(it)
        if not taken:                       # 완전히 새 화면이면 번호를 1부터 다시
            self.next_id = 1
        for it in fresh:
            while self.next_id in taken:
                self.next_id += 1
            it["id"] = self.next_id
            taken.add(self.next_id)
            self.next_id += 1
        n = len(elements)

        labels = {(e["win"]["id"], e["label"]) for e in elements if e["label"]}
        old = self.scene.get("labels", set())
        new_l = [lab for (_, lab) in labels - old][:12] if old else []
        gone = [lab for (_, lab) in old - labels][:8] if old else []
        with self.lock:
            self.scene = {"elements": {e["id"]: e for e in elements}, "labels": labels, "at": time.time()}

        lines = [f"화면 {img.width}x{img.height} · 밝기 {ret['밝기']} · 직전 대비 바뀐 칸 {len(ret['바뀐칸'])}/144 · "
                 f"읽는 데 {time.time() - t0:.1f}초"]
        if new_l:
            lines.append("새로 보임: " + " | ".join(new_l))
        if gone:
            lines.append("사라짐: " + " | ".join(gone))
        for w in wins:
            lines.append(f"\n창 \"{w['title'][:60]}\" ({w['app']}, {w['x']},{w['y']} {w['w']}x{w['h']}"
                         f"{', 포커스' if w['focused'] else ''})")
            row_y, row = None, []
            for e in (e for e in elements if e["win"]["id"] == w["id"]):
                y = e["box"][1] // 14
                if row_y is not None and y != row_y and row:
                    lines.append("  " + "  ".join(row))
                    row = []
                row_y = y
                row.append(_fmt(e))
            if row:
                lines.append("  " + "  ".join(row))
            if not any(e["win"]["id"] == w["id"] for e in elements):
                lines.append("  (읽을 수 있는 글자·요소가 없다 — 그림이나 영상일 수 있다. eye.look으로 눈 모델에게 물어라)")
        if gist:
            lines.append("\n눈 모델의 인상(추정): " + self.gist(ctx, img))
        return "\n".join(lines)

    def gist(self, ctx, img):
        from atanor import tools as T
        try:
            return T._vision(ctx, "이 컴퓨터 화면이 무엇을 하는 화면인지 한두 문장으로. 보이는 것만, 한국어로.",
                             _png(img.resize((1288, 728)))).strip()
        except Exception as e:  # noqa: BLE001
            return f"(실패: {e})"


def _inside(a, b):
    return a[0] >= b[0] - 3 and a[1] >= b[1] - 3 and a[0] + a[2] <= b[0] + b[2] + 3 and a[1] + a[3] <= b[1] + b[3] + 3


def _norm(s):
    return re.sub(r"[\s.…:_]+", "", str(s or "")).lower()


def _same(a, b):
    """접근성 이름과 OCR 글이 같은 것을 가리키나(OCR 오차를 조금 허용)."""
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 3 and short in long_ and len(short) / len(long_) >= 0.6


def _covered(a, boxes):
    """a 넓이 중 boxes에 덮인 비율(대략)."""
    area = max(1, a[2] * a[3])
    cov = 0
    for b in boxes:
        w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
        h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
        if w > 0 and h > 0:
            cov += w * h
    return cov / area


def _png(img):
    import io
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


def _fmt(e):
    flags = [f for f, k in (("포커스", "focused"), ("체크됨", "checked"), ("선택됨", "selected")) if e.get(k)]
    val = ""
    if e.get("value"):
        val = " = \"•••\"" if e.get("secret") else f" = \"{e['value'][:40]}\""
    kind = "" if e["kind"] == "글" else e["kind"] + " "
    return f"[{e['id']}] {kind}\"{e['label']}\"{val}" + (f"({','.join(flags)})" if flags else "")


def start(core):
    from atanor import tools as T
    eye = Eye(core)
    core.eye = eye

    def press(ctx, keys):
        return T.TOOLS["input.key"]["fn"]({"keys": keys}, ctx)

    def click_at(ctx, x, y, button="left", count=1):
        return T.TOOLS["mouse.click"]["fn"]({"x": int(x), "y": int(y), "button": button, "count": count}, ctx)

    @T.tool("eye.see", "눈으로 화면을 본다: 보이는 창들, 그 안의 글자와 버튼·입력칸을 [번호]가 붙은 줄 단위 장면으로 준다. "
            "새로 나타난 것·사라진 것도 알려 준다. 화면 조작 전에 먼저 부른다. scope: screen(기본)|focused, gist: true면 눈 모델의 한 줄 인상도.",
            {"scope": {"type": "string"}, "gist": {"type": "boolean"}})
    def eye_see(a, ctx):
        return eye.see(ctx, a.get("scope") or "screen", bool(a.get("gist")))

    @T.tool("eye.act", "eye.see의 [번호] 요소에 행동하고, 바뀐 화면을 다시 본다. action: click|double|right|hover|type. "
            "type이면 그 칸을 눌러 기존 글을 지우고 text를 쓴다(enter=true면 Enter까지).",
            {"id": {"type": "integer"}, "action": {"type": "string"}, "text": {"type": "string"}, "enter": {"type": "boolean"}},
            risk="write", required=["id"])
    def eye_act(a, ctx):
        e = eye.scene["elements"].get(int(a["id"]))
        if not e:
            return "그 번호는 지금 장면에 없다. eye.see를 다시 불러라."
        x, y, w, h = e["box"]
        cx, cy = x + w // 2, y + h // 2
        act = (a.get("action") or "click").lower()
        if act in ("click", "double", "right"):
            click_at(ctx, cx, cy, "right" if act == "right" else "left", 2 if act == "double" else 1)
        elif act == "hover":
            T.TOOLS["mouse.move"]["fn"]({"x": cx, "y": cy}, ctx)
        elif act == "type":
            click_at(ctx, cx, cy)
            time.sleep(0.15)
            press(ctx, "ctrl+a BackSpace")
            T.TOOLS["input.type"]["fn"]({"text": a.get("text", "")}, ctx)
            if a.get("enter"):
                press(ctx, "Return")
        else:
            return f"모르는 action: {act}"
        time.sleep(0.9)
        return f"{act} → [{e['id']}] \"{e['label']}\"\n\n" + eye.see(ctx)

    @T.tool("eye.look", "장면의 글만으로 모를 때(그림·아이콘·색·모양) 눈 모델에게 화면이나 [번호] 요소 주변을 보여 주고 묻는다.",
            {"question": {"type": "string"}, "id": {"type": "integer"}}, required=["question"])
    def eye_look(a, ctx):
        from PIL import Image
        T.run(["grim", "/tmp/atanor-eye.png"], env=T.need_gui(ctx))
        img = Image.open("/tmp/atanor-eye.png").convert("RGB")
        e = eye.scene["elements"].get(int(a["id"])) if a.get("id") else None
        if e:
            x, y, w, h = e["box"]
            pad = max(w, h, 80)
            img = img.crop((max(0, x - pad), max(0, y - pad), x + w + pad, y + h + pad))
            img.thumbnail((1288, 728))
        else:
            img = img.resize((1288, 728))
        return {"답(눈 모델 추정)": T._vision(ctx, f"보이는 것만 말하고 지어내지 마라. 한국어로.\n질문: {a['question']}", _png(img)).strip()}

    # ───────── mistral이 눈으로 보며 스스로 조작하는 루프 ─────────
    PLAN = {"type": "object", "properties": {
        "지금_상태": {"type": "string"}, "목표_달성": {"type": "boolean"},
        "생각": {"type": "string"},
        "행동": {"type": "string", "enum": ["click", "double", "right", "type", "key", "scroll", "open", "find", "wait", "done", "fail"]},
        "번호": {"type": "integer"}, "글": {"type": "string"}, "엔터": {"type": "boolean"}, "키": {"type": "string"},
        "방향": {"type": "string"}, "대상": {"type": "string"}, "답": {"type": "string"}},
        "required": ["지금_상태", "목표_달성", "생각", "행동", "번호", "글", "엔터", "키", "방향", "대상", "답"]}
    TASK = """너는 ATANOR의 손이다. 눈(eye)이 읽어 준 장면을 보고 목표를 이루기 위한 다음 행동 하나만 고른다.
목표: {goal}

지금까지 한 일:
{hist}

지금 장면:
{scene}

행동:
- click/double/right {{번호}}: 그 요소를 누른다. 폴더·파일을 여는 건 double.
- type {{번호, 글, 엔터}}: 그 칸에 글을 쓴다(엔터 true면 Enter까지).
- key {{키}}: 단축키. 예 "ctrl+l", "Return", "Escape", "alt+F4", "ctrl+a BackSpace".
- scroll {{방향: up|down, 번호(선택)}}
- open {{대상}}: 앱 실행(예 "pcmanfm ~/notes", "foot").
- find {{대상}}: 장면 글에 없는 것(아이콘·그림)을 눈 모델로 찾아 클릭 가능한 번호를 만든다.
- wait: 화면이 바뀌길 기다린다.
- done {{답}}: 목표를 이뤘다. 장면에서 확인한 결과를 한국어로 답한다. fail {{답}}: 불가능한 이유.
먼저 목표가 이미 이뤄졌는지 장면에서 확인한다. 이뤄졌으면 다른 행동 없이 바로 done으로, 장면에 보이는 결과를 답에 쓴다.
(예: 폴더를 열라는 목표라면 창 제목이 그 폴더 경로가 되었는지 본다.)
모든 칸을 채워 JSON으로 답한다. 쓰지 않는 칸은 번호 0, 글자는 "", 엔터 false.
지금_상태: 장면(특히 포커스된 창 제목과 내용)이 지금 무엇을 보여 주는지 한 문장. 목표_달성: 목표가 이미 이뤄졌으면 true(그러면 행동은 done).
예: {{"지금_상태": "파일 관리자가 / 폴더를 보여 준다", "목표_달성": false, "생각": "홈 폴더로 가려면 왼쪽 Home Folder를 연다", "행동": "double", "번호": 12, "글": "", "엔터": false, "키": "", "방향": "", "대상": "", "답": ""}}
규칙: 장면에 있는 번호만 쓴다. 같은 행동이 효과가 없었으면 다른 방법을 쓴다. 지어내지 않는다."""

    EXPECT = {"type": "object", "properties": {
        "창제목에": {"type": "array", "items": {"type": "string"}},
        "장면에": {"type": "array", "items": {"type": "string"}}}, "required": ["창제목에", "장면에"]}

    def expectations(goal):
        """시작할 때 한 번: 목표가 이뤄지면 화면에 '글자 그대로' 보여야 할 것을 정해 둔다(끝 판정의 잣대)."""
        q = (f"목표: {goal}\n\n이 목표가 이뤄졌을 때 화면에 글자 그대로 보일 짧은 낱말을 정하라.\n"
             "창제목에: 그때 포커스된 창 제목에 들어 있을 낱말(예: 폴더를 여는 목표면 그 폴더 이름). 확실하지 않으면 비운다.\n"
             "장면에: 그때 창 안에 보일 낱말(확실한 것만, 없으면 비운다). 목표 문장을 통째로 쓰지 말고 1~2 낱말만.")
        try:
            r = json.loads(core.brain.chat([{"role": "user", "content": q}], schema=EXPECT, temperature=0))
            clean = lambda xs: [str(x).strip() for x in xs if str(x).strip()][:3]  # noqa: E731
            return {"창제목에": clean(r.get("창제목에", [])), "장면에": clean(r.get("장면에", []))}
        except Exception:  # noqa: BLE001
            return {"창제목에": [], "장면에": []}

    def verify(exp, scene):
        """끝났다는 주장을 측정으로 확인한다: 정해 둔 낱말이 화면에 실제로 있어야 끝이다."""
        title = re.search(r'창 "([^"]*)"[^\n]*포커스', scene)
        title = title.group(1) if title else ""
        miss = [f"창 제목에 '{w}'가 없다(지금 '{title}')" for w in exp["창제목에"] if w.lower() not in title.lower()]
        miss += [f"장면에 '{w}'가 보이지 않는다" for w in exp["장면에"] if w.lower() not in scene.lower()]
        return (not miss), ("; ".join(miss) or f"확인됨 — 창 '{title}'" + (f", 장면에 {exp['장면에']}" if exp["장면에"] else ""))

    @T.tool("computer.task", "눈(eye)으로 화면을 읽으며 목표를 끝까지 해낸다(사람처럼 보고 누르고 쓴다). 여러 단계 GUI 작업용. "
            "예: '파일 관리자에서 notes 폴더를 열어 안에 뭐가 있는지 알려줘'. workspace: 작업 화면(기본 2). 웹은 browser.*가 더 빠르다.",
            {"goal": {"type": "string"}, "max_steps": {"type": "integer"}, "workspace": {"type": "string"}},
            risk="write", required=["goal"])
    def computer_task(a, ctx):
        goal, steps = a["goal"], max(1, min(25, int(a.get("max_steps") or 16)))
        T.swaymsg(ctx, "workspace", str(a.get("workspace") or "2"))
        time.sleep(0.5)
        hist, scene = [], eye.see(ctx)
        extra = {}
        exp = expectations(goal)
        ctx.emit("inner_step", {"tool": "eye.expect", "text": f"끝나면 보일 것: {exp}"})

        def finish(r):
            T.swaymsg(ctx, "workspace", "1")
            return r

        for i in range(steps):
            raw = ctx.brain.chat([{"role": "user", "content": TASK.format(goal=goal, hist="\n".join(hist[-10:]) or "(없음)",
                                                                           scene=scene[:6000])}], schema=PLAN, temperature=0.2)
            try:
                j = json.loads(raw)
            except ValueError:
                hist.append(f"{i + 1}. (답을 읽지 못함)")
                continue
            act = j.get("행동")
            ctx.emit("inner_step", {"tool": f"eye.{act}", "text": str(j.get("생각", ""))[:160]})
            if j.get("목표_달성") and act not in ("fail",):
                act = "done"
            if act == "done":
                ok, why = verify(exp, scene)
                if ok:
                    return finish({"결과": "완료", "답": j.get("답", ""), "근거": why, "기준": exp, "단계": hist})
                hist.append(f"{i + 1}. done이라 했지만 아직 아니다: {why[:160]}")
                continue
            if act == "fail":
                return finish({"결과": "실패", "이유": j.get("답", ""), "단계": hist})
            note = ""
            try:
                if act in ("click", "double", "right", "type"):
                    num = j.get("번호") or (int(re.sub(r"\D", "", str(j.get("대상"))) or 0) if re.search(r"\d", str(j.get("대상"))) else 0)
                    e = eye.scene["elements"].get(int(num)) or extra.get(int(num))
                    if not e:
                        note = f" {num}번 → 그런 번호는 지금 장면에 없다. 장면의 번호만 쓴다"
                    else:
                        x, y, w, h = e["box"]
                        if act == "type":
                            click_at(ctx, x + w // 2, y + h // 2)
                            time.sleep(0.15)
                            press(ctx, "ctrl+a BackSpace")
                            T.TOOLS["input.type"]["fn"]({"text": j.get("글", "")}, ctx)
                            if j.get("엔터"):
                                press(ctx, "Return")
                        else:
                            click_at(ctx, x + w // 2, y + h // 2, "right" if act == "right" else "left", 2 if act == "double" else 1)
                        note = f" [{e['id']}] \"{e['label'][:30]}\""
                elif act == "key":
                    press(ctx, j.get("키") or "Return")
                    note = f" {j.get('키')}"
                elif act == "scroll":
                    e = eye.scene["elements"].get(int(j.get("번호") or -1))
                    args = {"direction": j.get("방향") or "down", "amount": 5}
                    if e:
                        args.update(x=e["box"][0] + e["box"][2] // 2, y=e["box"][1] + e["box"][3] // 2)
                    T.TOOLS["mouse.scroll"]["fn"](args, ctx)
                elif act == "open":
                    T.TOOLS["app.open"]["fn"]({"app": j.get("대상") or "pcmanfm"}, ctx)
                    time.sleep(1.5)
                    note = f" {j.get('대상')}"
                elif act == "find":
                    r = T.TOOLS["screen.find"]["fn"]({"target": j.get("대상", "")}, ctx)
                    if isinstance(r, dict):
                        nid = 900 + len(extra)
                        b = r["box"]
                        extra[nid] = {"id": nid, "label": j.get("대상", ""), "box": [b[0], b[1], b[2] - b[0], b[3] - b[1]]}
                        note = f" → 찾음: [{nid}] \"{j.get('대상')}\" (눈 모델 추정 위치)"
                    else:
                        note = " → 못 찾음"
                elif act == "wait":
                    time.sleep(2)
            except Exception as e:  # noqa: BLE001
                note = f" → 오류: {e}"
            time.sleep(0.8)
            scene = eye.see(ctx)
            moved = scene.split("\n", 1)[0]
            changed = re.search(r"바뀐 칸 (\d+)", moved)
            title = re.search(r'창 "([^"]*)"[^\n]*포커스', scene)
            hist.append(f"{i + 1}. {act}{note} — " + ("화면이 바뀌었다" if changed and changed.group(1) != "0" else "화면이 그대로다(효과 없음)")
                        + (f", 지금 창: \"{title.group(1)}\"" if title else ""))
            if len(hist) >= 2 and all("효과 없음" in h for h in hist[-2:]):
                hist.append("   ※ 효과 없는 행동을 되풀이하고 있다. 목표가 이미 이뤄졌는지 장면을 다시 보고, 그렇다면 done으로 답하라.")
            if extra:
                scene += "\n눈 모델이 찾은 것: " + "  ".join(f"[{k}] \"{v['label']}\"" for k, v in extra.items())
        return finish({"결과": f"{steps}단계 안에 끝내지 못함", "단계": hist})
