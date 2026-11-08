#!/usr/bin/env python3
"""ATANOR MCP 다리 — Claude, Cursor 등 MCP를 쓰는 어떤 AI든 ATANOR의 모든 도구로 이 컴퓨터를 조작한다.

stdio 방식 MCP 서버. Core(127.0.0.1:7700)의 도구 목록을 그대로 MCP 도구로 노출한다.
권한·승인·스냅샷·기록은 전부 Core가 강제하므로, 어떤 AI가 붙어도 안전 규칙은 같다.

예) 이 PC에서 SSH로 붙이는 Claude Code 설정:
  claude mcp add atanor -- ssh -i <키> mind@192.168.0.149 /opt/atanor/atanor/mcp_bridge.py
"""
import json
import os
import sys
import urllib.request

CORE = os.environ.get("ATANOR_CORE", "http://127.0.0.1:7700")
TOKEN = open(os.path.expanduser("~/.atanor/token")).read().strip()


def core(path, body=None):
    req = urllib.request.Request(CORE + path, data=json.dumps(body).encode() if body else None,
                                 headers={"X-Atanor-Token": TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())


def tools():
    out = []
    for t in core("/api/tools"):
        out.append({"name": t["name"].replace(".", "_"), "description": f"[{t['risk']}] {t['description']}",
                    "inputSchema": t["params"]})
    out.append({"name": "ask_atanor", "description": "ATANOR 내장 비서에게 자연어로 일을 시키고 결과를 받는다.",
                "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}})
    return out


def send(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid, method, params = req.get("id"), req.get("method"), req.get("params") or {}
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": "2024-11-05",
                                                           "capabilities": {"tools": {}},
                                                           "serverInfo": {"name": "atanor", "version": "0.1"}}})
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": tools()}})
        elif method == "tools/call":
            name, args = params.get("name", ""), params.get("arguments") or {}
            try:
                if name == "ask_atanor":
                    r = core("/api/ask", {"text": args.get("text", ""), "source": "mcp", "wait": True})
                    text, ok = r.get("reply", ""), True
                else:
                    real = next((t["name"] for t in core("/api/tools") if t["name"].replace(".", "_") == name), name)
                    r = core("/api/tool", {"name": real, "args": args, "source": "mcp"})
                    text, ok = r["result"] if isinstance(r["result"], str) else json.dumps(r["result"], ensure_ascii=False), r["ok"]
                send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": str(text)}],
                                                               "isError": not ok}})
            except Exception as e:  # noqa: BLE001
                send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32000, "message": str(e)}})
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif mid is not None:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}})


if __name__ == "__main__":
    main()
