"""Tests for rooms link/unlink, the linked-repo cleanup in cmd_remove, and the
resolve_source_repo / exclude_from_status helpers."""

import pytest

from conftest import make_run, make_room, make_cfg


# ---------------------------------------------------------------------------
# resolve_source_repo
# ---------------------------------------------------------------------------

class TestResolveSourceRepo:
    def test_local_path_returns_expanded(self, rooms, tmp_path):
        repo = tmp_path / "myproject"
        repo.mkdir()
        assert rooms.resolve_source_repo(str(repo)) == str(repo.resolve())

    def test_nonexistent_local_path_exits(self, rooms, tmp_path):
        with pytest.raises(SystemExit):
            rooms.resolve_source_repo(str(tmp_path / "nope"))

    def test_url_clones_when_missing(self, rooms, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(rooms.Path, "home", lambda: tmp_path)
        calls = []
        monkeypatch.setattr(rooms, "run", lambda cmd, cwd=None, check=True: calls.append(cmd))
        result = rooms.resolve_source_repo("git@github.com:org/myproject.git")
        assert result == str(tmp_path / "code" / "myproject")
        assert "Cloning" in capsys.readouterr().out
        assert any("clone" in c for c in calls)

    def test_url_skips_clone_when_present(self, rooms, monkeypatch, tmp_path, capsys):
        (tmp_path / "code" / "myproject").mkdir(parents=True)
        monkeypatch.setattr(rooms.Path, "home", lambda: tmp_path)
        monkeypatch.setattr(rooms, "run", make_run({}))
        rooms.resolve_source_repo("https://github.com/org/myproject.git")
        assert "already exists" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# exclude_from_status
# ---------------------------------------------------------------------------

class TestExcludeFromStatus:
    def test_appends_line(self, rooms, monkeypatch, tmp_path):
        exclude = tmp_path / "info" / "exclude"
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "info/exclude"): (0, f"{exclude}\n", ""),
        }))
        rooms.exclude_from_status("/rooms/room-1", "sdk")
        assert "/sdk/" in exclude.read_text().splitlines()

    def test_idempotent(self, rooms, monkeypatch, tmp_path):
        exclude = tmp_path / "info" / "exclude"
        exclude.parent.mkdir(parents=True)
        exclude.write_text("/sdk/\n")
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "info/exclude"): (0, f"{exclude}\n", ""),
        }))
        rooms.exclude_from_status("/rooms/room-1", "sdk")
        assert exclude.read_text().count("/sdk/") == 1

    def test_no_git_path_is_noop(self, rooms, monkeypatch):
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "rev-parse", "info/exclude"): (1, "", "fatal"),
        }))
        # Should not raise even though there is no exclude file.
        rooms.exclude_from_status("/rooms/room-1", "sdk")


# ---------------------------------------------------------------------------
# cmd_link
# ---------------------------------------------------------------------------

class TestCmdLink:
    def _setup(self, rooms, monkeypatch, tmp_path):
        room_path = tmp_path / "room-1"
        room_path.mkdir()
        repo = tmp_path / "sdk"
        repo.mkdir()
        room = make_room(name="room-1", repo="/repo/myproject", path=str(room_path))
        cfg = make_cfg(room)
        monkeypatch.setattr(rooms, "load_config", lambda: cfg)
        monkeypatch.setattr(rooms, "exclude_from_status", lambda *a, **k: None)
        return cfg, room, room_path, repo

    def test_too_few_args_exits(self, rooms):
        with pytest.raises(SystemExit):
            rooms.cmd_link(["myproject/room-1"])

    def test_room_not_found_exits(self, rooms, monkeypatch):
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg())
        with pytest.raises(SystemExit):
            rooms.cmd_link(["myproject/ghost", "/some/repo"])

    def test_nonexistent_source_exits(self, rooms, monkeypatch, tmp_path):
        _, _, _, _ = self._setup(rooms, monkeypatch, tmp_path)
        with pytest.raises(SystemExit):
            rooms.cmd_link(["room-1", str(tmp_path / "nope")])

    def test_target_exists_exits(self, rooms, monkeypatch, tmp_path):
        cfg, room, room_path, repo = self._setup(rooms, monkeypatch, tmp_path)
        (room_path / "sdk").mkdir()  # collision
        with pytest.raises(SystemExit):
            rooms.cmd_link(["room-1", str(repo)])

    def test_duplicate_subdir_exits(self, rooms, monkeypatch, tmp_path):
        cfg, room, room_path, repo = self._setup(rooms, monkeypatch, tmp_path)
        room["linked_repos"] = [{"repo": str(repo), "subdir": "sdk", "path": str(room_path / "sdk")}]
        with pytest.raises(SystemExit):
            rooms.cmd_link(["room-1", str(repo)])

    def test_worktree_add_failure_exits(self, rooms, monkeypatch, tmp_path):
        cfg, room, room_path, repo = self._setup(rooms, monkeypatch, tmp_path)
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "worktree", "add"): (1, "", "fatal: error"),
        }))
        with pytest.raises(SystemExit):
            rooms.cmd_link(["room-1", str(repo)])

    def test_success_detached(self, rooms, monkeypatch, tmp_path, capsys):
        cfg, room, room_path, repo = self._setup(rooms, monkeypatch, tmp_path)
        saved = {}
        monkeypatch.setattr(rooms, "save_config", lambda c: saved.update(c))
        calls = []

        def capturing_run(cmd, cwd=None, check=True):
            calls.append(cmd)
            return make_run({("git", "worktree", "add"): (0, "", "")})(cmd, cwd=cwd, check=check)
        monkeypatch.setattr(rooms, "run", capturing_run)

        rooms.cmd_link(["room-1", str(repo)])

        out = capsys.readouterr().out
        assert "Linked" in out
        # Detached worktree by default
        add_calls = [c for c in calls if "add" in c]
        assert any("--detach" in c for c in add_calls)
        # Config persisted with the linked entry
        entry = saved["rooms"][0]["linked_repos"][0]
        assert entry["subdir"] == "sdk"
        assert entry["path"] == str(room_path / "sdk")

    def test_success_with_branch_and_subdir(self, rooms, monkeypatch, tmp_path):
        cfg, room, room_path, repo = self._setup(rooms, monkeypatch, tmp_path)
        saved = {}
        monkeypatch.setattr(rooms, "save_config", lambda c: saved.update(c))
        calls = []

        def capturing_run(cmd, cwd=None, check=True):
            calls.append(cmd)
            return make_run({("git", "worktree", "add"): (0, "", "")})(cmd, cwd=cwd, check=check)
        monkeypatch.setattr(rooms, "run", capturing_run)

        rooms.cmd_link(["room-1", str(repo), "libs", "develop"])

        add_calls = [c for c in calls if "add" in c]
        assert any("develop" in c for c in add_calls)
        assert all("--detach" not in c for c in add_calls)
        entry = saved["rooms"][0]["linked_repos"][0]
        assert entry["subdir"] == "libs"
        assert entry["path"] == str(room_path / "libs")


# ---------------------------------------------------------------------------
# cmd_unlink
# ---------------------------------------------------------------------------

class TestCmdUnlink:
    def _cfg(self, repo="/repo/sdk", path="/rooms/room-1/sdk"):
        room = make_room(name="room-1", repo="/repo/myproject")
        room["linked_repos"] = [{"repo": repo, "subdir": "sdk", "path": path}]
        return make_cfg(room)

    def test_too_few_args_exits(self, rooms):
        with pytest.raises(SystemExit):
            rooms.cmd_unlink(["myproject/room-1"])

    def test_no_linked_repo_exits(self, rooms, monkeypatch):
        room = make_room(name="room-1", repo="/repo/myproject")
        monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
        with pytest.raises(SystemExit):
            rooms.cmd_unlink(["room-1", "sdk"])

    def test_worktree_remove_failure_exits(self, rooms, monkeypatch):
        monkeypatch.setattr(rooms, "load_config", lambda: self._cfg())
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "worktree", "remove"): (1, "", "fatal: error"),
        }))
        with pytest.raises(SystemExit):
            rooms.cmd_unlink(["room-1", "sdk"])

    def test_success_removes_entry(self, rooms, monkeypatch, capsys):
        cfg = self._cfg()
        saved = {}
        monkeypatch.setattr(rooms, "load_config", lambda: cfg)
        monkeypatch.setattr(rooms, "save_config", lambda c: saved.update(c))
        monkeypatch.setattr(rooms, "run", make_run({
            ("git", "worktree", "remove"): (0, "", ""),
        }))
        rooms.cmd_unlink(["room-1", "sdk"])
        assert "Unlinked" in capsys.readouterr().out
        # linked_repos key is dropped once empty
        assert "linked_repos" not in saved["rooms"][0]


# ---------------------------------------------------------------------------
# cmd_remove cleans up linked worktrees
# ---------------------------------------------------------------------------

class TestCmdRemoveLinked:
    def test_removes_linked_worktrees_first(self, rooms, monkeypatch, tmp_path):
        worktree = tmp_path / "room-1"
        worktree.mkdir()
        room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree))
        room["linked_repos"] = [{"repo": "/repo/sdk", "subdir": "sdk",
                                 "path": str(worktree / "sdk")}]
        cfg = make_cfg(room)
        monkeypatch.setattr(rooms, "load_config", lambda: cfg)
        monkeypatch.setattr(rooms, "save_config", lambda _: None)
        calls = []

        def capturing_run(cmd, cwd=None, check=True):
            calls.append((cmd, cwd))
            return make_run({
                ("git", "rev-parse", "--abbrev-ref"): (0, "room-1\n", ""),
                ("git", "worktree", "remove"):        (0, "", ""),
                ("git", "branch", "-D"):              (0, "", ""),
            })(cmd, cwd=cwd, check=check)
        monkeypatch.setattr(rooms, "run", capturing_run)

        rooms.cmd_remove(["myproject/room-1"])

        # The linked worktree was removed via its own repo before the room itself.
        linked_removed = [c for c, cwd in calls
                          if "worktree" in c and "remove" in c and cwd == "/repo/sdk"]
        assert linked_removed
