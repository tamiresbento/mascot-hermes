import json
import os
import subprocess
import sys


def test_cli_help_and_agent_status_work_without_gui(tmp_path):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    cmd = [sys.executable, "-m", "mascot_studio"]
    result = subprocess.run(cmd + ["--help"], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert "sample" in result.stdout and "status" in result.stdout
    result = subprocess.run(
        cmd + ["--library", str(tmp_path), "status", "agente-exemplo", "review"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads((tmp_path / "agent-states.json").read_text())["agents"]["agente-exemplo"] == "review"
    result = subprocess.run(
        cmd + ["--library", str(tmp_path), "status", "agente-exemplo", "not-a-state"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
