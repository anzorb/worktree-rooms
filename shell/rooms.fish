# rooms — worktree manager shell wrapper + completion
# Install: copy to ~/.config/fish/conf.d/rooms.fish

function rooms
  if test "$argv[1]" = "occupy"
    set -l output (command rooms _occupy $argv[2..] 2>&1)
    set -l exit_code $status
    if test $exit_code -ne 0
      echo $output >&2
      return $exit_code
    end
    # Last line is the path; everything before is status messages
    set -l lines (string split \n $output)
    set -l path $lines[-1]
    set -l msgs (string join \n $lines[1..-2])
    test -n "$msgs" && echo $msgs
    cd $path
  else
    command rooms $argv
  end
end

# ---------------------------------------------------------------------------
# Completions
# ---------------------------------------------------------------------------

complete -c rooms -f

# Subcommands
complete -c rooms -n "not __fish_seen_subcommand_from add ls free move occupy purge config" \
  -a "add"    -d "Add a new room"
complete -c rooms -n "not __fish_seen_subcommand_from add ls free move occupy purge config" \
  -a "ls"     -d "List all rooms"
complete -c rooms -n "not __fish_seen_subcommand_from add ls free move occupy purge config" \
  -a "free"   -d "Free a room"
complete -c rooms -n "not __fish_seen_subcommand_from add ls free move occupy purge config" \
  -a "move"   -d "Move a branch between rooms"
complete -c rooms -n "not __fish_seen_subcommand_from add ls free move occupy purge config" \
  -a "occupy" -d "Enter a room and optionally check out a branch"
complete -c rooms -n "not __fish_seen_subcommand_from add ls free move occupy purge config" \
  -a "purge"  -d "Purge merged/pushed rooms"
complete -c rooms -n "not __fish_seen_subcommand_from add ls free move occupy purge config" \
  -a "config" -d "Configure rooms settings"

# Helper: true when we're on the first argument after the subcommand
function __rooms_on_first_arg
  test (count (commandline -opc)) -eq 2
end

# Helper: true when occupy and we're on the second argument (branch)
function __rooms_on_branch_arg
  set -l tokens (commandline -opc)
  __fish_seen_subcommand_from occupy && test (count $tokens) -ge 3
end

# Room name completions for free / move / occupy (first arg)
complete -c rooms -n "__fish_seen_subcommand_from free move occupy; and __rooms_on_first_arg" \
  -a "(command rooms _names 2>/dev/null)"

# Branch completions for occupy (second arg)
complete -c rooms -n "__rooms_on_branch_arg" \
  -a "(command rooms _branches (commandline -opc)[3] 2>/dev/null)"
