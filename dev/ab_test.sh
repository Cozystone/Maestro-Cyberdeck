#!/bin/bash
# A/B: run the same requests with a given brain model and check grounding.
# usage: ab_test.sh <model>
MODEL="$1"
CFG=~/.atanor/config.json
python3 - "$MODEL" <<'EOF'
import json, os, sys
p = os.path.expanduser("~/.atanor/config.json"); c = json.load(open(p)); c["brain"]["model"] = sys.argv[1]; c["autonomy"] = "off"
json.dump(c, open(p, "w"), ensure_ascii=False, indent=1)
EOF
sudo systemctl restart atanor-core; sleep 3
T=$(cat ~/.atanor/token); H="X-Atanor-Token: $T"; U=http://127.0.0.1:7700
curl -s -H "$H" -X POST $U/api/tool -d '{"name":"ui.remove","args":{"id":"*"}}' >/dev/null
REAL=$(ls -A ~ | sort | tr '\n' ' ')
echo "=== MODEL $MODEL  (real home: $REAL)"
ask () {
  local start=$(date +%s)
  python3 -c 'import json,sys;print(json.dumps({"text":sys.argv[1],"source":"user","wait":True}))' "$1" \
   | curl -s -H "$H" -H 'Content-Type: application/json' -X POST $U/api/ask -d @- > /tmp/ab.json
  python3 - "$1" "$(( $(date +%s)-start ))" "$REAL" <<'EOF'
import json, sys
d = json.load(open("/tmp/ab.json")); q, secs, real = sys.argv[1], sys.argv[2], set(sys.argv[3].split())
tools = [s["tool"] for s in d["steps"]]
print(f"\n--- Q: {q}\n    {secs}s, tools: {tools}")
print("    REPLY:", d["reply"][:220].replace("\n", " "))
for s in d["steps"]:
    if s["tool"] == "ui.panel" and s["args"].get("type") == "table":
        rows = (s["args"].get("data") or {}).get("rows") or []
        names = {str(r[0]) for r in rows if isinstance(r, list) and r}
        fake = names - real
        print(f"    TABLE rows={len(rows)} names_not_on_disk={sorted(fake)[:6]}")
EOF
}
ask "내 홈 폴더 내용을 표로 보여줘"
ask "디스크 남은 용량이랑 메모리 사용량을 숫자로 알려줘"
ask "웹에서 Debian 13 코드네임이 뭔지 찾아서 알려줘"
ask "할 일 패널 만들어줘: 빨래, 장보기, 운동"
STATE=$(curl -s -H "$H" $U/api/state)
echo; echo "panels now: $(echo "$STATE" | python3 -c 'import sys,json;d=json.load(sys.stdin);print({k:v["type"] for k,v in d["ui"]["panels"].items()}, d["ui"]["theme"].get("layout"))')"
