#!/bin/sh -e
cd "$(dirname "$0")"
pkgver=${PKGVER:-0.1.18}
git archive --prefix="FanslyRecorder-$pkgver/" HEAD -o "FanslyRecorder-$pkgver.tar.gz"
makepkg "$@"
