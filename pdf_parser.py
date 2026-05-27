"""
Robust PDF text extraction with header/footer filtering and image-page detection.

Dependencies: PyMuPDF (pip install PyMuPDF)
"""

import fitz  # PyMuPDF
import sys
from pathlib import Path


def extract_text_from_pdf(file_path: str) -> str:
    """
    从 PDF 中提取干净文本，具备以下能力：

    1. 坐标过滤：裁剪页面顶部 5% 和底部 5%，剔除页眉页脚
    2. 纯图片页识别：自动跳过仅有图片、无实质文字内容的页面
    3. 异常容错：对坏损 PDF、单个损坏页面均做降级处理，不会整体崩溃
    4. 返回拼接后的 UTF-8 纯文本字符串
    """
    # ---- 打开 PDF ----
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        print(f"Error: Cannot open PDF '{file_path}': {e}", file=sys.stderr)
        return ""

    pages_text: list[str] = []

    # ---- 逐页处理 ----
    for page_idx in range(len(doc)):
        try:
            page = doc[page_idx]
            rect = page.rect

            # ============ 1. 纯图片页检测 ============
            full_text = page.get_text("text").strip()
            if len(full_text) < 20:
                # 近乎无文字 + 页面上存在图片 → 判定为纯图片页
                if page.get_images(full=True):
                    continue  # 跳过本页
                # 即使无图片，文字极度稀疏也跳过（空白页/扫描件）
                if len(full_text) == 0:
                    continue

            # ============ 2. 页眉页脚坐标过滤 ============
            # 内容区：页面高度 [5%, 95%]
            header_ymax = rect.y0 + rect.height * 0.05
            footer_ymin = rect.y0 + rect.height * 0.95

            # 逐块提取（比 clip= 参数更精准，不会截断跨边界文本行）
            blocks = page.get_text("blocks")
            kept_lines: list[str] = []

            for b in blocks:
                if len(b) < 5:
                    continue
                x0, y0, x1, y1 = b[0], b[1], b[2], b[3]
                text = b[4] if isinstance(b[4], str) else ""
                text = text.strip()
                if not text:
                    continue

                # 块的纵向范围与内容区有交集 → 保留
                if y1 > header_ymax and y0 < footer_ymin:
                    kept_lines.append(text)

            page_text = "\n".join(kept_lines)
            if page_text:
                pages_text.append(page_text)

        except Exception as e:
            print(
                f"Warning: Skipping page {page_idx + 1} in '{file_path}': {e}",
                file=sys.stderr,
            )
            continue  # 单页损坏不影响其他页

    doc.close()
    return "\n\n".join(pages_text)


# ------------------------------------------------------------
# CLI entrypoint (optional): python pdf_parser.py input.pdf
# ------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pdf_parser.py <pdf_path>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    if not Path(path).exists():
        print(f"Error: File not found: '{path}'", file=sys.stderr)
        sys.exit(1)

    result = extract_text_from_pdf(path)
    if not result:
        print("(No text extracted — document may be entirely image-based.)", file=sys.stderr)
        sys.exit(0)

    sys.stdout.write(result)
