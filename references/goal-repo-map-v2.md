# 开发目标：仓库结构图 v2（Aider repo-map × Cline 目录树）

> 状态：设计定稿（Bob 2026-08-26），未实施。第二批第2项。
> 实现路线：纯 SKILL.md 提示词协议 + Hermes 自带工具，不改 hca_gate.py。

## 两张索引卡

### 卡1 目录卡（Cline 式）
- 项目目录+文件名清单；排除 node_modules/.git/__pycache__/venv 等垃圾
- 工具：search_files(files) / terminal ls
- 时机：每个编程任务开始时生成
- 回答："项目长什么样、东西在哪"

### 卡2 符号卡（Aider 式，土法实现）
- 对代码文件抽 class/def/function 定义行：`rg '^\s*(class |def |function )'`
- 工具：search_files(content) —— ripgrep 是 Hermes 全新安装自带
- 时机：按需——PLAN 阶段结合用户需求挑出相关文件后生成，不全量做
- 回答："这个文件里有什么功能、该去哪改"

## 使用流程

```
任务开始 → 目录卡(全景) → 按需求挑相关文件 → 符号卡(细节) → 动手
```

先粗后细、按需展开。比 Aider 全仓库建索引省力，比 Cline 只看名字精准。

## 与 Aider 的差异标注

- Aider: tree-sitter(语法解剖)+PageRank(引用排名)，重依赖高精度
- 我们: ripgrep 抓定义行(精度九折、零依赖)；相关性判断交给模型
  结合任务需求直接挑(Aider 生成索引时不知道任务,我们知道——形态优势)

## 实施清单

- [ ] SKILL.md PLAN 段写入两卡协议(目录卡必做、符号卡按需)
- [ ] 排除清单标准化(node_modules/.git 等)
- [ ] README 功能对照表更新此行状态
