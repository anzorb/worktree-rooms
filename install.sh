#!/usr/bin/env bash
set -e

REPO="https://raw.githubusercontent.com/anzorb/worktree-rooms/main"
BIN="$HOME/bin"
MARKER="# rooms — worktree manager shell wrapper + completion"

echo "Installing rooms…"
echo ""

# 1. Check Python 3.10+
if ! python3 -c "import sys; assert sys.version_info >= (3, 10)" 2>/dev/null; then
  echo "Error: Python 3.10 or later is required."
  echo "Install it via Homebrew:  brew install python"
  exit 1
fi

# 2. Check git
if ! command -v git &>/dev/null; then
  echo "Error: git is required but not found."
  exit 1
fi

# 3. Warn if gh CLI missing
if ! command -v gh &>/dev/null; then
  echo "Warning: 'gh' CLI not found — PR and CI status will be unavailable."
  echo "         Install it via Homebrew:  brew install gh"
  echo ""
fi

# 4. Install binary
mkdir -p "$BIN"
curl -fsSL "$REPO/rooms" -o "$BIN/rooms"
chmod +x "$BIN/rooms"
echo "✓ Binary installed to $BIN/rooms"

# 5. Ensure ~/bin is on PATH
if [[ ":$PATH:" != *":$BIN:"* ]]; then
  echo ""
  echo "Note: $BIN is not on your PATH."
  echo "Add this to your shell config:  export PATH=\"\$HOME/bin:\$PATH\""
  echo ""
fi

# ---------------------------------------------------------------------------
# Shell config — detect which shells are configured and install for each
# ---------------------------------------------------------------------------

_append_to_file() {
  local file="$1" url="$2"
  if ! grep -qF "$MARKER" "$file" 2>/dev/null; then
    echo "" >> "$file"
    curl -fsSL "$url" >> "$file"
    echo "✓ Shell config added to $file"
  else
    echo "✓ Shell config already present in $file — skipping"
  fi
}

installed_any_shell=false

# zsh
if [[ -f "$HOME/.zshrc" ]]; then
  _append_to_file "$HOME/.zshrc" "$REPO/shell/rooms.zsh"
  installed_any_shell=true
fi

# bash — prefer .bashrc, fall back to .bash_profile
if [[ -f "$HOME/.bashrc" ]]; then
  _append_to_file "$HOME/.bashrc" "$REPO/shell/rooms.bash"
  installed_any_shell=true
elif [[ -f "$HOME/.bash_profile" ]]; then
  _append_to_file "$HOME/.bash_profile" "$REPO/shell/rooms.bash"
  installed_any_shell=true
fi

# fish
if [[ -d "$HOME/.config/fish" ]]; then
  mkdir -p "$HOME/.config/fish/conf.d"
  FISH_CONF="$HOME/.config/fish/conf.d/rooms.fish"
  curl -fsSL "$REPO/shell/rooms.fish" -o "$FISH_CONF"
  echo "✓ Fish config installed to $FISH_CONF"
  installed_any_shell=true
fi

if [[ "$installed_any_shell" == false ]]; then
  echo ""
  echo "No shell config files detected. Manually source the appropriate file:"
  echo "  zsh:  source $REPO/shell/rooms.zsh  (or append to ~/.zshrc)"
  echo "  bash: source $REPO/shell/rooms.bash  (or append to ~/.bashrc)"
  echo "  fish: copy $REPO/shell/rooms.fish to ~/.config/fish/conf.d/rooms.fish"
fi

echo ""
echo "Done! Reload your shell:"
echo ""
echo "  source ~/.zshrc          # zsh"
echo "  source ~/.bashrc         # bash"
echo "  source ~/.config/fish/conf.d/rooms.fish  # fish (or open a new terminal)"
echo ""
echo "Then set up your first room:"
echo ""
echo "  rooms add <path-to-repo> <room-name>"
echo ""
echo "Rooms will be created under ~/rooms by default."
echo "Change this with:  rooms config set-base-path <path>"
