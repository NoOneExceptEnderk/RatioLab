#!/usr/bin/env bash
# Prepare the pinned Wasm toolchain in the disposable Pages build container.
set -euo pipefail

repository_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
site_python=${RATIOLAB_SITE_PYTHON:-python3}
rust_channel=$("$site_python" -c 'import pathlib, sys, tomllib; print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text())["toolchain"]["channel"])' "$repository_dir/rust-toolchain.toml")
export PATH="${CARGO_HOME:-"$HOME/.cargo"}/bin:$PATH"

if ! command -v rustup >/dev/null 2>&1; then
  rustup_installer=$(mktemp)
  trap 'rm -f "$rustup_installer"' EXIT
  curl --proto '=https' --tlsv1.2 --fail --silent --show-error https://sh.rustup.rs -o "$rustup_installer"
  sh "$rustup_installer" -y --no-modify-path --profile minimal --default-toolchain "$rust_channel" --target wasm32-unknown-unknown
  rm -f "$rustup_installer"
  trap - EXIT
else
  rustup toolchain install "$rust_channel" --profile minimal --target wasm32-unknown-unknown
fi

exec bash "$repository_dir/website/build.sh" "$@"
