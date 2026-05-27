# 🧠 个人知识库 —— GraphRAG 自动化知识管理流水线

**PDF / 研报 / 笔记 → 自动提炼 → Obsidian 双链网络 → MCP 知识检索**

将你的每一份输入文件转化为 Obsidian 知识图谱中的结构化节点，自动维护全局实体库与知识中枢网络，并通过 MCP 协议让 LLM 客户端直接检索你的个人知识库。

---

## ✨ 核心能力

| 步骤 | 模块 | 功能 |
|------|------|------|
| 📥 输入 | `pdf_parser.py` | 支持 PDF、Markdown 文件上传 |
| 🧠 提炼 | `llm_processor.py` | 调用 DeepSeek 提取核心逻辑、实体关系、关键论点 |
| 💾 存储 | `storage.py` | 自动写入 Obsidian Vault，标题即文件名 |
| 🕸️ 融合 | `storage.py` | 全局实体扫描消除同义词 + 图谱逻辑链追加中枢网络 |
| 🔎 检索 | `mcp_server.py` | MCP 服务，供 Cursor / Claude Desktop 等检索知识库 |

## 📂 文件清单

| 文件 | 职责 |
|------|------|
| `pdf_parser.py` | PDF 文本提取（PyMuPDF，坐标过滤页眉页脚 + 纯图片页跳过） |
| `llm_processor.py` | DeepSeek API 封装（tenacity 重试 + 全局实体词典动态注入） |
| `storage.py` | Obsidian 写入 + 全局实体扫描 + 00_全局知识网络中枢管理 |
| `app.py` | Streamlit 交互界面（全局实体预加载 + 中枢网络更新） |
| `mcp_server.py` | FastMCP 服务（全文检索 / 读取节点 / 双链探测） |

## 🚀 快速上手

```bash
# 1. 安装依赖
pip install streamlit PyMuPDF openai tenacity mcp

# 2. 启动 Web 界面
streamlit run app.py
# 侧边栏填入 DeepSeek API Key + Obsidian Vault 路径
# 上传 PDF / Markdown → 一键处理 → 自动入库
```

## 🔗 MCP 知识检索（供 LLM 客户端用）

在 Cursor / Claude Desktop / OpenClaw 等支持 MCP 的客户端中配置：

```json
{
    "mcpServers": {
        "personal-knowledge-base": {
            "command": "python",
            "args": ["path/to/mcp_server.py"],
            "env": {
                "OBSIDIAN_VAULT_PATH": "/path/to/ObsidianVault"
            }
        }
    }
}
```

配置后，LLM 可直接检索你的个人知识库：

| MCP 工具 | 功能 |
|----------|------|
| `search_vault(query)` | 全局全文检索，返回匹配文件名 + 上下文片段 |
| `read_node(entity_name)` | 读取指定知识节点的完整内容 |
| `get_linked_nodes(entity_name)` | 提取节点中所有 `[[]]` 双链，顺藤摸瓜 |

## 🧩 全局知识融合机制

- **📋 全局实体词典**：每次处理新文档前，自动扫描 Vault 中所有已有文件名 + `[[]]` 双链，注入 DeepSeek 提示词，强制复用已有实体名，杜绝同义词节点分裂。
- **🌐 知识网络中枢**：每篇新文档落盘后，自动提取「图谱逻辑链」段落，追加到 `00_全局知识网络中枢.md`，构建不断生长的全局知识网络。
- **📎 批次内感知**：同一批上传的多个文件，后一个能感知前一个生成的新实体，确保同批文档互相关联。

## ⚙️ 技术栈

```
Python 3.11+  |  Streamlit  |  PyMuPDF  |  OpenAI SDK  |  DeepSeek  |  Tenacity  |  FastMCP
```

## 🛤️ 工作流

```
上传 PDF/MD
    │
    ▼
┌─────────────────────┐
│ 阶段 0: 全局实体扫描  │  ← get_existing_entities()
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ 阶段 1: 文本提取      │  ← extract_text_from_pdf()
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ 阶段 2: AI 提炼      │  ← generate_graph_node( + 全局实体词典)
│    · YAML Frontmatter│
│    · 核心摘要        │
│    · 图谱逻辑链      │
│    · 关键论点        │
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ 阶段 3: 落盘 Vault   │  ← save_to_obsidian()
│    · 新实体 → 注入   │
│    · 下一文件感知     │
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ 阶段 4: 中枢更新     │  ← update_master_graph()
│    00_全局知识网络    │
│   中枢.md (追加)      │
└─────────────────────┘
```
