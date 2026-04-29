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

function _rooms_complete() {
  local -a commands
  commands=(add ls free remove move occupy purge)

  if (( CURRENT == 2 )); then
    _describe 'command' commands
    return
  fi

  local cmd=$words[2]
  case $cmd in
    occupy)
      if (( CURRENT == 3 )); then
        local -a names
        names=(${(f)"$(command rooms _names 2>/dev/null)"})
        # Allow slash in completions (project/room format)
        compset -P '*/'
        _describe 'room' names
      elif (( CURRENT == 4 )); then
        local -a branches
        branches=(${(f)"$(command rooms _branches $words[3] 2>/dev/null)"})
        _describe 'branch' branches
      fi
      ;;
    free|remove|move)
      local -a names
      names=(${(f)"$(command rooms _names 2>/dev/null)"})
      compset -P '*/'
      _describe 'room' names
      ;;
    add)
      if (( CURRENT == 4 )); then
        local -a names
        names=(${(f)"$(command rooms _names 2>/dev/null)"})
        _describe 'room' names
      fi
      ;;
  esac
}
compdef _rooms_complete rooms
