# 安装副本同步方法

## 背景

hermes-code-agent 项目有两个目录：
- **开发目录** `/opt/data/workspace/hermes-code-agent/`：git 仓库，含 `.git/`、`tests/`、`benchmarks/` 等
- **安装副本** `/opt/data/skills/hermes-code-agent/`：Hermes 运行时加载的 Skill，**无 git**

## 默认流程：走自检升级（不要手动同步）

项目自带 `update-check` / `update-apply` 子命令，每次 CLARIFY 阶段静默探 GitHub，72h 节流。开发完成 = git push + GitHub Release。Skill 下次任务开始时自动探到新版本，提示用户 A/B 选择升级，全程不需要碰安装副本。

```
dev edit → snapshot → tests → commit + push → git tag vX.Y.Z → GitHub Release
   ↓
  (Skill 自检 update-check, 72h 内最多一次)
   ↓
  GATE 后 update-pending 提示: "A. 升级 Skill  B. 不升级 (3天后再提示)"
   ↓
  A: update-apply 自动下载 tarball + 覆盖安装副本 (skill_state.json 豁免)
```

**Bob 拍板**（2026-09-07）：项目改动后**不要**手动 cp 同步安装副本，让 Skill 自己从 GitHub 探测升级。这是为了持续验证自检升级功能正常。

## 例外：何时需要手动同步

只在以下情况手动同步（调试 / 离线 / 没法走自检时）：

1. **Fresh install**（全新环境，git clone 后第一次部署）—— 装副本还不存在，需手动 `cp -r` 建副本
2. **GitHub 不可达**（断网 / 私有开发 / 调试中还没 push）—— `update-apply` 拉不到 tarball
3. **测试自检升级本身** —— 开发时想验证自检流程前，先手动同步一次当前开发版作为对照
4. **紧急热修复**（release 创建后想立即生效，不等 72h 节流窗口）—— `update-apply --version vX.Y.Z --skip-verify`

## 手动同步命令（仅例外时用）

rsync 通常不可用（环境依赖），改用 Python shutil：

```bash
cd /opt/data/workspace/hermes-code-agent

python3 -c "
import shutil, pathlib
src = pathlib.Path('/opt/data/workspace/hermes-code-agent')
dst = pathlib.Path('/opt/data/skills/hermes-code-agent')
skip = {'.git','tests','.venv','.pytest_cache','benchmarks',
        'hermes-code-agent.md','.hermes','backups','__pycache__'}
count = 0
for f in src.rglob('*'):
    if not f.is_file(): continue
    parts = list(f.relative_to(src).parts)
    if any(p in skip for p in parts): continue
    dst_f = dst / f.relative_to(src)
    dst_f.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(f, dst_f)
    count += 1
print(f'synced {count} files')
"
```

## 关键约束

1. **skill_state.json 永不覆盖**：这个文件在开发副本不存在（每次 git clone 新环境都没有），安装副本已有的也要保留（含节流指针）。上面脚本的 `skip` 列表排除了它，所以不会被覆盖。
2. **`.gitignore` 里的 `skills/*/skill_state.json` 只防 git track，不影响同步**——skill_state.json 本来就不在 git 里，rsync/cp 都不会碰它。
3. **验证同步结果**：
   ```bash
   grep '^version:' /opt/data/skills/hermes-code-agent/SKILL.md
   ls /opt/data/skills/hermes-code-agent/scripts/hca_gate.py
   ```
   确认版本号已是最新，新文件存在。

## 常见错误

- **常规开发流程直接用 `cp -r` 整个复制**：默认应走自检升级路径，手动 cp 只在例外场景。手动 cp 还会把 `.git/`、`tests/`、`benchmarks/` 也带过去，污染安装副本
- **用 `rsync`**：多数 Hermes 环境下 rsync 未安装，需回退到 Python 脚本
- **忘记更新 SKILL.md version**：版本号要先行 bump，否则同步后运行 `update-status` 显示的还是旧版
- **手动同步后假装走过自检升级**：手动 cp 不会触发 `last_check_ts` 更新，节流窗口不重置，看起来"没升级"是正常的——节流本就是设计如此
