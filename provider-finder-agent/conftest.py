"""Shared test setup. Tests never use the real Muse or your API key."""
import os
import sys
from types import SimpleNamespace as NS

os.environ["MOCK_MODEL"] = "1"                      # must be set before agent is imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import agent


@pytest.fixture(autouse=True)
def quiet(tmp_path, monkeypatch):
    """Run logs go to a temp folder, and mock flags start off."""
    monkeypatch.setattr(agent, "RUN_LOG_DIR", str(tmp_path / "runs"))
    for k in ("MOCK_BAD_QUOTE", "MOCK_BAD_FINAL", "MOCK_CARD_TEXT"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def web():
    import app as webapp
    webapp.SESSIONS.clear()
    return webapp.app.test_client()


# ---- a tiny scripted model, so a test can make Muse misbehave on purpose ----
def call(i, name, args):
    import json
    return NS(id=f"c{i}", type="function", function=NS(name=name, arguments=json.dumps(args)))


def reply(content=None, calls=None):
    return NS(choices=[NS(message=NS(content=content, tool_calls=calls or None),
                          finish_reason="tool_calls" if calls else "stop")])


class Scripted:
    """Gives back the prepared replies one by one. Raises if a reply is an Exception."""
    def __init__(self, replies):
        self.replies, self.seen = list(replies), []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.seen.append(kw)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture
def scripted(monkeypatch):
    def make(replies):
        c = Scripted(replies)
        monkeypatch.setattr(agent, "get_client", lambda: c)
        return c
    return make
