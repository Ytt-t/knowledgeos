"""PDF 解析服务

用 pdfplumber 提取纯文本，MVP 不做版面还原。
"""
import logging
from pathlib import Path
from typing import Optional

import pdfplumber

logger = logging.getLogger(__name__)

# 单 PDF 最大提取字符数（防止超大文件爆 token）
MAX_CHARS = 50000


def extract_text(file_path: str | Path) -> str:
    """提取 PDF 全文文本

    Args:
        file_path: PDF 文件路径

    Returns:
        纯文本（页之间用 \n\n 分隔）
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {file_path}")

    pages_text = []
    total_chars = 0
    with pdfplumber.open(str(file_path)) as pdf:
        for i, page in enumerate(pdf.pages):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            pages_text.append(text)
            total_chars += len(text)
            if total_chars >= MAX_CHARS:
                logger.info(
                    f"PDF 文本已达 {MAX_CHARS} 字符上限，第 {i+1} 页之后截断"
                )
                break

    full_text = "\n\n".join(pages_text).strip()
    logger.info(
        f"PDF 解析完成: {file_path.name}, 共 {len(pdf.pages)} 页，"
        f"提取 {len(full_text)} 字符"
    )
    return full_text
