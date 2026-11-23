#!/bin/sh
# Check a downloaded Lichii tarball against its GitHub digest and unpack it.
#
#   lichii-install.sh <tarball> <sha256> <dest>
#
# A mismatch exits non zero before anything is unpacked, which fails the
# image build. The tarball's top directory lichii/ is an unpacked AppDir
# (AppRun, usr/bin, usr/lib), so it runs without FUSE or --appimage-extract.
set -eu

tarball=${1:?tarball}
sha256=${2:?sha256}
dest=${3:?destination}

echo "${sha256}  ${tarball}" | sha256sum -c -
work=$(mktemp -d)
tar xzf "${tarball}" -C "${work}" --no-same-owner
test -x "${work}/lichii/usr/bin/lichii"
mv "${work}/lichii" "${dest}"
rmdir "${work}"
chmod -R go-w,a+rX "${dest}"
