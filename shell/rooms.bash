# rooms — worktree manager shell wrapper + completion
function rooms() {
  if [[ "$1" == "occupy" ]]; then
    local target
    target=$(command rooms _occupy "${@:2}" 2>&1)
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
      echo "$target" >&2
      return $exit_code
    fi
    # Last line is the path; everything before it is status messages
    local path="${target##*$'\n'}"
    local msgs="${target%$'\n'*}"
    [[ -n "$msgs" ]] && echo "$msgs"
    cd "$path"
  else
    command rooms "$@"
  fi
}

_rooms_complete() {
  local cur="${COMP_WORDS[COMP_CWORD]}"
  local cmd="${COMP_WORDS[1]}"

  if [[ $COMP_CWORD -eq 1 ]]; then
    COMPREPLY=($(compgen -W "add ls free move occupy purge config" -- "$cur"))
    return
  fi

  case $cmd in
    occupy)
      if [[ $COMP_CWORD -eq 2 ]]; then
        local names
        names=$(command rooms _names 2>/dev/null)
        COMPREPLY=($(compgen -W "$names" -- "$cur"))
      elif [[ $COMP_CWORD -eq 3 ]]; then
        local branches
        branches=$(command rooms _branches "${COMP_WORDS[2]}" 2>/dev/null)
        COMPREPLY=($(compgen -W "$branches" -- "$cur"))
      fi
      ;;
    free|move)
      local names
      names=$(command rooms _names 2>/dev/null)
      COMPREPLY=($(compgen -W "$names" -- "$cur"))
      ;;
  esac
}
complete -F _rooms_complete rooms
