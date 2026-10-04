# heavy-queue

A Claude Code plugin that queues heavy builds and tests, so parallel agents in separate worktrees don't all compile at once and fight over CPU, RAM and disk.

> Not affiliated with or endorsed by Anthropic. "Claude" is a trademark of Anthropic.

## How it works

Every Bash call goes through a `PreToolUse` hook. If the command looks heavy (`cargo build`, `xcodebuild`, `npm test`, `pytest`, …), the hook waits until one of N slots is free and takes a lease on it. `PostToolUse` drops the lease when the command finishes. Slots are shared by every Claude Code session on the machine.

- The command is never rewritten, so your permission rules match it exactly as before.
- Waiting happens in the hook, so it doesn't eat into the Bash tool's 10-minute timeout.
- Light commands (`git status`, `ls`, `cat`) never wait.
- Commands started with `run_in_background` are not queued.

## Install

```
/plugin marketplace add Prains/heavy-queue
/plugin install heavy-queue@heavy-queue
```

Requires `python3` (stdlib only). macOS and Linux.

## Configure

Set these in the `env` block of `~/.claude/settings.json` or in your shell:

| Variable | Default | Meaning |
| --- | --- | --- |
| `HEAVY_QUEUE_SLOTS` | CPU cores / 4 | How many heavy commands may run at once |
| `HEAVY_QUEUE_TTL` | `900` | Seconds after which a lease is considered abandoned. Keep it above `BASH_MAX_TIMEOUT_MS` if you raised that |
| `HEAVY_QUEUE_DIR` | `~/.cache/heavy-queue` | Where leases live |

Which commands count as heavy is a list of regexes in [`patterns`](patterns). `{cmd}` in a pattern matches where a command starts, so `cat vitest.config.ts` doesn't count as running vitest. To change the list, copy that file to `~/.config/heavy-queue/patterns` and edit it.

A project can add its own patterns in `.claude/heavy-queue-patterns`, committed with the repo. They apply on top of the default or user list:

```
# any turbo task except dev servers
{cmd}turbo\s+run\s+(?!dev\b)
```

See what's holding the slots:

```sh
"$(ls -d ~/.claude/plugins/cache/heavy-queue/heavy-queue/*/ | tail -1)"bin/heavy-queue status
```

## Limits

- A call that ends without `PostToolUse` (denied by another hook, permission prompt refused, cancelled) keeps its slot until that agent runs its next heavy command or finishes its turn. If the turn was interrupted, the slot stays taken until the lease expires (`HEAVY_QUEUE_TTL`).
- If a command is moved to the background mid-run, its slot is released at that moment.
- Waiters poll once a second; there is no strict FIFO order.
- A wait longer than an hour hits the hook timeout, and the command then runs without a slot.

## Test

```sh
python3 test_heavy_queue.py
```

## License

[MIT](LICENSE)
