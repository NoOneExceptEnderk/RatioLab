#!/bin/sh
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
# Installs only the bundled application. No root access or package manager needed.
set -eu
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
destination=${XDG_DATA_HOME:-$HOME/.local/share}/ratiolab/app
menu=1
quiet=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --destination) [ "$#" -ge 2 ] || exit 2; destination=$2; shift 2 ;;
        --no-desktop) menu=0; shift ;;
        --yes) quiet=1; shift ;;
        --help) printf '%s\n' 'Install RatioLab with GTK and Python included.' 'Usage: sh install.sh [--destination /absolute/folder] [--no-desktop] [--yes]'; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
    esac
done
case "$destination" in /*) ;; *) printf '%s\n' 'Installation path must be absolute.' >&2; exit 2 ;; esac
case "$destination" in /|"$HOME"|/usr|/usr/local|/opt) printf '%s\n' 'Choose a dedicated RatioLab folder.' >&2; exit 2 ;; esac
if [ -L "$destination" ]; then printf '%s\n' 'The installation folder must not be a symbolic link.' >&2; exit 1; fi
if [ -e "$destination" ] && [ "$(cat "$destination/.ratiolab-installation" 2>/dev/null || true)" != ratiolab.bundle.v1 ]; then
    printf 'The destination already exists and is not a RatioLab bundle: %s\n' "$destination" >&2
    exit 1
fi
parent=$(dirname -- "$destination")
mkdir -p -- "$parent"
stage=$(mktemp -d "$parent/.ratiolab-install.XXXXXX")
backup=
cleanup() {
    if [ -n "$stage" ] && [ -d "$stage" ]; then rm -rf -- "$stage"; fi
    if [ -n "$backup" ] && [ -d "$backup/previous" ] && ! [ -e "$destination" ]; then
        mv -- "$backup/previous" "$destination"
    fi
    if [ -n "$backup" ] && [ -d "$backup" ]; then rm -rf -- "$backup"; fi
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
if [ -d "$destination" ]; then
    cp -a -- "$destination/." "$stage/"
    # Keep unlisted projects even when a user chose the application folder for
    # exports. Only the previous bundle's recorded runtime files are replaced.
    sh "$source_dir/uninstall.sh" --stage-only "$stage"
fi
cp -a -- "$source_dir/RatioLab/." "$stage/"
cp -- "$source_dir/uninstall.sh" "$stage/uninstall.sh"
cp -- "$source_dir/installed-files.txt" "$stage/installed-files.txt"
chmod 755 "$stage/uninstall.sh"
printf '%s\n' 'ratiolab.bundle.v1' > "$stage/.ratiolab-installation"
printf '%s\n' 'Checking the bundled runtime…'
if ! "$stage/RatioLab" --self-test > "$stage/installation-check.log" 2>&1; then
    cat "$stage/installation-check.log" >&2
    printf '%s\n' 'The bundled application cannot run on this system; the previous installation was preserved.' >&2
    exit 1
fi
if [ -d "$destination" ]; then
    backup=$(mktemp -d "$parent/.ratiolab-backup.XXXXXX")
    mv -- "$destination" "$backup/previous"
fi
mv -- "$stage" "$destination"
stage=
if [ "$menu" = 1 ]; then
    if ! "$destination/RatioLab" --install-desktop; then
        printf 'RatioLab is installed. The application menu could not be updated; launch %s/RatioLab.\n' "$destination" >&2
    fi
fi
printf 'RatioLab installed in %s\nUninstall with: "%s/uninstall.sh"\n' "$destination" "$destination"
if [ "$quiet" = 0 ] && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v zenity >/dev/null 2>&1; then
    zenity --info --no-markup --title=RatioLab --text="RatioLab is installed. Open it from your application menu.\n\nLocation: $destination" 2>/dev/null || true
fi
