#!/bin/sh
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
# Source this file to choose a Homebrew Python supported by installed pygobject3.
# Homebrew can build its bindings for multiple Python formulae; the user's
# python3 on PATH can be another version entirely.
choose_macos_python() {
    brew_prefix=$(brew --prefix)
    for python_formula in $(brew deps --include-build pygobject3 | LC_ALL=C sort -r); do
        case "$python_formula" in
            python@*)
                candidate="$brew_prefix/opt/$python_formula/libexec/bin/python"
                if [ -x "$candidate" ] && "$candidate" -c 'import gi,cairo; gi.require_version("Gtk","4.0"); from gi.repository import Gtk; assert Gtk.check_version(4,12,0) is None' >/dev/null 2>&1; then
                    printf '%s\n' "$candidate"
                    return 0
                fi
                ;;
        esac
    done
    printf '%s\n' 'No Homebrew Python matching pygobject3 can import GTK 4 and Cairo. Reinstall pygobject3/gtk4 or inspect brew info pygobject3.' >&2
    return 1
}
