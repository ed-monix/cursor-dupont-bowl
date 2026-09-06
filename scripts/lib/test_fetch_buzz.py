"""Tests for scripts/fetch_buzz.py — dual-mode X buzz for the tabloid.

Hermetic: tmp_path repos, requests.post monkeypatched. The invariant under
test everywhere: NO failure path may raise — a broken/missing buzz source
means "skipped", never a blocked league run.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import fetch_buzz


class _FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise fetch_buzz.requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _ok_payload(text="- Everyone is furious about the Bears offensive line."):
    return {"choices": [{"message": {"content": text}}]}


def test_manual_file_short_circuits_and_is_never_overwritten(tmp_path, monkeypatch):
    path = fetch_buzz.buzz_path(tmp_path, 3)
    path.parent.mkdir(parents=True)
    path.write_text("# my pasted buzz\n- CMC hype is out of control\n")
    monkeypatch.setenv("GROK_API_KEY", "k")  # key present, must still not call

    def boom(*a, **kw):
        raise AssertionError("API must not be called when a manual file exists")
    monkeypatch.setattr(fetch_buzz.requests, "post", boom)

    status, detail = fetch_buzz.gather_buzz(tmp_path, 3)
    assert status == "manual"
    assert "CMC hype" in path.read_text()


def test_no_key_no_file_skips_cleanly(tmp_path, monkeypatch):
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    status, detail = fetch_buzz.gather_buzz(tmp_path, 3)
    assert status == "skipped"
    assert not fetch_buzz.buzz_path(tmp_path, 3).exists()


def test_api_success_writes_header_and_content(tmp_path, monkeypatch):
    monkeypatch.setenv("GROK_API_KEY", "k")
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResponse(payload=_ok_payload())
    monkeypatch.setattr(fetch_buzz.requests, "post", fake_post)

    status, detail = fetch_buzz.gather_buzz(tmp_path, 5)
    assert status == "api"
    text = fetch_buzz.buzz_path(tmp_path, 5).read_text()
    assert "source: grok live search" in text
    assert "furious about the Bears" in text
    # Sentiment-only guard is written into the file itself.
    assert "sole source of facts" in text
    # The call carried the key and asked X live search.
    assert captured["headers"]["Authorization"] == "Bearer k"
    assert captured["json"]["search_parameters"]["sources"] == [{"type": "x"}]


@pytest.mark.parametrize("failure", [
    lambda *a, **kw: _FakeResponse(status=500),
    lambda *a, **kw: _FakeResponse(payload={"choices": []}),
    lambda *a, **kw: _FakeResponse(payload=_ok_payload("   ")),
    lambda *a, **kw: (_ for _ in ()).throw(
        fetch_buzz.requests.ConnectionError("no route")),
])
def test_every_api_failure_becomes_skipped_not_raised(tmp_path, monkeypatch, failure):
    monkeypatch.setenv("GROK_API_KEY", "k")
    monkeypatch.setattr(fetch_buzz.requests, "post", failure)

    status, detail = fetch_buzz.gather_buzz(tmp_path, 5)
    assert status == "skipped"
    assert not fetch_buzz.buzz_path(tmp_path, 5).exists()


def test_empty_existing_file_falls_through_to_skip_without_key(tmp_path, monkeypatch):
    path = fetch_buzz.buzz_path(tmp_path, 7)
    path.parent.mkdir(parents=True)
    path.write_text("   \n")
    monkeypatch.delenv("GROK_API_KEY", raising=False)

    status, _ = fetch_buzz.gather_buzz(tmp_path, 7)
    assert status == "skipped"
