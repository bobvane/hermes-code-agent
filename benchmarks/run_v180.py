#!/usr/bin/env python3
"""v1.8.0 总体测试编排器：A组(裸模型) vs B组(带 hca_gate v1.8.0) 对比基准.

每组: 2 道题 × 3 次独立运行 = 6 轮。量化指标:
- 通过率(11/11 判例全绿)、首过率(0 红修轮)、红修轮数、耗时、token 消耗、熔断触发。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

GATE = "/opt/data/workspace/hermes-code-agent/scripts/hca_gate.py"
BENCH_SRC = "/opt/data/workspace/hca-bench-0825"
OUT = Path("/tmp/hca_v180_results")
OUT.mkdir(exist_ok=True)

BASE_URL = "http://192.168.2.2:20128/v1"
MODELS = [m for m in os.environ.get("BENCH_MODEL", "hf/deepseek-ai/DeepSeek-V4-Flash").split(",") if m]
MODEL = MODELS[0]
_model_idx = 0

def rotate_model():
    global MODEL, _model_idx
    _model_idx = (_model_idx + 1) % len(MODELS)
    MODEL = MODELS[_model_idx]
MAX_TURNS = 8          # 每轮上限(防死循环烧钱; B 组由 gate 自身兜底)
RED_CAP_B = 5          # B 组红轮上限(gate budget 同步)

def env():
    e = dict(os.environ)
    for ln in open("/opt/data/.env"):
        if "=" in ln:
            k, v = ln.strip().split("=", 1)
            e.setdefault(k, v)
    return e

def chat(messages, max_tokens=8000):
    """Streaming chat completion; returns (content, usage_dict)."""
    body = json.dumps({"model": MODEL, "messages": messages,
                       "max_tokens": max_tokens, "stream": True}).encode()
    req = urllib.request.Request(
        BASE_URL + "/chat/completions", data=body,
        headers={"Authorization": "Bearer " + env()["OPENAI_API_KEY"],
                 "Content-Type": "application/json"})
    content, usage = [], {}
    try:
        resp_ctx = urllib.request.urlopen(req, timeout=600)
    except urllib.error.HTTPError as e:
        if e.code in (404, 429, 503) and len(MODELS) > 1:
            rotate_model()
            body = json.dumps({"model": MODEL, "messages": messages,
                               "max_tokens": max_tokens,
                               "stream": True}).encode()
            req = urllib.request.Request(
                BASE_URL + "/chat/completions", data=body,
                headers={"Authorization": "Bearer " + env()["OPENAI_API_KEY"],
                         "Content-Type": "application/json"})
        else:
            raise
        resp_ctx = urllib.request.urlopen(req, timeout=600)
    r_open = resp_ctx
    with r_open as r:
        for raw in r:
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            try:
                chunk = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if chunk.get("usage"):
                usage = chunk["usage"]
            for ch in chunk.get("choices", []):
                delta = ch.get("delta", {}) or {}
                c = delta.get("content")
                if c:
                    content.append(c)
    text = "".join(content)
    pt = usage.get("prompt_tokens", len("".join(m.get("content","") for m in messages)) // 4)
    ct = usage.get("completion_tokens", len(text) // 4)
    return text, {"prompt_tokens": pt, "completion_tokens": ct}

CODE_FENCE = re.compile(r"```(?:python)?\n(.*?)```", re.S)

def extract_code(text):
    blocks = CODE_FENCE.findall(text)
    if blocks:
        best = max(blocks, key=len)
        if "class " in best:
            return best
    return None

TASKS = {
    "kvstore": {"task_file": "TASK.md", "judge": "test_kvstore_judge.py",
                "n_cases": 11},
    "lockmgr": {"task_file": "TASK2.md", "judge": "test_lockmgr_judge.py",
                "n_cases": None},   # read from judge run
}

def fresh_run_dir(group, task, run_id):
    d = OUT / f"{group}_{task}_{run_id}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    src = Path(BENCH_SRC)
    shutil.copy(src / TASKS[task]["task_file"], d / "TASK.md")
    shutil.copy(src / TASKS[task]["judge"], d / "judge.py")
    (d / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
    py = d / ".venv" / "bin" / "python"
    py.write_text("#!/bin/sh\nexec " + sys.executable + ' "$@"\n')
    py.chmod(0o755)
    subprocess.run(["git", "init", "-q"], cwd=d)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "--allow-empty", "-qm", "init"], cwd=d)
    return d

def count_judge(d):
    try:
        r = subprocess.run([str(d / ".venv/bin/python"), "-m", "pytest", "-q",
                            "judge.py"], cwd=d, capture_output=True,
                           text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return 124, 0, 12   # deadlock / hang → hard fail
    m = re.search(r"(\d+) passed", r.stdout)
    passed = int(m.group(1)) if m else 0
    m2 = re.search(r"(\d+) failed", r.stdout)
    failed = int(m2.group(1)) if m2 else 0
    errors = len(re.findall(r"ERROR", r.stdout))
    total = passed + failed + errors
    return r.returncode, passed, max(total, 12)

def run_group(group, task, run_id):
    cfg = TASKS[task]
    d = fresh_run_dir(group, task, run_id)
    t0 = time.time()
    msgs = [
        {"role": "system",
         "content": "You are an expert Python engineer. Write complete, "
                    "production-quality code using only the stdlib."},
        {"role": "user", "content":
            (d / "TASK.md").read_text() +
            "\n\nRespond with the FULL implementation in a single python "
            "code block only. No explanations."},
    ]
    red_cycles, total_tokens = 0, 0
    doom_hit = budget_hit = False
    first_pass = True
    impl_written = False
    for turn in range(MAX_TURNS):
        text, usage = chat(msgs)
        total_tokens += usage["prompt_tokens"] + usage["completion_tokens"]
        code = extract_code(text)
        if group == "B" and not impl_written:
            subprocess.run([sys.executable, GATE, "guard", "record"],
                           cwd=d, capture_output=True)
        if code:
            (d / "impl.py").write_text(code)
            impl_written = True
        if group == "A":
            # A 组: 写完即宣布完成, 不跑测试 (按任务定义)
            break
        rc, passed, total = count_judge(d)
        digest = ""
        if rc != 0:
            vr = subprocess.run(
                [sys.executable, GATE, "verify"], cwd=d,
                capture_output=True, text=True, timeout=600)
            rc_gate = vr.returncode
            digest = trim(vr.stdout + vr.stderr)
            if rc_gate == 2:
                if "budget" in vr.stdout.lower() or "BUDGET" in vr.stdout:
                    budget_hit = True
                else:
                    doom_hit = True
                break
            red_cycles += 1
            msgs.append({"role": "assistant", "content": text})
            msgs.append({"role": "user", "content":
                         "Tests failed. Error digest:\n" + digest +
                         "\n\nFix impl.py. Respond with the FULL corrected "
                         "implementation in a single python code block."})
            if red_cycles >= RED_CAP_B:
                break
        else:
            subprocess.run([sys.executable, GATE, "verify"], cwd=d,
                           capture_output=True, text=True, timeout=600)
            break
    elapsed = round(time.time() - t0, 1)
    if (d / "impl.py").exists():
        rc, passed, total = count_judge(d)
    else:
        rc, passed, total = 1, 0, 11
    result = {
        "group": group, "task": task, "run": run_id, "model": MODEL,
        "passed": passed, "total": max(total, 1),
        "all_green": rc == 0 and passed > 0,
        "first_pass": first_pass and red_cycles == 0 and rc == 0,
        "red_cycles": red_cycles, "elapsed_s": elapsed,
        "tokens": total_tokens, "doom_stop": doom_hit,
        "budget_stop": budget_hit,
    }
    (d / "result.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result), flush=True)
    return result

def trim(s, cap=1500):
    lines = [l for l in s.splitlines()
             if re.search(r"(FAILED|Error|assert|Exception)", l)]
    out = "\n".join(lines)[:cap]
    return out or s[-cap:]

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    results = []
    jobs = []
    if which in ("all", "A"):
        for task in ("kvstore", "lockmgr"):
            for rid in (1, 2, 3):
                jobs.append(("A", task, rid))
    if which in ("all", "B"):
        for task in ("kvstore", "lockmgr"):
            for rid in (1, 2, 3):
                jobs.append(("B", task, rid))
    for g, t, rid in jobs:
        for attempt in range(4):
            try:
                results.append(run_group(g, t, rid))
                break
            except Exception as exc:
                if attempt == 3:
                    print(json.dumps({"group": g, "task": t, "run": rid,
                                      "error": str(exc)[:200]}), flush=True)
                else:
                    time.sleep(20 * (attempt + 1))
    (OUT / "summary.json").write_text(json.dumps(results, indent=1))
