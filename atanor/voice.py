"""ATANOR 목소리 — 듣고(음성 인식), 말하고(음성 합성), 간단한 말은 두뇌를 거치지 않고 바로 한다.

- 듣기: 화면이 마이크 소리를 16kHz 날 PCM으로 보내면, 터널 너머 PC 문지기(/atanor/stt, whisper)가 글자로 바꾼다.
- 말하기: edge-tts(마이크로소프트 신경망 음성)로 답을 mp3로 만들어 화면이 재생한다. 답 글자만 나간다.
- 즉답: 시간·날짜·배터리·음량·밝기·앱 닫기·타이머처럼 뻔한 말은 정해진 도구를 바로 불러 1초 안에 답한다.
  애매하면 손대지 않고 두뇌에게 넘긴다(None).
"""
import asyncio
import datetime as dt
import glob
import hashlib
import json
import os
import re
import time
import urllib.request

from atanor import tools as T

TTS_DIR = os.path.expanduser("~/.atanor/tts")
VOICES = {"남성": "ko-KR-InJoonNeural", "여성": "ko-KR-SunHiNeural", "male": "ko-KR-InJoonNeural",
          "female": "ko-KR-SunHiNeural"}
WAKE = re.compile(r"^\s*(아시[긴진]트|아식[긴진]트|asigint|아[타다따][노놀][르를]?|아탄오르|자비스|jarvis|atanor|아타노)[\s,.!?~야아]*", re.I)
FIX = re.compile(r"(알려|틀어|줄여|올려|키워|꺼|켜|해|봐|보여|닫아|열어|적어|찾아|읽어|띄워|바꿔|낮춰|높여|깨워|맞춰|멈춰)져(?=[.!?\s]*$)")


# ───────── 듣기 ─────────
def stt(core, pcm):
    url = core.cfg["brain"]["url"].rstrip("/") + "/atanor/stt"
    req = urllib.request.Request(url, data=pcm, method="POST", headers={"Content-Type": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=60) as r:
        text = json.loads(r.read()).get("text", "")
    return FIX.sub(r"\1줘", text.strip())


def strip_wake(text):
    """깨우는 말('아타노르', '자비스')로 시작하면 (True, 나머지), 아니면 (False, 원문)."""
    m = WAKE.match(text)
    return (True, text[m.end():].strip()) if m else (False, text)


# ───────── 말하기 ─────────
def tts(core, text):
    import edge_tts  # noqa: WPS433
    text = re.sub(r"[*`#>|]", "", text)
    text = re.sub(r"https?://\S+", "링크", text)[:700].strip()
    if not text:
        return b""
    voice = core.ui_state["theme"].get("voice") or VOICES["남성"]
    os.makedirs(TTS_DIR, exist_ok=True)
    f = os.path.join(TTS_DIR, hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()[:20] + ".mp3")
    if not os.path.exists(f):
        asyncio.run(edge_tts.Communicate(text, voice, rate="+8%").save(f + ".part"))
        os.replace(f + ".part", f)
        old = sorted(glob.glob(os.path.join(TTS_DIR, "*.mp3")), key=os.path.getmtime)
        for x in old[:-300]:   # 캐시는 최근 300개만
            os.remove(x)
    with open(f, "rb") as fh:
        return fh.read()


def warm(core):
    """자주 쓰는 짧은 답은 미리 만들어 둔다 — 이름을 부르면 '네?'가 바로 나와야 이어지는 말을 놓치지 않는다."""
    import threading  # noqa: WPS433

    def go():
        for t in ("네?", "천만에요.", "중단했어요."):
            try:
                tts(core, t)
            except Exception:  # noqa: BLE001  인터넷이 없으면 다음에
                return
    threading.Thread(target=go, daemon=True).start()


@T.tool("voice.set", "목소리 설정. speak: 답을 소리 내어 말할지(true/false) | wake: 항상 듣다가 '아타노르'라고 부르면 "
        "대답할지(true/false) | voice: 남성|여성. 주인이 말한 항목만 넣는다.",
        {"speak": {"type": "boolean"}, "wake": {"type": "boolean"}, "voice": {"type": "string"}}, risk="write")
def voice_set(a, ctx):
    th, done = ctx.ui_state["theme"], []
    for k, label in (("speak", "말하기"), ("wake", "항상 듣기")):
        if isinstance(a.get(k), bool):
            th[k] = a[k]
            done.append(f"{label} {'켬' if a[k] else '끔'}")
    if a.get("voice"):
        v = VOICES.get(str(a["voice"]).lower(), a["voice"])
        if v not in VOICES.values():
            raise ValueError("voice는 남성 또는 여성")
        th["voice"] = v
        done.append(f"목소리 {a['voice']}")
    if not done:
        return "바꿀 것이 없다(speak/wake/voice)."
    ctx.save_ui()
    ctx.emit("ui", ctx.ui_state)
    return "목소리: " + ", ".join(done)


# ───────── 브리핑 ─────────
def _battery():
    for b in glob.glob("/sys/class/power_supply/BAT*"):
        try:
            cap = int(open(f"{b}/capacity").read())
            st = open(f"{b}/status").read().strip()
            return cap, st
        except (OSError, ValueError):
            pass
    return None, ""


def _hm(t=None):
    t = t or dt.datetime.now()
    return f"{'오전' if t.hour < 12 else '오후'} {t.hour % 12 or 12}시 {t.minute}분"


def _eun(word):
    """받침이 있으면 '은', 없으면 '는'."""
    c = word[-1] if word else ""
    return "은" if "가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 else "는"


def _weather_line(core, place=None, tomorrow=False):
    place = place or core.cfg.get("home_city", "서울")
    r = core.call_tool("weather.get", {"place": place, "days": 2 if tomorrow else 1}, source="quick")
    if not r["ok"] or not isinstance(r["result"], dict):
        return None
    w = r["result"]
    if tomorrow and len(w.get("예보") or []) > 1:
        fc = w["예보"][1]
        kind = fc.split(":", 1)[1].split(",")[0].strip()
        rng = re.search(r"(-?[\d.]+)~(-?[\d.]+)°C", fc)
        rain = re.search(r"비 올 확률 (\d+)%", fc)
        s = f"내일 {place}{_eun(place)} {kind}"
        if rng:
            s += f", {round(float(rng.group(1)))}도에서 {round(float(rng.group(2)))}도"
        if rain:
            s += f", 비 올 확률 {rain.group(1)}%" + ("라 우산을 챙기세요" if int(rain.group(1)) >= 40 else "")
        return s + "."
    now = w["지금"].split(",")
    fc = (w.get("예보") or [""])[0]
    rng = re.search(r"(-?[\d.]+)~(-?[\d.]+)°C", fc)
    rain = re.search(r"비 올 확률 (\d+)%", fc)
    tmp = re.search(r"(-?[\d.]+)°C", now[1])
    s = f"{place}{_eun(place)} 지금 {now[0].strip()}, {round(float(tmp.group(1))) if tmp else now[1].strip()}도"
    if rng:
        s += f", 오늘은 {round(float(rng.group(1)))}도에서 {round(float(rng.group(2)))}도"
    if rain and int(rain.group(1)) >= 40:
        s += f", 비 올 확률 {rain.group(1)}%라 우산을 챙기세요"
    return s + "."


def briefing(core):
    t = dt.datetime.now()
    hi = "좋은 아침이에요" if 4 <= t.hour < 11 else "좋은 오후예요" if t.hour < 18 else "좋은 저녁이에요"
    parts = [f"{hi}. {t.month}월 {t.day}일 {'월화수목금토일'[t.weekday()]}요일, {_hm(t)}입니다."]
    try:
        w = _weather_line(core)
        if w:
            parts.append(w)
    except Exception:  # noqa: BLE001
        pass
    todo = [x["text"] for x in T.TOOLS["todo.list"]["fn"]({}, core) if not x.get("done")]
    if todo:
        parts.append(f"할 일이 {len(todo)}개 있어요: {', '.join(todo[:4])}.")
    end = time.mktime((t.date() + dt.timedelta(days=1)).timetuple())
    rem = sorted((s for s in core.schedules if s.get("remind") and s["next"] < end
                  and not s["remind"].endswith("타이머 끝")), key=lambda s: s["next"])
    if rem:
        parts.append("오늘 알림: " + ", ".join(f"{_hm(dt.datetime.fromtimestamp(s['next']))} {s['remind']}" for s in rem[:3]) + ".")
    cap, st = _battery()
    if cap is not None and cap <= 30 and st != "Charging":
        parts.append(f"배터리가 {cap}%라 충전기를 꽂아 두세요.")
    return " ".join(parts)


# ───────── 즉답 ─────────
APPS = r"(브라우저|크롬|chrome|chromium|터미널|파일\s?관리자|메모장|편집기|유튜브)"
NUM_KO = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10,
          "십": 10, "이십": 20, "삼십": 30, "사십": 40, "오십": 50}


def _num(s):
    s = s.strip()
    return float(s) if re.fullmatch(r"\d+(\.\d+)?", s) else NUM_KO.get(s)


def _call(core, steps, name, args):
    r = core.call_tool(name, args, source="quick")
    out = r["result"] if isinstance(r["result"], str) else json.dumps(r["result"], ensure_ascii=False, default=str)
    steps.append({"tool": name, "args": args, "ok": r["ok"], "result": out[:800]})
    if not r["ok"]:
        raise RuntimeError(out)
    return r["result"]


def quick(core, text):
    """뻔한 말이면 (답, 단계들). 아니면 None — 두뇌가 맡는다."""
    s = re.sub(r"[.!?~]+$", "", text.strip())
    s = re.sub(r"\s+", " ", s)
    if not s or len(s) > 32:
        return None
    steps = []
    try:
        # 시간 · 날짜
        if re.fullmatch(r"(지금 )?(몇 ?시|시간)(야|예요|에요|지|인가요?|이야|좀 알려 ?줘|알려 ?줘)?", s):
            return f"지금 {_hm()}이에요.", steps
        if re.fullmatch(r"(오늘 )?(며칠|몇 월 며칠|날짜|무슨 요일)(이야|야|예요|에요|지|인가요?| 알려 ?줘)?", s):
            t = dt.date.today()
            return f"오늘은 {t.month}월 {t.day}일 {'월화수목금토일'[t.weekday()]}요일이에요.", steps
        # 배터리
        if re.match(r"(배터리|충전)", s) and len(s) <= 20 and not re.search(r"패널|화면|설정|절약|모드|띄워|보여", s):
            cap, st = _battery()
            if cap is None:
                return "배터리를 찾지 못했어요.", steps
            return f"배터리 {cap}%{', 충전 중' if st == 'Charging' else ', 완충' if st == 'Full' else ''}이에요.", steps
        # 브리핑
        if re.fullmatch(r"(오늘 )?(브리핑|아침 브리핑|하루 정리)( 해 ?줘| 부탁해)?|오늘 어때|좋은 아침", s):
            return briefing(core), steps
        # 날씨(장소 하나 또는 없음)
        m = re.fullmatch(r"(?:(오늘|지금|내일) )?(?:([가-힣]{2,6}?)(?:의)? )?(?:(오늘|지금|내일) )?날씨(?: 어때| 알려 ?줘| 어떄|는| 좀 알려 ?줘)?", s)
        if m and m.group(2) not in ("모레", "이번주", "주말", "이번", "다음주"):
            place, day = m.group(2), m.group(1) or m.group(3)
            if place == "내일":
                place, day = None, "내일"
            w = _weather_line(core, place, tomorrow=day == "내일")
            return (w, steps) if w else None
        # 음량
        m = re.fullmatch(r"(소리|볼륨|음량)(를|을)? ?(.*)", s)
        if m:
            rest = m.group(3)
            n = re.search(r"(\d+|[가-힣]+) ?(퍼센트|%|프로)", rest) or re.search(r"(\d+) ?(으로|로|에)", rest)
            if n and _num(n.group(1)) is not None:
                lv = f"{int(_num(n.group(1)))}%"
            elif re.search(r"음소거|꺼|끄", rest):
                lv = "mute"
            elif re.search(r"켜", rest):
                lv = "unmute"
            elif re.search(r"키워|올려|크게|높여", rest):
                lv = "+10%"
            elif re.search(r"줄여|낮춰|작게|내려", rest):
                lv = "-10%"
            else:
                return None
            _call(core, steps, "device.volume", {"level": lv})
            if lv in ("mute", "unmute"):
                return ("소리를 껐어요." if lv == "mute" else "소리를 다시 켰어요."), steps
            got = re.search(r"([\d.]+)", str(steps[-1]["result"]))
            pct = f" {round(float(got.group(1)) * 100)}%로" if got and float(got.group(1)) <= 1.5 else ""
            verb = "맞췄어요" if lv[0] not in "+-" else "올렸어요" if lv[0] == "+" else "줄였어요"
            return f"음량을{pct} {verb}.", steps
        if re.fullmatch(r"(음소거|조용히)( 해 ?줘)?", s):
            _call(core, steps, "device.volume", {"level": "mute"})
            return "소리를 껐어요.", steps
        # 밝기
        m = re.fullmatch(r"(화면 )?밝기(를|을)? ?(.*)", s)
        if m:
            rest = m.group(3)
            n = re.search(r"(\d+|[가-힣]+) ?(퍼센트|%|프로)", rest)
            if n and _num(n.group(1)) is not None:
                lv = f"{int(_num(n.group(1)))}%"
            elif re.search(r"올려|밝게|높여|키워", rest):
                lv = "+15%"
            elif re.search(r"내려|어둡게|낮춰|줄여", rest):
                lv = "-15%"
            else:
                return None
            out = _call(core, steps, "device.brightness", {"level": lv})
            return f"{out}로 맞췄어요." if "밝기" in str(out) else "밝기를 바꿨어요.", steps
        # 앱 닫기
        m = re.fullmatch(APPS + r"(을|를)? ?(닫아|꺼|종료해)( ?줘| ?주세요)?", s, re.I)
        if m:
            app = m.group(1)
            out = str(_call(core, steps, "app.close", {"app": "chromium" if app in ("유튜브",) else app}))
            if re.search(r"없|못", out):
                return f"열려 있는 {app}{'이' if _eun(app) == '은' else '가'} 없어요.", steps
            return f"{app}{'을' if _eun(app) == '은' else '를'} 닫았어요.", steps
        # 타이머 · 알림
        m = re.fullmatch(r"(\d+|[가-힣]{1,3}) ?(분|시간|초) ?타이머( 맞춰 ?줘| 해 ?줘| 시작)?", s)
        m2 = re.fullmatch(r"(\d+|[가-힣]{1,3}) ?(분|시간|초) ?(?:뒤|후)에? (.+?)(하라고|라고|고)? ?(?:알려|깨워|말해) ?(?:줘|주세요)", s)
        if m or m2:
            g = m or m2
            n = _num(g.group(1))
            if n is None:
                return None
            mins = n * 60 if g.group(2) == "시간" else n / 60 if g.group(2) == "초" else n
            unit = f"{g.group(1)}{g.group(2)}"
            if m2:   # '물 마시라고' → '물 마시세요', '스트레칭하라고' → '스트레칭하세요'
                what, suf = m2.group(3).strip(), m2.group(4)
                what += {"하라고": "하세요", "라고": "세요"}.get(suf, "")
            else:
                what = f"{unit} 타이머 끝"
            _call(core, steps, "reminder.add", {"text": what, "in_minutes": max(0.2, mins)})
            return (f"{unit} 타이머를 맞췄어요." if m else f"{unit} 뒤에 알려 드릴게요: {what}"), steps
        # 정해진 패널(시계·할 일·상태) 띄우기 — 작은 모델은 여러 개를 부탁받으면 하나만 띄우곤 한다
        m = re.fullmatch(r"(.+?) ?패널(을|를|들)?( 좀)? ?(띄워|보여|열어|켜)( ?줘| ?주세요)?", s)
        if m:
            kinds = {"시계": ("clock", "clock", "시계"), "할 ?일": ("todo", "todo", "할 일"),
                     "상태|시스템": ("status", "status", "시스템 상태")}
            src = re.sub(r"할\s+일", "할일", m.group(1))
            names = [x for x in re.split(r"\s*(?:이랑|랑|와|과|하고|,|및)\s*|\s+", src) if x and x not in ("오늘", "내", "그")]
            hit = []
            for nm in names:
                k = next((v for pat, v in kinds.items() if re.fullmatch(pat, nm)), None)
                if k is None:
                    return None          # 모르는 패널이 섞이면 두뇌에게
                hit.append(k)
            if not hit:
                return None
            for pid, typ, title in hit:
                _call(core, steps, "ui.panel", {"id": pid, "type": typ, "title": title})
            return f"{', '.join(t for _, _, t in hit)} 패널을 띄웠어요.", steps
        # 인사
        if re.fullmatch(r"(고마워|고맙습니다|감사합니다|땡큐|thanks?)(요)?", s, re.I):
            return "천만에요.", steps
    except RuntimeError as e:
        return None if not steps else (f"하려고 했는데 안 됐어요: {str(e)[:120]}", steps)
    return None
