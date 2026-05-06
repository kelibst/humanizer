#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
npm run compile
npx vsce package -o humanizer.vsix --no-dependencies
code --uninstall-extension humanizer-vscode 2>/dev/null || true
code --install-extension humanizer.vsix
echo "Extension installed. Reload VS Code window (Ctrl+Shift+P → Reload Window)."
