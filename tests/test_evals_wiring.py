"""The eval suite runs end to end against the fake provider, so its wiring cannot rot silently.
(Quality checks need the real model; this only proves the script executes and reports.)"""
import subprocess
import sys


def test_eval_runner_executes_with_fake_llm():
    import os
    env = {**os.environ, "LLM_FAKE": "true"}
    out = subprocess.run([sys.executable, "-m", "evals.run_evals"], capture_output=True, text=True, env=env, timeout=120)
    assert "checks passed" in out.stdout, out.stdout + out.stderr
