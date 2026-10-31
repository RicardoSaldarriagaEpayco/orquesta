import os
import subprocess
import sys
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo.sh"


def test_demo_runs_end_to_end() -> None:
    env = {**os.environ, "ORQUESTA_BIN": str(Path(sys.executable).parent / "orquesta"), "ORQUESTA_ACTOR": "demo"}
    result = subprocess.run(["bash", str(DEMO)], capture_output=True, text=True, env=env, timeout=300)
    assert result.returncode == 0, result.stderr
    assert "skill/ship" in result.stdout
    assert "[readonly-repo]" in result.stdout
    assert '"accuracy": 0.9333' in result.stdout and '"ask_recall": 0.8' in result.stdout
