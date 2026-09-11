"""HTTP client for the unofficial Grok Bot desktop gateway.

The Grok Bot app on a Mac can expose an internal HTTP API (community
docs: typically ``http://127.0.0.1:1340``, token in
``sand-data/gateway.json``). This is **not** an official xAI public API
and is **not** available inside this Cloud Agent VM.

Env (highest priority):
  GROKBOT_GATEWAY_URL   e.g. http://127.0.0.1:1340
  SAND_GATEWAY_TOKEN    bearer token

Disk fallback:
  GROKBOT_GATEWAY_JSON  path to gateway.json
  else ~/.grok-bot/gateway.json, then cwd sand-data/gateway.json
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_PORT = 1340
DEFAULT_BASE = f"http://127.0.0.1:{DEFAULT_PORT}"
GATEWAY_JSON_CANDIDATES = (
    Path.home() / ".grok-bot" / "gateway.json",
    Path("sand-data") / "gateway.json",
    Path("/home/box/sand-data/gateway.json"),
)


class GatewayError(RuntimeError):
    pass


@dataclass(frozen=True)
class GatewayConfig:
    base_url: str
    token: str
    source: str


def load_gateway_config(
    *,
    url: str | None = None,
    token: str | None = None,
    json_path: str | Path | None = None,
) -> GatewayConfig | None:
    env_url = (url or os.environ.get("GROKBOT_GATEWAY_URL") or "").strip()
    env_token = (token or os.environ.get("SAND_GATEWAY_TOKEN") or "").strip()
    if env_url and env_token:
        return GatewayConfig(env_url.rstrip("/"), env_token, "env")

    path: Path | None = None
    if json_path:
        path = Path(json_path)
    else:
        env_json = (os.environ.get("GROKBOT_GATEWAY_JSON") or "").strip()
        if env_json:
            path = Path(env_json)
        else:
            for candidate in GATEWAY_JSON_CANDIDATES:
                if candidate.is_file():
                    path = candidate
                    break
    if path is None or not path.is_file():
        if env_url or env_token:
            raise GatewayError(
                "Gateway URL and token must both be set "
                "(GROKBOT_GATEWAY_URL + SAND_GATEWAY_TOKEN)."
            )
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    tok = str(data.get("token") or data.get("gatewayToken") or "").strip()
    port = data.get("port") or DEFAULT_PORT
    base = str(data.get("url") or data.get("baseUrl") or f"http://127.0.0.1:{port}").rstrip("/")
    if env_url:
        base = env_url.rstrip("/")
    if env_token:
        tok = env_token
    if not tok:
        raise GatewayError(f"No token in {path}")
    return GatewayConfig(base, tok, str(path))


def _post(cfg: GatewayConfig, command: str, body: dict[str, Any], *, timeout: float = 60) -> Any:
    url = f"{cfg.base_url}/api/{command}"
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {cfg.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise GatewayError(f"{command} HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise GatewayError(f"{command} failed: {e.reason}") from e
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"text": raw}


def list_agents(cfg: GatewayConfig) -> list[dict[str, Any]]:
    data = _post(cfg, "listAgents", {})
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("agents", "data", "result"):
            val = data.get(key)
            if isinstance(val, list):
                return val
    raise GatewayError(f"Unexpected listAgents payload: {type(data).__name__}")


def find_agent(agents: list[dict[str, Any]], *, name: str) -> dict[str, Any] | None:
    want = name.strip().casefold()
    for agent in agents:
        label = str(agent.get("name") or agent.get("title") or "").strip().casefold()
        if label == want:
            return agent
    return None


def create_agent(
    cfg: GatewayConfig,
    *,
    name: str,
    instructions: str,
    model: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"name": name, "instructions": instructions}
    if model:
        body["model"] = model
    data = _post(cfg, "createAgent", body, timeout=120)
    if isinstance(data, dict):
        return data
    raise GatewayError(f"Unexpected createAgent payload: {type(data).__name__}")


def send_prompt(cfg: GatewayConfig, *, agent_id: str, prompt: str, timeout: float = 180) -> Any:
    return _post(
        cfg,
        "sendPrompt",
        {"agentId": agent_id, "prompt": prompt},
        timeout=timeout,
    )


def agent_id_of(agent: dict[str, Any]) -> str:
    for key in ("id", "agentId", "uuid"):
        val = agent.get(key)
        if val:
            return str(val)
    raise GatewayError(f"Agent has no id: {agent!r}"[:400])


def agent_status_of(agent: dict[str, Any]) -> str:
    return str(agent.get("status") or agent.get("state") or "").strip().lower()


def wait_until_idle(
    cfg: GatewayConfig,
    *,
    agent_id: str,
    timeout_s: float = 180,
    poll_s: float = 2.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        agents = list_agents(cfg)
        for agent in agents:
            try:
                if agent_id_of(agent) != agent_id:
                    continue
            except GatewayError:
                continue
            last = agent
            status = agent_status_of(agent)
            if status in {"idle", "ready", "", "complete", "completed"}:
                return agent
        time.sleep(poll_s)
    raise GatewayError(f"Timed out waiting for agent {agent_id} to go idle (last={last})")


def extract_reply_text(payload: Any, agent: dict[str, Any] | None = None) -> str:
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    if isinstance(payload, dict):
        for key in ("text", "message", "reply", "content", "result", "output"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        msgs = payload.get("messages")
        if isinstance(msgs, list) and msgs:
            last = msgs[-1]
            if isinstance(last, str) and last.strip():
                return last.strip()
            if isinstance(last, dict):
                for key in ("text", "content", "message"):
                    val = last.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
    if agent:
        for key in ("lastMessage", "lastReply", "output"):
            val = agent.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        msgs = agent.get("messages")
        if isinstance(msgs, list) and msgs:
            last = msgs[-1]
            if isinstance(last, dict):
                for key in ("text", "content"):
                    val = last.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
            if isinstance(last, str) and last.strip():
                return last.strip()
    raise GatewayError("sendPrompt returned no reply text")


def enablement_text() -> str:
    return """The clock is the Commissioner Bot (Grok cloud), not a Mac.

Daily: python scripts/daily_ops.py
  → POST that public JSON to the Commissioner's daily-slate webhook
  → Commissioner wakes GMs; orchestrator sends each GM its pack

GMs have no calendars. Owned teams stay on Cursor.

Mac gateway (GROKBOT_GATEWAY_URL) is optional leftover, not the product.
"""
