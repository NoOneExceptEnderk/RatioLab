#!/bin/sh
# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
# Produce a real drag-to-Applications DMG from a native, verified .app.
set -eu
if [ "$(uname -s)" != Darwin ]; then
    printf '%s\n' 'Build the macOS application and DMG on macOS.' >&2
    exit 1
fi
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
arch=$(uname -m)
bundle=${1:-$root/dist/bundles/macos-$arch/RatioLab.app}
output=${2:-$root/dist/installers}
python=${RATIOLAB_BUILD_PYTHON:-python3}
"$python" "$root/scripts/build-bundle.py" --verify-only "$bundle"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$bundle"
version=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$bundle/Contents/Info.plist")
identifier=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$bundle/Contents/Info.plist")
if [ "$identifier" != local.solidcraft.reducers ]; then
    printf '%s\n' 'The application bundle has the wrong identifier.' >&2
    exit 1
fi
mkdir -p "$output"
output=$(CDPATH= cd -- "$output" && pwd)
staging=$(mktemp -d "${TMPDIR:-/tmp}/ratiolab-dmg.XXXXXX")
trap 'rm -rf "$staging"' EXIT HUP INT TERM
/usr/bin/ditto "$bundle" "$staging/RatioLab.app"
ln -s /Applications "$staging/Applications"
cp "$(dirname -- "$bundle")/bundle-manifest.json" "$staging/bundle-manifest.json"
cat > "$staging/Install RatioLab.txt" <<'TEXT'
Drag RatioLab.app to Applications, then open it from Applications.
Python, GTK and the app's native dependencies are included. No Homebrew or
additional Python installation is needed on the destination computer.
Third-party notices are inside RatioLab.app/Contents/Resources/notices.
To uninstall, move RatioLab.app to Trash. User preferences and exports are kept.
TEXT
target="$output/RatioLab-$version-macos-$arch.dmg"
/usr/bin/hdiutil create -volname "RatioLab $version" -srcfolder "$staging" -format UDZO -ov "$target"
if [ -n "${RATIOLAB_CODESIGN_IDENTITY:-}" ]; then
    /usr/bin/codesign --force --sign "$RATIOLAB_CODESIGN_IDENTITY" --timestamp "$target"
fi
# No identity or Apple account is invented. A maintainer may opt in using an
# existing notarytool keychain profile, after providing a Developer ID identity.
if [ -n "${RATIOLAB_NOTARY_PROFILE:-}" ]; then
    if [ -z "${RATIOLAB_CODESIGN_IDENTITY:-}" ]; then
        printf '%s\n' 'Notarization requires RATIOLAB_CODESIGN_IDENTITY.' >&2
        exit 1
    fi
    /usr/bin/xcrun notarytool submit "$target" --keychain-profile "$RATIOLAB_NOTARY_PROFILE" --wait
    /usr/bin/xcrun stapler staple "$target"
    /usr/bin/xcrun stapler validate "$target"
fi
(
    cd "$output"
    /usr/bin/shasum -a 256 "RatioLab-$version-macos-$arch.dmg"
) > "$target.sha256"
printf '%s\n' "$target"
