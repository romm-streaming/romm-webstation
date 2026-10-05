#!/usr/bin/env bash

# Default files
if [ ! -f "${HOME}"/Desktop/pcsx2-qt.desktop ]; then
  mkdir -p "${HOME}"/Desktop
  cp /defaults/desktop/* "${HOME}"/Desktop
  sudo cp /defaults/desktop/* /usr/share/applications/
  chmod +x "${HOME}"/Desktop/*.desktop
fi

# Start DE
export PATH=$PATH:/usr/games
if [ "${SELKIES_DESKTOP,,}" == "true" ]; then
  exec dbus-launch --exit-with-session /usr/bin/openbox-session > /dev/null 2>&1 &
  OPENBOX_PID=$!
  sleep 1
  selkies-desktop
  kill $OPENBOX_PID
else
  exec dbus-launch --exit-with-session /usr/bin/openbox-session > /dev/null 2>&1
fi
