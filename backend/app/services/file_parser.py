"""文件解析服务 — V4 支持 PDF / Word(doc/docx) / 图片(OCR)

V4 变化：
- 去掉 txt/markdown（V4 PRD 只列 PDF/Word/图片）
- 新增 Word 解析（python-docx）
- 图片走 Image Agent 的 OCR，不在此处理
"""
import logging
from pathlib import Path

from app.services import pdf_parser

logger = logging.getLogger(__name__)

MAX_CHARS = 50000


def extract_text(file_path: str | Path, source_type: str) -> str:
    """根据 source_type 调用对应解析器

    Args:
        file_path: 文件路径
        source_type: pdf / docx

    Returns:
        纯文本
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    if source_type == "pdf":
        text = pdf_parser.extract_text(file_path)
    elif source_type == "docx":
        text = _extract_docx(file_path)
    elif source_type == "txt":
        text = _extract_txt(file_path)
    else:
        raise ValueError(f"不支持的 source_type: {source_type}")

    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
        logger.info(f"文本截断到 {MAX_CHARS} 字符")
    return text


def _extract_docx(file_path: Path) -> str:
    """Word 文档解析（python-docx）"""
    from docx import Document

    doc = Document(str(file_path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    text = "\n\n".join(paragraphs)
    logger.info(f"docx 解析完成: {file_path.name}, {len(text)} 字符")
    return text


def _extract_txt(file_path: Path) -> str:
    """纯文本文件解析"""
    text = file_path.read_text(encoding="utf-8")
    logger.info(f"txt 解析完成: {file_path.name}, {len(text)} 字符")
    return text
