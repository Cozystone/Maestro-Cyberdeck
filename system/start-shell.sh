#!/bin/bash
# Launch the ATANOR shell (Chromium kiosk on the Core) once the Core answers.
# Notes for this laptop (HP Pavilion, Intel HD 530 + NVIDIA GTX 950M):
#  - force Mesa/Intel for EGL; the NVIDIA GBM path fails under sway and takes the GPU process down
#  - Chromium 156 segfaults on Wayland in --app mode, so we use --kiosk with a plain URL instead
export GTK_IM_MODULE=fcitx XMODIFIERS=@im=fcitx QT_IM_MODULE=fcitx
export __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json __GLX_VENDOR_LIBRARY_NAME=mesa
PROFILE="$HOME/.atanor/shell-profile"
for i in $(seq 1 60); do
  curl -sf http://127.0.0.1:7700/static/style.css >/dev/null && break
  sleep 1
done
pgrep -f "[s]hell-profile" >/dev/null && exit 0
rm -f "$PROFILE"/Singleton*
exec chromium \
  --ozone-platform=wayland --enable-wayland-ime \
  --class=atanor --kiosk --start-fullscreen \
  --no-first-run --noerrdialogs --disable-infobars --disable-session-crashed-bubble \
  --password-store=basic --user-data-dir="$PROFILE" \
  --render-node-override=/dev/dri/renderD128 --disable-features=Vulkan --ignore-gpu-blocklist \
  --disable-component-update --disable-background-networking \
  --autoplay-policy=no-user-gesture-required --lang=ko \
  http://127.0.0.1:7700/ \
  >/dev/null 2>&1
