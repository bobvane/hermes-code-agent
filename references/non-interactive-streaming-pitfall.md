# Non-interactive streaming pitfall

## Problem
When invoking coding agents in **headless/one-shot/non-interactive mode** (e.g. `aider -m "…"`, `opencode run "…"`), **default streaming output is unstable on long/complex generations**. Two failure modes were observed in-session:

### Symptom A — Aider emits a 0-byte file
```
$ aider --model openai/... --no-auto-commits --yes-always -m "$PROMPT" > aider_run.log
... (log shows model generating code internally) ...
$ ls -la impl_a.py
-rwx 1 hermes hermes  0  ... impl_a.py     # ← ZERO BYTES
```
The Aider log contains reasoning ("But we want to allow only one request…") but the final write to disk never materializes. Root cause: with `--yes-always -m` Aider's single-turn mode produces the code in the conversation but does not execute the file-write tool when the model stream is truncated or the run ends early.

### Symptom B — OpenCode crashes mid-generation
```
$ opencode run "$PROMPT" --model omni/...
Error: { "name": "UnknownError",
  "data": { "message": "Unexpected server error. Check server logs for details.",
  "ref": "err_…" } }
OPENTCODE_DONE exit=1
```
No `impl_a.py` is produced. OpenCode's run/build mode emits no file after an OmniRoute server error on a multi-hundred-token streaming generation.

## Reproduction (session: 2026-08-25, Async AI Provider Scheduler task)
- **Task**: implement an async AI Provider scheduler (asyncio, weighted LB, timeout, retry, circuit-breaker, semaphore) — a ~200-line file.
- **Aider**: 3 runs × `stream:true` default → **all 0 bytes** (exit 0 but no file).
  - 1st: 2.6k tokens sent, 150 received (truncated).
  - 2nd (with empty file pre-built): still 0 bytes.
  - 3rd (with `openai/` prefix): 0 bytes.
- **OpenCode**: 3 runs × `stream` implicit → **all `Unexpected server error` (OmniRoute 500)**.
  - 2× `hf/deepseek-ai/DeepSeek-V4-Flash` → 500 / reset token.
  - 1× `sensenova/...` → 404 not found.
- **Skill harness** (custom gen.py): `stream:false` + non-interactive POST to same endpoint → **5/5 passed first try** (120-line impl, all pytest green).

## Fix
**Force non-streaming completion for headless/non-interactive invocations.**

### API layer
Always POST with `"stream": false`:
```python
payload = {
    "model": "ds-web/deepseek-v4-flash",
    ...
    "stream": False,         # ← critical
    "max_tokens": 8000,
}
```
Then collect the full response with `urlopen(req).read()` and extract `choices[0].message.content` (non-streaming shape, not the `delta` chunks you'd parse for SSE).

> Why this works: streaming delivers the response as a sequence of small chunks. A long generation has many chunk-rounds; any backend hiccup (OmniRoute 500, timeout, token reset) truncates the stream and the client receives a partial body. Non-streaming asks the upstream to buffer until completion (or fail atomically), so the client gets either a complete answer or a clean error — no silent truncation.

### CLI layer
- **Aider**: Aider does not expose a `--no-stream` toggle for the non-interactive `-m` path cleanly; the reliable workaround is to invoke the provider API directly (see `scripts/make_bugbench.py` pattern) OR use `aider --chat` (interactive) where streaming is safe.
- **OpenCode**: `opencode run` always streams internally; to get non-streaming reliability, route through the provider API directly with `stream:false`.

### Scope rule
| Mode | Keep streaming? |
|---|---|
| Interactive TUI / chat | ✅ yes (low-latency UX, user sees progress) |
| Headless `aider -m` / `opencode run` | ❌ no — force `stream: false` |

> Interactive use keeps streaming for responsiveness; only the headless/non-interactive path switches to non-streaming.

## Template (reproduce-with-modifications)
The working harness used in-session (saved as `scripts/gen_noninteractive.py` pattern):

```python
import json, urllib.request

def call_noninteractive(url, key, model, prompt, max_tokens=8000):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": False,                 # ← the fix
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = r.read().decode()
    if raw.lstrip().startswith("{"):          # non-streaming: whole JSON
        content = json.loads(raw)["choices"][0]["message"]["content"]
    else:                                      # SSE fallback (shouldn't happen with stream=False)
        content = ""
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("data:") and not line.endswith("[DONE]"):
                content += json.loads(line[6:])["choices"][0]["delta"].get("content","")
    return content
```

Usage:
```python
code = call_noninteractive(
    url="https://openrouter.ai/api/v1/chat/completions",
    key="sk-or-...",
    model="~deepseek/deepseek-v4-flash-latest",
    prompt=open("TASK.md").read(),
)
open("impl_a.py", "w").write(code)
```

## See also
- `SKILL.md` §Advanced patterns #1 (pitfall note, links here)
- Session log 2026-08-25: Async AI Provider Scheduler — OpenCode/Aider streamed 5/5 fail, SKILL harness stream:false 5/5 pass.
