# Benchmark — does the hard loop actually help a weak model?

## Setup
- Model under test: `hy3-free` (free-tier weak model, the same one this session runs on).
- Harness: hermes-code-agent hard loop (SKILL.md §"The hard loop").
- Task: fix a 2-bug Python module (`add` off-by-one, `divide` missing zero-check) with 3 pytest cases.

## Baseline (no loop, model "guesses")
```
2 failed, 1 passed
- test_add: assert 6 == 5
- test_divide_by_zero: ZeroDivisionError
```
A weak model told "fix the bugs" with no forced verify step tends to:
- edit one spot and declare done,
- or rewrite broad strokes without re-running tests.

## With the hard loop
1. **Implement (step 1):** fix `add` only.
2. **Verify:** `pytest` → `test_divide_by_zero` still RED, exact error `ZeroDivisionError: division by zero at calc.py:6` captured.
3. **Loop on red:** feed exact error back, fix `divide` with a zero guard.
4. **Verify (gate):** `pytest` → `3 passed, EXIT=0`.

## Observation
- The loop converged **without needing model cleverness** — the discipline is structural, not advisory.
- This is the core value: weak model + forced verify ≈ mid model on bare chat, for small/medium tasks.

## Honest limits
- Converges well for **local, testable** bugs.
- For bugs needing cross-file reasoning, implicit contracts, or wrong tests, the model can hit the red→fix cap (5) still red. The loop cannot fix a model that can't reason — it only prevents "fake done".
- **Conclusion:** keep `hy3-free` + this skill for daily small tasks; switch to a stronger model (Claude/DeepSeek mid-tier via OpenRouter) only when a task loops red past the cap.

## How to re-run
```bash
mkdir /opt/data/bugbench && cd /opt/data/bugbench
# create calc.py + test_calc.py (see SKILL.md / this file's setup)
uv venv .venv && . .venv/bin/activate && uv pip install pytest
python3 -m pytest   # baseline red
# apply the hard loop manually, then:
python3 -m pytest   # expect 3 passed
```
