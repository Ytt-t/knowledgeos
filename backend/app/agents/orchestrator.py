"""KnowledgeOS V4 Orchestrator — 多模态统一归一化流程

架构 4.1 决策：Video/Document/Image 三个 Agent 输出统一结构 {raw_text, metadata}
下游 Organizer（总结+命名+分类+标签+归档）完全不感知输入形态。

V4 状态机: pending → parsing → summarizing → classifying → done/failed
"""
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import (
    KnowledgeSource, KnowledgeCard, KnowledgeSpace, ConceptRelation,
)
from app.services.vector_store import get_store
from app.agents.summarizer import summarize
from app.agents.organizer import organize

logger = logging.getLogger(__name__)

# content_type 映射
SOURCE_TYPE_TO_CONTENT_TYPE = {
    "pdf": "document",
    "docx": "document",
    "txt": "document",
    "image": "image",
    "bilibili_video": "video",
    "xiaohongshu_video": "video",
    "douyin_video": "video",
}


def _set_status(db: Session, source: KnowledgeSource, status: str, error: Optional[str] = None):
    source.status = status
    if error:
        source.error_message = error
    db.commit()
    logger.info(f"[source {source.id}] status -> {status}")


async def _capture_content(db: Session, source: KnowledgeSource) -> dict:
    """Content Capture Agent：根据 source_type 路由到对应子 Agent

    Returns:
        归一化结构 { raw_text, metadata, content_type }
    """
    stype = source.source_type

    if stype in ("bilibili_video", "xiaohongshu_video", "douyin_video"):
        # Video Agent
        from app.services import video_agent
        result = await video_agent.capture(source.source_url)
        return {
            "raw_text": result["raw_text"],
            "metadata": result["metadata"],
            "content_type": "video",
        }

    elif stype in ("pdf", "docx", "txt"):
        # Document Agent
        from app.services import file_parser
        text = file_parser.extract_text(source.file_path, stype)
        title = Path(source.file_path).stem if source.file_path else "未命名文档"
        return {
            "raw_text": text,
            "metadata": {"title": title, "file_type": stype},
            "content_type": "document",
        }

    elif stype == "image":
        # Image Agent
        from app.services import image_parser
        text = image_parser.extract_text(source.file_path)
        title = Path(source.file_path).stem if source.file_path else "图片笔记"
        return {
            "raw_text": text,
            "metadata": {"title": title, "image_type": "screenshot"},
            "content_type": "image",
        }

    else:
        raise ValueError(f"未知 source_type: {stype}")


async def _run_pipeline(db: Session, source: KnowledgeSource, *, skip_parsing=False, skip_dedup=False):
    """V4 统一处理链路：parsing → (去重检测) → summarizing → classifying → done"""
    try:
        # 1. parsing：Content Capture Agent 识别类型 + 解析内容
        if skip_parsing and source.raw_text:
            # V7: 去重后「仍然新建」的续跑路径，内容已解析过
            raw_text = source.raw_text
            content_type = SOURCE_TYPE_TO_CONTENT_TYPE.get(source.source_type, "document")
            meta_title = ""
            logger.info(f"[source {source.id}] 跳过解析（已有 raw_text {len(raw_text)} chars）")
        else:
            _set_status(db, source, "parsing")
            captured = await _capture_content(db, source)
            raw_text = captured["raw_text"]
            content_type = captured["content_type"]
            meta_title = captured["metadata"].get("title", "未命名")

            source.raw_text = raw_text
            source.platform = captured["metadata"].get("platform")
            db.commit()
            logger.info(
                f"[source {source.id}] 内容捕获完成: type={content_type}, "
                f"chars={len(raw_text)}, title={meta_title}"
            )

        if not raw_text.strip():
            raise ValueError("解析到的文本为空，无法生成知识卡片")

        # V7: 去重检测（省 R1 蒸馏费用；命中 → duplicate 终态等待用户决策）
        if not skip_dedup and not source.force_create:
            from app.services.dedup import check_duplicate
            dup_card_id = check_duplicate(db, source)
            if dup_card_id:
                source.duplicate_card_id = dup_card_id
                _set_status(db, source, "duplicate")
                logger.info(f"[source {source.id}] 命中重复内容 card_id={dup_card_id}，等待用户决策")
                return

        # 2. summarizing：AI 总结 + 自动命名
        _set_status(db, source, "summarizing")

        def _on_thinking(thinking: str):
            """V6.1: 把 R1 思维链节选写入 source，供前端「思考过程」展示。
            回调永不抛异常（异常会连累 smart_json 降级路径）。"""
            try:
                source.thinking_text = (thinking or "")[:2000]
                db.commit()
                logger.info(f"[source {source.id}] 思维链已写入 {len(source.thinking_text)} chars")
            except Exception as e:
                logger.warning(f"[source {source.id}] 写入思考链失败: {e}")

        ai_result = await summarize(text=raw_text, title=meta_title, on_thinking=_on_thinking)
        card_title = ai_result.get("title") or meta_title
        logger.info(
            f"[source {source.id}] AI 总结完成: title={card_title}, "
            f"key_points={len(ai_result['key_points'])}"
        )

        # 3. classifying：AI 标签建议 + 空间建议（V6：不再强制分类/归档）
        _set_status(db, source, "classifying")
        space_names = [row[0] for row in db.query(KnowledgeSpace.name).all()]
        org_result = await organize(
            title=card_title,
            summary=ai_result["summary"],
            keywords=ai_result["keywords"],
            space_names=space_names,
        )
        logger.info(
            f"[source {source.id}] 标签建议完成: tags={org_result['tags']}, "
            f"suggested_space={org_result['suggested_space']}"
        )

        # 4. 写入 knowledge_cards + 向量库
        card = KnowledgeCard(
            source_id=source.id,
            user_id=source.user_id,
            title=card_title,
            content_type=content_type,
            ai_summary={
                "summary": ai_result["summary"],
                "key_points": ai_result["key_points"],
                "structure": ai_result["structure"],
            },
            # V4.1 Card 2.0 新字段
            one_liner=ai_result.get("one_liner", ""),
            core_points=ai_result.get("core_points", []),
            knowledge_structure=ai_result.get("knowledge_structure", {}),
            importance=None,  # V6: AI 不再自动标重要，由用户自己决定
            misconceptions=ai_result.get("misconceptions", []),
            quick_test=ai_result.get("quick_test", []),
            quality_score=ai_result.get("quality_score", {}),
            summary_mode="study",
            key_cases=ai_result.get("key_cases", []),
            next_steps=ai_result.get("next_steps", []),
            keywords=ai_result["keywords"],
            domain=org_result["suggested_space"] or "",  # 兼容旧 UI
            tags=org_result["tags"],
            is_archived=False,  # V6: 取消自动归档
            # V6: 知识空间 —— 未分类等用户确认，AI 建议暂存 suggested_space
            space_id=None,
            suggested_space=org_result["suggested_space"],
        )
        db.add(card)
        db.flush()

        # 向量入库（V6: 带 detail 的完整内容，检索质量更高）
        store = get_store()
        cp_text = "\n".join(
            f"- {p['point']}" + (f"：{p.get('detail', '')}" if p.get('detail') else "")
            for p in card.core_points or []
            if isinstance(p, dict) and p.get("point")
        )
        doc = f"{card.title}\n{ai_result['summary']}\n{cp_text}\n关键词：{', '.join(ai_result['keywords'])}"
        try:
            store.add(card.id, doc)
        except Exception as ve:
            logger.warning(f"card {card.id} 向量入库失败（不影响主流程）: {ve}")
        db.commit()

        # 5. 知识关联发现（P1，V4 保留）
        _discover_relations(db, store, [card.id])

        _set_status(db, source, "done")
    except Exception as e:
        logger.exception(f"[source {source.id}] pipeline failed")
        _set_status(db, source, "failed", error=str(e))


def _discover_relations(db: Session, store, new_card_ids: list[int]):
    """新卡片与已有卡片做关联发现"""
    SEMANTIC_THRESHOLD = 0.35
    TOP_K = 5

    for cid in new_card_ids:
        card = db.query(KnowledgeCard).filter(KnowledgeCard.id == cid).first()
        if not card:
            continue
        query_text = f"{card.title}\n{card.ai_summary.get('summary', '') if card.ai_summary else ''}"
        try:
            hits = store.query(query_text, top_k=TOP_K + 1)
        except Exception as e:
            logger.warning(f"card {cid} 关联发现检索失败: {e}")
            hits = []

        related_count = 0
        for other_id, score in hits:
            if other_id == cid or score < SEMANTIC_THRESHOLD:
                continue
            if _relation_exists(db, cid, other_id):
                continue
            rel = ConceptRelation(
                from_card_id=cid,
                to_card_id=other_id,
                relation_type="semantic_similar",
                similarity_score=round(score, 3),
            )
            db.add(rel)
            related_count += 1

        # 同空间关联（V6: 基于用户知识空间，替代原 domain 关联）
        if card.space_id:
            same_space_cards = (
                db.query(KnowledgeCard)
                .filter(
                    KnowledgeCard.space_id == card.space_id,
                    KnowledgeCard.id != card.id,
                    KnowledgeCard.deleted_at.is_(None),
                )
                .all()
            )
            for other in same_space_cards:
                if _relation_exists(db, cid, other.id):
                    continue
                rel = ConceptRelation(
                    from_card_id=cid,
                    to_card_id=other.id,
                    relation_type="same_space",
                    similarity_score=0.0,
                )
                db.add(rel)
                related_count += 1

        if related_count:
            logger.info(f"card {cid} 发现 {related_count} 条关联")
    db.commit()


def _relation_exists(db: Session, a: int, b: int) -> bool:
    return (
        db.query(ConceptRelation)
        .filter(
            ((ConceptRelation.from_card_id == a) & (ConceptRelation.to_card_id == b))
            | ((ConceptRelation.from_card_id == b) & (ConceptRelation.to_card_id == a))
        )
        .first()
        is not None
    )


async def run_pipeline(source_id: int, db_factory, *, skip_parsing=False, skip_dedup=False):
    """异步执行整个 Capture 流程（V7: 幂等护栏 + 去重续跑参数）"""
    db = db_factory()
    try:
        source = db.query(KnowledgeSource).get(source_id)
        if not source:
            logger.error(f"source {source_id} not found")
            return
        # 幂等护栏：已完成/处理中的 source 不重复执行
        if source.status == "done" or source.status in ("summarizing", "classifying"):
            logger.warning(f"[source {source_id}] 状态 {source.status}，跳过重复执行")
            return
        await _run_pipeline(db, source, skip_parsing=skip_parsing, skip_dedup=skip_dedup)
    finally:
        db.close()
