# Archive - Templates

## 归档原因

此目录存放已过时或不再使用的模板文件。

### rc_lowpass.yaml

**归档日期**: 2026-01-02

**原因**:
- SymKit 定位为「公式推导引擎」，专注于数学推导和学术溯源
- 电路分析模板属于应用层面，不符合 SymKit 内核定位
- 这类领域特定模板应由其他专门 MCP server 处理（如 circuit-analysis-mcp）

**SymKit 专注于**:
- ✅ 公式推导（derivation）
- ✅ 符号运算（symbolic computation）
- ✅ 学术溯源（provenance tracking）
- ❌ 领域特定应用模板（circuit analysis, pharmacokinetics, etc.）

如需电路分析功能，建议：
1. 使用 Python lcapy 库直接分析
2. 使用 sympy-mcp 进行符号计算
3. 用 SymKit 推导通用公式后，写成 Python 程序

**保留原因**:
- 作为模板系统设计的参考范例
- 展示如何结构化领域知识
- 可能对未来的「应用层 MCP」有参考价值
