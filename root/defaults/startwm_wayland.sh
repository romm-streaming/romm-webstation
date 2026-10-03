#!/usr/bin/env bash

# Default files
if [ ! -f "${HOME}"/Desktop/pcsx2-qt.desktop ]; then
  mkdir -p "${HOME}"/Desktop
  cp /defaults/desktop/* "${HOME}"/Desktop
  sudo cp /defaults/desktop/* /usr/share/applications/
  chmod +x "${HOME}"/Desktop/*.desktop
fi

# Start DE
ulimit -c 0
export PATH=$PATH:/usr/games
export XCURSOR_THEME=breeze
export XCURSOR_SIZE=24
export XKB_DEFAULT_LAYOUT=us
export XKB_DEFAULT_RULES=evdev
export WAYLAND_DISPLAY=wayland-1
if [ "${SELKIES_DESKTOP}" == "true" ]; then
  labwc > /dev/null 2>&1 &
  sleep 1
  export WAYLAND_DISPLAY=wayland-0
  export DISPLAY=:0
  selkies-desktop
else
  labwc > /dev/null 2>&1
fi
