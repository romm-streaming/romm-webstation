"""Let absolute mouse moves reach an app that holds a pointer lock.

A game that hides the cursor and warps it (RetroArch's mouse grab, ScummVM)
makes Xwayland take a Wayland pointer lock. While it holds one, labwc drops
absolute pointer motion and only forwards relative motion. Selkies sends
absolute moves unless the browser itself has pointer lock (Gaming Mode), so
outside Gaming Mode the game gets no movement at all.

This patches selkies' input handler so every absolute move on the Wayland
backend is also injected as the relative delta from the previous absolute
position, ahead of the absolute position itself. Unlocked, the two land on the
same spot, so nothing changes; locked, the delta is what gets through.

The anchors are matched exactly and each must appear once, so a selkies update
that moves this code fails the build instead of shipping unpatched.

Usage: python3 selkies_pointer_lock.py <path to selkies/input_handler.py>
"""

import sys
from pathlib import Path

PATCHES = [
    (
        # Keep the previous tracked position; the tracking below overwrites it.
        "        position_changed = (was_stale or final_x != self.last_x or final_y != self.last_y)\n"
        "        self.last_x = final_x\n",
        "        position_changed = (was_stale or final_x != self.last_x or final_y != self.last_y)\n"
        "        prev_x, prev_y = self.last_x, self.last_y\n"
        "        self.last_x = final_x\n",
    ),
    (
        "                else:\n"
        "                    self.wayland_input.inject_mouse_move(float(final_x), float(final_y))\n",
        "                else:\n"
        "                    # romm-webstation: a pointer-locked app only sees relative\n"
        "                    # motion, so send the delta first. Skipped when there is no\n"
        "                    # trustworthy previous position (first move, or the tracked\n"
        "                    # one is an estimate left by a relative message).\n"
        "                    if (not was_stale and prev_x >= 0 and prev_y >= 0\n"
        "                            and (final_x != prev_x or final_y != prev_y)\n"
        "                            and hasattr(self.wayland_input, 'inject_relative_mouse_move')):\n"
        "                        self.wayland_input.inject_relative_mouse_move(\n"
        "                            float(final_x - prev_x), float(final_y - prev_y))\n"
        "                    self.wayland_input.inject_mouse_move(float(final_x), float(final_y))\n",
    ),
]


def main() -> None:
    path = Path(sys.argv[1])
    text = path.read_text()
    for old, new in PATCHES:
        count = text.count(old)
        if count != 1:
            sys.exit(f"selkies_pointer_lock: anchor found {count} times, expected 1:\n{old}")
        text = text.replace(old, new)
    path.write_text(text)
    print(f"selkies_pointer_lock: patched {path}")


if __name__ == "__main__":
    main()
