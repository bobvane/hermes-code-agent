# Parallel implement + review pattern

Borrowed from OpenCode's Task-tool fan-out and Codex's `multi_agents_v2`
(spawn → send_message → wait → interrupt). Hermes equivalent: `delegate_task`
with two isolated leaf children run in parallel, then reconcile.

Use this for any non-trivial task (new feature, refactor, multi-file fix).

## The two roles

### Builder (isolated context)
Goal: implement the task to green. Receives the same task spec + the project's
test/lint commands. Must NOT report done until its own checks pass.

### Reviewer (isolated context)
Goal: critique the builder's diff for correctness, security, and simplicity.
Does NOT edit code. Returns a findings list with severity.

## Reusable prompts

### Builder goal
```
Implement this task in repo <path>: <task>.

Constraints:
- Follow existing code style and project conventions.
- After changes, run: <test cmd> and <lint cmd>. Do NOT report done unless both pass.
- If a check is missing in the repo, add a minimal one.
- Prefer small, focused edits. No refactoring unrelated code.
- Respond in <language>. Report: files changed, checks run, final status (green/blocked).
```

### Reviewer goal
```
Review the diff for task "<task>" in repo <path>.

You do NOT edit. Read the changed files and the project's tests.
Check for:
1. Correctness — does it actually solve <task>? Edge cases?
2. Security — secrets, injection, unsafe ops?
3. Simplicity — unnecessary complexity, dead code?
Return a findings list: [severity: blocker|major|minor] <file:line> <what/why>.
If clean, say "No findings". Respond in <language>.
```

## Reconcile (done by the parent / you)
- If reviewer finds a **blocker**, send it back to the builder as a new task (one more loop).
- If only minor, apply the tweak yourself or note it as follow-up.
- Only when builder green + reviewer no-blocker → mark the task done.

## Notes
- Children are isolated: neither sees the other's transcript. The parent holds the shared spec.
- Hermes caps concurrent children — rely on that as the capacity guard (Codex's `AgentExecutionLimiter` equivalent).
- For a single small bug, skip this and just run the hard loop directly.
