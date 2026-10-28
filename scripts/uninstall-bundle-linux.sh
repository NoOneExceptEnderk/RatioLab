#!/bin/sh
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
# Preferences and exported projects are deliberately kept outside this directory.
set -eu
installation=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
stage_only=0
if [ "${1:-}" = --stage-only ] && [ "$#" = 2 ]; then
    installation=$(CDPATH= cd -- "$2" && pwd -P)
    stage_only=1
fi
if [ "$(cat "$installation/.ratiolab-installation" 2>/dev/null)" != ratiolab.bundle.v1 ]; then
    printf '%s\n' 'This folder is not a RatioLab user installation.' >&2
    exit 1
fi
if ! [ -f "$installation/installed-files.txt" ]; then
    printf '%s\n' 'The installed file inventory is missing. No files have been removed.' >&2
    exit 1
fi
data_home=${XDG_DATA_HOME:-$HOME/.local/share}
desktop_file=$data_home/applications/local.solidcraft.reducers.desktop
remove_launcher() {
    if [ -f "$1" ] && grep -F -- "$installation/" "$1" >/dev/null 2>&1; then rm -- "$1"; fi
}
if [ "$stage_only" = 0 ]; then remove_launcher "$desktop_file"; fi
if [ "$stage_only" = 0 ] && command -v xdg-user-dir >/dev/null 2>&1; then
    desktop=$(xdg-user-dir DESKTOP)
    case "$desktop" in /*) remove_launcher "$desktop/RatioLab.desktop" ;; esac
fi
while IFS= read -r relative; do
    case "$relative" in ''|/*|..|../*|*/../*|*/..) printf '%s\n' 'Unsafe installed file inventory; stopping.' >&2; exit 1 ;; esac
    target=$installation/$relative
    if [ -f "$target" ] || [ -L "$target" ]; then
        # A modified symlink in a parent directory must never redirect a
        # removal outside this installation. The final symlink itself is safe.
        parent=$(realpath -- "$(dirname -- "$target")")
        case "$parent/" in "$installation/"*) rm -f -- "$target" ;; esac
    fi
done < "$installation/installed-files.txt"
rm -f -- "$installation/.ratiolab-installation" "$installation/installed-files.txt" \
    "$installation/uninstall.sh" "$installation/installation-check.log"
find "$installation" -mindepth 1 -depth -type d -empty -delete
if [ "$stage_only" = 0 ]; then rmdir -- "$installation" 2>/dev/null || true; fi
if [ "$stage_only" = 0 ] && command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$data_home/applications" >/dev/null 2>&1 || true
fi
if [ "$stage_only" = 0 ]; then printf '%s\n' 'RatioLab removed. Your preferences and exported files have been kept.'; fi
