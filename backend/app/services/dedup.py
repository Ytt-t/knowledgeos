"""V7 上传去重：MD5 精确匹配 + 向量相似度双检测"""
import hashlib
import logging
import re
import unicodedata
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import KnowledgeSource, KnowledgeCard
from app.services.vector_store import get_store

logger = logging.getLogger(__name__)


def normalize_text(t: str) -> str:
    """NFKC 归一化 + 全空白折叠为单空格 + 去首尾 + 小写（消除视频字幕换行/PDF 断行差异）"""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", t or "")).strip().lower()


def check_duplicate(db: Session, source: KnowledgeSource) -> Optional[int]:
    """检测 source 内容是否与已有卡片重复。

    Returns:
        命中的已有 card_id；无重复返回 None
    """
    raw = source.raw_text or ""
    if not raw.strip():
        return None

    norm = normalize_text(raw)
    md5 = hashlib.md5(norm.encode("utf-8")).hexdigest()
    source.content_md5 = md5

    # 1) MD5 精确匹配（V7 之后创建的 source 才带 content_md5）
    dup_source = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.content_md5 == md5,
            KnowledgeSource.status == "done",
            KnowledgeSource.id != source.id,
        )
        .first()
    )
    if dup_source:
        card = (
            db.query(KnowledgeCard)
            .filter(
                KnowledgeCard.source_id == dup_source.id,
                KnowledgeCard.deleted_at.is_(None),
            )
            .first()
        )
        if card:
            logger.info(f"[source {source.id}] MD5 命中重复，已有卡片 card_id={card.id}")
            return card.id

    # 2) 向量相似度（长文截断 1500 字符，MiniLM 截断 256 token）
    try:
        store = get_store()
        hits = store.query(norm[:1500], top_k=settings.DEDUP_TOP_K)
        for cid, score in hits:
            if score >= settings.DEDUP_SIM_THRESHOLD:
                logger.info(f"[source {source.id}] 向量命中重复 card_id={cid} score={score:.3f}")
                return cid
    except Exception as e:
        # 向量库异常（如预热失败加载中）按"无重复"放行，不阻断主流程
        logger.warning(f"[source {source.id}] 去重向量检索失败（放行）: {e}")

    return None
