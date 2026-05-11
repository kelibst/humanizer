#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
npm run compile
npx vsce package -o humanizer.vsix --no-dependencies
code --uninstall-extension sis-caro.sis-caro-humanizer 2>/dev/null || true
code --install-extension humanizer.vsix
# Also copy compiled files directly so the installed extension updates immediately
INSTALL_DIR="$HOME/.vscode/extensions/sis-caro.sis-caro-humanizer-1.0.0"
if [ -d "$INSTALL_DIR" ]; then
  cp -r out/. "$INSTALL_DIR/out/"
  cp src/webview/sidebar.html "$INSTALL_DIR/src/webview/sidebar.html"
  cp src/webview/sidebar.css  "$INSTALL_DIR/src/webview/sidebar.css"
fi
echo "Extension installed. Reload VS Code window (Ctrl+Shift+P → Reload Window)."
