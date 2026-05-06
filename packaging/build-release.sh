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

VERSION=${1:-"1.5.0"}

# Resolve repo root relative to this script so the script can be called
# from any working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

echo "Building humanize v${VERSION}..."

# Detect platform for the release artifact name.
# On Windows under MSYS2/Git Bash/Cygwin, uname -s returns MSYS_NT-*, MINGW64_NT-*,
# CYGWIN_NT-* etc. We detect all three and set IS_WINDOWS accordingly.
OS="$(uname -s)"
ARCH="$(uname -m)"

IS_WINDOWS=0
case "$OS" in
    MSYS_NT-*|MINGW*|CYGWIN*)
        IS_WINDOWS=1
        OS_SLUG="windows"
        ;;
    Linux)
        OS_SLUG="linux"
        ;;
    Darwin)
        OS_SLUG="macos"
        ;;
    *)
        echo "Unsupported OS: $OS" >&2
        exit 1
        ;;
esac

case "$ARCH" in
    x86_64|AMD64|amd64)  ARCH_SLUG="x86_64" ;;
    arm64|aarch64|ARM64) ARCH_SLUG="arm64" ;;
    *)
        echo "Unsupported arch: $ARCH" >&2
        exit 1
        ;;
esac

# On Windows, the venv uses Scripts/ instead of bin/ and the binary has
# an .exe suffix.
if [ "$IS_WINDOWS" -eq 1 ]; then
    VENV_BIN=".venv/Scripts"
    BIN_SUFFIX=".exe"
    BINARY_NAME="humanize.exe"
else
    VENV_BIN=".venv/bin"
    BIN_SUFFIX=""
    BINARY_NAME="humanize"
fi

ARTIFACT_NAME="humanize-${OS_SLUG}-${ARCH_SLUG}${BIN_SUFFIX}"

# Build
"${VENV_BIN}/python" -m PyInstaller packaging/pyinstaller.spec --clean --noconfirm
echo "Binary: dist/${BINARY_NAME} ($(du -sh "dist/${BINARY_NAME}" | cut -f1))"

# Package
mkdir -p dist/release
cp "dist/${BINARY_NAME}" "dist/release/${ARTIFACT_NAME}"
if [ -f install.sh ]; then
    cp install.sh dist/release/
fi
echo "Release artifacts in dist/release/"
ls -lh dist/release/

echo ""
echo "Upload to GitHub Releases:"
echo "  gh release create v${VERSION} dist/release/* \\"
echo "    --title 'humanizer v${VERSION}' \\"
echo "    --notes-file packaging/RELEASE_NOTES_v${VERSION}.md"
