"""Additional tests to cover gaps: config I/O, fetch helpers, cmd_add,
cmd_ls, cmd_occupy, cmd_names, cmd_branches, cmd_occupy_internal,
cmd_move error paths, cmd_purge error paths, usage, main."""

import json
import sys
import time

import pytest

from conftest import make_run, make_room, make_cfg


# ---------------------------------------------------------------------------
# load_config / save_config / save_cache
# ---------------------------------------------------------------------------

class TestConfigIO:
    def test_load_config_missing_returns_defaults(self, rooms, tmp_path, monkeypatch):
        monkeypatch.setattr(rooms, "CONFIG_PATH", tmp_path / "nonexistent.json")
        cfg = rooms.load_config()
        assert cfg["rooms"] == []
        assert "rooms_base" in cfg

    def test_load_config_reads_existing_file(self, rooms, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"rooms_base": "/custom", "rooms": []}))
        monkeypatch.setattr(rooms, "CONFIG_PATH", config_file)
        cfg = rooms.load_config()
        assert cfg["rooms_base"] == "/custom"

    def test_save_config_writes_json(self, rooms, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(rooms, "CONFIG_PATH", config_file)
        rooms.save_config({"rooms_base": "/x", "rooms": []})
        data = json.loads(config_file.read_text())
        assert data["rooms_base"] == "/x"

    def test_save_cache_stores_cache_and_timestamp(self, rooms, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(rooms, "CONFIG_PATH", config_file)
        cfg = {"rooms_base": "/x", "rooms": []}
        cache = {"key": {"merged": True}}
        ts = int(time.time())
        rooms.save_cache(cfg, cache, updated_at=ts)
        assert cfg["cache"] == cache
        assert cfg["cache_updated_at"] == ts


# ---------------------------------------------------------------------------
# fetch_repo
# ---------------------------------------------------------------------------

class TestFetchRepo:
    def test_fetch_repo_online(self, rooms, monkeypatch):
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "fetch"): (0, "", ""),
        }))
        assert rooms.fetch_repo("/repo") is True

    def test_fetch_repo_offline(self, rooms, monkeypatch):
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "fetch"): (1, "", "network unreachable"),
        }))
        assert rooms.fetch_repo("/repo") is False


# ---------------------------------------------------------------------------
# detect_default_branch
# ---------------------------------------------------------------------------

class TestDetectDefaultBranch:
    def test_parses_head_branch_from_remote_show(self, rooms, monkeypatch):
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "remote", "show"): (0, "  HEAD branch: develop\n", ""),
        }))
        assert rooms.detect_default_branch("/repo") == "develop"

    def test_falls_back_to_symbolic_ref(self, rooms, monkeypatch):
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "remote", "show"):   (0, "  no HEAD line here\n", ""),
            ("git", "symbolic-ref"):     (0, "master\n", ""),
        }))
        assert rooms.detect_default_branch("/repo") == "master"

    def test_falls_back_to_main(self, rooms, monkeypatch):
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "remote", "show"):   (0, "", ""),
            ("git", "symbolic-ref"):     (1, "", ""),
        }))
        assert rooms.detect_default_branch("/repo") == "main"


# ---------------------------------------------------------------------------
# current_branch (error path)
# ---------------------------------------------------------------------------

def test_current_branch_returns_none_on_exception(rooms, monkeypatch):
    def exploding_run(cmd, cwd=None, check=True):
        raise OSError("no git")
    monkeypatch.setattr(rooms, "run", exploding_run)
    assert rooms.current_branch("/repo") is None


# ---------------------------------------------------------------------------
# last_commit_age
# ---------------------------------------------------------------------------

class TestLastCommitAge:
    def test_returns_age_string(self, rooms, monkeypatch):
        ts = str(int(time.time()) - 3600)
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "log"): (0, ts + "\n", ""),
        }))
        assert rooms.last_commit_age("/repo") == "1h ago"

    def test_no_commits(self, rooms, monkeypatch):
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "log"): (1, "", ""),
        }))
        assert rooms.last_commit_age("/repo") == "no commits"

    def test_empty_output_means_no_commits(self, rooms, monkeypatch):
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "log"): (0, "", ""),
        }))
        assert rooms.last_commit_age("/repo") == "no commits"

    def test_exception_returns_question_mark(self, rooms, monkeypatch):
        def exploding_run(cmd, cwd=None, check=True):
            raise OSError("no git")
        monkeypatch.setattr(rooms, "run", exploding_run)
        assert rooms.last_commit_age("/repo") == "?"


# ---------------------------------------------------------------------------
# parallel_fetch / parallel_room_info
# ---------------------------------------------------------------------------

class TestParallel:
    def test_parallel_fetch_returns_online_map(self, rooms, monkeypatch):
        monkeypatch.setattr(rooms, "fetch_repo", lambda repo: repo == "/repo/a")
        room_a = make_room(repo="/repo/a")
        room_b = make_room(repo="/repo/b")
        result = rooms.parallel_fetch([room_a, room_b])
        assert result["/repo/a"] is True
        assert result["/repo/b"] is False

    def test_parallel_room_info_empty_pending(self, rooms):
        result = rooms.parallel_room_info([], {}, {})
        assert result == {}

    def test_parallel_room_info_returns_results(self, rooms, monkeypatch, tmp_path):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree))
        monkeypatch.setattr(rooms, "get_remote_info",
                            lambda r, b, online, cache: (False, None, False, {}))
        monkeypatch.setattr(rooms, "last_commit_age", lambda _: "1h ago")
        result = rooms.parallel_room_info(
            [(room, "feat")], {"/repo/myproject": True}, {}
        )
        assert "room-1" in result
        merged, pr_info, pushed, age, update = result["room-1"]
        assert age == "1h ago"
        assert merged is False


# ---------------------------------------------------------------------------
# cmd_add
# ---------------------------------------------------------------------------

class TestCmdAdd:
    def test_no_args_exits(self, rooms):
        with pytest.raises(SystemExit):
            rooms.cmd_add([])

    def test_duplicate_name_exits(self, rooms, monkeypatch):
        room = make_room(name="room-1", repo="/repo/myproject")
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        with pytest.raises(SystemExit):
            rooms.cmd_add(["/repo/myproject", "room-1"])

    def test_nonexistent_local_path_exits(self, rooms, monkeypatch, tmp_path):
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg())
        with pytest.raises(SystemExit):
            rooms.cmd_add([str(tmp_path / "nope"), "room-1"])

    def test_local_path_success(self, rooms, monkeypatch, tmp_path, capsys):
        repo = tmp_path / "myproject"
        repo.mkdir()
        rooms_base = tmp_path / "rooms"
        cfg = {"rooms_base": str(rooms_base), "rooms": []}
        saved = {}
        monkeypatch.setattr(rooms, "load_config", lambda: cfg)
        monkeypatch.setattr(rooms, "save_config", lambda c: saved.update(c))
        monkeypatch.setattr(rooms, "detect_default_branch", lambda _: "main")
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--verify"): (1, "", "not found"),
            ("git", "branch",):               (0, "", ""),
            ("git", "worktree", "add"):       (0, "", ""),
        }))
        rooms.cmd_add([str(repo), "room-1"])
        out = capsys.readouterr().out
        assert "is ready" in out
        assert saved["rooms"][0]["name"] == "room-1"

    def test_local_path_branch_already_exists(self, rooms, monkeypatch, tmp_path, capsys):
        repo = tmp_path / "myproject"
        repo.mkdir()
        rooms_base = tmp_path / "rooms"
        cfg = {"rooms_base": str(rooms_base), "rooms": []}
        monkeypatch.setattr(rooms, "load_config", lambda: cfg)
        monkeypatch.setattr(rooms, "save_config", lambda _: None)
        monkeypatch.setattr(rooms, "detect_default_branch", lambda _: "main")
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--verify"): (0, "abc123", ""),  # branch exists
            ("git", "worktree", "add"):       (0, "", ""),
        }))
        rooms.cmd_add([str(repo), "room-1"])
        out = capsys.readouterr().out
        assert "already exists" in out

    def test_url_already_cloned(self, rooms, monkeypatch, tmp_path, capsys):
        clone_base = tmp_path / "code"
        clone_base.mkdir()
        repo_dir = clone_base / "myproject"
        repo_dir.mkdir()
        rooms_base = tmp_path / "rooms"
        cfg = {"rooms_base": str(rooms_base), "rooms": []}
        monkeypatch.setattr(rooms, "load_config", lambda: cfg)
        monkeypatch.setattr(rooms, "save_config", lambda _: None)
        monkeypatch.setattr(rooms, "detect_default_branch", lambda _: "main")
        # Patch Path.home() via the clone_base path trick
        monkeypatch.setattr(rooms.Path, "home", lambda: tmp_path)
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--verify"): (1, "", ""),
            ("git", "branch",):               (0, "", ""),
            ("git", "worktree", "add"):       (0, "", ""),
        }))
        rooms.cmd_add(["git@github.com:org/myproject.git", "room-1"])
        out = capsys.readouterr().out
        assert "already exists" in out


# ---------------------------------------------------------------------------
# cmd_ls
# ---------------------------------------------------------------------------

class TestCmdLs:
    def test_no_rooms_message(self, rooms, monkeypatch, capsys):
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg())
        rooms.cmd_ls()
        assert "No rooms" in capsys.readouterr().out

    def test_free_room_shows_dash(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree))
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        monkeypatch.setattr(rooms, "save_config", lambda _: None)
        monkeypatch.setattr(rooms, "parallel_fetch", lambda _: {"/repo/myproject": True})
        monkeypatch.setattr(rooms, "parallel_room_info", lambda *_: {})
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),
        }))
        rooms.cmd_ls()
        out = capsys.readouterr().out
        assert "[free]" in out
        assert "myproject" in out

    def test_missing_worktree_shows_missing(self, rooms, monkeypatch, tmp_path, capsys):
        room = make_room(name="room-1", repo="/repo/myproject",
                         path=str(tmp_path / "nonexistent"))
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        monkeypatch.setattr(rooms, "save_config", lambda _: None)
        monkeypatch.setattr(rooms, "parallel_fetch", lambda _: {"/repo/myproject": True})
        monkeypatch.setattr(rooms, "parallel_room_info", lambda *_: {})
        rooms.cmd_ls()
        out = capsys.readouterr().out
        assert "[missing]" in out

    def test_busy_room_shows_status(self, rooms, monkeypatch, tmp_path, capsys):
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
        rooms.cmd_ls()
        out = capsys.readouterr().out
        assert "feat" in out
        assert "in-progress" in out

    def test_offline_shows_cached_message(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree))
        cfg = make_cfg(room)
        cfg["cache_updated_at"] = int(time.time()) - 3600
        monkeypatch.setattr(rooms, "load_config", lambda: cfg)
        monkeypatch.setattr(rooms, "save_config", lambda _: None)
        # One repo offline
        monkeypatch.setattr(rooms, "parallel_fetch", lambda _: {"/repo/myproject": False})
        monkeypatch.setattr(rooms, "parallel_room_info", lambda *_: {})
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),
        }))
        rooms.cmd_ls()
        out = capsys.readouterr().out
        assert "offline" in out

    def test_busy_room_with_pr_link(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree))
        pr_info = {"url": "https://github.com/org/repo/pull/42", "number": 42,
                   "ci": "passing", "draft": False, "title": "Fix the thing"}
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        monkeypatch.setattr(rooms, "save_config", lambda _: None)
        monkeypatch.setattr(rooms, "parallel_fetch", lambda _: {"/repo/myproject": True})
        monkeypatch.setattr(rooms, "parallel_room_info", lambda *_: {
            "room-1": (False, pr_info, False, "1h ago", {"key": {"merged": False}})
        })
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "feat\n", ""),
        }))
        rooms.cmd_ls()
        out = capsys.readouterr().out
        assert "feat" in out


# ---------------------------------------------------------------------------
# cmd_occupy (public wrapper)
# ---------------------------------------------------------------------------

class TestCmdOccupy:
    def test_occupy_no_branch_prints_ready(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree))
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),
        }))
        rooms.cmd_occupy(["myproject/room-1"])
        out = capsys.readouterr().out
        assert "is ready" in out
        assert str(worktree) in out

    def test_occupy_with_branch_prints_path(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree))
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),
            ("git", "checkout",):                 (0, "", ""),
        }))
        rooms.cmd_occupy(["myproject/room-1", "feat"])
        out = capsys.readouterr().out
        assert str(worktree) in out


# ---------------------------------------------------------------------------
# cmd_names / cmd_branches
# ---------------------------------------------------------------------------

class TestCompletionHelpers:
    def test_cmd_names_prints_project_slash_name(self, rooms, monkeypatch, capsys):
        room = make_room(name="room-1", repo="/repo/myproject")
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        rooms.cmd_names()
        assert "myproject/room-1" in capsys.readouterr().out

    def test_cmd_branches_no_args_exits(self, rooms):
        with pytest.raises(SystemExit):
            rooms.cmd_branches([])

    def test_cmd_branches_prints_branches(self, rooms, monkeypatch, capsys):
        room = make_room(name="room-1", repo="/repo/myproject")
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "branch",): (0, "main\nfeat\n", ""),
        }))
        rooms.cmd_branches(["myproject/room-1"])
        out = capsys.readouterr().out
        assert "main" in out
        assert "feat" in out

    def test_cmd_branches_handles_exception(self, rooms, monkeypatch, capsys):
        room = make_room(name="room-1", repo="/repo/myproject")
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        def boom(cmd, cwd=None, check=True):
            raise OSError("no git")
        monkeypatch.setattr(rooms, "run", boom)
        rooms.cmd_branches(["myproject/room-1"])  # should not raise


# ---------------------------------------------------------------------------
# usage / main
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# cmd_move — remaining error paths
# ---------------------------------------------------------------------------

class TestCmdMoveErrorPaths:
    def _two_room_cfg(self, src_path, dst_path):
        src = make_room(name="room-1", repo="/repo/myproject", path=str(src_path))
        dst = make_room(name="room-2", repo="/repo/myproject", path=str(dst_path))
        return make_cfg(src, dst)

    def test_same_room_exits(self, rooms, monkeypatch, tmp_path):
        """src is dst identity check when the same spec is passed twice."""
        src_path = tmp_path / "room-1"
        src_path.mkdir()
        room = make_room(name="room-1", repo="/repo/myproject", path=str(src_path))
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        with pytest.raises(SystemExit):
            rooms.cmd_move(["myproject/room-1", "myproject/room-1"])

    def test_src_placeholder_checkout_fails_exits(self, rooms, monkeypatch, tmp_path):
        src_path = tmp_path / "room-1"
        dst_path = tmp_path / "room-2"
        src_path.mkdir(); dst_path.mkdir()
        monkeypatch.setattr(rooms, "load_config",
                            lambda: self._two_room_cfg(src_path, dst_path))

        call_count = [0]
        def run_mock(cmd, cwd=None, check=True):
            import subprocess as sp
            if "rev-parse" in cmd:
                call_count[0] += 1
                branch = "feat\n" if call_count[0] == 1 else "room-2\n"
                return sp.CompletedProcess(cmd, 0, branch, "")
            if "status" in cmd:
                return sp.CompletedProcess(cmd, 0, "", "")
            if "checkout" in cmd:
                return sp.CompletedProcess(cmd, 1, "", "checkout failed")
            return sp.CompletedProcess(cmd, 0, "", "")
        monkeypatch.setattr(rooms, "run", run_mock)
        with pytest.raises(SystemExit):
            rooms.cmd_move(["myproject/room-1", "myproject/room-2"])

    def test_dst_checkout_fails_rolls_back(self, rooms, monkeypatch, tmp_path, capsys):
        src_path = tmp_path / "room-1"
        dst_path = tmp_path / "room-2"
        src_path.mkdir(); dst_path.mkdir()
        monkeypatch.setattr(rooms, "load_config",
                            lambda: self._two_room_cfg(src_path, dst_path))

        call_count = [0]
        checkout_count = [0]
        def run_mock(cmd, cwd=None, check=True):
            import subprocess as sp
            if "rev-parse" in cmd:
                call_count[0] += 1
                branch = "feat\n" if call_count[0] == 1 else "room-2\n"
                return sp.CompletedProcess(cmd, 0, branch, "")
            if "status" in cmd:
                return sp.CompletedProcess(cmd, 0, "", "")
            if "checkout" in cmd:
                checkout_count[0] += 1
                # first checkout (src→placeholder) succeeds, second (dst) fails
                rc = 0 if checkout_count[0] == 1 else 1
                return sp.CompletedProcess(cmd, rc, "", "error")
            return sp.CompletedProcess(cmd, 0, "", "")
        monkeypatch.setattr(rooms, "run", run_mock)
        with pytest.raises(SystemExit):
            rooms.cmd_move(["myproject/room-1", "myproject/room-2"])
        out = capsys.readouterr().out
        assert "Rolled back" in out


# ---------------------------------------------------------------------------
# cmd_purge — remaining error paths
# ---------------------------------------------------------------------------

class TestCmdPurgeErrorPaths:
    def _setup(self, rooms, monkeypatch, tmp_path, info_result):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree))
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        monkeypatch.setattr(rooms, "save_config", lambda _: None)
        monkeypatch.setattr(rooms, "parallel_fetch",
                            lambda _: {"/repo/myproject": True})
        monkeypatch.setattr(rooms, "parallel_room_info", lambda *_: info_result)
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "feat\n", ""),
        }))
        monkeypatch.setattr("builtins.input", lambda _: "y")
        return worktree

    def test_offline_shows_message(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree))
        cfg = make_cfg(room)
        cfg["cache_updated_at"] = int(time.time()) - 3600
        monkeypatch.setattr(rooms, "load_config", lambda: cfg)
        monkeypatch.setattr(rooms, "save_config", lambda _: None)
        monkeypatch.setattr(rooms, "parallel_fetch",
                            lambda _: {"/repo/myproject": False})
        monkeypatch.setattr(rooms, "parallel_room_info", lambda *_: {})
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),
        }))
        rooms.cmd_purge()
        out = capsys.readouterr().out
        assert "offline" in out

    def test_missing_worktree_skipped(self, rooms, monkeypatch, tmp_path):
        room = make_room(name="room-1", repo="/repo/myproject",
                         path=str(tmp_path / "nonexistent"))
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        monkeypatch.setattr(rooms, "save_config", lambda _: None)
        monkeypatch.setattr(rooms, "parallel_fetch",
                            lambda _: {"/repo/myproject": True})
        monkeypatch.setattr(rooms, "parallel_room_info", lambda *_: {})
        rooms.cmd_purge()  # should complete without error

    def test_pushed_shows_as_candidate(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = self._setup(rooms, monkeypatch, tmp_path, {
            "room-1": (False, None, True, "2h ago", {})  # pushed=True
        })
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "feat\n", ""),
            ("git", "status", "--porcelain"):     (0, "", ""),
            ("git", "checkout",):                 (0, "", ""),
            ("git", "branch", "-D"):              (0, "", ""),
        }))
        rooms.cmd_purge()
        out = capsys.readouterr().out
        assert "freed" in out

    def test_uncommitted_changes_skips_room(self, rooms, monkeypatch, tmp_path, capsys):
        worktree = self._setup(rooms, monkeypatch, tmp_path, {
            "room-1": (True, None, False, "2h ago", {})
        })
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "feat\n", ""),
            ("git", "status", "--porcelain"):     (0, "M file.py\n", ""),
        }))
        rooms.cmd_purge()
        out = capsys.readouterr().out
        assert "uncommitted changes" in out

    def test_checkout_placeholder_fails_skips(self, rooms, monkeypatch, tmp_path, capsys):
        self._setup(rooms, monkeypatch, tmp_path, {
            "room-1": (True, None, False, "2h ago", {})
        })
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "--abbrev-ref"): (0, "feat\n", ""),
            ("git", "status", "--porcelain"):     (0, "", ""),
            ("git", "checkout",):                 (1, "", "error"),
        }))
        rooms.cmd_purge()
        out = capsys.readouterr().out
        assert "could not switch" in out

    def test_branch_delete_fails_reports(self, rooms, monkeypatch, tmp_path, capsys):
        self._setup(rooms, monkeypatch, tmp_path, {
            "room-1": (True, None, False, "2h ago", {})
        })

        checkout_count = [0]
        def run_mock(cmd, cwd=None, check=True):
            import subprocess as sp
            if "rev-parse" in cmd and "--abbrev-ref" in cmd:
                return sp.CompletedProcess(cmd, 0, "feat\n", "")
            if "status" in cmd:
                return sp.CompletedProcess(cmd, 0, "", "")
            if "checkout" in cmd:
                return sp.CompletedProcess(cmd, 0, "", "")
            if "branch" in cmd and "-D" in cmd:
                return sp.CompletedProcess(cmd, 1, "", "cannot delete")
            return sp.CompletedProcess(cmd, 0, "", "")
        monkeypatch.setattr(rooms, "run", run_mock)
        rooms.cmd_purge()
        out = capsys.readouterr().out
        assert "could not remove" in out


# ---------------------------------------------------------------------------
# cmd_occupy_internal
# ---------------------------------------------------------------------------

def test_cmd_occupy_internal_prints_only_path(rooms, monkeypatch, tmp_path, capsys):
    worktree = tmp_path / "room-1"
    worktree.mkdir()
    room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree))
    monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
    monkeypatch.setattr(rooms, "run", make_run({
        ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),
    }))
    rooms.cmd_occupy_internal(["myproject/room-1"])
    out = capsys.readouterr().out.strip()
    assert out == str(worktree)


# ---------------------------------------------------------------------------
# Multi-project cmd_ls (covers the blank-line-between-projects path)
# ---------------------------------------------------------------------------

def test_cmd_ls_two_projects_prints_headers(rooms, monkeypatch, tmp_path, capsys):
    w1 = tmp_path / "room-1"; w1.mkdir()
    w2 = tmp_path / "room-2"; w2.mkdir()
    r1 = make_room(name="room-1", repo="/repo/alpha",   path=str(w1))
    r2 = make_room(name="room-2", repo="/repo/beta",    path=str(w2))
    monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(r1, r2))
    monkeypatch.setattr(rooms, "save_config", lambda _: None)
    monkeypatch.setattr(rooms, "parallel_fetch",
                        lambda _: {"/repo/alpha": True, "/repo/beta": True})
    monkeypatch.setattr(rooms, "parallel_room_info", lambda *_: {})
    monkeypatch.setattr(rooms, "run", make_run({
        ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),
    }))
    rooms.cmd_ls()
    out = capsys.readouterr().out
    assert "alpha" in out
    assert "beta" in out


# ---------------------------------------------------------------------------
# detect_default_branch exception paths
# ---------------------------------------------------------------------------

def test_detect_default_branch_exception_in_remote_show(rooms, monkeypatch):
    call_count = [0]
    def run_mock(cmd, cwd=None, check=True):
        import subprocess as sp
        call_count[0] += 1
        if "remote" in cmd:
            raise OSError("no network")
        return sp.CompletedProcess(cmd, 0, "main\n", "")
    monkeypatch.setattr(rooms, "run", run_mock)
    result = rooms.detect_default_branch("/repo")
    assert result == "main"


def test_detect_default_branch_exception_in_symbolic_ref(rooms, monkeypatch):
    call_count = [0]
    def run_mock(cmd, cwd=None, check=True):
        import subprocess as sp
        call_count[0] += 1
        if "remote" in cmd:
            return sp.CompletedProcess(cmd, 0, "", "")  # no HEAD branch line
        if "symbolic-ref" in cmd:
            raise OSError("not a git repo")
        return sp.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(rooms, "run", run_mock)
    result = rooms.detect_default_branch("/repo")
    assert result == "main"


class TestMain:
    def test_usage_prints_commands(self, rooms, capsys):
        rooms.usage()
        out = capsys.readouterr().out
        assert "rooms add" in out
        assert "rooms ls" in out
        assert "rooms free" in out

    def test_main_no_args_exits(self, rooms, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["rooms"])
        with pytest.raises(SystemExit):
            rooms.main()

    def test_main_unknown_command_exits(self, rooms, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["rooms", "bogus"])
        with pytest.raises(SystemExit):
            rooms.main()

    def test_main_dispatches_ls(self, rooms, monkeypatch):
        called = []
        monkeypatch.setattr(sys, "argv", ["rooms", "ls"])
        monkeypatch.setattr(rooms, "cmd_ls", lambda: called.append("ls"))
        rooms.main()
        assert "ls" in called

    def test_main_dispatches_free(self, rooms, monkeypatch):
        called = []
        monkeypatch.setattr(sys, "argv", ["rooms", "free", "myproject/room-1"])
        monkeypatch.setattr(rooms, "cmd_free", lambda args: called.append(args))
        rooms.main()
        assert called[0] == ["myproject/room-1"]

    def test_main_dispatches_remove(self, rooms, monkeypatch):
        called = []
        monkeypatch.setattr(sys, "argv", ["rooms", "remove", "myproject/room-1"])
        monkeypatch.setattr(rooms, "cmd_remove", lambda args: called.append(args))
        rooms.main()
        assert called[0] == ["myproject/room-1"]

    def test_main_dispatches_add(self, rooms, monkeypatch):
        called = []
        monkeypatch.setattr(sys, "argv", ["rooms", "add", "/repo", "room-1"])
        monkeypatch.setattr(rooms, "cmd_add", lambda args: called.append(args))
        rooms.main()
        assert called[0] == ["/repo", "room-1"]

    def test_main_dispatches_move(self, rooms, monkeypatch):
        called = []
        monkeypatch.setattr(sys, "argv", ["rooms", "move", "myproject/r1", "myproject/r2"])
        monkeypatch.setattr(rooms, "cmd_move", lambda args: called.append(args))
        rooms.main()
        assert called

    def test_main_dispatches_occupy(self, rooms, monkeypatch):
        called = []
        monkeypatch.setattr(sys, "argv", ["rooms", "occupy", "myproject/room-1"])
        monkeypatch.setattr(rooms, "cmd_occupy", lambda args: called.append(args))
        rooms.main()
        assert called

    def test_main_dispatches_purge(self, rooms, monkeypatch):
        called = []
        monkeypatch.setattr(sys, "argv", ["rooms", "purge"])
        monkeypatch.setattr(rooms, "cmd_purge", lambda *_: called.append("purge"))
        rooms.main()
        assert "purge" in called

    def test_main_dispatches_config(self, rooms, monkeypatch):
        called = []
        monkeypatch.setattr(sys, "argv", ["rooms", "config", "set-base-path", "/x"])
        monkeypatch.setattr(rooms, "cmd_config", lambda args: called.append(args))
        rooms.main()
        assert called

    def test_main_dispatches_internal_occupy(self, rooms, monkeypatch):
        called = []
        monkeypatch.setattr(sys, "argv", ["rooms", "_occupy", "myproject/room-1"])
        monkeypatch.setattr(rooms, "cmd_occupy_internal", lambda args: called.append(args))
        rooms.main()
        assert called

    def test_main_dispatches_names(self, rooms, monkeypatch):
        called = []
        monkeypatch.setattr(sys, "argv", ["rooms", "_names"])
        monkeypatch.setattr(rooms, "cmd_names", lambda: called.append("names"))
        rooms.main()
        assert "names" in called

    def test_main_dispatches_branches(self, rooms, monkeypatch):
        called = []
        monkeypatch.setattr(sys, "argv", ["rooms", "_branches", "myproject/room-1"])
        monkeypatch.setattr(rooms, "cmd_branches", lambda args: called.append(args))
        rooms.main()
        assert called

    def test_main_help_flag_exits_cleanly(self, rooms, monkeypatch, capsys):
        for flag in ("-h", "--help"):
            monkeypatch.setattr(sys, "argv", ["rooms", flag])
            with pytest.raises(SystemExit) as exc:
                rooms.main()
            assert exc.value.code == 0
            assert "rooms add" in capsys.readouterr().out
