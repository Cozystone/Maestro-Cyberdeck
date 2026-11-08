"""AT-SPI(접근성) 도우미 — 별도 프로세스로 돌아 Core를 멈추게 하지 않는다.

python3 atspi_helper.py list [앱이름]
python3 atspi_helper.py act  [앱이름] <id> click|focus|set_text [text]
id는 앱 안에서의 자식 번호 경로(예: "0.2.5")라서 호출 사이에 상태를 들고 있을 필요가 없다.
"""
import json
import sys

import pyatspi

ROLES = {"push button", "toggle button", "check box", "radio button", "menu item", "menu", "check menu item",
         "radio menu item", "text", "entry", "password text", "combo box", "list item", "table cell", "page tab",
         "link", "icon", "spin button", "slider", "tree item", "terminal", "document text", "paragraph"}


def apps():
    d = pyatspi.Registry.getDesktop(0)
    return [d.getChildAtIndex(i) for i in range(d.childCount) if d.getChildAtIndex(i) is not None]


def is_active(app):
    for i in range(app.childCount):
        w = app.getChildAtIndex(i)
        try:
            if w is not None and w.getState().contains(pyatspi.STATE_ACTIVE):
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


def pick(name):
    al = apps()
    if name:
        for a in al:
            if name.lower() in (a.name or "").lower():
                return a
        return None
    act = [a for a in al if is_active(a)]
    return act[0] if act else None


def walk(node, path, out, depth=0):
    if node is None or depth > 30 or len(out) >= 200:
        return
    try:
        role, st = node.getRoleName(), node.getState()
    except Exception:  # noqa: BLE001
        return
    if not st.contains(pyatspi.STATE_SHOWING) and depth > 1:
        return
    if role in ROLES:
        name = (node.name or "").strip()
        val = ""
        try:
            if role in ("text", "entry", "password text", "document text", "paragraph", "terminal"):
                t = node.queryText()
                val = t.getText(0, min(80, t.characterCount)) if role != "password text" else "•••"
        except Exception:  # noqa: BLE001
            pass
        flags = [f for f, s in (("포커스", pyatspi.STATE_FOCUSED), ("선택됨", pyatspi.STATE_SELECTED),
                                ("체크됨", pyatspi.STATE_CHECKED)) if st.contains(s)]
        if name or val or role in ("text", "entry", "password text"):
            out.append(f"[{'.'.join(map(str, path))}] {role} \"{name[:60]}\"" + (f" = {val!r}" if val else "")
                       + (f" ({', '.join(flags)})" if flags else ""))
    for i in range(min(node.childCount, 400)):
        walk(node.getChildAtIndex(i), path + [i], out, depth + 1)


def resolve(app, ident):
    node = app
    for k in ident.split("."):
        node = node.getChildAtIndex(int(k))
        if node is None:
            raise LookupError("요소가 사라졌다. desktop.elements를 다시 불러라.")
    return node


def scan(pids):
    """눈(eye.py)용: 주어진 프로세스들의 보이는 요소를 창 기준 좌표와 함께 돌려준다."""
    out = []
    for ai, app in enumerate(apps()):
        try:
            pid = app.get_process_id()
        except Exception:  # noqa: BLE001
            continue
        if pids and pid not in pids:
            continue

        def walk_geo(node, path, depth=0):
            if node is None or depth > 30 or len(out) >= 400:
                return
            try:
                role, st = node.getRoleName(), node.getState()
            except Exception:  # noqa: BLE001
                return
            if depth > 1 and not st.contains(pyatspi.STATE_SHOWING):
                return
            if role in ROLES:
                try:
                    x, y, w, h = node.queryComponent().getExtents(pyatspi.WINDOW_COORDS)
                except Exception:  # noqa: BLE001
                    x = y = w = h = -1
                if w > 2 and h > 2 and x > -10000:
                    val = ""
                    try:
                        if role in ("text", "entry", "document text", "terminal"):
                            t = node.queryText()
                            val = t.getText(0, min(80, t.characterCount))
                        elif role == "password text":
                            val = "•••"
                    except Exception:  # noqa: BLE001
                        pass
                    out.append({"pid": pid, "path": ".".join(map(str, path)), "role": role, "name": (node.name or "").strip()[:80],
                                "value": val, "box": [x, y, w, h], "focused": st.contains(pyatspi.STATE_FOCUSED),
                                "checked": st.contains(pyatspi.STATE_CHECKED), "selected": st.contains(pyatspi.STATE_SELECTED)})
            for i in range(min(node.childCount, 400)):
                walk_geo(node.getChildAtIndex(i), path + [i], depth + 1)

        for i in range(app.childCount):
            walk_geo(app.getChildAtIndex(i), [i])
    return out


def act_pid(pid, ident, action, text):
    for app in apps():
        try:
            if app.get_process_id() == pid:
                return act_node(resolve(app, ident), action, text)
        except LookupError:
            raise
        except Exception:  # noqa: BLE001
            continue
    raise LookupError("앱을 찾지 못했다.")


def act_node(node, action, text):
    if action == "set_text":
        node.queryEditableText().setTextContents(text)
        return "글 넣음"
    if action == "focus":
        node.queryComponent().grabFocus()
        return "포커스"
    ac = node.queryAction()
    names = [ac.getName(i) for i in range(ac.nActions)]
    idx = next((i for i, n in enumerate(names) if n in ("click", "press", "activate", "toggle", "jump")), 0)
    ac.doAction(idx)
    return f"{names[idx] if names else 'action'} 실행"


def main():
    if sys.argv[1] == "scan":
        print(json.dumps(scan({int(p) for p in sys.argv[2:] if p.isdigit()}), ensure_ascii=False))
        return
    if sys.argv[1] == "actpid":
        print(json.dumps({"결과": act_pid(int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5] if len(sys.argv) > 5 else "")},
                         ensure_ascii=False))
        return
    cmd, name = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""
    app = pick(name)
    if app is None:
        names = [a.name for a in apps()]
        print(json.dumps({"error": "접근성 정보를 주는 앱을 찾지 못했다.", "앱들": names}, ensure_ascii=False))
        return
    if cmd == "list":
        out = []
        for i in range(app.childCount):
            walk(app.getChildAtIndex(i), [i], out)
        print(json.dumps({"앱": app.name, "요소": out or ["(읽을 수 있는 요소가 없다 — screen.find를 써라)"]}, ensure_ascii=False))
        return
    ident, action, text = sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "click", sys.argv[5] if len(sys.argv) > 5 else ""
    node = resolve(app, ident)
    if action == "set_text":
        node.queryEditableText().setTextContents(text)
        res = "글 넣음"
    elif action == "focus":
        node.queryComponent().grabFocus()
        res = "포커스"
    else:
        ac = node.queryAction()
        names = [ac.getName(i) for i in range(ac.nActions)]
        idx = next((i for i, n in enumerate(names) if n in ("click", "press", "activate", "toggle", "jump")), 0)
        ac.doAction(idx)
        res = f"{names[idx] if names else 'action'} 실행"
    print(json.dumps({"결과": res, "대상": f"{node.getRoleName()} \"{node.name}\""}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
