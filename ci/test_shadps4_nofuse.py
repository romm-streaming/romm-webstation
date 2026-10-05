"""svc-shadps4-nofuse: the loop that swaps shadPS4 AppImages for their bare binary.

Real AppImages are 50 MB downloads, so these use stand-ins: a bash script whose
shebang puts the type 2 magic "AI\\2" at byte 8, through a symlink named so the
interpreter path carries it. Run with --appimage-extract it unpacks a
squashfs-root holding a fake usr/bin/shadps4 that names its build.
"""

from __future__ import annotations

import shlex
import time
import uuid

import pytest
from conftest import Station

VERSIONS = "/config/.local/share/shadPS4QtLauncher/versions"
TARGET = "Shadps4-sdl.AppImage"
MARKER = ".nofuse_ready"
INTERP = r"/tmp/xAI\002"
# the service sleeps 5s between passes
SWAP_TIMEOUT = 20


def _as_abc(station: Station, script: str) -> str:
    return station.sh(f"s6-setuidgid abc bash -c {shlex.quote(script)}")


def _fake_appimage(path: str, build: str) -> str:
    """Shell that writes a stand-in AppImage for `build` to `path`."""
    body = (
        '[[ "$1" == --appimage-extract ]] || { echo ran >> "$(dirname "$0")/ran"; exit 0; }\n'
        "mkdir -p squashfs-root/usr/bin\n"
        f"printf {build} > squashfs-root/usr/bin/shadps4\n"
    )
    return f"{{ printf '#!{INTERP}\\n'; printf %s {shlex.quote(body)}; }} > {shlex.quote(path)}"


def _wait_for(station: Station, check: str) -> bool:
    deadline = time.monotonic() + SWAP_TIMEOUT
    while time.monotonic() < deadline:
        if station.exec("bash", "-c", check, check=False).returncode == 0:
            return True
        time.sleep(1)
    return False


@pytest.fixture
def versions(station: Station):
    """A unique prefix for one test's version folders, removed afterwards.

    The service only looks one level down, so the folders sit directly in VERSIONS.
    """
    station.sh(f"ln -sf /bin/bash $(printf '{INTERP}')")
    _as_abc(station, f"mkdir -p {VERSIONS}")
    prefix = f"{VERSIONS}/ci-{uuid.uuid4().hex[:8]}"
    yield prefix
    station.sh(f"rm -rf {prefix}-*", check=False)


def test_new_build_swapped(station: Station, versions: str) -> None:
    folder = f"{versions}-v1"
    _as_abc(station, f"mkdir -p {folder} && {_fake_appimage(f'{folder}/{TARGET}', 'BUILD1')}")
    assert _wait_for(station, f"grep -qx BUILD1 {folder}/{TARGET}"), "build was never swapped"
    assert sorted(station.sh(f"ls -A {folder}").split()) == sorted([MARKER, TARGET])


def test_build_updated_in_place_swapped_again(station: Station, versions: str) -> None:
    """The launcher's Pre-release update unzips a new build over the swapped one."""
    folder = f"{versions}-Pre-release"
    _as_abc(station, f"mkdir -p {folder} && {_fake_appimage(f'{folder}/{TARGET}', 'BUILD1')}")
    assert _wait_for(station, f"grep -qx BUILD1 {folder}/{TARGET}"), "first build was never swapped"
    zip_build = (
        f"cd /tmp && rm -rf upd && mkdir upd && {_fake_appimage(f'upd/{TARGET}', 'BUILD2')} && "
        'python3 -c "import zipfile; '
        f"zipfile.ZipFile('upd.zip', 'w').write('upd/{TARGET}', '{TARGET}')\" && "
        f"unzip -o -q upd.zip -d {folder} && rm -rf upd upd.zip"
    )
    _as_abc(station, zip_build)
    assert _wait_for(station, f"grep -qx BUILD2 {folder}/{TARGET}"), "updated build was never swapped"


def test_failed_extract_leaves_nothing(station: Station, versions: str) -> None:
    folder = f"{versions}-broken"
    # magic intact but no payload, like a download cut short
    _as_abc(station, f"mkdir -p {folder} && printf '#!{INTERP}\\nexit 1\\n' > {folder}/{TARGET}")
    time.sleep(12)
    assert station.sh(f"ls -A {folder}").split() == [TARGET]


def test_non_appimage_never_run(station: Station, versions: str) -> None:
    """A bare binary takes --appimage-extract as a game path, so it must not be started."""
    folder = f"{versions}-bare"
    _as_abc(
        station,
        f"mkdir -p {folder} && printf '#!/bin/bash\\necho ran >> {folder}/ran\\n' > {folder}/{TARGET} && "
        f"chmod +x {folder}/{TARGET}",
    )
    time.sleep(12)
    assert station.sh(f"ls -A {folder}").split() == [TARGET]


def test_old_empty_marker_relinked(station: Station, versions: str) -> None:
    """Folders swapped before the marker became a hard link keep their binary as is."""
    folder = f"{versions}-legacy"
    _as_abc(
        station,
        f"mkdir -p {folder} && printf '#!/bin/bash\\necho ran >> {folder}/ran\\n' > {folder}/{TARGET} && "
        f"chmod +x {folder}/{TARGET} && : > {folder}/{MARKER}",
    )
    assert _wait_for(station, f"[[ {folder}/{TARGET} -ef {folder}/{MARKER} ]]"), "old marker was not relinked"
    assert sorted(station.sh(f"ls -A {folder}").split()) == sorted([MARKER, TARGET])
