"""EDEN_LEGACY and XEMU_LEGACY: the pre-AVX2 builds swapped in at boot.

The swap downloads both builds from git.eden-emu.dev and Launchpad, so it runs
in a container of its own and only with WEBSTATION_LEGACY_TESTS=1. pr.yml sets
it; release builds leave it off so an upstream outage cannot block a publish.
"""

from __future__ import annotations

import os
import subprocess
import time
import uuid

import pytest
from conftest import STARTUP_TIMEOUT, Station, start_container, stop_container, wait_for_health

EDEN_WRAPPER = "/usr/bin/eden"
XEMU_APPRUN = "/opt/xemu/AppRun"
EDEN_LEGACY = "/config/.local/share/eden-legacy"
XEMU_LEGACY = "/config/.local/share/xemu-legacy"
# the session the broker launches emulators into (romm-broker emulators/base.py)
LAUNCH_ENV = [
    "-e",
    "HOME=/config",
    "-e",
    "DISPLAY=:0",
    "-e",
    "WAYLAND_DISPLAY=wayland-0",
    "-e",
    "XDG_RUNTIME_DIR=/config/.XDG",
]


def test_bundled_builds_untouched_by_default(station: Station) -> None:
    """Without the variables both oneshots leave the image's binaries alone."""
    left = station.sh(f"ls {EDEN_WRAPPER}.bundled {XEMU_APPRUN}.bundled 2>/dev/null", check=False)
    assert not left.strip(), f"legacy swap ran without being asked: {left}"
    assert station.sh(f"head -c 4 {EDEN_WRAPPER} | od -An -c").split() == ["177", "E", "L", "F"]


@pytest.fixture(scope="module")
def legacy(image: str) -> Station:
    if os.environ.get("WEBSTATION_LEGACY_TESTS") != "1":
        pytest.skip("downloads from upstream; set WEBSTATION_LEGACY_TESTS=1")
    st = start_container(
        image,
        "ci-secret",
        f"webstation-ci-legacy-{uuid.uuid4().hex[:8]}",
        extra_env={"EDEN_LEGACY": "true", "XEMU_LEGACY": "true"},
    )
    try:
        # both builds are downloaded before the desktop comes up
        wait_for_health(st, STARTUP_TIMEOUT + 300)
    except Exception:
        stop_container(st, "container-legacy.log")
        raise
    yield st
    stop_container(st, "container-legacy.log")


@pytest.mark.slow
def test_legacy_eden_swapped(legacy: Station) -> None:
    assert "[eden-legacy] /usr/bin/eden now runs the legacy build" in legacy.logs()
    legacy.exec("test", "-x", f"{EDEN_WRAPPER}.bundled")
    assert f"{EDEN_LEGACY}/app/AppRun" in legacy.sh(f"cat {EDEN_WRAPPER}")
    root_owned = legacy.sh(f"find {EDEN_LEGACY} ! -user abc | head -5")
    assert not root_owned.strip(), f"legacy Eden files not owned by abc: {root_owned}"


@pytest.mark.slow
def test_legacy_xemu_swapped(legacy: Station) -> None:
    assert "[xemu-legacy] /opt/xemu/AppRun now runs xemu" in legacy.logs()
    legacy.exec("test", "-L", f"{XEMU_APPRUN}.bundled")
    missing = legacy.sh(f"ldd {XEMU_LEGACY}/root/usr/bin/xemu | grep 'not found' || true")
    assert not missing.strip(), f"legacy xemu has unresolved libraries: {missing}"


@pytest.mark.slow
def test_legacy_xemu_keeps_argv0(legacy: Station) -> None:
    """The broker finds xemu by XEMU_BIN in its argv, so the wrapper must keep it."""
    legacy.sh("pkill -x xemu || true")
    pid_cmd = f"pgrep -u abc -f '^{XEMU_APPRUN}( |$)' | head -1"
    try:
        subprocess.run(
            ["docker", "exec", "-d", "-u", "abc", *LAUNCH_ENV, legacy.name, XEMU_APPRUN],
            check=True,
            timeout=30,
        )
        pid = ""
        deadline = time.monotonic() + 20
        while not pid and time.monotonic() < deadline:
            pid = legacy.sh(pid_cmd, check=False).strip()
            time.sleep(0.5)
        # comm names the binary that was exec'd, AppRun while still in the wrapper;
        # /proc/<pid>/exe would be exact but needs CAP_SYS_PTRACE, which docker drops
        comm = legacy.sh(f"cat /proc/{pid}/comm", check=False).strip() if pid else ""
        assert pid, "xemu was not running under argv[0] /opt/xemu/AppRun"
        assert comm == "xemu", f"argv[0] matched but the process is {comm!r}"
    finally:
        legacy.sh("pkill -x xemu || true", check=False)


@pytest.mark.slow
def test_legacy_versions_recorded(legacy: Station) -> None:
    """webstation-versions names the builds actually running, not only the bundled ones."""
    out = legacy.sh("webstation-versions")
    assert any(line.split()[0] == "eden-legacy" for line in out.splitlines()), out
    assert any(line.split()[0] == "xemu-legacy" for line in out.splitlines()), out
