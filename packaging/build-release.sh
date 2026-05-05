#!/usr/bin/env bash
set -euo pipefail

# Usage: ./packaging/build-release.sh [version]
#
# Builds the humanize PyInstaller binary for the current platform and
# packages it alongside install.sh into dist/release/ ready for upload
# to a GitHub Release.
#
# Run from the repo root:
#   ./packaging/build-release.sh 1.2.0

VERSION=${1:-"1.2.0"}

# Resolve repo root relative to this script so the script can be called
# from any working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

echo "Building humanize v${VERSION}..."

# Detect platform for the release artifact name
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
    Linux)  OS_SLUG="linux" ;;
    Darwin) OS_SLUG="macos" ;;
    *)
        echo "Unsupported OS: $OS" >&2
        exit 1
        ;;
esac

case "$ARCH" in
    x86_64)        ARCH_SLUG="x86_64" ;;
    arm64|aarch64) ARCH_SLUG="arm64" ;;
    *)
        echo "Unsupported arch: $ARCH" >&2
        exit 1
        ;;
esac

ARTIFACT_NAME="humanize-${OS_SLUG}-${ARCH_SLUG}"

# Build
.venv/bin/python -m PyInstaller packaging/pyinstaller.spec --clean --noconfirm
echo "Binary: dist/humanize ($(du -sh dist/humanize | cut -f1))"

# Package
mkdir -p dist/release
cp dist/humanize "dist/release/${ARTIFACT_NAME}"
cp install.sh dist/release/
echo "Release artifacts in dist/release/"
ls -lh dist/release/

echo ""
echo "Upload to GitHub Releases:"
echo "  gh release create v${VERSION} dist/release/* \\"
echo "    --title 'humanizer v${VERSION}' \\"
echo "    --notes-file packaging/RELEASE_NOTES_v${VERSION}.md"
