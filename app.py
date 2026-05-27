"""
Streamlit 前端 —— GraphRAG 全局知识图谱融合流水线入口。

将 PDF/MD → 文本提取 → DeepSeek 提炼（含全局实体感知）→ Obsidian 落盘 → 中枢网络更新，串为一体。

Usage:
    streamlit run app.py
"""

import os
import sys
from pathlib import Path

import streamlit as st

# ------------------------------------------------------------
# 导入三个自制模块（确保与本文件同目录）
# ------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pdf_parser import extract_text_from_pdf
from llm_processor import generate_graph_node
from storage import (
    save_to_obsidian,
    get_existing_entities,
    _extract_entities_from_markdown,
    update_master_graph,
)

# ------------------------------------------------------------
# 页面配置
# ------------------------------------------------------------
st.set_page_config(
    page_title="GraphRAG 全局融合流水线",
    page_icon="🧠",
    layout="wide",
)

st.title("🧠 GraphRAG 全局知识图谱融合流水线")
st.caption("PDF 提取 → DeepSeek 提炼（全局实体感知）→ Obsidian 双链落盘 → 中枢网络更新，一键完成。")

# ------------------------------------------------------------
# 会话状态初始化
# ------------------------------------------------------------
if "results" not in st.session_state:
    st.session_state.results = {}  # {filename: markdown_string}

if "errors" not in st.session_state:
    st.session_state.errors = {}  # {filename: error_message}

# ------------------------------------------------------------
# 侧边栏 — 配置
# ------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 配置")

    api_key = st.text_input(
        "DeepSeek API Key",
        type="password",
        placeholder="sk-...",
        help="你的 DeepSeek API 密钥，不会存储在本地。",
    )

    vault_path = st.text_input(
        "Obsidian Vault 路径",
        value=str(Path.home() / "ObsidianVault"),
        placeholder="C:\\Users\\...\\ObsidianVault",
        help="生成的 .md 文件将写入此目录。",
    )

    st.divider()

    st.markdown("### 🔗 流水线结构")
    st.markdown(
        """
        0. 🌐 扫描 Vault → 提取全局实体词典
        1. 📄 PDF → `extract_text_from_pdf` (pdf_parser)
        2. 🤖 文本 + 全局实体 → `generate_graph_node` (llm_processor)
        3. 💾 Markdown → `save_to_obsidian` (storage)
        4. 🕸️ 逻辑链 → `update_master_graph` (中枢网络)
        """
    )

    st.divider()
    st.caption("Made with ❤️ + PyMuPDF + DeepSeek + Streamlit")

# ------------------------------------------------------------
# 主页面 — 上传 + 处理
# ------------------------------------------------------------
uploaded_files = st.file_uploader(
    "拖拽或选择文件（支持 PDF / Markdown）",
    type=["pdf", "md"],
    accept_multiple_files=True,
)

process_btn = st.button(
    "🚀 开始处理",
    type="primary",
    disabled=(not uploaded_files or not api_key),
    use_container_width=True,
)

if not api_key:
    st.info("👈 请先在侧边栏输入 DeepSeek API Key。")
elif not vault_path:
    st.info("👈 请先在侧边栏输入 Obsidian Vault 路径。")


# ------------------------------------------------------------
# 处理逻辑
# ------------------------------------------------------------
def process_single_file(
    uploaded,
    api_key: str,
    vault_path: str,
    existing_entities: list[str] | None = None,
) -> str:
    """
    处理单个文件的三阶段流水线（含全局实体感知）。

    Args:
        uploaded          : Streamlit uploaded file
        api_key           : DeepSeek API Key
        vault_path        : Obsidian Vault 路径
        existing_entities : 当前全局实体列表，用于指导 AI 复用已有实体名

    Returns:
        生成的 Markdown 内容；失败则抛出异常。
    """
    temp_pdf = None

    # ---------- 阶段 1：文本提取 ----------
    if uploaded.name.lower().endswith(".pdf"):
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded.getvalue())
            temp_pdf = tmp.name

        raw_text = extract_text_from_pdf(temp_pdf)
        if not raw_text:
            raise RuntimeError("PDF 未提取到任何文本（可能为纯图片文档）。")
    else:
        raw_text = uploaded.getvalue().decode("utf-8", errors="replace")
        if not raw_text.strip():
            raise RuntimeError("Markdown 文件内容为空。")

    # ---------- 阶段 2：AI 提炼（传入全局实体）----------
    markdown_result = generate_graph_node(raw_text, api_key, existing_entities)
    if not markdown_result:
        raise RuntimeError("DeepSeek API 返回为空（3 次重试均失败）。")

    # ---------- 阶段 3：落盘 Obsidian ----------
    base_name = Path(uploaded.name).stem
    saved_path = save_to_obsidian(markdown_result, vault_path, filename=base_name)

    # 清理临时 PDF
    if temp_pdf and os.path.exists(temp_pdf):
        os.unlink(temp_pdf)

    return markdown_result


if process_btn:
    st.session_state.results = {}
    st.session_state.errors = {}

    # ---- 步骤 0：扫描 Vault，加载全局实体记忆 ----
    with st.status("🔍 流水线运行中……", expanded=True) as status_bar:
        # 阶段 0：全局实体预加载
        st.write("🌐 **阶段 0：加载全局实体词典**")
        global_entities = get_existing_entities(vault_path)
        entity_count = len(global_entities)
        st.write(f"   已发现 **{entity_count}** 个全局实体")
        if entity_count > 0:
            with st.expander(f"查看全局实体 ({entity_count})", expanded=False):
                st.text("、".join(global_entities))

        st.divider()

        # ---- 逐文件处理 ----
        total = len(uploaded_files)

        for idx, uploaded in enumerate(uploaded_files, 1):
            fname = uploaded.name
            st.write(f"**[{idx}/{total}]** `{fname}`")

            step_cols = st.columns(3)

            try:
                step_cols[0].caption("📄 提取文本...")
                step_cols[1].caption("🤖 请求 DeepSeek + 全局实体...")
                step_cols[2].caption("💾 写入 Vault...")

                md = process_single_file(
                    uploaded, api_key, vault_path, global_entities
                )

                step_cols[0].success("✅ 提取完成")
                step_cols[1].success("✅ 模型返回")
                step_cols[2].success("✅ 已落盘")

                st.session_state.results[fname] = md

                # ---- 动态更新全局实体：将刚生成的实体注入列表 ----
                new_ents = _extract_entities_from_markdown(md)
                if new_ents:
                    # 合并去重
                    existing_set = set(global_entities)
                    added = [e for e in new_ents if e not in existing_set]
                    global_entities = sorted(existing_set | set(new_ents))
                    if added:
                        st.caption(f"   🆕 新实体注入 ({len(added)}): {', '.join(added[:10])}{'...' if len(added) > 10 else ''}")

            except Exception as e:
                step_cols[0].error("❌ 失败")
                step_cols[1].error("❌")
                step_cols[2].error("❌")
                st.error(f"{fname}: {e}")
                st.session_state.errors[fname] = str(e)

        # ---- 阶段 4：更新全局网络中枢 ----
        st.divider()
        st.write("🕸️ **阶段 4：更新全局知识网络中枢**")

        master_updates = 0
        for fname, md in st.session_state.results.items():
            result = update_master_graph(md, vault_path, fname)
            if result:
                master_updates += 1

        if master_updates > 0:
            st.success(f"✅ 已将 {master_updates} 个文档的逻辑链并入中枢: `00_全局知识网络中枢.md`")
        else:
            st.info("ℹ️ 没有可提取的逻辑链，中枢未更新。")

        # ---- 汇总 ----
        success_count = len(st.session_state.results)
        fail_count = len(st.session_state.errors)
        total_entities_final = len(global_entities)
        status_label = (
            f"✅ 全部完成！全局实体: {total_entities_final}"
            if fail_count == 0
            else f"⚠️ 完成 {success_count}/{total}（{fail_count} 个失败）"
        )
        status_bar.update(label=status_label, state="complete")


# ------------------------------------------------------------
# 结果展示 — st.tabs 分页预览
# ------------------------------------------------------------
if st.session_state.results:
    st.divider()
    st.subheader("📋 生成结果预览")

    filenames = list(st.session_state.results.keys())
    tabs = st.tabs(filenames)

    for tab, fname in zip(tabs, filenames):
        with tab:
            md_content = st.session_state.results[fname]
            parts = md_content.split("---", 2)
            if len(parts) >= 3 and md_content.startswith("---"):
                frontmatter = parts[1]
                body = parts[2]
                with st.expander("📋 YAML Frontmatter", expanded=False):
                    st.code(frontmatter, language="yaml")
                st.markdown(body)
            else:
                st.markdown(md_content)

if st.session_state.errors:
    st.divider()
    st.subheader("⚠️ 处理失败的文件")
    for fname, err in st.session_state.errors.items():
        st.warning(f"**{fname}**: {err}")
