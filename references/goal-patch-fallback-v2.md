# 开发目标：补丁容错应用 v2（Codex 全量照抄）

> 状态：定稿（Bob 2026-08-26 拍板"全部原封不动抄过来"），未实施。第二批第5项。
> 原则：逐组件比质量，Codex 强就全换，不用 difflib 等现有弱等价物。

## 范围（五组件全换为 Codex 方案，Rust→Python 翻译）
1. seek_sequence 四级匹配：精确→rstrip→trim→Unicode归一化 + EOF优先 + 防越界
   （源: codex-rs/apply-patch/src/seek_sequence.rs 193行）
2. diff 计算/展示：similar crate 算法照搬，弃用 difflib
3. 补丁解析器：parser.rs 682行防御性解析，替换 hca_gate.py 简单版
4. 结构化错误：ApplyPatchError（区分IO/匹配错误+带hunk定位）喂回模型自愈
5. 测试用例集：file_update_tests.rs 278行实战用例 → pytest

## 实现位置
- scripts/hca_gate.py 重构 apply_patch/locate 子命令
- 预计 500-700 行 Python + 测试

## 已核实事实
- Codex apply-patch 模块位于 codex-rs/apply-patch/src/（约5100行 Rust）
- "重试协议"= 结构化错误反馈注入对话由模型自愈，非程序内重试循环
- similar 是专用文本 diff 库，质量/性能优于 Python difflib
