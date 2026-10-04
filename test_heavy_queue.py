"""Self-check: python3 test_heavy_queue.py"""
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

BIN = Path(__file__).parent / "bin" / "heavy-queue"


def start(action, env, session="s1", tool_use_id=None, command=None, **extra):
    event = {"session_id": session, **extra.pop("agent", {})}
    if tool_use_id:
        event |= {"tool_use_id": tool_use_id, "tool_input": {"command": command, **extra}}
    proc = subprocess.Popen([BIN, action], stdin=subprocess.PIPE, env=env, text=True)
    proc.stdin.write(json.dumps(event))
    proc.stdin.close()
    return proc


def call(*args, **kwargs):
    proc = start(*args, **kwargs)
    assert proc.wait(timeout=5) == 0
    return proc


def leases(state):
    return sorted(p.name for p in Path(state).glob("*.lease"))


with tempfile.TemporaryDirectory() as state:
    env = {**os.environ, "HEAVY_QUEUE_DIR": state, "HEAVY_QUEUE_SLOTS": "1"}

    # light and background commands never wait
    call("acquire", env, "s1", "a", "cargo build")
    t = time.time()
    call("acquire", env, "s2", "x", "git status")
    call("acquire", env, "s2", "z", "cat vitest.config.ts | grep 'make'")
    call("acquire", env, "s2", "y", "cargo test", run_in_background=True)
    assert time.time() - t < 1

    # another agent's heavy command waits until the slot is released
    waiter = start("acquire", env, "s2", "b", "npm test")
    time.sleep(2)
    assert waiter.poll() is None, "should be waiting for a slot"
    call("release", env, "s1", "a", "cargo build")
    assert waiter.wait(timeout=3) == 0
    assert leases(state) == ["s2_main.b.lease"]

    # the same agent's next heavy command drops its leftover lease instead of waiting on it
    call("acquire", env, "s2", "c", "make")
    assert leases(state) == ["s2_main.c.lease"]

    # Stop releases the main agent's leases, SubagentStop only that subagent's
    call("release", env, "s2")
    assert leases(state) == []
    call("acquire", {**env, "HEAVY_QUEUE_SLOTS": "2"}, "s3", "d", "make", agent={"agent_id": "sub1"})
    call("acquire", {**env, "HEAVY_QUEUE_SLOTS": "2"}, "s3", "g", "make")
    call("release", env, "s3", agent={"agent_id": "sub1"})
    assert leases(state) == ["s3_main.g.lease"]
    call("release", env, "s3")
    assert leases(state) == []

    # a lease nobody released is reclaimed after the TTL
    call("acquire", env, "s4", "e", "make")
    call("acquire", {**env, "HEAVY_QUEUE_TTL": "0"}, "s5", "f", "make")
    assert leases(state) == ["s5_main.f.lease"]
    call("release", env, "s5")

    # a project's .claude/heavy-queue-patterns adds to the defaults
    with tempfile.TemporaryDirectory() as project:
        (Path(project) / ".claude").mkdir()
        (Path(project) / ".claude" / "heavy-queue-patterns").write_text("# comment\n\\bnuxi\\s+prepare\\b\n")
        call("acquire", {**env, "CLAUDE_PROJECT_DIR": project}, "s6", "h", "bunx nuxi prepare")
        call("acquire", {**env, "CLAUDE_PROJECT_DIR": project}, "s7", "i", "git status")
        assert leases(state) == ["s6_main.h.lease"]

print("ok")
