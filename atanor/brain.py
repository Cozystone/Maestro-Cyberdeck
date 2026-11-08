"""두뇌 연결 — 어떤 모델이든 같은 방식으로 부른다.

~/.atanor/config.json 의 "brain":
  {"type": "ollama", "url": "http://127.0.0.1:11434", "model": "dolphin24"}
  {"type": "openai", "url": "http://host:8000/v1", "model": "...", "api_key_env": "OPENAI_API_KEY"}
    (llama.cpp server, vLLM, LM Studio, OpenAI 등 OpenAI 호환 서버 전부)
"""
import json
import os
import urllib.request


class Brain:
    def __init__(self, cfg):
        self.cfg = cfg
        self.type = cfg.get("type", "ollama")
        self.url = cfg.get("url", "http://127.0.0.1:11434").rstrip("/")
        self.model = cfg.get("model", "dolphin24")

    def _post(self, path, payload, headers=None, timeout=600):
        req = urllib.request.Request(self.url + path, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json", **(headers or {})})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def alive(self):
        try:
            path = "/api/version" if self.type == "ollama" else "/models"
            with urllib.request.urlopen(self.url + path, timeout=4):
                return True
        except Exception:  # noqa: BLE001
            return False

    def chat(self, messages, schema=None, temperature=0.4):
        """messages -> 문자열. schema가 있으면 그 JSON 형식으로만 답하게 강제한다."""
        if self.type == "ollama":
            body = {"model": self.model, "messages": messages, "stream": False,
                    "options": {"temperature": temperature}}
            if schema:
                body["format"] = schema
            return self._post("/api/chat", body)["message"]["content"]
        headers = {}
        key = os.environ.get(self.cfg.get("api_key_env", ""), "") or self.cfg.get("api_key", "")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        body = {"model": self.model, "messages": messages, "temperature": temperature}
        if schema:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "action", "schema": schema}}
        return self._post("/chat/completions", body, headers)["choices"][0]["message"]["content"]
