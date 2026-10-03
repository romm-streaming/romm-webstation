#!/usr/bin/env bash

# Default files
if [ ! -f "${HOME}"/Desktop/pcsx2-qt.desktop ]; then
  mkdir -p "${HOME}"/Desktop
  cp /defaults/desktop/* "${HOME}"/Desktop
  sudo cp /defaults/desktop/* /usr/share/applications/
  chmod +x "${HOME}"/Desktop/*.desktop
fi

# shadPS4 loop to extract appimage
monitor_shadps4_no_fuse() {
  local SLEEP_TIME="${1:-5}"
  local VERSIONS_DIR="$HOME/.local/share/shadPS4QtLauncher/versions"
  local TARGET_APPIMAGE="Shadps4-sdl.AppImage"
  local INTERNAL_BIN_PATH="usr/bin/shadps4"
  local MARKER_FILE=".nofuse_ready"
  local PARENT_PID=$$
  local stat
  while true; do
    # Once this script exits (openbox or selkies-desktop quit) the loop is
    # reparented, and nothing else stops it, so each DE restart would leave
    # one more behind.
    # Comparing the ppid rather than probing $$ stays right if that pid is reused.
    # The plain `exec dbus-launch` below keeps this pid, so it still counts as alive.
    # The line is "pid (comm) state ppid ..." and comm may hold spaces, so the
    # ppid is taken from after the last ") ".
    read -r stat < "/proc/${BASHPID}/stat" || return
    stat=${stat##*) }
    stat=${stat#* }
    [[ "${stat%% *}" == "$PARENT_PID" ]] || return
    shopt -s nullglob
    for folder in "$VERSIONS_DIR"/*; do
      if [[ -d "$folder" ]]; then
        if [[ -f "$folder/$MARKER_FILE" ]]; then
          continue
        fi
        if [[ -f "$folder/$TARGET_APPIMAGE" ]]; then
          (
            cd "$folder" || exit
            # The previous session's loop can still be mid-extract until it
            # notices it was reparented; never share squashfs-root with it.
            exec 9<.
            flock -n 9 || exit
            [[ -f "$MARKER_FILE" ]] && exit
            chmod +x "$TARGET_APPIMAGE"
            ./"$TARGET_APPIMAGE" --appimage-extract >/dev/null 2>&1
            # svc-de's finish TERMs the session, so keep the swap to one rename
            # with the marker right behind it: a kill between the two would
            # leave the bare binary unmarked and run with --appimage-extract
            # every pass.
            if [[ -f "squashfs-root/$INTERNAL_BIN_PATH" ]] &&
              mv -f "squashfs-root/$INTERNAL_BIN_PATH" "$TARGET_APPIMAGE"; then
              : >"$MARKER_FILE"
            fi
            rm -rf squashfs-root
          )
        fi
      fi
    done
    shopt -u nullglob
    sleep "$SLEEP_TIME"
  done
}

monitor_shadps4_no_fuse 5 &

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
