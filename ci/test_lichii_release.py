"""Guards on the Lichii release the image picks up, without building an image.

lichii-release.sh decides which release the Dockerfile downloads and
lichii-install.sh refuses a tarball that does not match its GitHub digest.
Both run here against canned API answers, so no network and no container.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent / "scripts"
ASSET = "lichii-linux-x86_64.tar.gz"
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
DIGEST = "a" * 64


def _release(tag: str, age_hours: float, *, prerelease: bool = False, draft: bool = False, **asset) -> dict:
    published = (NOW - timedelta(hours=age_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    files = [{"name": ASSET, "digest": f"sha256:{DIGEST}"} | asset] if asset.get("name") != "" else []
    # A release body with a backslash escape, which a plain `echo` would turn
    # into a control character and break jq.
    return {
        "tag_name": tag,
        "published_at": published,
        "prerelease": prerelease,
        "draft": draft,
        "body": "path C:\\new\\temp",
        "assets": files,
    }


def _fake_api(tmp_path: Path, answers: dict[str, object]) -> Path:
    """A gh-api.sh stand in that prints the canned answer for each path."""
    for i, (path, body) in enumerate(answers.items()):
        (tmp_path / f"answer{i}.json").write_text(json.dumps(body))
        (tmp_path / f"answer{i}.path").write_text(path)
    script = tmp_path / "gh-api"
    script.write_text(
        "#!/bin/sh\n"
        f'for p in "{tmp_path}"/answer*.path; do\n'
        '  if [ "$(cat "$p")" = "$1" ]; then cat "${p%.path}.json"; exit 0; fi\n'
        "done\n"
        'echo "unexpected api path $1" >&2\n'
        "exit 22\n"
    )
    script.chmod(0o755)
    return script


def _resolve(tmp_path: Path, answers: dict[str, object], *args: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "GH_API": str(_fake_api(tmp_path, answers)),
        "LICHII_NOW": str(int(NOW.timestamp())),
    }
    return subprocess.run(
        [str(SCRIPTS / "lichii-release.sh"), *args], capture_output=True, text=True, env=env, check=False
    )


LIST = "repos/zortos293/Lichii/releases?per_page=30"


def test_picks_newest_eligible(tmp_path: Path) -> None:
    releases = [_release("build-3", 30), _release("build-1", 90), _release("build-2", 50)]
    r = _resolve(tmp_path, {LIST: releases})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f"build-3 {DIGEST}"


def test_skips_release_younger_than_24h(tmp_path: Path) -> None:
    releases = [_release("build-4", 23.5), _release("build-3", 24.5)]
    r = _resolve(tmp_path, {LIST: releases})
    assert r.returncode == 0, r.stderr
    assert r.stdout.split()[0] == "build-3"


def test_skips_prereleases_and_drafts(tmp_path: Path) -> None:
    releases = [
        _release("build-5", 40, prerelease=True),
        _release("build-4", 40, draft=True),
        _release("build-3", 60),
    ]
    r = _resolve(tmp_path, {LIST: releases})
    assert r.returncode == 0, r.stderr
    assert r.stdout.split()[0] == "build-3"


def test_fails_when_nothing_is_old_enough(tmp_path: Path) -> None:
    r = _resolve(tmp_path, {LIST: [_release("build-9", 2), _release("build-8", 30, prerelease=True)]})
    assert r.returncode != 0
    assert "older than 24 hours" in r.stderr


def test_override_skips_the_lookup(tmp_path: Path) -> None:
    """LICHII_VERSION is the rollback: it pins a tag whatever its age."""
    r = _resolve(
        tmp_path, {"repos/zortos293/Lichii/releases/tags/build-7": _release("build-7", 1)}, "build-7"
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f"build-7 {DIGEST}"


def test_override_rejects_odd_tags(tmp_path: Path) -> None:
    r = _resolve(tmp_path, {}, "../../evil")
    assert r.returncode != 0
    assert "not a Lichii release tag" in r.stderr


@pytest.mark.parametrize(
    ("asset", "message"),
    [
        ({"digest": None}, "has no sha256 digest"),
        ({"digest": "sha1:abc"}, "has no sha256 digest"),
        ({"name": ""}, f"has no {ASSET}"),
    ],
)
def test_fails_without_a_usable_digest(tmp_path: Path, asset: dict, message: str) -> None:
    r = _resolve(tmp_path, {LIST: [_release("build-3", 30, **asset)]})
    assert r.returncode != 0
    assert message in r.stderr


def _tarball(tmp_path: Path) -> tuple[Path, str]:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = b"#!/bin/sh\n"
        info = tarfile.TarInfo("lichii/usr/bin/lichii")
        info.size = len(data)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(data))
    path = tmp_path / ASSET
    path.write_bytes(buf.getvalue())
    return path, hashlib.sha256(buf.getvalue()).hexdigest()


def _install(tarball: Path, sha256: str, dest: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(SCRIPTS / "lichii-install.sh"), str(tarball), sha256, str(dest)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_install_unpacks_a_matching_tarball(tmp_path: Path) -> None:
    tarball, sha256 = _tarball(tmp_path)
    dest = tmp_path / "opt-lichii"
    r = _install(tarball, sha256, dest)
    assert r.returncode == 0, r.stderr
    assert (dest / "usr/bin/lichii").stat().st_mode & 0o755 == 0o755


def test_install_refuses_a_digest_mismatch(tmp_path: Path) -> None:
    tarball, sha256 = _tarball(tmp_path)
    dest = tmp_path / "opt-lichii"
    wrong = ("0" if sha256[0] != "0" else "1") + sha256[1:]
    r = _install(tarball, wrong, dest)
    assert r.returncode != 0
    assert "FAILED" in r.stdout + r.stderr
    assert not dest.exists()
