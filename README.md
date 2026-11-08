# ATANOR OS (Maestro Cyberdeck)

AI-centric shell layer for Debian: the laptop boots straight into an orb + prompt UI, and a local LLM composes panels, layouts and mini apps to carry out requests.

- `atanor/` — Core (HTTP/SSE on 127.0.0.1:7700), tool registry, memory engine, Sentinel guard, autonomy loop, CDP browser control, MCP bridge
- `atanor/shell/` — kiosk UI (three.js orb, layout engine, Hangul IME, offline matrix rain via Rezmason/matrix, MIT)
- `system/` — systemd units, sway config, `install.sh`
- `pc/` — `ollama_gate.py`, the allowlisting proxy the laptop reaches through a reverse SSH tunnel
- `dev/` — mock Core for UI work (`python dev/mock_server.py` → http://127.0.0.1:7799/)

Deploy: copy `atanor/` and `system/` to the laptop, then `bash system/install.sh`.
