"""
MCP Server —— Obsidian Vault 知识检索服务。

提供三个工具供大模型客户端调用：
  search_vault     — 全文检索，返回匹配片段
  read_node        — 读取指定知识节点完整内容
  get_linked_nodes — 提取节点中的所有 [[双链]] 实体

依赖安装:
    pip install mcp

客户端配置示例 (Claude Desktop / OpenClaw config.json):
{
    "mcpServers": {
        "obsidian-vault": {
            "command": "python",
            "args": ["C:\\Users\\81374\\Desktop\\新建文件夹\\mcp_server.py"],
            "env": {
                "OBSIDIAN_VAULT_PATH": "C:\\Users\\81374\\Documents\\ObsidianVault"
            }
        }
    }
}
"""

import os
import re
import sys
from pathlib import Path

# ------------------------------------------------------------
# 注入同目录，以便直接 import storage 复用正则与逻辑
# ------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from storage import _WIKILINK_RE  # [[...]] 双链提取正则（复用，保持一致性）

from mcp.server.fastmcp import FastMCP

# ------------------------------------------------------------
# 环境变量校验
# ------------------------------------------------------------
VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", "")
if not VAULT_PATH:
    print(
        "Error: 环境变量 OBSIDIAN_VAULT_PATH 未设置。\n"
        "请在启动时指定 Obsidian Vault 的根目录路径。\n"
        "示例: OBSIDIAN_VAULT_PATH=/path/to/vault python mcp_server.py",
        file=sys.stderr,
    )
    sys.exit(1)

VAULT_DIR = Path(VAULT_PATH)
if not VAULT_DIR.exists():
    print(
        f"Error: Vault 目录不存在: {VAULT_PATH}",
        file=sys.stderr,
    )
    sys.exit(1)

# ------------------------------------------------------------
# FastMCP 实例
# ------------------------------------------------------------
mcp = FastMCP("obsidian-vault")


# ------------------------------------------------------------
# 工具 1: 全局全文检索
# ------------------------------------------------------------
@mcp.tool()
def search_vault(query: str) -> str:
    """
    在 Obsidian Vault 中全局全文检索。

    Args:
        query: 搜索关键词（支持中文/英文）

    Returns:
        匹配到的文件名及上下文片段，最多 10 条。
    """
    if not query.strip():
        return "查询关键词不能为空。"

    results: list[str] = []
    query_lower = query.lower()
    _MAX_RESULTS = 10

    for md_file in sorted(VAULT_DIR.glob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        lines = content.splitlines()
        file_hits: list[str] = []

        for i, line in enumerate(lines):
            if query_lower in line.lower():
                # 构造上下文：前 1 行 + 当前行 + 后 1 行
                prev_line = lines[i - 1].strip() if i > 0 else ""
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                snippet_parts = []
                if prev_line:
                    snippet_parts.append(f"  ... {prev_line[:120]}")
                snippet_parts.append(f"  → {line.strip()[:200]}")
                if next_line:
                    snippet_parts.append(f"  ... {next_line[:120]}")

                highlighted = "\n".join(snippet_parts)
                file_hits.append(f"  L{i+1}: \n{highlighted}")

            if len(results) + len(file_hits) >= _MAX_RESULTS:
                break

        if file_hits:
            results.append(f"📄 **{md_file.name}** ({len(file_hits)} 处匹配):")
            results.extend(file_hits)
            results.append("")  # 空行分隔

        if len(results) >= _MAX_RESULTS:
            # 粗略截断（results 中每条文件标题 + 匹配行）
            break

    if not results:
        return f'未找到包含 "{query}" 的内容。'

    # 如果结果过多，取前 10 条文件名级别
    output = "\n".join(results)
    return output


# ------------------------------------------------------------
# 工具 2: 精准读取知识节点
# ------------------------------------------------------------
@mcp.tool()
def read_node(entity_name: str) -> str:
    """
    读取指定知识节点的完整 Markdown 内容。

    Args:
        entity_name: 实体名称（可带或不带 .md 后缀），
                     例如 "BERT" 或 "BERT.md" 均可。

    Returns:
        文件的完整文本内容；文件不存在时返回明确提示。
    """
    clean = entity_name.strip()
    if not clean:
        return "错误：实体名称不能为空。"

    # 统一补 .md 后缀
    target = VAULT_DIR / (clean if clean.endswith(".md") else clean + ".md")

    if not target.exists():
        similar = [f.stem for f in VAULT_DIR.glob("*.md") if clean.lower() in f.stem.lower()]
        hint = ""
        if similar:
            hint = f"\n\n你可能想找: {', '.join(similar[:5])}"
        return f'未找到节点 "{clean}"{hint}'

    try:
        return target.read_text(encoding="utf-8")
    except Exception as e:
        return f"读取文件失败: {e}"


# ------------------------------------------------------------
# 工具 3: 图谱节点探测（提取双链）
# ------------------------------------------------------------
@mcp.tool()
def get_linked_nodes(entity_name: str) -> list[str]:
    """
    读取某个知识节点，提取其中所有 [[双向链接]] 实体。

    逻辑复用 storage._WIKILINK_RE 正则，保证与写入端一致。

    Args:
        entity_name: 实体名称（可带或不带 .md 后缀）

    Returns:
        去重后的链接实体列表。
    """
    clean = entity_name.strip()
    if not clean:
        return ["错误：实体名称不能为空。"]

    target = VAULT_DIR / (clean if clean.endswith(".md") else clean + ".md")

    if not target.exists():
        return [f'未找到节点 "{clean}"']

    try:
        content = target.read_text(encoding="utf-8")
    except Exception as e:
        return [f"读取文件失败: {e}"]

    linked: set[str] = set()
    for m in _WIKILINK_RE.finditer(content):
        entity = m.group(1).strip()
        if entity:
            linked.add(entity)

    if not linked:
        return [f'节点 "{clean}" 中未发现任何 [[双链]]。']

    return sorted(linked)


# ------------------------------------------------------------
# 启动
# ------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="stdio")
