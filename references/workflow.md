# Workflow reference — verify commands by stack

The hard loop's step 4 (VERIFY) needs real commands. Use the project's own test/lint/build when present; fall back to these per-stack defaults only when the repo has none configured.

## Detection order

1. Read `package.json` scripts / `Makefile` / `pyproject.toml` / `Cargo.toml` / `go.mod` for existing `test`/`lint`/`build` targets. Prefer those.
2. If none, pick from the defaults below.
3. If no tooling exists at all, state "no verify harness available" and downgrade confidence — do NOT claim green.

## Defaults by stack

### Node / TypeScript
```
npm test            # if present
npm run lint        # if present
npx tsc --noEmit    # type check
```

### Python
```
pytest -q
ruff check .        # if installed
mypy .              # if configured
```

### Go
```
go test ./...
go vet ./...
gofmt -l .
```

### Rust
```
cargo test
cargo clippy
cargo fmt --check
```

## Red → fix loop
On failure, copy the EXACT error lines into the next reasoning step. Do not paraphrase into vagueness. Fix the smallest cause. Re-run the SAME command. Max 5 cycles; if still red, stop and report the blocker honestly.

## Green gate
All targeted checks pass AND the change matches the stated scope → mark done. Report: files changed, checks green, anything left untested.
