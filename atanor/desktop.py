"""ATANOR 데스크톱 조작 — 화면을 보고 마우스·키보드로 무엇이든 다룬다 (Claude의 computer use와 같은 일).

세 가지 길을 함께 쓴다. 정확한 길부터:
1. 접근성 트리(AT-SPI): GTK·Qt 앱의 버튼·입력칸을 이름과 번호로 받아, 좌표 없이 직접 누르고 글을 넣는다.
2. 눈 모델(qwen2.5vl) 위치 찾기: "저장 버튼"처럼 말하면 화면 좌표를 찾아 준다.
3. 원시 입력: sway의 가상 커서(seat cursor)로 이동·클릭·드래그·스크롤, wtype으로 글자·단축키.
여러 단계 작업(computer.task)은 eye.py에 있다 — 눈이 읽은 장면을 보고 두뇌가 조작한다.

좌표는 언제나 실제 화면 픽셀(예: 1920x1080, 왼쪽 위가 0,0)이다.
"""
import base64
import io
import json
import os
import re
import subprocess
import time
import urllib.request

GW, GH = 1288, 728          # 눈 모델에 보내는 그림 크기(28의 배수 → 모델이 다시 줄이지 않아 좌표가 정확하다)
HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "atspi_helper.py")
BTN = {"left": "BTN_LEFT", "right": "BTN_RIGHT", "middle": "BTN_MIDDLE"}


def start(core):
    from atanor import tools as T

    def sway(ctx, *cmd):
        return T.swaymsg(ctx, *cmd)

    def screen_size(ctx):
        outs = json.loads(T.swaymsg(ctx, "-t", "get_outputs"))
        o = next((o for o in outs if o.get("focused")), outs[0])
        return o["rect"]["width"], o["rect"]["height"]

    def capture(ctx):
        from PIL import Image
        path = "/tmp/atanor-screen.png"
        code, _, err = T.run(["grim", path], env=T.need_gui(ctx))
        if code != 0:
            raise RuntimeError(err)
        return Image.open(path).convert("RGB")

    def vision(ctx, prompt, img, temperature=0.0):
        v = ctx.cfg.get("vision") or {}
        b = io.BytesIO()
        img.save(b, "PNG")
        body = {"model": v.get("model", "qwen2.5vl:7b"), "stream": False, "options": {"temperature": temperature},
                "messages": [{"role": "user", "content": prompt, "images": [base64.b64encode(b.getvalue()).decode()]}]}
        req = urllib.request.Request(v.get("url", "http://127.0.0.1:11434").rstrip("/") + "/api/chat",
                                     data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())["message"]["content"]

    def first_json(text):
        m = re.search(r"(\[.*\]|\{.*\})", text, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except ValueError:
            return None

    def to_screen(ctx, x, y, size=None):
        W, H = size or screen_size(ctx)
        return round(x * W / GW), round(y * H / GH)

    # ───────── 원시 입력 ─────────
    def move(ctx, x, y):
        sway(ctx, "seat", "-", "cursor", "set", str(int(x)), str(int(y)))

    def click(ctx, x, y, button="left", count=1):
        move(ctx, x, y)
        time.sleep(0.05)
        b = BTN.get(button, "BTN_LEFT")
        for _ in range(max(1, min(3, int(count)))):
            sway(ctx, "seat", "-", "cursor", "press", b)
            time.sleep(0.03)
            sway(ctx, "seat", "-", "cursor", "release", b)
            time.sleep(0.06)

    def scroll(ctx, x, y, direction="down", amount=3):
        move(ctx, x, y)
        b = {"up": "button4", "down": "button5", "left": "button6", "right": "button7"}.get(direction, "button5")
        for _ in range(max(1, min(30, int(amount)))):
            sway(ctx, "seat", "-", "cursor", "press", b)
            sway(ctx, "seat", "-", "cursor", "release", b)
            time.sleep(0.03)

    def drag(ctx, x1, y1, x2, y2):
        move(ctx, x1, y1)
        sway(ctx, "seat", "-", "cursor", "press", "BTN_LEFT")
        for i in range(1, 11):
            move(ctx, x1 + (x2 - x1) * i / 10, y1 + (y2 - y1) * i / 10)
            time.sleep(0.02)
        sway(ctx, "seat", "-", "cursor", "release", "BTN_LEFT")

    def type_text(ctx, text):
        code, _, err = T.run(["wtype", "-d", "8", text], env=T.need_gui(ctx), timeout=120)
        if code != 0:
            raise RuntimeError(err)

    # 단축키·특수키는 커널 가상 키보드(uinput)로 보낸다 — 진짜 키보드처럼 모든 앱에 닿는다.
    # (이 sway에서는 wtype의 키 누름이 버려진다. 글자 입력은 wtype이 잘 된다.)
    KB = {}
    ALIAS = {"return": "ENTER", "enter": "ENTER", "esc": "ESC", "escape": "ESC", "backspace": "BACKSPACE", "del": "DELETE",
             "delete": "DELETE", "pageup": "PAGEUP", "page_up": "PAGEUP", "pagedown": "PAGEDOWN", "page_down": "PAGEDOWN",
             "ctrl": "LEFTCTRL", "control": "LEFTCTRL", "alt": "LEFTALT", "altgr": "RIGHTALT", "shift": "LEFTSHIFT",
             "super": "LEFTMETA", "win": "LEFTMETA", "meta": "LEFTMETA", "logo": "LEFTMETA", "ins": "INSERT",
             "hangul": "HANGEUL", "hanja": "HANJA", "printscreen": "SYSRQ", "print": "SYSRQ", "menu": "COMPOSE",
             "-": "MINUS", "=": "EQUAL", "[": "LEFTBRACE", "]": "RIGHTBRACE", ";": "SEMICOLON", "'": "APOSTROPHE",
             ",": "COMMA", ".": "DOT", "/": "SLASH", "\\": "BACKSLASH", "`": "GRAVE"}

    def keyboard():
        if "dev" not in KB:
            from evdev import UInput, ecodes as e
            keys = [v for k, v in e.ecodes.items() if k.startswith("KEY_") and isinstance(v, int) and v < 0x2ff]
            KB["dev"], KB["e"] = UInput({e.EV_KEY: keys}, name="atanor-keyboard"), e
            time.sleep(0.4)  # 새 장치를 sway가 알아챌 시간
        return KB["dev"], KB["e"]

    def keycode(e, name):
        n = ALIAS.get(name.lower(), name.upper())
        code = getattr(e, f"KEY_{n}", None)
        if code is None:
            raise ValueError(f"모르는 키: {name}")
        return code

    def press_keys(ctx, keys):
        dev, e = keyboard()
        for combo in str(keys).split():
            codes = [keycode(e, p) for p in (combo.split("+") if combo != "+" else ["+"]) if p]
            for c in codes:
                dev.write(e.EV_KEY, c, 1)
                dev.syn()
                time.sleep(0.02)
            for c in reversed(codes):
                dev.write(e.EV_KEY, c, 0)
                dev.syn()
                time.sleep(0.02)
            time.sleep(0.05)

    @T.tool("input.key", "키를 누른다(진짜 키보드처럼). 예: 'Return', 'ctrl+s', 'alt+Tab', 'ctrl+l', 'Escape'. "
            "공백으로 나누면 차례로 누른다: 'ctrl+a BackSpace'.", {"keys": {"type": "string"}}, risk="write", required=["keys"])
    def input_key(a, ctx):
        press_keys(ctx, a["keys"])
        return f"눌렀다: {a['keys']}"

    # ───────── 눈 모델로 위치 찾기 ─────────
    def locate(ctx, target, img=None):
        img = img or capture(ctx)
        W, H = img.size
        small = img.resize((GW, GH))
        out = vision(ctx, f'Locate "{target}" in this computer screenshot. If it is not visible, output []. '
                          'Otherwise output its bbox coordinates using JSON format: [{"bbox_2d": [x1, y1, x2, y2], "label": "..."}]', small)
        j = first_json(out)
        if isinstance(j, dict):
            j = [j]
        if not j or not isinstance(j, list) or "bbox_2d" not in j[0]:
            return None
        x1, y1, x2, y2 = j[0]["bbox_2d"]
        (sx1, sy1), (sx2, sy2) = to_screen(ctx, x1, y1, (W, H)), to_screen(ctx, x2, y2, (W, H))
        return {"x": (sx1 + sx2) // 2, "y": (sy1 + sy2) // 2, "box": [sx1, sy1, sx2, sy2], "label": j[0].get("label", target)}

    @T.tool("screen.find", "화면에서 대상(예: '저장 버튼', '주소창', '빨간 경고창의 확인')을 눈으로 찾아 화면 좌표 {x,y,box}를 돌려준다. "
            "찾지 못하면 그렇게 말한다.", {"target": {"type": "string"}}, required=["target"])
    def screen_find(a, ctx):
        r = locate(ctx, a["target"])
        return r or f"화면에서 '{a['target']}'을(를) 찾지 못했다."

    @T.tool("screen.click", "화면에서 대상을 눈으로 찾아 바로 누른다. button: left|right|middle, count: 2면 더블클릭.",
            {"target": {"type": "string"}, "button": {"type": "string"}, "count": {"type": "integer"}},
            risk="write", required=["target"])
    def screen_click(a, ctx):
        r = locate(ctx, a["target"])
        if not r:
            return f"화면에서 '{a['target']}'을(를) 찾지 못해 누르지 않았다."
        click(ctx, r["x"], r["y"], a.get("button", "left"), a.get("count", 1))
        return {"누름": r}

    @T.tool("screen.zoom", "화면의 한 부분(x,y,w,h 화면 픽셀)을 크게 확대해 눈 모델에게 묻는다. 작은 글씨 읽기에 쓴다.",
            {"x": {"type": "integer"}, "y": {"type": "integer"}, "w": {"type": "integer"}, "h": {"type": "integer"},
             "question": {"type": "string"}}, required=["x", "y", "w", "h"])
    def screen_zoom(a, ctx):
        img = capture(ctx)
        x, y, w, h = (int(a[k]) for k in ("x", "y", "w", "h"))
        crop = img.crop((x, y, x + max(8, w), y + max(8, h)))
        crop.thumbnail((GW, GH))
        q = a.get("question") or "여기 보이는 글자와 내용을 그대로 읽어라."
        return {"답": vision(ctx, f"보이는 것만 말하고 지어내지 마라. 한국어로 답하라.\n질문: {q}", crop).strip()}

    @T.tool("mouse.click", "화면 좌표(x,y 픽셀)를 누른다. button: left|right|middle, count: 2면 더블클릭.",
            {"x": {"type": "integer"}, "y": {"type": "integer"}, "button": {"type": "string"}, "count": {"type": "integer"}},
            risk="write", required=["x", "y"])
    def mouse_click(a, ctx):
        click(ctx, a["x"], a["y"], a.get("button", "left"), a.get("count", 1))
        return f"클릭 ({a['x']}, {a['y']})"

    @T.tool("mouse.move", "마우스 포인터를 화면 좌표로 옮긴다(메뉴 펼치기·툴팁 보기).",
            {"x": {"type": "integer"}, "y": {"type": "integer"}}, risk="write", required=["x", "y"])
    def mouse_move(a, ctx):
        move(ctx, a["x"], a["y"])
        return "이동"

    @T.tool("mouse.drag", "(x1,y1)에서 눌러 (x2,y2)까지 끌어 놓는다(파일 옮기기, 범위 선택, 슬라이더).",
            {"x1": {"type": "integer"}, "y1": {"type": "integer"}, "x2": {"type": "integer"}, "y2": {"type": "integer"}},
            risk="write", required=["x1", "y1", "x2", "y2"])
    def mouse_drag(a, ctx):
        drag(ctx, a["x1"], a["y1"], a["x2"], a["y2"])
        return "끌어 놓음"

    @T.tool("mouse.scroll", "화면 좌표 위에서 스크롤한다. direction: up|down|left|right, amount: 칸 수(기본 3).",
            {"x": {"type": "integer"}, "y": {"type": "integer"}, "direction": {"type": "string"}, "amount": {"type": "integer"}},
            risk="write", required=["direction"])
    def mouse_scroll(a, ctx):
        W, H = screen_size(ctx)
        scroll(ctx, a.get("x", W // 2), a.get("y", H // 2), a["direction"], a.get("amount", 3))
        return "스크롤"

    # ───────── 접근성 트리(AT-SPI) ─────────
    def helper(ctx, *args):
        env = T.need_gui(ctx)
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={env['XDG_RUNTIME_DIR']}/bus")
        p = subprocess.run(["python3", HELPER, *args], capture_output=True, text=True, timeout=40, env=env)
        try:
            return json.loads(p.stdout)
        except ValueError:
            return {"error": (p.stderr or p.stdout)[-500:]}

    @T.tool("desktop.elements", "앱 창 속 버튼·입력칸·메뉴 같은 요소를 접근성 정보로 읽어 [번호] 목록으로 준다(GTK·Qt 앱). "
            "app을 비우면 포커스된 앱. 좌표 없이 desktop.act로 정확히 누를 수 있다. 목록이 비면 screen.find를 쓴다.",
            {"app": {"type": "string"}})
    def desktop_elements(a, ctx):
        return helper(ctx, "list", a.get("app") or "")

    @T.tool("desktop.act", "desktop.elements의 요소 번호(id)에 행동한다. action: click|focus|set_text. set_text면 text를 넣는다.",
            {"id": {"type": "string"}, "action": {"type": "string"}, "text": {"type": "string"}, "app": {"type": "string"}},
            risk="write", required=["id"])
    def desktop_act(a, ctx):
        return helper(ctx, "act", a.get("app") or "", str(a["id"]), a.get("action", "click"), a.get("text", ""))

    # ── 창 지킴이: 앱 창이 닫혀 그 작업 공간이 비면 ATANOR 화면(작업 공간 1)으로 돌아온다 ──
    # (앱은 작업 공간 2에 열린다. 그 창을 닫으면 빈 작업 공간의 검은 바탕만 남았다.)
    import threading

    def empty_focused_ws():
        """(지금 보이는 작업 공간 이름, 창이 하나도 없는가)"""
        wss = json.loads(T.swaymsg(None, "-t", "get_workspaces"))
        name = next((w["name"] for w in wss if w.get("focused")), None)
        tree = json.loads(T.swaymsg(None, "-t", "get_tree"))
        count = [0]

        def walk(n, ws=None):
            if n.get("type") == "workspace":
                ws = n.get("name")
            if n.get("pid") and ws == name:
                count[0] += 1
            for c in n.get("nodes", []) + n.get("floating_nodes", []):
                walk(c, ws)
        walk(tree)
        return name, count[0] == 0

    def watch_windows():
        while True:
            env = T.wl_env(None)
            if not env or "SWAYSOCK" not in env:
                time.sleep(5)
                continue
            try:
                p = subprocess.Popen(["swaymsg", "-t", "subscribe", "-m", '["window"]'], env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                for line in p.stdout:
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if ev.get("change") != "close":
                        continue
                    time.sleep(0.3)          # sway가 포커스를 옮길 틈
                    ws = empty_focused_ws()
                    if ws and ws[0] != "1" and ws[1]:
                        T.swaymsg(None, "workspace", "1")
                p.wait()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(3)

    threading.Thread(target=watch_windows, daemon=True, name="window-keeper").start()
