# hermes-code-agent — 项目规则

> 本文件由 hermes-code-agent Skill 首次接触项目时生成（按实际技术栈代填），放在项目目录内、跟项目一起走。
> 本文件覆盖全局 CONVENTIONS.md 的对应条目；第1节通用纪律不可覆盖。
> 生成后以本文件内容为准——项目名固化在标题里。

## 1. 通用纪律

见全局 CONVENTIONS.md 第1节（本项目无覆盖）。

## 2. 工具链约定

- 语言: Python 3.8+，仅标准库（scripts/hca_gate.py 零第三方依赖）
- 测试: `.venv/bin/python -m pytest tests/`（venv 位于基准工作区 hca-bench-0825）
- Lint: 无独立 linter；用 `python3 -m py_compile` 做秒级语法门
- 构建: 无（纯脚本 Skill 项目）
- 发布: push 升版本 → tag + GitHub Release 同步（Release 用 commit message 作 note）

## 3. 编码规范

- 命名: snake_case 函数/变量，cmd_<name> 为子命令入口命名惯例
- 注释/文档: 中英双语——SKILL.md 英文为主（模型消费），README/ROADMAP 中文主体
- 版本号: 只在最后一位递增+1，到9进位到第二位
- 对标纪律: 六家没有的不做；"我们有等价物"不构成不抄更强方案的理由

## 4. 提交纪律

- 每个功能批次一个 commit，message 英文一行式
- push 成功 = 必须打 tag + 建 Release（不能只 push 不发版）

## 5. 测试与验证要求

- tests/test_hca_gate.py 全绿才算完成（当前待重写）
- 新子命令必须有实测验证记录（真实运行输出，非推断）

## 6. 禁区

- 不引入第三方依赖（stdlib only 是硬约束）
- 不做宿主程序能力才能做的功能（影子 git、常驻进程管理）
- 砍掉的功能不在任何项目材料中提及
- 凭据文件（.git-credentials）内容绝不入库、绝不明文输出
