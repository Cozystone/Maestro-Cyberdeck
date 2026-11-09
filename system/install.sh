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
# computer use: pixel-free keyboard via a kernel virtual keyboard (wtype key presses are dropped by this sway)
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3-evdev python3-pil python3-pyatspi gir1.2-atspi-2.0 tesseract-ocr tesseract-ocr-kor python3-numpy >/dev/null
# voice: Korean neural speech for replies (only the reply text leaves the laptop); speech recognition runs on the PC
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3-pip python3-aiohttp >/dev/null
python3 -m pip install -q --user --break-system-packages --upgrade edge-tts >/dev/null
echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' | sudo tee /etc/udev/rules.d/60-atanor-uinput.rules >/dev/null
echo uinput | sudo tee /etc/modules-load.d/atanor-uinput.conf >/dev/null
sudo modprobe uinput; sudo udevadm control --reload; sudo udevadm trigger --subsystem-match=misc
sudo usermod -aG video,input,seat,render,audio mind 2>/dev/null || true

# 추적 방지: 바깥 인터넷 통신을 기본으로 Tor를 거치게 한다(로컬 두뇌·LAN·들어오는 SSH는 제외)
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q tor >/dev/null
if ! grep -q "ATANOR transparent Tor" /etc/tor/torrc 2>/dev/null; then
  sudo tee -a /etc/tor/torrc >/dev/null <<'TORRC'

# === ATANOR transparent Tor ===
SOCKSPort 127.0.0.1:9050
DNSPort 127.0.0.1:5353
TransPort 127.0.0.1:9040
VirtualAddrNetworkIPv4 10.192.0.0/10
AutomapHostsOnResolve 1
AutomapHostsSuffixes .onion,.exit
TORRC
fi
sudo chmod +x /opt/atanor/system/atanor-tor-route.sh
sudo systemctl enable --now tor@default >/dev/null 2>&1 || true
sudo systemctl restart tor@default >/dev/null 2>&1 || true

# services
sudo cp /opt/atanor/system/atanor-core.service /opt/atanor/system/atanor-session.service /opt/atanor/system/atanor-tor-route.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable seatd atanor-core atanor-session atanor-tor-route >/dev/null
sudo systemctl restart atanor-core
sudo loginctl enable-linger mind
echo "ATANOR installed. Core: $(sleep 2; curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:7700/static/style.css)"
