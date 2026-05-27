"""
Obsidian Vault 落盘模块 —— 将 AI 生成的结构化 Markdown 写入本地双链网络。

核心策略：
- 正则提取 YAML frontmatter 的 title → 作为文件名
- 目录不存在自动创建
- 同名文件自动追加时间戳，绝不覆盖
- 全局实体感知：扫描 Vault 中所有节点，消除同义词/节点分裂
- 全局网络中枢：每次新文档落盘后，将其逻辑链并入 00_全局知识网络中枢.md
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional


# ------------------------------------------------------------
# 正则常量
# ------------------------------------------------------------
_TITLE_RE = re.compile(
    r"^---\s*\n(?:.*\n)*?title\s*:\s*[\"']?(.*?)[\"']?\s*\n(?:.*\n)*?---",
    re.MULTILINE,
)

_WIKILINK_RE = re.compile(r"\[\[(.*?)\]\]")

_GRAPH_SECTION_RE = re.compile(
    r"#{2,4}.*?图谱逻辑链.*?\n([\s\S]*?)(?=\n#|\Z)",
    re.MULTILINE,
)


# ------------------------------------------------------------
# YAML title 提取
# ------------------------------------------------------------
def _extract_title_from_frontmatter(content: str) -> Optional[str]:
    """从 Markdown 的 YAML frontmatter 中提取 title 字段。"""
    match = _TITLE_RE.search(content)
    if not match:
        return None
    title = match.group(1).strip()
    return title if title else None


# ------------------------------------------------------------
# 文件名净化
# ------------------------------------------------------------
def _sanitize_filename(name: str) -> str:
    """
    去除文件名中的非法字符：
    Windows:  \ / : * ? " < > |
    以及换行、制表符。
    """
    return re.sub(r'[\\/*?:"<>|\r\n\t]', "", name).strip()


# ------------------------------------------------------------
# 实体提取（供全局感知使用）
# ------------------------------------------------------------
def _extract_entities_from_markdown(md_content: str) -> list[str]:
    """
    从单篇 Markdown 中提取所有实体名。
    来源包括：YAML title + 正文中所有 [[实体]] 双链。
    返回去重后的列表。
    """
    entities: set[str] = set()

    # 1. YAML title
    title = _extract_title_from_frontmatter(md_content)
    if title:
        entities.add(title)

    # 2. 所有 [[实体]] 双链
    for m in _WIKILINK_RE.finditer(md_content):
        entity = m.group(1).strip()
        if entity:
            entities.add(entity)

    return sorted(entities)


def get_existing_entities(vault_path: str) -> list[str]:
    """
    扫描 Vault 下所有 .md 文件，提取全局实体集合。

    来源：
      1. 文件名（去掉 .md 后缀）
      2. 文件中所有 [[实体]] 双链

    排除 00_全局知识网络中枢.md 自身，避免循环引用。
    返回去重后的排序列表。
    """
    vault_dir = Path(vault_path)
    if not vault_dir.exists():
        return []

    all_entities: set[str] = set()

    for md_file in vault_dir.glob("*.md"):
        # 跳过中枢文件自身
        if md_file.name == "00_全局知识网络中枢.md":
            continue

        # 文件名即实体（常见命名惯例）
        all_entities.add(md_file.stem)

        # 文件中所有双链
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        for m in _WIKILINK_RE.finditer(content):
            entity = m.group(1).strip()
            if entity:
                all_entities.add(entity)

    return sorted(all_entities)


# ------------------------------------------------------------
# 核心函数：保存到 Obsidian
# ------------------------------------------------------------
def save_to_obsidian(
    markdown_content: str,
    vault_path: str,
    filename: str = "untitled",
) -> str:
    """
    将 Markdown 内容保存为 Obsidian 兼容的 .md 文件。

    Args:
        markdown_content : AI 生成的 Markdown（含 YAML frontmatter）
        vault_path       : Obsidian Vault 的目标目录（不存在则自动创建）
        filename         : 后备文件名（不含扩展名），仅当无法从
                           frontmatter 提取 title 时使用

    Returns:
        实际写入的完整文件路径。

    防覆盖策略：
        若目标文件已存在，文件名追加 "_YYYYMMDD_HHMMSS" 时间戳。
    """
    # ---- 1. 确定文件名 ----
    title = _extract_title_from_frontmatter(markdown_content)
    raw_name = title if title else filename
    safe_name = _sanitize_filename(raw_name)
    if not safe_name:
        safe_name = "untitled"

    # ---- 2. 确保目录存在 ----
    vault_dir = Path(vault_path)
    vault_dir.mkdir(parents=True, exist_ok=True)

    # ---- 3. 防覆盖：同名则加时间戳 ----
    target = vault_dir / f"{safe_name}.md"
    if target.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = vault_dir / f"{safe_name}_{ts}.md"

    # ---- 4. UTF-8 写入 ----
    target.write_text(markdown_content, encoding="utf-8")

    return str(target)


# ------------------------------------------------------------
# 核心函数：全局网络中枢更新
# ------------------------------------------------------------
def update_master_graph(
    markdown_content: str,
    vault_path: str,
    pdf_filename: str,
) -> Optional[str]:
    """
    将新文档的图谱逻辑链追加写入全局中枢文件。

    Args:
        markdown_content : AI 生成的完整 Markdown
        vault_path       : Vault 根目录
        pdf_filename     : 来源 PDF 的文件名（含扩展名），用于标注来源

    Returns:
        中枢文件的绝对路径；若无逻辑链可提取则返回 None。
    """
    # ---- 1. 提取图谱逻辑链 ----
    match = _GRAPH_SECTION_RE.search(markdown_content)
    if not match:
        return None

    graph_lines = match.group(1).strip()
    if not graph_lines:
        return None

    # ---- 2. 组装追加块 ----
    source_label = Path(pdf_filename).stem
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    block = f"""

---

## 📎 来源: [[{source_label}]]
> 导入时间: {ts}

{graph_lines}
"""

    # ---- 3. 写入中枢文件 ----
    vault_dir = Path(vault_path)
    vault_dir.mkdir(parents=True, exist_ok=True)
    master_path = vault_dir / "00_全局知识网络中枢.md"

    if master_path.exists():
        # 追加
        with master_path.open("a", encoding="utf-8") as f:
            f.write(block)
    else:
        # 初始化
        header = f"""# 🌐 全局知识网络中枢

> 自动维护，每次新文档入库后追加其图谱逻辑链。
> 最后更新: {ts}

"""
        master_path.write_text(header + block.lstrip(), encoding="utf-8")

    return str(master_path)


# ------------------------------------------------------------
# CLI 快速测试（可选）
# ------------------------------------------------------------
if __name__ == "__main__":
    import sys

    sample_md = """---
title: "BERT 模型架构解析"
aliases: ["双向Transformer"]
tags:
  - AI/NLP
date: 2018-10-11
status: processed
---

## 核心摘要
这篇论文提出了 [[BERT]] 模型……

## 3. 图谱逻辑链 (Knowledge Graph Relations)
* [[BERT]] ——(依赖)——> [[Transformer]] : BERT 使用 Transformer 编码器作为基础架构。
* [[MLM]] ——(属于)——> [[BERT]] : 掩码语言模型是 BERT 的核心预训练任务。
"""

    vault = sys.argv[1] if len(sys.argv) > 1 else "./test_vault"
    saved = save_to_obsidian(sample_md, vault)
    print(f"Saved: {saved}")

    entities = get_existing_entities(vault)
    print(f"现有实体 ({len(entities)}): {entities}")

    master = update_master_graph(sample_md, vault, "BERT论文.pdf")
    if master:
        print(f"中枢已更新: {master}")
