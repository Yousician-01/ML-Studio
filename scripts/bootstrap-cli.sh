#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
bin=${MLS_BIN_DIR:-"$HOME/.local/bin"}
case "$(uname -s)/$(uname -m)" in
  Linux/x86_64) asset=mls-linux-x64 ;;
  Darwin/arm64) asset=mls-macos-arm64 ;;
  Darwin/x86_64) asset=mls-macos-x64 ;;
  *) echo 'Unsupported CLI bootstrap platform' >&2; exit 1 ;;
esac
case "${1:-}" in
  --source)
    command -v cargo >/dev/null 2>&1 || { echo 'Install Rust from https://rustup.rs or obtain verified local CLI assets. No runtime is downloaded by this script.' >&2; exit 1; }
    cargo build --manifest-path "$repo/cli/Cargo.toml" --release --locked
    mkdir -p "$bin"
    cp "$repo/cli/target/release/mls" "$bin/mls"
    ;;
  --assets)
    directory=${2:?Pass the directory containing verified local binaries and SHA256SUMS}
    expected=$(awk -v name="$asset" '$2 == name { print $1 }' "$directory/SHA256SUMS")
    test "${#expected}" -eq 64 || { echo 'Missing/ambiguous artifact checksum' >&2; exit 1; }
    if command -v sha256sum >/dev/null 2>&1; then
      actual=$(sha256sum "$directory/$asset" | awk '{print $1}')
    else
      actual=$(shasum -a 256 "$directory/$asset" | awk '{print $1}')
    fi
    test "$expected" = "$actual" || { echo 'CLI checksum mismatch. Nothing installed.' >&2; exit 1; }
    mkdir -p "$bin"
    cp "$directory/$asset" "$bin/mls"
    ;;
  *) echo 'Usage: sh scripts/bootstrap-cli.sh --source | --assets <verified local artifact directory>' >&2; exit 1 ;;
esac
chmod 755 "$bin/mls"
printf 'CLI installed: %s/mls\nAdd %s to PATH manually, or use its full path.\n' "$bin" "$bin"
printf 'From the checkout: mls install, then mls start\n'
