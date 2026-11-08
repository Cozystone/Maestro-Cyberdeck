# ATANOR OS (Maestro Cyberdeck)

AI-centric shell layer for Debian: the laptop boots straight into an orb + prompt UI, and a local LLM composes panels, layouts and mini apps to carry out requests.

- `atanor/` — Core (HTTP/SSE on 127.0.0.1:7700), tool registry, memory engine, Sentinel guard, autonomy loop, CDP browser control, MCP bridge
- `atanor/shell/` — kiosk UI (three.js orb, layout engine, Hangul IME, offline matrix rain via Rezmason/matrix, MIT)
- `system/` — systemd units, sway config, `install.sh`
- `pc/` — `ollama_gate.py`, the allowlisting proxy the laptop reaches through a reverse SSH tunnel
- `dev/` — mock Core for UI work (`python dev/mock_server.py` → http://127.0.0.1:7799/)

Deploy: copy `atanor/` and `system/` to the laptop, then `bash system/install.sh`.

## Eye (`atanor/eye.py`) — human-like screen perception

Successor to the ATANOR-Demo perception v0 (measure, don't imagine; provenance; scene graph; redact secrets).
Retina (low-res change map) → periphery (sway window layout) → fovea (Tesseract OCR only on changed windows, dark-adapted)
→ where/what pathways (AT-SPI roles merged with OCR positions) → attention (what appeared / disappeared, stable element ids).
`eye.see` returns a numbered text scene so a text-only brain can operate any app; `eye.act` acts and re-sees;
`computer.task` lets the brain loop on the scene and only accepts "done" when pre-declared on-screen evidence is measured.
Input: sway virtual cursor for the mouse, a uinput kernel keyboard for keys, wtype for text (Hangul included).
