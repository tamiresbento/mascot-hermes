"""Eventos explícitos de agentes por arquivo local; sem rede nem credenciais."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import time
import uuid

MAX_BYTES = 65536
STATES = frozenset(
    ("idle", "running-right", "running-left", "waving", "jumping", "failed", "waiting", "running", "review")
)
ALIASES = {"run": "running", "wave": "waving", "jump": "jumping"}


def _validate_agent(agent: str) -> None:
    if not isinstance(agent, str) or not agent.strip() or len(agent) > 100 or any(ord(x) < 32 for x in agent):
        raise ValueError("Identificador de agente deve conter entre 1 e 100 caracteres, sem controles.")


def read_agent_states(root: Path) -> dict[str, str]:
    path = Path(root) / "agent-states.json"
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return {}
    if len(data) > MAX_BYTES:
        raise ValueError("Arquivo de eventos excede 64 KiB.")
    try:
        payload = json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Arquivo de eventos não é JSON válido.") from exc
    if (
        not isinstance(payload, dict)
        or type(payload.get("schema_version")) is not int
        or payload.get("schema_version") != 1
        or not isinstance(payload.get("agents"), dict)
    ):
        raise ValueError("Formato de eventos inválido; esperado schema_version 1 e agents.")
    agents = payload["agents"]
    for agent, state in agents.items():
        _validate_agent(agent)
        if not isinstance(state, str) or state not in STATES:
            raise ValueError("Estado inválido no arquivo de eventos.")
    return dict(agents)


@contextmanager
def _locked(root: Path):
    lock = root / ".agent-states.lock"
    deadline = time.monotonic() + 5
    while True:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            break
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise ValueError(
                    "Arquivo de eventos ocupado; se nenhum processo estiver ativo, remova .agent-states.lock."
                ) from exc
            time.sleep(0.025)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def update_agent_state(root: Path, agent: str, state: str) -> dict[str, str]:
    _validate_agent(agent)
    if not isinstance(state, str):
        raise ValueError("Estado deve ser texto.")
    state = ALIASES.get(state, state)
    if state not in STATES:
        raise ValueError("Estado inválido. Use idle, running, review, waiting, waving, jumping ou failed.")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with _locked(root):
        agents = read_agent_states(root)
        agents[agent] = state
        data = (
            json.dumps({"schema_version": 1, "agents": agents}, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        if len(data) > MAX_BYTES:
            raise ValueError("Eventos excedem 64 KiB; mantenha apenas os agentes em uso.")
        temp = root / f".agent-states-{uuid.uuid4().hex}.tmp"
        try:
            temp.write_bytes(data)
            os.replace(temp, root / "agent-states.json")
        finally:
            temp.unlink(missing_ok=True)
    return agents
