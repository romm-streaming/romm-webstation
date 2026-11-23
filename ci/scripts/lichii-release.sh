#!/bin/sh
# Pick the Lichii release the image installs and print "<tag> <sha256>".
#
#   lichii-release.sh            newest eligible release
#   lichii-release.sh <tag>      that release, the LICHII_VERSION override
#
# Only github.com/zortos293/Lichii releases count, never lichii.org or a
# mirror. Without a tag the newest release that is not a draft or prerelease
# and was published at least 24 hours ago wins, so a broken daily build has a
# day to be pulled before an image picks it up. Either way the release must
# carry the asset with a sha256 digest from GitHub; the Dockerfile checks the
# download against it. A missing release, asset or digest exits non zero.
#
# GH_API and LICHII_NOW (epoch seconds) exist for ci/test_lichii_release.py.
set -eu

here=$(dirname "$0")
api=${GH_API:-${here}/gh-api.sh}
repo=repos/zortos293/Lichii
asset=lichii-linux-x86_64.tar.gz
tag=${1:-}
# Tags go into a download URL; their release tags are build-NNN.
valid='^[A-Za-z0-9._-]+$'

if [ -n "${tag}" ]; then
  if ! printf '%s' "${tag}" | grep -Eq "${valid}"; then
    echo "not a Lichii release tag: ${tag}" >&2
    exit 2
  fi
  release=$("${api}" "${repo}/releases/tags/${tag}")
else
  release=$("${api}" "${repo}/releases?per_page=30" | jq -ec \
    --argjson now "${LICHII_NOW:-$(date +%s)}" '
      [.[] | select((.draft | not) and (.prerelease | not))
           | select((.published_at | fromdateiso8601) <= $now - 86400)]
      | sort_by(.published_at) | last // error("no Lichii release is older than 24 hours")')
fi

printf '%s\n' "${release}" | jq -er --arg a "${asset}" --arg valid "${valid}" '
  .tag_name as $t
  | if ($t | type == "string" and test($valid)) then . else error("unexpected tag \($t)") end
  | ([.assets // [] | .[] | select(.name == $a)] | first
      // error("release \($t) has no \($a)")) as $f
  | ($f.digest // "") as $d
  | if ($d | test("^sha256:[0-9a-f]{64}$")) then "\($t) \($d[7:])"
    else error("\($t) \($a) has no sha256 digest") end'
