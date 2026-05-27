# 🧠 GraphRAG 自动化知识图谱流水线

PDF 提取 → DeepSeek 提炼 → Obsidian 双链落盘 → MCP 知识检索，一体化闭环。

## 架构

```
                         ┌─────────────────┐
                         │    PDF / MD 文件  │
                         └────────┬────────┘
                                  ▼
                         ┌─────────────────┐
                         │   pdf_parser.py  │  PyMuPDF 文本提取，坐标过滤页眉页脚
                         └────────┬────────┘
                                  ▼
                         ┌─────────────────┐
                         │ llm_processor.py │  DeepSeek API 提炼为结构化 Markdown
                         │                  │  + 全局实体感知（消除同义词节点分裂）
                         └────────┬────────┘
                                  ▼
                         ┌─────────────────┐
                         │   storage.py     │  写入 Obsidian Vault
                         │                  │  + 提取逻辑链追加 00_全局知识网络中枢.md
                         └────────┬────────┘
                                  ▼
               ┌──────────────────────────────────┐
               │          app.py (Streamlit)       │  ← 交互式前端入口
               └──────────────────────────────────┘
                                  ▼
                         ┌─────────────────┐
                         │ mcp_server.py    │  ← MCP 服务，供 LLM 检索 Vault
                         │ /search_vault    │
                         │ /read_node       │
                         │ /get_linked_nodes │
                         └─────────────────┘
```

## 快速启动

```bash
pip install streamlit PyMuPDF openai tenacity mcp

# 设置 DeepSeek API Key，运行 Web 界面
streamlit run app.py
```

## MCP 服务（供 LLM 客户端调用）

```json
{
    "mcpServers": {
        "obsidian-vault": {
            "command": "python",
            "args": ["path/to/mcp_server.py"],
            "env": {
                "OBSIDIAN_VAULT_PATH": "/path/to/ObsidianVault"
            }
        }
    }
}
```

### MCP 工具

| 工具 | 功能 |
|------|------|
| `search_vault(query)` | 全局全文检索，返回匹配文件名 + 上下文片段 |
| `read_node(entity_name)` | 读取指定知识节点的完整内容 |
| `get_linked_nodes(entity_name)` | 提取节点中所有 `[[]]` 双链，返回链接实体列表 |

## 全局知识融合

- **全局实体感知**：每次处理新文档时，自动扫描 Vault 已有实体列表注入 DeepSeek 提示词，强制复用已有实体名，消除同义词节点。
- **全局知识网络中枢**：每次落盘后自动提取 `图谱逻辑链` 段落，追加到 `00_全局知识网络中枢.md`，构建不断生长的知识网络。

## 文件清单

| 文件 | 职责 |
|------|------|
| `pdf_parser.py` | PDF 文本提取（坐标过滤 + 纯图片页跳过） |
| `llm_processor.py` | DeepSeek API 封装（重试 + 全局实体注入） |
| `storage.py` | Obsidian 写入 + 全局实体扫描 + 中枢更新 |
| `app.py` | Streamlit 交互界面 |
| `mcp_server.py` | MCP 服务（stdio 模式） |
