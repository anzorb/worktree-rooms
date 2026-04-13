"""Shared fixtures and helpers for the rooms test suite."""

import importlib.machinery
import importlib.util
import pathlib
import subprocess

import pytest

_ROOMS_PATH = pathlib.Path(__file__).parent.parent / "rooms"


def _load_rooms():
    # rooms has no .py extension; use SourceFileLoader to load it explicitly
    loader = importlib.machinery.SourceFileLoader("rooms", str(_ROOMS_PATH))
    spec = importlib.util.spec_from_loader("rooms", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def rooms():
    """The rooms module, loaded once per test session."""
    return _load_rooms()


def make_run(responses: dict):
    """
    Return a drop-in replacement for rooms.run() that matches commands by
    checking whether every string in a key-tuple appears in the argv list.

    responses = {
        ("git", "branch", "-r", "--merged"): (0, "  origin/feat\\n", ""),
        ("git", "status", "--porcelain"):     (0, "",                 ""),
    }

    The first matching key wins. Falls back to (returncode=0, stdout="", stderr="")
    for unmatched commands.  Raises CalledProcessError when returncode != 0 and
    check=True (matching real subprocess.run behaviour).
    """
    def _run(cmd, cwd=None, check=True):
        for key, (rc, stdout, stderr) in responses.items():
            if all(k in cmd for k in key):
                if check and rc != 0:
                    raise subprocess.CalledProcessError(rc, cmd, stderr=stderr)
                return subprocess.CompletedProcess(cmd, rc, stdout, stderr)
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return _run


def make_room(name="room-1", repo="/repo/myproject", path=None,
              placeholder=None, default_branch="main"):
    """Build a minimal room dict."""
    return {
        "name": name,
        "main_repo": repo,
        "path": path or f"/rooms/{name}",
        "placeholder_branch": placeholder or name,
        "default_branch": default_branch,
    }


def make_cfg(*rooms, rooms_base="/rooms"):
    """Build a minimal config dict containing the given room dicts."""
    return {"rooms_base": rooms_base, "rooms": list(rooms)}
