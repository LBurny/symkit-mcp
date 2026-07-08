# Research Workflow Guide for Copilot

> 这份指南帮助 Copilot 理解如何正确使用 Zotero + PubMed MCP tools

## 🔍 文献搜索流程

### 步骤 1: 了解研究问题
使用 `parse_pico` 将研究问题拆解为 PICO 结构：
- **P**opulation: 研究对象
- **I**ntervention: 介入措施
- **C**omparison: 对照组
- **O**utcome: 结果指针

### 步骤 2: 生成搜索策略
使用 `generate_search_queries` 产生专业的搜索策略，包含：
- MeSH terms
- Boolean operators
- Field tags

### 步骤 3: 运行搜索
使用 `search_literature` 搜索 PubMed，注意：
- 结果会自动缓存到 Session
- 使用 `get_session_pmids` 取得已搜索的 PMID
- **不要重复搜索相同的关键字**

### 步骤 4: 过滤已有文献
使用 `search_pubmed_exclude_owned` 直接搜索「尚未拥有」的新文献

---

## 📥 导入 Zotero 流程

### ⚠️ 重要：先询问 Collection！
在导入任何文献前，**必须先询问用户**要存入哪个 Collection。

### 导入方式选择

| 情境 | 推荐工具 | 说明 |
|------|----------|------|
| 少量文献 (1-5) | `quick_import_pmids` | 简单快速 |
| 中量文献 (5-20) | `import_from_pmids` | 可指定 collection |
| 大量文献 (20+) | `batch_import_from_pubmed` | 批量处理，有进度回报 |
| 有 RIS 文件 | `import_ris_to_zotero` | 标准格式导入 |

### 导入前确认清单
1. ✅ 已询问目标 Collection
2. ✅ 已确认 PMID 列表（使用 `get_session_pmids` 取得）
3. ✅ 已提醒用户文献数量

---

## 🔄 Session 管理

### 为什么需要 Session？
- PubMed 搜索结果会缓存
- 避免重复 API 调用
- 保持 PMID 追踪，不依赖 Agent 记忆

### Session 工具使用时机

| 工具 | 何时使用 |
|------|----------|
| `get_session_pmids` | 需要取得之前搜索的 PMID |
| `list_search_history` | 查看本次对话的搜索纪录 |
| `get_cached_article` | 取得已缓存的文章详情（避免重复 fetch） |
| `get_session_summary` | 检查 Session 状态 |

---

## 📚 Zotero 书库管理

### 查找现有文献
1. `list_collections` - 先看有哪些 Collections
2. `get_collection_items` - 取得特定 Collection 的文献
3. `search_items` - 在书库中搜索

### 避免重复导入
使用 `check_articles_owned` 检查 PMID 是否已存在

### 书库分析
- `get_library_stats` - 统计分析
- `find_orphan_items` - 找出孤儿文献（未分类）

---

## ⚠️ 常见错误避免

### ❌ 错误做法
1. 搜索后直接导入，没问 Collection
2. 重复搜索相同关键字
3. 导入时没确认 PMID 列表
4. 从 PubMed 重新取摘要（Zotero 已有）

### ✅ 正确做法
1. 搜索 → 确认结果 → 询问 Collection → 导入
2. 用 `get_session_pmids` 取得已有的 PMID
3. 用 `get_item` 从 Zotero 读取已存文献的详情
4. 导入前用 `check_articles_owned` 检查重复

---

## 🎯 典型对话流程范例

```
用户: 帮我找最近的 AI 麻醉研究

Copilot 动作:
1. parse_pico: 分析研究问题
2. generate_search_queries: 产生搜索策略
3. search_literature: 运行搜索
4. [回报结果，询问是否要存入 Zotero]
5. list_collections: 取得 Collection 列表
6. [询问用户要存入哪个 Collection]
7. quick_import_pmids 或 batch_import_from_pubmed: 导入
8. [确认完成]
```
