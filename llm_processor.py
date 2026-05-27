"""
DeepSeek API 调用封装 —— 将纯文本提炼为结构化 Markdown 节点。

Dependencies:
    pip install openai tenacity
"""

from typing import Optional

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


# ------------------------------------------------------------
# GraphRAG 抽取指令 —— 知识图谱架构师（基础模板）
# ------------------------------------------------------------
_BASE_SYSTEM_PROMPT = r"""
# Role
你是一个顶尖的知识图谱架构师与 Obsidian 知识库管理专家。你的任务是阅读我提供的非结构化长文本（研报、文献或笔记），从中提取核心逻辑，并将其转化为带有高度结构化元数据和双向链接 `[[ ]]` 的 Obsidian 标准 Markdown 文件。

# Core Objectives
1. 消除信息的"堆砌感"，提取文本中概念之间的深度逻辑关系。
2. 识别关键实体，利用 `[[ ]]` 语法为 Obsidian 的图谱（Graph View）准备节点。
3. 保持输出极度客观、克制、结构化，不输出任何主观废话。

# Output Format Specifications (严格遵循)
你的输出必须由以下四个固定模块组成：

## 1. YAML Frontmatter
在文档最顶部生成，必须包含以下字段：
---
title: "[提炼一个不超过15个字的精准标题]"
aliases: ["[别名1]", "[别名2]"]
tags:
  - #[一级学科]/[细分领域]
date: YYYY-MM-DD  # 提取文本发布日期，若无则留空
status: processed
---

## 2. 核心摘要 (Executive Summary)
用 150-300 字的高度凝练语言，概括整篇文档的核心研究目的、使用的方法或框架、以及最终得出的结论。
要求：遇到重要的专有名词、模型名称、政策框架时，**必须**使用 `[[ ]]` 包裹。

## 3. 图谱逻辑链 (Knowledge Graph Relations)
提取文中核心概念之间的依赖、因果或递进关系。使用列表形式输出：
* [[实体A]] ——(导致/依赖/属于/正相关/负相关)——> [[实体B]] : 简要补充逻辑解释。

## 4. 关键论点解析 (Key Takeaways)
提炼 3-5 个文中的核心技术细节、公式逻辑或业务启示。
要求：
- 使用多级列表。
- 代码、数学逻辑或量化指标的描述必须精准。清晰写明核心框架的输入输出或业务边界。

# Constraints (绝对不可违反)
1. **双链原则：** 仅对"名词、概念、模型、专有名词、人名、机构"使用 `[[ ]]`。绝对不要对动词、形容词或无意义的短语加双链（例如绝对禁止 `[[增加]]`、`[[因此]]`）。
2. **纯粹输出：** 只输出 Markdown 本身。开头不要说"好的"，结尾不要说"希望这对您有帮助"。
3. **禁止幻觉：** 如果原文没有提供具体年份、数据或结论，保留空白或写明"未提及"，绝对禁止自行编造。
"""


def _build_system_prompt(existing_entities: Optional[list[str]] = None) -> str:
    """
    构建完整的 SYSTEM_PROMPT，可选地注入全局实体词典。
    """
    prompt = _BASE_SYSTEM_PROMPT

    if existing_entities:
        entities_str = "、".join(existing_entities)
        entity_block = rf"""

# 全局实体词典（必读 —— 最高优先级）
这是知识库中已存在的实体列表：{entities_str}。
在提取图谱逻辑和摘要时，**必须绝对优先**使用词典中已有的实体名称进行双链，严禁生造同义词（例如：词典中有"Alpha因子"，就绝不能输出"阿尔法因子"）。
"""
        prompt += entity_block

    return prompt


# ---------- 可重试的异常白名单 ----------
_RETRYABLE_ERRORS = (
    TimeoutError,
    ConnectionError,
    # openai 内部继承自 APITimeoutError / APIConnectionError 等
)

# 尝试捕获 openai 的专用超时/连接异常（若未安装则忽略）
try:
    from openai import APITimeoutError, APIConnectionError

    _RETRYABLE_ERRORS = _RETRYABLE_ERRORS + (APITimeoutError, APIConnectionError)
except ImportError:
    pass


def _is_retryable(exception: BaseException) -> bool:
    """判定异常是否值得重试（超时、连接中断）。"""
    return isinstance(exception, _RETRYABLE_ERRORS)


@retry(
    retry=retry_if_exception_type(_RETRYABLE_ERRORS),  # 仅对超时/连接异常重试
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry_error_callback=lambda retry_state: None,
)
def _call_deepseek(client: OpenAI, user_text: str, system_prompt: str) -> str:
    """单次 API 调用（被 tenacity 包装，自动重试）。"""
    response = client.chat.completions.create(
        model="deepseek-chat",
        temperature=0.1,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        timeout=120,  # 单次请求最长等待 120 秒
    )
    return response.choices[0].message.content or ""


def generate_graph_node(
    text: str,
    api_key: str,
    existing_entities: Optional[list[str]] = None,
) -> str:
    """
    将纯文本送入 DeepSeek API，返回提炼后的 Markdown 字符串。

    Args:
        text              : PDF 提取后的纯文本，作为 user prompt 传入
        api_key           : DeepSeek API Key
        existing_entities : 知识库中已存在的全局实体列表，
                            用于指导 AI 优先复用已有实体名，避免节点分裂

    Returns:
        结构化 Markdown 字符串。若 3 次重试均失败则返回空字符串。
    """
    if not text or not text.strip():
        return ""

    system_prompt = _build_system_prompt(existing_entities)
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")

    try:
        return _call_deepseek(client, text, system_prompt)
    except Exception as e:
        # 重试 3 次后依然失败 —— 兜底返回空串
        print(f"Error: DeepSeek API call failed after 3 retries: {e}")
        return ""


# ------------------------------------------------------------
# CLI 快速测试（可选）
# ------------------------------------------------------------
if __name__ == "__main__":
    import os
    import sys

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("Error: Please set DEEPSEEK_API_KEY environment variable.", file=sys.stderr)
        sys.exit(1)

    sample = "这是一段从 PDF 提取的示例文本，用于测试 GraphRAG 节点生成。"
    md = generate_graph_node(sample, api_key)
    sys.stdout.write(md if md else "(No output)")
