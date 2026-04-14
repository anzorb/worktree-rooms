"""Tests for get_remote_info (online/offline/cache) and format_status."""

import pytest

from conftest import make_run, make_room, make_cfg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PR_INFO = {"url": "https://github.com/org/repo/pull/42", "number": 42, "ci": "passing", "draft": False, "state": "OPEN"}
PR_INFO_MERGED = {**PR_INFO, "state": "MERGED"}
PR_INFO_DRAFT = {**PR_INFO, "draft": True}
PR_INFO_FAILING = {**PR_INFO, "ci": "failing"}
PR_INFO_PENDING = {**PR_INFO, "ci": "pending"}


# ---------------------------------------------------------------------------
# format_status
# ---------------------------------------------------------------------------

def test_format_status_merged_with_pr(rooms):
    result = rooms.format_status(merged=True, pr_info=PR_INFO)
    assert "🟣 merged" in result
    assert "#42" in result


def test_format_status_merged_no_pr(rooms):
    result = rooms.format_status(merged=True, pr_info=None)
    assert "🟣 merged" in result
    assert "#" not in result


def test_format_status_in_progress_no_pr(rooms):
    result = rooms.format_status(merged=False, pr_info=None)
    assert "🔨in-progress" in result
    assert "no PR" in result


def test_format_status_in_progress_with_pr_passing(rooms):
    result = rooms.format_status(merged=False, pr_info=PR_INFO)
    assert "🔨in-progress" in result
    assert "#42" in result
    assert "✅" in result


def test_format_status_in_progress_with_pr_failing(rooms):
    result = rooms.format_status(merged=False, pr_info=PR_INFO_FAILING)
    assert "❌" in result


def test_format_status_in_progress_with_pr_pending(rooms):
    result = rooms.format_status(merged=False, pr_info=PR_INFO_PENDING)
    assert "🔄" in result


def test_format_status_draft_pr(rooms):
    result = rooms.format_status(merged=False, pr_info=PR_INFO_DRAFT)
    assert "draft" in result


def test_format_status_pr_without_url_shows_no_pr(rooms):
    pr_no_url = {"url": None, "number": 42, "ci": "passing", "draft": False}
    result = rooms.format_status(merged=False, pr_info=pr_no_url)
    assert "no PR" in result


# ---------------------------------------------------------------------------
# get_remote_info — online
# ---------------------------------------------------------------------------

def test_get_remote_info_online_merged(rooms, monkeypatch):
    room = make_room(name="room-1", repo="/repo/myproject")

    monkeypatch.setattr(rooms, "branch_merged", lambda *_: True)
    monkeypatch.setattr(rooms, "get_pr_info", lambda *_: PR_INFO)
    monkeypatch.setattr(rooms, "branch_fully_pushed", lambda *_: False)

    merged, pr_info, pushed, update = rooms.get_remote_info(room, "feat", True, {})

    assert merged is True
    assert pr_info == PR_INFO
    # pushed is always False when merged (no need to check)
    assert pushed is False
    key = "myproject/room-1:feat"
    assert update[key]["merged"] is True
    assert update[key]["pr_url"] == PR_INFO["url"]


def test_get_remote_info_online_not_merged_pushed(rooms, monkeypatch):
    room = make_room(name="room-1", repo="/repo/myproject")

    monkeypatch.setattr(rooms, "branch_merged", lambda *_: False)
    monkeypatch.setattr(rooms, "get_pr_info", lambda *_: None)
    monkeypatch.setattr(rooms, "branch_fully_pushed", lambda *_: True)

    merged, pr_info, pushed, update = rooms.get_remote_info(room, "feat", True, {})

    assert merged is False
    assert pr_info is None
    assert pushed is True
    assert update["myproject/room-1:feat"]["pushed"] is True


def test_get_remote_info_online_cache_update_contains_all_fields(rooms, monkeypatch):
    room = make_room(name="room-1", repo="/repo/myproject")

    monkeypatch.setattr(rooms, "branch_merged", lambda *_: False)
    monkeypatch.setattr(rooms, "get_pr_info", lambda *_: PR_INFO_DRAFT)
    monkeypatch.setattr(rooms, "branch_fully_pushed", lambda *_: False)

    _, _, _, update = rooms.get_remote_info(room, "feat", True, {})
    entry = update["myproject/room-1:feat"]

    assert entry["pr_draft"] is True
    assert entry["ci"] == "passing"
    assert entry["pr_number"] == 42


def test_get_remote_info_merged_pr_overrides_branch_merged(rooms, monkeypatch):
    """If gh reports the PR as MERGED, treat the room as merged even when
    branch_merged (git-based) returns False (e.g. remote branch was deleted)."""
    room = make_room(name="room-1", repo="/repo/myproject")

    monkeypatch.setattr(rooms, "branch_merged", lambda *_: False)
    monkeypatch.setattr(rooms, "get_pr_info", lambda *_: PR_INFO_MERGED)
    monkeypatch.setattr(rooms, "branch_fully_pushed", lambda *_: False)

    merged, pr_info, pushed, update = rooms.get_remote_info(room, "feat", True, {})

    assert merged is True
    assert update["myproject/room-1:feat"]["merged"] is True
    # pushed is skipped when merged
    assert pushed is False


# ---------------------------------------------------------------------------
# get_remote_info — offline
# ---------------------------------------------------------------------------

def test_get_remote_info_offline_reads_cache(rooms, monkeypatch):
    room = make_room(name="room-1", repo="/repo/myproject")
    cache = {
        "myproject/room-1:feat": {
            "merged": False,
            "pushed": True,
            "pr_url": PR_INFO["url"],
            "pr_number": 42,
            "pr_draft": False,
            "ci": "passing",
        }
    }

    merged, pr_info, pushed, update = rooms.get_remote_info(room, "feat", False, cache)

    assert merged is False
    assert pushed is True
    assert pr_info["number"] == 42
    assert pr_info["ci"] == "passing"
    assert update == {}  # no cache updates when offline


def test_get_remote_info_offline_empty_cache_returns_defaults(rooms, monkeypatch):
    room = make_room(name="room-1", repo="/repo/myproject")

    merged, pr_info, pushed, update = rooms.get_remote_info(room, "feat", False, {})

    assert merged is False
    assert pr_info is None
    assert pushed is False
    assert update == {}


def test_get_remote_info_offline_no_pr_url_gives_none_pr_info(rooms, monkeypatch):
    room = make_room(name="room-1", repo="/repo/myproject")
    cache = {
        "myproject/room-1:feat": {
            "merged": True,
            "pushed": False,
            "pr_url": None,
            "pr_number": None,
            "pr_draft": False,
            "ci": None,
        }
    }

    merged, pr_info, pushed, _ = rooms.get_remote_info(room, "feat", False, cache)

    assert merged is True
    assert pr_info is None
