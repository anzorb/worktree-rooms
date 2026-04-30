"""Tests for rooms commands: cmd_free, cmd_move, cmd_remove, _do_occupy, cmd_purge, cmd_config."""

import pytest

from conftest import make_run, make_room, make_cfg


# ---------------------------------------------------------------------------
# cmd_free
# ---------------------------------------------------------------------------

class TestCmdFree:
    def _cfg(self, worktree_path):
        room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree_path))
        return make_cfg(room)

    def test_no_args_exits(self, rooms):
        with pytest.raises(SystemExit):
            rooms.cmd_free([])

    def test_room_not_found_exits(self, rooms, monkeypatch):
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg())
        with pytest.raises(SystemExit):
            rooms.cmd_free(["myproject/ghost"])

    def test_already_free_prints_message(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        monkeypatch.setattr(rooms, "load_config", lambda: self._cfg(worktree))
        # current_branch returns placeholder "room-1"
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),
        }))
        rooms.cmd_free(["myproject/room-1"])
        out = capsys.readouterr().out
        assert "already on the placeholder" in out

    def test_uncommitted_changes_exits(self, rooms, monkeypatch, tmp_path):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        monkeypatch.setattr(rooms, "load_config", lambda: self._cfg(worktree))
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "feat\n", ""),
            ("git", "status", "--porcelain"):     (0, "M  file.py\n", ""),
        }))
        with pytest.raises(SystemExit):
            rooms.cmd_free(["myproject/room-1"])

    def test_success_checks_out_placeholder(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        monkeypatch.setattr(rooms, "load_config", lambda: self._cfg(worktree))
        monkeypatch.setattr(rooms, "save_config", lambda _: None)
        calls = []
        def capturing_run(cmd, cwd=None, check=True):
            calls.append(cmd)
            return make_run({
                ("git", "rev-parse", "--abbrev-ref"): (0, "feat\n", ""),
                ("git", "status", "--porcelain"):     (0, "", ""),
                ("git", "checkout",):                 (0, "", ""),
            })(cmd, cwd=cwd, check=check)
        monkeypatch.setattr(rooms, "run", capturing_run)

        rooms.cmd_free(["myproject/room-1"])
        out = capsys.readouterr().out
        assert "is now free" in out
        checkout_calls = [c for c in calls if "checkout" in c]
        assert any("room-1" in c for c in checkout_calls)

    def test_checkout_failure_exits(self, rooms, monkeypatch, tmp_path):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        monkeypatch.setattr(rooms, "load_config", lambda: self._cfg(worktree))
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "feat\n", ""),
            ("git", "status", "--porcelain"):     (0, "", ""),
            ("git", "checkout",):                 (1, "", "error"),
        }))
        with pytest.raises(SystemExit):
            rooms.cmd_free(["myproject/room-1"])


# ---------------------------------------------------------------------------
# cmd_remove
# ---------------------------------------------------------------------------

class TestCmdRemove:
    def _cfg(self, worktree_path):
        room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree_path))
        return make_cfg(room)

    def test_no_args_exits(self, rooms):
        with pytest.raises(SystemExit):
            rooms.cmd_remove([])

    def test_room_not_found_exits(self, rooms, monkeypatch):
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg())
        with pytest.raises(SystemExit):
            rooms.cmd_remove(["myproject/ghost"])

    def test_occupied_room_exits(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        monkeypatch.setattr(rooms, "load_config", lambda: self._cfg(worktree))
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "feat\n", ""),
        }))
        with pytest.raises(SystemExit):
            rooms.cmd_remove(["myproject/room-1"])
        assert "Free it first" in capsys.readouterr().out

    def test_worktree_remove_failure_exits(self, rooms, monkeypatch, tmp_path):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        monkeypatch.setattr(rooms, "load_config", lambda: self._cfg(worktree))
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),
            ("git", "worktree", "remove"):        (1, "", "fatal: error"),
        }))
        with pytest.raises(SystemExit):
            rooms.cmd_remove(["myproject/room-1"])

    def test_success_removes_worktree_branch_and_config(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        cfg = self._cfg(worktree)
        saved = {}
        monkeypatch.setattr(rooms, "load_config", lambda: cfg)
        monkeypatch.setattr(rooms, "save_config", lambda c: saved.update(c))

        calls = []
        def capturing_run(cmd, cwd=None, check=True):
            calls.append(cmd)
            return make_run({
                ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),
                ("git", "worktree", "remove"):        (0, "", ""),
                ("git", "branch", "-D"):              (0, "", ""),
            })(cmd, cwd=cwd, check=check)
        monkeypatch.setattr(rooms, "run", capturing_run)

        rooms.cmd_remove(["myproject/room-1"])

        out = capsys.readouterr().out
        assert "removed" in out
        assert any("worktree" in c and "remove" in c for c in calls)
        assert any("branch" in c and "-D" in c for c in calls)
        assert saved.get("rooms") == []


# ---------------------------------------------------------------------------
# cmd_move
# ---------------------------------------------------------------------------

class TestCmdMove:
    def _two_room_cfg(self, src_path, dst_path):
        src = make_room(name="room-1", repo="/repo/myproject", path=str(src_path))
        dst = make_room(name="room-2", repo="/repo/myproject", path=str(dst_path))
        return make_cfg(src, dst)

    def test_no_args_exits(self, rooms):
        with pytest.raises(SystemExit):
            rooms.cmd_move([])

    def test_src_already_free_exits(self, rooms, monkeypatch, tmp_path):
        src_path = tmp_path / "room-1"
        dst_path = tmp_path / "room-2"
        src_path.mkdir(); dst_path.mkdir()
        monkeypatch.setattr(rooms, "load_config", lambda: self._two_room_cfg(src_path, dst_path))
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),  # both on placeholder
        }))
        with pytest.raises(SystemExit):
            rooms.cmd_move(["myproject/room-1", "myproject/room-2"])

    def test_dst_occupied_exits(self, rooms, monkeypatch, tmp_path):
        src_path = tmp_path / "room-1"
        dst_path = tmp_path / "room-2"
        src_path.mkdir(); dst_path.mkdir()
        monkeypatch.setattr(rooms, "load_config", lambda: self._two_room_cfg(src_path, dst_path))

        call_count = [0]
        def branch_for_path(cmd, cwd=None, check=True):
            if "rev-parse" in cmd:
                call_count[0] += 1
                # src on feat, dst on its own feature (occupied)
                return __import__("subprocess").CompletedProcess(
                    cmd, 0, "feat\n" if call_count[0] == 1 else "other-feat\n", ""
                )
            return __import__("subprocess").CompletedProcess(cmd, 0, "", "")
        monkeypatch.setattr(rooms, "run", branch_for_path)

        with pytest.raises(SystemExit):
            rooms.cmd_move(["myproject/room-1", "myproject/room-2"])

    def test_uncommitted_changes_exits(self, rooms, monkeypatch, tmp_path):
        src_path = tmp_path / "room-1"
        dst_path = tmp_path / "room-2"
        src_path.mkdir(); dst_path.mkdir()
        monkeypatch.setattr(rooms, "load_config", lambda: self._two_room_cfg(src_path, dst_path))

        call_count = [0]
        def run_mock(cmd, cwd=None, check=True):
            if "rev-parse" in cmd:
                call_count[0] += 1
                branch = "feat\n" if call_count[0] == 1 else "room-2\n"
                return __import__("subprocess").CompletedProcess(cmd, 0, branch, "")
            if "status" in cmd:
                return __import__("subprocess").CompletedProcess(cmd, 0, "M  file.py\n", "")
            return __import__("subprocess").CompletedProcess(cmd, 0, "", "")
        monkeypatch.setattr(rooms, "run", run_mock)

        with pytest.raises(SystemExit):
            rooms.cmd_move(["myproject/room-1", "myproject/room-2"])

    def test_success(self, rooms, monkeypatch, tmp_path, capsys):
        src_path = tmp_path / "room-1"
        dst_path = tmp_path / "room-2"
        src_path.mkdir(); dst_path.mkdir()
        monkeypatch.setattr(rooms, "load_config", lambda: self._two_room_cfg(src_path, dst_path))
        monkeypatch.setattr(rooms, "save_config", lambda _: None)

        call_count = [0]
        def run_mock(cmd, cwd=None, check=True):
            if "rev-parse" in cmd:
                call_count[0] += 1
                branch = "feat\n" if call_count[0] == 1 else "room-2\n"
                return __import__("subprocess").CompletedProcess(cmd, 0, branch, "")
            return __import__("subprocess").CompletedProcess(cmd, 0, "", "")
        monkeypatch.setattr(rooms, "run", run_mock)

        rooms.cmd_move(["myproject/room-1", "myproject/room-2"])
        out = capsys.readouterr().out
        assert "Done" in out


# ---------------------------------------------------------------------------
# _do_occupy
# ---------------------------------------------------------------------------

class TestDoOccupy:
    def _cfg(self, worktree_path):
        room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree_path))
        return make_cfg(room)

    def test_no_args_exits(self, rooms):
        with pytest.raises(SystemExit):
            rooms._do_occupy([])

    def test_room_not_found_exits(self, rooms, monkeypatch):
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg())
        with pytest.raises(SystemExit):
            rooms._do_occupy(["myproject/ghost"])

    def test_occupied_room_exits(self, rooms, monkeypatch, tmp_path):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        monkeypatch.setattr(rooms, "load_config", lambda: self._cfg(worktree))
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "feat\n", ""),
        }))
        with pytest.raises(SystemExit):
            rooms._do_occupy(["myproject/room-1"])

    def test_free_room_no_branch_returns_path(self, rooms, monkeypatch, tmp_path):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        monkeypatch.setattr(rooms, "load_config", lambda: self._cfg(worktree))
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),
        }))
        result = rooms._do_occupy(["myproject/room-1"])
        assert result == str(worktree)

    def test_free_room_with_branch_checks_out(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        monkeypatch.setattr(rooms, "load_config", lambda: self._cfg(worktree))
        calls = []
        def capturing_run(cmd, cwd=None, check=True):
            calls.append(cmd)
            return make_run({
                ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),
                ("git", "checkout",):                 (0, "", ""),
            })(cmd, cwd=cwd, check=check)
        monkeypatch.setattr(rooms, "run", capturing_run)

        result = rooms._do_occupy(["myproject/room-1", "feat"])
        assert result == str(worktree)
        checkout_cmds = [c for c in calls if "checkout" in c]
        assert any("feat" in c for c in checkout_cmds)

    def test_branch_checkout_failure_exits(self, rooms, monkeypatch, tmp_path):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        monkeypatch.setattr(rooms, "load_config", lambda: self._cfg(worktree))
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),
            ("git", "checkout",):                 (1, "", "error: branch not found"),
        }))
        with pytest.raises(SystemExit):
            rooms._do_occupy(["myproject/room-1", "nonexistent"])

    def test_silent_suppresses_checkout_message(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        monkeypatch.setattr(rooms, "load_config", lambda: self._cfg(worktree))
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),
            ("git", "fetch",):                    (0, "", ""),
            ("git", "reset",):                    (0, "", ""),
            ("git", "checkout",):                 (0, "", ""),
        }))
        rooms._do_occupy(["myproject/room-1", "feat"], silent=True)
        out = capsys.readouterr().out
        assert "Checked out" not in out

    def test_sync_fetches_and_resets_to_default_branch(self, rooms, monkeypatch, tmp_path):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        monkeypatch.setattr(rooms, "load_config", lambda: self._cfg(worktree))
        calls = []
        def capturing_run(cmd, cwd=None, check=True):
            calls.append(cmd)
            return make_run({
                ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),
                ("git", "fetch",):                    (0, "", ""),
                ("git", "reset",):                    (0, "", ""),
            })(cmd, cwd=cwd, check=check)
        monkeypatch.setattr(rooms, "run", capturing_run)

        rooms._do_occupy(["myproject/room-1"])

        assert any("fetch" in c and "origin" in c and "main" in c for c in calls)
        assert any("reset" in c and "--hard" in c and "origin/main" in c for c in calls)

    def test_sync_offline_prints_warning_and_continues(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        monkeypatch.setattr(rooms, "load_config", lambda: self._cfg(worktree))
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),
            ("git", "fetch",):                    (1, "", "fatal: unable to connect"),
        }))

        result = rooms._do_occupy(["myproject/room-1"])

        out = capsys.readouterr().out
        assert "offline" in out
        assert result == str(worktree)


# ---------------------------------------------------------------------------
# cmd_purge
# ---------------------------------------------------------------------------

class TestCmdPurge:
    def test_no_rooms_exits_early(self, rooms, monkeypatch, capsys):
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg())
        rooms.cmd_purge()
        assert "No rooms" in capsys.readouterr().out

    def test_all_unpushed_nothing_to_purge(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree))
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        monkeypatch.setattr(rooms, "save_config", lambda _: None)
        monkeypatch.setattr(rooms, "parallel_fetch", lambda _: {"/repo/myproject": True})
        monkeypatch.setattr(rooms, "parallel_room_info", lambda *_: {
            "room-1": (False, None, False, "2h ago", {})
        })
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "feat\n", ""),
        }))

        rooms.cmd_purge()
        out = capsys.readouterr().out
        assert "Nothing to purge" in out

    def test_merged_candidate_abort(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree))
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        monkeypatch.setattr(rooms, "save_config", lambda _: None)
        monkeypatch.setattr(rooms, "parallel_fetch", lambda _: {"/repo/myproject": True})
        monkeypatch.setattr(rooms, "parallel_room_info", lambda *_: {
            "room-1": (True, None, False, "2h ago", {})
        })
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "feat\n", ""),
        }))
        monkeypatch.setattr("builtins.input", lambda _: "n")

        rooms.cmd_purge()
        out = capsys.readouterr().out
        assert "Aborted" in out

    def test_merged_candidate_confirmed_frees_room(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree))
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        monkeypatch.setattr(rooms, "save_config", lambda _: None)
        monkeypatch.setattr(rooms, "parallel_fetch", lambda _: {"/repo/myproject": True})
        monkeypatch.setattr(rooms, "parallel_room_info", lambda *_: {
            "room-1": (True, None, False, "2h ago", {})
        })
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "feat\n", ""),
            ("git", "status", "--porcelain"):     (0, "", ""),
            ("git", "checkout",):                 (0, "", ""),
            ("git", "branch", "-D"):              (0, "", ""),
        }))
        monkeypatch.setattr("builtins.input", lambda _: "y")

        rooms.cmd_purge()
        out = capsys.readouterr().out
        assert "freed" in out

    def test_merged_only_excludes_pushed_rooms(self, rooms, monkeypatch, tmp_path, capsys):
        """--merged skips rooms that are only fully-pushed (not merged)."""
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree))
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        monkeypatch.setattr(rooms, "save_config", lambda _: None)
        monkeypatch.setattr(rooms, "parallel_fetch", lambda _: {"/repo/myproject": True})
        monkeypatch.setattr(rooms, "parallel_room_info", lambda *_: {
            "room-1": (False, None, True, "2h ago", {})  # pushed but NOT merged
        })
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "feat\n", ""),
        }))

        rooms.cmd_purge(["--merged"])
        out = capsys.readouterr().out
        assert "Nothing to purge" in out
        assert "merged PR" in out

    def test_merged_only_includes_merged_rooms(self, rooms, monkeypatch, tmp_path, capsys):
        """--merged still purges rooms whose PR was merged."""
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree))
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        monkeypatch.setattr(rooms, "save_config", lambda _: None)
        monkeypatch.setattr(rooms, "parallel_fetch", lambda _: {"/repo/myproject": True})
        monkeypatch.setattr(rooms, "parallel_room_info", lambda *_: {
            "room-1": (True, None, False, "2h ago", {})  # merged
        })
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "feat\n", ""),
            ("git", "status", "--porcelain"):     (0, "", ""),
            ("git", "checkout",):                 (0, "", ""),
            ("git", "branch", "-D"):              (0, "", ""),
        }))
        monkeypatch.setattr("builtins.input", lambda _: "y")

        rooms.cmd_purge(["--merged"])
        out = capsys.readouterr().out
        assert "freed" in out


# ---------------------------------------------------------------------------
# cmd_config
# ---------------------------------------------------------------------------

class TestCmdConfig:
    def test_no_args_exits(self, rooms):
        with pytest.raises(SystemExit):
            rooms.cmd_config([])

    def test_wrong_subcommand_exits(self, rooms):
        with pytest.raises(SystemExit):
            rooms.cmd_config(["bad-command", "/some/path"])

    def test_set_base_path_updates_config(self, rooms, monkeypatch, tmp_path, capsys):
        saved = {}
        monkeypatch.setattr(rooms, "load_config", lambda: {"rooms_base": "/old/path", "rooms": []})
        monkeypatch.setattr(rooms, "save_config", lambda cfg: saved.update(cfg))

        rooms.cmd_config(["set-base-path", str(tmp_path)])
        assert saved["rooms_base"] == str(tmp_path)
        out = capsys.readouterr().out
        assert "/old/path" in out
        assert str(tmp_path) in out


# ---------------------------------------------------------------------------
# cmd_update
# ---------------------------------------------------------------------------

class TestCmdUpdate:
    def test_success_runs_install_script(self, rooms, monkeypatch, capsys):
        calls = []
        monkeypatch.setattr(rooms, "run", make_run({("bash",): (0, "", "")}))
        monkeypatch.setattr(rooms, "run", lambda cmd, check=True: (
            calls.append(cmd) or
            __import__("subprocess").CompletedProcess(cmd, 0, "", "")
        ))
        rooms.cmd_update()
        assert any("bash" in c and "curl" in " ".join(c) for c in calls)

    def test_failure_exits(self, rooms, monkeypatch):
        monkeypatch.setattr(rooms, "run", make_run({("bash",): (1, "", "error")}))
        with pytest.raises(SystemExit):
            rooms.cmd_update()
