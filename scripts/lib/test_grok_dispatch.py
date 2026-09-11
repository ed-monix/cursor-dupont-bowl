"""Gateway client + one-command Grok Bot dispatch (no live Bots)."""
from __future__ import annotations

import json
from pathlib import Path
import grok_bots as grok_bots_cli
from lib import grok_bots
from lib import grok_dispatch
from lib.grok_gateway import (
    GatewayConfig,
    GatewayError,
    enablement_text,
    extract_reply_text,
    find_agent,
    load_gateway_config,
)

REPO = Path(__file__).resolve().parents[2]
CFG = GatewayConfig("http://127.0.0.1:1340", "tok", "test")


def test_load_gateway_config_from_env(monkeypatch, tmp_path):
    monkeypatch.delenv("GROKBOT_GATEWAY_URL", raising=False)
    monkeypatch.delenv("SAND_GATEWAY_TOKEN", raising=False)
    monkeypatch.delenv("GROKBOT_GATEWAY_JSON", raising=False)
    assert load_gateway_config() is None

    monkeypatch.setenv("GROKBOT_GATEWAY_URL", "http://127.0.0.1:1340")
    monkeypatch.setenv("SAND_GATEWAY_TOKEN", "abc")
    cfg = load_gateway_config()
    assert cfg.token == "abc"
    assert cfg.source == "env"

    path = tmp_path / "gateway.json"
    path.write_text(json.dumps({"token": "filetok", "port": 1340}))
    monkeypatch.delenv("GROKBOT_GATEWAY_URL")
    monkeypatch.delenv("SAND_GATEWAY_TOKEN")
    cfg = load_gateway_config(json_path=path)
    assert cfg.token == "filetok"
    assert cfg.base_url.endswith(":1340")


def test_extract_reply_text_shapes():
    assert extract_reply_text({"text": '{"claims":[]}'}) == '{"claims":[]}'
    assert extract_reply_text({"messages": [{"content": "hi"}]}) == "hi"
    agent = {"messages": [{"text": "from-agent"}]}
    try:
        extract_reply_text({}, None)
        assert False, "expected GatewayError"
    except GatewayError:
        pass
    assert extract_reply_text({}, agent) == "from-agent"


def test_find_agent_casefold():
    agents = [{"id": "1", "name": "GM Costanza"}]
    assert find_agent(agents, name="gm costanza")["id"] == "1"
    assert find_agent(agents, name="nope") is None


def test_ensure_links_existing_without_create():
    roster = grok_bots.load_roster(REPO)
    created = []

    def fake_create(*_a, **_k):
        created.append(1)
        return {"id": "should-not"}

    def fake_list(_cfg):
        return [{"id": "agt-costanza", "name": "GM Costanza"}]

    # Only Costanza missing an id; others already blank — fake list only has Costanza
    # so other grok_bot rows would try create. Strip to one role.
    slim = {
        "roles": [
            next(r for r in roster["roles"] if r.get("slug") == "costanza"),
        ]
    }
    out, notes = grok_dispatch.ensure_agents(
        CFG, slim, root=REPO, create=fake_create, list_fn=fake_list
    )
    assert created == []
    assert out["roles"][0]["gateway_agent_id"] == "agt-costanza"
    assert notes and "linked" in notes[0]


def test_ensure_creates_when_missing():
    roster = grok_bots.load_roster(REPO)
    slim = {
        "roles": [
            next(r for r in roster["roles"] if r.get("slug") == "costanza"),
        ]
    }
    calls = []

    def fake_create(_cfg, **kwargs):
        calls.append(kwargs)
        return {"id": "new-1"}

    def fake_list(_cfg):
        return []

    out, notes = grok_dispatch.ensure_agents(
        CFG, slim, root=REPO, create=fake_create, list_fn=fake_list
    )
    assert calls and "Costanza" in calls[0]["name"]
    assert "general-manager.md" not in calls[0]["instructions"] or "pack" in calls[0]["instructions"].lower()
    assert "## Football Philosophy" not in calls[0]["instructions"]
    assert out["roles"][0]["gateway_agent_id"] == "new-1"
    assert "created" in notes[0]


def test_dispatch_one_writes_validated_json(tmp_path):
    roster = grok_bots.load_roster(REPO)
    role = next(r for r in roster["roles"] if r.get("slug") == "costanza")
    reply = json.dumps({
        "claims": [],
        "drops": [],
        "note_reply": "No claims. The universe is already punishing me.",
    })

    def fake_send(_cfg, **_k):
        return {"text": reply}

    result = grok_dispatch.dispatch_one(
        CFG,
        week=1,
        kind="waivers",
        role=role,
        agent_id="agt-1",
        pack_root=REPO,
        out_root=tmp_path,
        send=fake_send,
        wait=lambda *_a, **_k: {},
    )
    assert result.ok, result.error
    path = Path(result.path)
    assert path.exists()
    body = json.loads(path.read_text())
    assert body["claims"] == []
    # Isolation: prompt is huge but we did not copy GM files onto a bot disk.
    assert "costanza.json" in result.path


def test_dispatch_week_skips_owned_and_requires_id():
    results = grok_dispatch.dispatch_week(
        CFG,
        week=1,
        kind="waivers",
        root=REPO,
        out_root=REPO / "does-not-write",
        slugs=["your-team"],
        dry_run=True,
    )
    assert results
    assert results[0].ok is False
    assert "celebrity" in (results[0].error or "")


def test_dispatch_dry_run_does_not_send(tmp_path):
    roster = grok_bots.load_roster(REPO)
    role = next(r for r in roster["roles"] if r.get("slug") == "costanza")
    sent = []

    def boom(*_a, **_k):
        sent.append(1)
        raise AssertionError("send should not run")

    result = grok_dispatch.dispatch_one(
        CFG,
        week=1,
        kind="waivers",
        role=role,
        agent_id="agt-1",
        pack_root=REPO,
        out_root=tmp_path,
        send=boom,
        dry_run=True,
    )
    assert result.skipped is True
    assert sent == []
    assert not list(tmp_path.rglob("*.json"))


def test_cli_dispatch_without_gateway_prints_enablement(monkeypatch, capsys):
    monkeypatch.setattr(grok_bots_cli, "load_gateway_config", lambda **_k: None)
    code = grok_bots_cli.main([
        "--root", str(REPO), "dispatch", "--week", "1", "--kind", "waivers",
    ])
    assert code == 2
    err = capsys.readouterr().err
    assert "commish_gate.py" in err
    assert "git gate" in enablement_text()


def test_cli_run_sheet_says_dispatch(capsys):
    code = grok_bots_cli.main([
        "--root", str(REPO), "run-sheet", "--week", "1", "--run", "waivers",
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "dispatch --week 1 --kind waivers" in out
    assert "Do not paste 12 packs" in out


def test_celebrity_gm_roles_excludes_owned():
    roster = grok_bots.load_roster(REPO)
    slugs = {r["slug"] for r in grok_dispatch.celebrity_gm_roles(roster)}
    assert "your-team" not in slugs
    assert "wifes-team" not in slugs
    assert "costanza" in slugs
    assert len(slugs) == 10
