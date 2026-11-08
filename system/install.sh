#!/bin/bash
# Install/upgrade ATANOR on this laptop. Run as mind (sudo without password).
set -e
SRC="$(cd "$(dirname "$0")/.." && pwd)"
sudo mkdir -p /opt/atanor
sudo rsync -a --delete --exclude '__pycache__' --exclude 'pc/' "$SRC/" /opt/atanor/
sudo chown -R root:root /opt/atanor
sudo chmod +x /opt/atanor/system/*.sh /opt/atanor/atanor/mcp_bridge.py /opt/atanor/atanor/core.py
sudo mkdir -p /opt/atanor/user && sudo chown mind:mind /opt/atanor/user

# command-line client
sudo tee /usr/local/bin/atanor >/dev/null <<'EOF'
#!/bin/bash
# atanor "할 일"  → Core의 내장 비서에게 보낸다
T=$(cat ~/.atanor/token)
if [ -z "$1" ]; then echo "usage: atanor <request>"; exit 1; fi
curl -s -X POST http://127.0.0.1:7700/api/ask -H "X-Atanor-Token: $T" -H 'Content-Type: application/json' \
  -d "$(python3 -c 'import json,sys;print(json.dumps({"text":" ".join(sys.argv[1:]),"source":"cli","wait":True}))' "$@")" \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("reply",d))'
EOF
sudo chmod +x /usr/local/bin/atanor

# user config
mkdir -p ~/.atanor ~/.config/sway ~/.config/fcitx5 ~/Pictures/screenshots
cp /opt/atanor/system/sway.config ~/.config/sway/config
cat > ~/.config/fcitx5/profile <<'EOF'
[Groups/0]
Name=Default
Default Layout=us
DefaultIM=hangul
[Groups/0/Items/0]
Name=keyboard-us
[Groups/0/Items/1]
Name=hangul
[GroupOrder]
0=Default
EOF

# brightness without password
echo 'mind ALL=(root) NOPASSWD: /usr/bin/brightnessctl' | sudo tee /etc/sudoers.d/91-atanor-brightness >/dev/null
sudo chmod 440 /etc/sudoers.d/91-atanor-brightness
sudo usermod -aG video,input,seat,render,audio mind 2>/dev/null || true

# services
sudo cp /opt/atanor/system/atanor-core.service /opt/atanor/system/atanor-session.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable seatd atanor-core atanor-session >/dev/null
sudo systemctl restart atanor-core
sudo loginctl enable-linger mind
echo "ATANOR installed. Core: $(sleep 2; curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:7700/static/style.css)"
