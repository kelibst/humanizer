#!/usr/bin/env bash
set -euo pipefail

# One-command installer for humanizer.
# Usage: curl -fsSL https://github.com/kelibst/humanizer/releases/latest/download/install.sh | bash

RELEASE_BASE="https://github.com/kelibst/humanizer/releases/latest/download"
INSTALL_DIR="$HOME/.local/bin"
BINARY_NAME="humanize"

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

print_step() { printf '\n\033[1;34m==> %s\033[0m\n' "$1"; }
print_ok()   { printf '\033[1;32m✓ %s\033[0m\n' "$1"; }
print_warn() { printf '\033[1;33m! %s\033[0m\n' "$1"; }
print_err()  { printf '\033[1;31mError: %s\033[0m\n' "$1" >&2; }

# --------------------------------------------------------------------------
# Step 1: Detect OS and architecture
# --------------------------------------------------------------------------

detect_platform() {
    local os arch
    os="$(uname -s)"
    arch="$(uname -m)"

    case "$os" in
        Linux)  ;;
        Darwin) ;;
        *)
            print_err "Unsupported OS: $os. humanizer runs on Linux and macOS only."
            exit 1
            ;;
    esac

    case "$arch" in
        x86_64)          ;;
        arm64|aarch64)   arch="arm64" ;;
        *)
            print_err "Unsupported architecture: $arch."
            exit 1
            ;;
    esac

    # Normalise Darwin → macos
    if [ "$os" = "Darwin" ]; then
        PLATFORM="macos-${arch}"
    else
        PLATFORM="linux-${arch}"
    fi

    print_ok "Platform: $PLATFORM"
}

# --------------------------------------------------------------------------
# Step 2: Install Ollama if missing
# --------------------------------------------------------------------------

install_ollama() {
    if command -v ollama &>/dev/null; then
        print_ok "Ollama already installed ($(ollama --version 2>/dev/null || echo 'version unknown'))"
        return
    fi

    print_step "Installing Ollama…"
    local os
    os="$(uname -s)"
    if [ "$os" = "Linux" ]; then
        curl -fsSL https://ollama.com/install.sh | sh
        print_ok "Ollama installed"
    else
        # macOS — requires the desktop app or brew; we cannot install silently
        print_warn "Ollama is not installed."
        print_warn "Download it from https://ollama.com/download and install it, then press Enter to continue."
        read -r
        if ! command -v ollama &>/dev/null; then
            print_err "Ollama still not found. Please install it and re-run this script."
            exit 1
        fi
        print_ok "Ollama found"
    fi
}

# --------------------------------------------------------------------------
# Step 3: Start Ollama daemon if not already running
# --------------------------------------------------------------------------

start_ollama() {
    if ollama list &>/dev/null; then
        print_ok "Ollama daemon is running"
        return
    fi

    print_step "Starting Ollama daemon…"
    # Start in background; give it two seconds to come up
    ollama serve &>/dev/null &
    sleep 2
    if ollama list &>/dev/null; then
        print_ok "Ollama daemon started"
    else
        print_warn "Could not confirm Ollama daemon started. Continuing anyway — it may still be initialising."
    fi
}

# --------------------------------------------------------------------------
# Step 4: Pull gemma3:4b if not already present
# --------------------------------------------------------------------------

pull_model() {
    if ollama list 2>/dev/null | grep -q "gemma3:4b"; then
        print_ok "AI model gemma3:4b already present"
        return
    fi

    print_step "Downloading AI model (gemma3:4b, ~2 GB) — this takes a few minutes on first run."
    ollama pull gemma3:4b
    print_ok "AI model downloaded"
}

# --------------------------------------------------------------------------
# Step 5: Download the humanize binary
# --------------------------------------------------------------------------

download_binary() {
    print_step "Downloading humanize binary…"
    mkdir -p "$INSTALL_DIR"

    local url="${RELEASE_BASE}/${BINARY_NAME}-${PLATFORM}"
    local dest="${INSTALL_DIR}/${BINARY_NAME}"

    curl -fL --progress-bar "$url" -o "$dest"
    chmod +x "$dest"
    print_ok "Binary installed at $dest"
}

# --------------------------------------------------------------------------
# Step 6: Add ~/.local/bin to PATH if not already there
# --------------------------------------------------------------------------

ensure_path() {
    case ":${PATH}:" in
        *":${INSTALL_DIR}:"*)
            # Already on PATH — nothing to do
            return
            ;;
    esac

    print_step "Adding $INSTALL_DIR to PATH…"
    local export_line="export PATH=\"\$HOME/.local/bin:\$PATH\""

    # Append to shell RC files that already exist
    for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
        if [ -f "$rc" ]; then
            # Avoid duplicate entries
            if ! grep -qF "$INSTALL_DIR" "$rc"; then
                printf '\n# Added by humanizer installer\n%s\n' "$export_line" >> "$rc"
                print_ok "Updated $rc"
            fi
        fi
    done

    # Export in the current shell so the success banner can use humanize directly
    export PATH="$INSTALL_DIR:$PATH"
    PATH_CHANGED=1
}

# --------------------------------------------------------------------------
# Step 7: Success banner
# --------------------------------------------------------------------------

print_banner() {
    printf '\n'
    printf '\033[1;32m✓ Humanizer installed!\033[0m\n'
    printf '\n'
    printf '  Run:  humanize\n'
    printf '  Docs: https://github.com/kelibst/humanizer\n'
    printf '\n'
    printf '  First time? Just run \033[1mhumanize\033[0m — no setup needed.\n'
    printf '\n'

    if [ "${PATH_CHANGED:-0}" = "1" ]; then
        printf '\033[1;33m! Your PATH was updated. Restart your terminal, or run:\033[0m\n'
        printf '    source ~/.bashrc   # (or ~/.zshrc on Zsh)\n'
        printf '\n'
    fi
}

# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

PATH_CHANGED=0

print_step "humanizer installer"

detect_platform
install_ollama
start_ollama
pull_model
download_binary
ensure_path
print_banner
