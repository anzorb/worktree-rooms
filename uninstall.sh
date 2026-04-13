#!/usr/bin/env bash
set -e

BIN="$HOME/bin/rooms"
START_MARKER="# rooms — worktree manager shell wrapper + completion"

echo "Uninstalling rooms…"
echo ""

# 1. Remove binary
if [[ -f "$BIN" ]]; then
  rm "$BIN"
  echo "✓ Removed $BIN"
else
  echo "  Binary not found at $BIN — skipping"
fi

# ---------------------------------------------------------------------------
# Strip shell config blocks
# ---------------------------------------------------------------------------

# Strip the marker-delimited block from a file, including the blank line before it.
# Usage: _strip_from_file <file> <end-marker>
_strip_from_file() {
  local file="$1" end_marker="$2"
  if grep -qF "$START_MARKER" "$file" 2>/dev/null; then
    awk -v start="$START_MARKER" -v end="$end_marker" '
      /^$/ { blank = $0; next }
      $0 ~ start { skip = 1; blank = ""; next }
      skip && $0 ~ end { skip = 0; next }
      skip { next }
      { if (blank != "") print blank; blank = ""; print }
    ' "$file" > "$file.tmp" && mv "$file.tmp" "$file"
    echo "✓ Shell config removed from $file"
  fi
}

# zsh
[[ -f "$HOME/.zshrc" ]] && _strip_from_file "$HOME/.zshrc" "compdef _rooms_complete rooms"

# bash
[[ -f "$HOME/.bashrc" ]]       && _strip_from_file "$HOME/.bashrc"       "complete -F _rooms_complete rooms"
[[ -f "$HOME/.bash_profile" ]] && _strip_from_file "$HOME/.bash_profile" "complete -F _rooms_complete rooms"

# fish
FISH_CONF="$HOME/.config/fish/conf.d/rooms.fish"
if [[ -f "$FISH_CONF" ]]; then
  rm "$FISH_CONF"
  echo "✓ Removed $FISH_CONF"
fi

echo ""
echo "Done. Config file at ~/.config/rooms/config.json was left intact."
echo "Remove it manually if you no longer need it:"
echo ""
echo "  rm -rf ~/.config/rooms"
