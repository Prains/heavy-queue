"""Self-check: python3 test_heavy_queue.py"""
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

BIN = Path(__file__).parent / "bin" / "heavy-queue"


def run(action, tool_use_id, command, env, **extra):
    event = {"tool_use_id": tool_use_id, "tool_input": {"command": command, **extra}}
    return subprocess.Popen([BIN, action], stdin=subprocess.PIPE, env=env, text=True), json.dumps(event)


def call(action, tool_use_id, command, env, **extra):
    proc, payload = run(action, tool_use_id, command, env, **extra)
    proc.communicate(payload)
    return proc


with tempfile.TemporaryDirectory() as state:
    env = {**os.environ, "HEAVY_QUEUE_DIR": state, "HEAVY_QUEUE_SLOTS": "1"}

    # light and background commands never wait
    call("acquire", "a", "cargo build", env)
    t = time.time()
    call("acquire", "x", "git status", env)
    call("acquire", "y", "cargo test", env, run_in_background=True)
    assert time.time() - t < 1

    # a second heavy command waits until the first releases its slot
    waiter, payload = run("acquire", "b", "npm test", env)
    waiter.stdin.write(payload)
    waiter.stdin.close()
    time.sleep(2)
    assert waiter.poll() is None, "should be waiting for a slot"
    call("release", "a", "cargo build", env)
    assert waiter.wait(timeout=3) == 0

    # a stale lease (cancelled tool call) is reclaimed after the TTL
    call("acquire", "c", "make", {**env, "HEAVY_QUEUE_TTL": "0"})
    assert sorted(p.name for p in Path(state).glob("*.lease")) == ["c.lease"]

print("ok")
