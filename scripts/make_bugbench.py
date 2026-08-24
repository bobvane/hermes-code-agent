#!/usr/bin/env python3
"""Generate a throwaway buggy Python repo to validate a coding-workflow skill.

Usage:
    python3 make_bugbench.py <dir>

Creates <dir>/calc.py (2 bugs), <dir>/test_calc.py, <dir>/pytest.ini.
Bugs: add() off-by-one (+1); divide() no zero-check.
Baseline test run: 2 failed, 1 passed.
A correct hard-loop run should reach: 3 passed.
"""
import os
import sys

CALC = '''def add(a, b):
    # BUG: off by one - should return a + b
    return a + b + 1

def divide(a, b):
    # BUG: no zero-check, should raise ValueError on b == 0
    return a / b
'''

TEST = '''import pytest
from calc import add, divide

def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0

def test_divide_normal():
    assert divide(10, 2) == 5

def test_divide_by_zero():
    with pytest.raises(ValueError):
        divide(10, 0)
'''

INI = '[pytest]\naddopts = -q\n'


def main():
    if len(sys.argv) < 2:
        print("usage: make_bugbench.py <dir>")
        sys.exit(1)
    d = sys.argv[1]
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "calc.py"), "w") as f:
        f.write(CALC)
    with open(os.path.join(d, "test_calc.py"), "w") as f:
        f.write(TEST)
    with open(os.path.join(d, "pytest.ini"), "w") as f:
        f.write(INI)
    print(f"bugbench created at {d}")
    print("baseline: run `python3 -m pytest` -> expect 2 failed, 1 passed")


if __name__ == "__main__":
    main()
