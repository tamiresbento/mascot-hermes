import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor

import pytest


def test_status_store_is_atomic_validated_and_supports_ten_agents(tmp_path):
    assert importlib.util.find_spec("mascot_studio.events") is not None, "Falta implementar eventos locais"
    from mascot_studio.events import read_agent_states, update_agent_state

    def update(i):
        update_agent_state(tmp_path, f"agente-{i}", "review")

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(update, range(10)))
    states = read_agent_states(tmp_path)
    assert states == {f"agente-{i}": "review" for i in range(10)}
    update_agent_state(tmp_path, "agente-0", "run")
    assert read_agent_states(tmp_path)["agente-0"] == "running"
    payload = json.loads((tmp_path / "agent-states.json").read_text())
    assert payload["schema_version"] == 1
    assert not (tmp_path / ".agent-states.lock").exists()
    for agent, state in [
        ("", "idle"),
        ("x" * 101, "idle"),
        ("agente", "executar_codigo"),
        ("agente", "../idle"),
    ]:
        with pytest.raises(ValueError):
            update_agent_state(tmp_path, agent, state)
    (tmp_path / "agent-states.json").write_text("{" + "x" * 70000)
    with pytest.raises(ValueError):
        read_agent_states(tmp_path)


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": True, "agents": {}},
        {"schema_version": 1, "agents": []},
        {"schema_version": 2, "agents": {}},
        {"schema_version": 1, "agents": {"x": None}},
    ],
)
def test_event_schema_rejects_ambiguous_types(tmp_path, payload):
    from mascot_studio.events import read_agent_states

    (tmp_path / "agent-states.json").write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        read_agent_states(tmp_path)
