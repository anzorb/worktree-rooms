"""Tests for pure git helper functions."""

import json
import subprocess
import time

import pytest

from conftest import make_run, make_room, make_cfg


# ---------------------------------------------------------------------------
# human_age
# ---------------------------------------------------------------------------

def test_human_age_minutes(rooms, freezer=None):
    now = int(time.time())
    assert rooms.human_age(now - 90) == "1m ago"
    assert rooms.human_age(now - 3000) == "50m ago"


def test_human_age_hours(rooms):
    now = int(time.time())
    assert rooms.human_age(now - 7200) == "2h ago"


def test_human_age_days(rooms):
    now = int(time.time())
    assert rooms.human_age(now - 86400 * 3) == "3d ago"


# ---------------------------------------------------------------------------
# project_of / resolve_room
# ---------------------------------------------------------------------------

def test_project_of(rooms):
    room = make_room(repo="/home/user/dev/myproject")
    assert rooms.project_of(room) == "myproject"


def test_resolve_room_by_full_spec(rooms):
    room = make_room(name="room-1", repo="/repo/myproject")
    cfg = make_cfg(room)
    result = rooms.resolve_room(cfg, "myproject/room-1")
    assert result is room


def test_resolve_room_by_bare_name_unique(rooms):
    room = make_room(name="room-1", repo="/repo/myproject")
    cfg = make_cfg(room)
    result = rooms.resolve_room(cfg, "room-1")
    assert result is room


def test_resolve_room_not_found_exits(rooms):
    cfg = make_cfg()
    with pytest.raises(SystemExit):
        rooms.resolve_room(cfg, "myproject/room-99")


def test_resolve_room_ambiguous_exits(rooms):
    r1 = make_room(name="room-1", repo="/repo/proj-a")
    r2 = make_room(name="room-1", repo="/repo/proj-b")
    cfg = make_cfg(r1, r2)
    with pytest.raises(SystemExit):
        rooms.resolve_room(cfg, "room-1")


def test_resolve_room_bare_not_found_exits(rooms):
    cfg = make_cfg()
    with pytest.raises(SystemExit):
        rooms.resolve_room(cfg, "ghost")


# ---------------------------------------------------------------------------
# branch_merged
# ---------------------------------------------------------------------------

def test_branch_merged_true(rooms, monkeypatch):
    monkeypatch.setattr(rooms, "run", make_run({
        ("git", "branch", "-r", "--merged"): (0, "  origin/main\n  origin/feat\n", ""),
    }))
    assert rooms.branch_merged("/repo", "feat", "main") is True


def test_branch_merged_false(rooms, monkeypatch):
    monkeypatch.setattr(rooms, "run", make_run({
        ("git", "branch", "-r", "--merged"): (0, "  origin/main\n", ""),
    }))
    assert rooms.branch_merged("/repo", "feat", "main") is False


def test_branch_merged_git_error_returns_false(rooms, monkeypatch):
    def bad_run(cmd, cwd=None, check=True):
        raise Exception("git exploded")
    monkeypatch.setattr(rooms, "run", bad_run)
    assert rooms.branch_merged("/repo", "feat", "main") is False


# ---------------------------------------------------------------------------
# branch_fully_pushed
# ---------------------------------------------------------------------------

def test_branch_fully_pushed_no_remote(rooms, monkeypatch):
    monkeypatch.setattr(rooms, "run", make_run({
        ("git", "rev-parse", "origin/feat"): (1, "", "not found"),
    }))
    assert rooms.branch_fully_pushed("/repo", "feat") is False


def test_branch_fully_pushed_ahead(rooms, monkeypatch):
    monkeypatch.setattr(rooms, "run", make_run({
        ("git", "rev-parse", "origin/feat"): (0, "abc123\n", ""),
        ("git", "log", "origin/feat..feat"): (0, "abc123 some commit\n", ""),
    }))
    assert rooms.branch_fully_pushed("/repo", "feat") is False


def test_branch_fully_pushed_clean(rooms, monkeypatch):
    monkeypatch.setattr(rooms, "run", make_run({
        ("git", "rev-parse", "origin/feat"): (0, "abc123\n", ""),
        ("git", "log", "origin/feat..feat"): (0, "", ""),
    }))
    assert rooms.branch_fully_pushed("/repo", "feat") is True


# ---------------------------------------------------------------------------
# get_pr_info — CI status parsing
# ---------------------------------------------------------------------------

def _gh_response(state="OPEN", is_draft=False, rollup=None):
    return json.dumps({
        "url": "https://github.com/org/repo/pull/42",
        "number": 42,
        "state": state,
        "isDraft": is_draft,
        "statusCheckRollup": rollup or [],
    })


def test_get_pr_info_no_pr(rooms, monkeypatch):
    monkeypatch.setattr(rooms, "run", make_run({
        ("gh", "pr", "view"): (1, "", "no pull requests found"),
    }))
    assert rooms.get_pr_info("/repo", "feat") is None


def test_get_pr_info_no_rollup_ci_is_none(rooms, monkeypatch):
    monkeypatch.setattr(rooms, "run", make_run({
        ("gh", "pr", "view"): (0, _gh_response(rollup=[]), ""),
    }))
    info = rooms.get_pr_info("/repo", "feat")
    assert info["ci"] is None
    assert info["number"] == 42
    assert info["draft"] is False


def test_get_pr_info_ci_failing(rooms, monkeypatch):
    rollup = [{"conclusion": "FAILURE", "status": "COMPLETED"}]
    monkeypatch.setattr(rooms, "run", make_run({
        ("gh", "pr", "view"): (0, _gh_response(rollup=rollup), ""),
    }))
    assert rooms.get_pr_info("/repo", "feat")["ci"] == "failing"


def test_get_pr_info_ci_pending(rooms, monkeypatch):
    rollup = [{"conclusion": None, "status": "IN_PROGRESS"}]
    monkeypatch.setattr(rooms, "run", make_run({
        ("gh", "pr", "view"): (0, _gh_response(rollup=rollup), ""),
    }))
    assert rooms.get_pr_info("/repo", "feat")["ci"] == "pending"


def test_get_pr_info_ci_passing(rooms, monkeypatch):
    rollup = [{"conclusion": "SUCCESS", "status": "COMPLETED"}]
    monkeypatch.setattr(rooms, "run", make_run({
        ("gh", "pr", "view"): (0, _gh_response(rollup=rollup), ""),
    }))
    assert rooms.get_pr_info("/repo", "feat")["ci"] == "passing"


def test_get_pr_info_ci_error_counts_as_failing(rooms, monkeypatch):
    rollup = [{"conclusion": "ERROR", "status": "COMPLETED"}]
    monkeypatch.setattr(rooms, "run", make_run({
        ("gh", "pr", "view"): (0, _gh_response(rollup=rollup), ""),
    }))
    assert rooms.get_pr_info("/repo", "feat")["ci"] == "failing"


def test_get_pr_info_draft(rooms, monkeypatch):
    monkeypatch.setattr(rooms, "run", make_run({
        ("gh", "pr", "view"): (0, _gh_response(is_draft=True), ""),
    }))
    assert rooms.get_pr_info("/repo", "feat")["draft"] is True


def test_get_pr_info_returns_state(rooms, monkeypatch):
    monkeypatch.setattr(rooms, "run", make_run({
        ("gh", "pr", "view"): (0, _gh_response(state="MERGED"), ""),
    }))
    assert rooms.get_pr_info("/repo", "feat")["state"] == "MERGED"
