"""Tests for rooms ls --json output."""

import json

from conftest import make_run, make_room, make_cfg


def _busy(rooms, monkeypatch, tmp_path, branch, info):
    worktree = tmp_path / "room-1"
    worktree.mkdir()
    room = make_room(name="room-1", repo="/repo/myproject", path=str(worktree))
    monkeypatch.setattr(rooms, "load_config", lambda: make_cfg(room))
    monkeypatch.setattr(rooms, "save_config", lambda _: None)
    monkeypatch.setattr(rooms, "parallel_fetch", lambda _: {"/repo/myproject": True})
    monkeypatch.setattr(rooms, "parallel_room_info", lambda *_: info)
    monkeypatch.setattr(rooms, "run", make_run({
        ("git", "rev-parse", "--abbrev-ref"): (0, branch + "\n", ""),
    }))
    return worktree


def test_json_in_progress(rooms, monkeypatch, tmp_path, capsys):
    _busy(rooms, monkeypatch, tmp_path, "feat", {"room-1": (False, None, False, "2h ago", {})})
    rooms.cmd_ls(["--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["version"] == 1
    r = data["rooms"][0]
    assert r["project"] == "myproject"
    assert r["name"] == "room-1"
    assert r["status"] == "in-progress"
    assert r["branch"] == "feat"
    assert r["last_commit_age"] == "2h ago"
    assert r["pr"] is None


def test_json_free_room(rooms, monkeypatch, tmp_path, capsys):
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
    rooms.cmd_ls(["--json"])
    r = json.loads(capsys.readouterr().out)["rooms"][0]
    assert r["status"] == "free"
    assert r["branch"] is None


def test_json_pr_fields(rooms, monkeypatch, tmp_path, capsys):
    pr_info = {"url": "https://github.com/org/repo/pull/42", "number": 42,
               "ci": "passing", "draft": False, "title": "Fix the thing"}
    _busy(rooms, monkeypatch, tmp_path, "feat", {"room-1": (False, pr_info, False, "1h ago", {})})
    rooms.cmd_ls(["--json"])
    r = json.loads(capsys.readouterr().out)["rooms"][0]
    assert r["status"] == "in-progress"
    assert r["pr"]["number"] == 42
    assert r["pr"]["ci"] == "passing"
    assert r["pr"]["title"] == "Fix the thing"
    assert r["merged"] is False


def test_json_empty(rooms, monkeypatch, capsys):
    monkeypatch.setattr(rooms, "load_config", lambda: make_cfg())
    rooms.cmd_ls(["--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["rooms"] == []