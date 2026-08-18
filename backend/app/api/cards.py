"""API 路由 — V4.1 Card 2.0 + 知识图谱 + V6 知识空间"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import KnowledgeCard, KnowledgeSource, ConceptRelation
from app.schemas import CardOut, CardDetailOut, CardUpdate

router = APIRouter()
logger = logging.getLogger(__name__)


# ===== Cards CRUD =====
@router.get("/cards", response_model=list[CardOut])
def list_cards(
    domain: str | None = None,
    tag: str | None = None,
    favorite: bool | None = None,
    archived: bool | None = None,
    space_id: int | None = None,      # V6: 按知识空间过滤
    unclassified: bool = False,       # V6: 只看未分类
    source_id: int | None = None,     # V6: 按来源过滤（确认面板用）
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """列表查询（排除软删除）"""
    q = db.query(KnowledgeCard).filter(KnowledgeCard.deleted_at.is_(None))
    if domain:
        q = q.filter(KnowledgeCard.domain == domain)
    if tag:
        q = q.filter(KnowledgeCard.tags.like(f'%"{tag}"%'))
    if favorite is not None:
        q = q.filter(KnowledgeCard.is_favorite == favorite)
    if archived is not None:
        q = q.filter(KnowledgeCard.is_archived == archived)
    if space_id is not None:
        q = q.filter(KnowledgeCard.space_id == space_id)
    if unclassified:
        q = q.filter(KnowledgeCard.space_id.is_(None))
    if source_id is not None:
        q = q.filter(KnowledgeCard.source_id == source_id)
    return (
        q.order_by(KnowledgeCard.created_at.desc())
        .offset(offset).limit(limit).all()
    )


@router.get("/cards/{card_id}", response_model=CardDetailOut)
def get_card(card_id: int, db: Session = Depends(get_db)):
    c = db.query(KnowledgeCard).filter(
        KnowledgeCard.id == card_id,
        KnowledgeCard.deleted_at.is_(None),
    ).first()
    if not c:
        raise HTTPException(404, "card not found")

    # V4 迭代：关联 source 信息
    source = db.query(KnowledgeSource).filter(
        KnowledgeSource.id == c.source_id
    ).first()
    if source:
        c.source_platform = source.platform or source.source_type
        c.source_url = source.source_url
        c.raw_text = source.raw_text

    rels = (
        db.query(ConceptRelation)
        .filter(or_(ConceptRelation.from_card_id == card_id, ConceptRelation.to_card_id == card_id))
        .all()
    )
    related_ids = set()
    for r in rels:
        related_ids.add(r.to_card_id if r.from_card_id == card_id else r.from_card_id)
    related_cards = (
        db.query(KnowledgeCard).filter(
            KnowledgeCard.id.in_(related_ids),
            KnowledgeCard.deleted_at.is_(None),
        ).all() if related_ids else []
    )
    c.related_cards = related_cards
    return c


@router.patch("/cards/{card_id}", response_model=CardOut)
def update_card(card_id: int, payload: CardUpdate, db: Session = Depends(get_db)):
    """编辑卡片（title/domain/tags/space_id/importance/is_favorite/is_archived 等）"""
    c = db.query(KnowledgeCard).filter(
        KnowledgeCard.id == card_id, KnowledgeCard.deleted_at.is_(None),
    ).first()
    if not c:
        raise HTTPException(404, "card not found")

    data = payload.model_dump(exclude_unset=True)
    # V6: 卡片从空间移出时清空 AI 建议残留
    if data.get("space_id") is None and "space_id" in data:
        c.suggested_space = None
    for k, v in data.items():
        setattr(c, k, v)
    db.commit(); db.refresh(c)

    # V6: 标题/标签变化时重建向量，保证检索内容不过期
    if any(k in data for k in ("title", "tags")):
        try:
            from app.services.vector_store import get_store
            cp_text = "\n".join(
                f"- {p['point']}" + (f"：{p.get('detail', '')}" if p.get('detail') else "")
                for p in c.core_points or []
                if isinstance(p, dict) and p.get("point")
            )
            doc = f"{c.title}\n{(c.ai_summary or {}).get('summary', '')}\n{cp_text}\n关键词：{', '.join(c.keywords or [])}"
            get_store().update(card_id, doc)
        except Exception as e:
            logger.warning(f"card {card_id} 向量更新失败（不影响主流程）: {e}")
    return c


@router.post("/cards/{card_id}/redistill")
async def redistill_card(card_id: int, db: Session = Depends(get_db)):
    """V6.3.2: 用最新深度蒸馏重新总结旧卡片（旧卡片是旧格式：无分段/无粗体/无 detail）

    取原始文本重新跑 summarize（R1 深度版），更新卡片全部蒸馏字段 + 向量。
    保留用户手动修改过的：title（仅当标题是 AI 生成时可覆盖，这里保守：保留用户当前标题）、
    space_id / tags / importance / learning_status 等用户数据不动。
    """
    from app.agents.summarizer import summarize
    from app.services.vector_store import get_store

    c = db.query(KnowledgeCard).filter(
        KnowledgeCard.id == card_id, KnowledgeCard.deleted_at.is_(None),
    ).first()
    if not c:
        raise HTTPException(404, "card not found")

    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == c.source_id).first()
    raw_text = (source.raw_text if source and source.raw_text else "").strip()
    if not raw_text:
        raise HTTPException(400, "该卡片的原始内容已丢失，无法重新总结")

    ai_result = await summarize(text=raw_text, title=c.title)

    # 更新蒸馏字段（用户数据不动）
    c.ai_summary = {
        "summary": ai_result["summary"],
        "key_points": ai_result["key_points"],
        "structure": ai_result["structure"],
    }
    c.one_liner = ai_result.get("one_liner", "")
    c.core_points = ai_result.get("core_points", [])
    c.knowledge_structure = ai_result.get("knowledge_structure", {})
    c.key_cases = ai_result.get("key_cases", [])
    c.next_steps = ai_result.get("next_steps", [])
    c.misconceptions = ai_result.get("misconceptions", [])
    c.quick_test = ai_result.get("quick_test", [])
    c.quality_score = ai_result.get("quality_score", {})
    db.commit(); db.refresh(c)

    # 更新向量（检索内容同步刷新）
    try:
        cp_text = "\n".join(
            f"- {p['point']}" + (f"：{p.get('detail', '')}" if p.get('detail') else "")
            for p in c.core_points or []
            if isinstance(p, dict) and p.get("point")
        )
        doc = f"{c.title}\n{ai_result['summary']}\n{cp_text}\n关键词：{', '.join(c.keywords or [])}"
        get_store().update(card_id, doc)
    except Exception as e:
        logger.warning(f"card {card_id} 重新总结后向量更新失败（不影响主流程）: {e}")

    return c


@router.delete("/cards/{card_id}")
def delete_card(card_id: int, db: Session = Depends(get_db)):
    """软删除卡片（V6: 同步清理向量索引与知识关联）"""
    c = db.query(KnowledgeCard).filter(
        KnowledgeCard.id == card_id, KnowledgeCard.deleted_at.is_(None),
    ).first()
    if not c:
        raise HTTPException(404, "card not found")
    c.deleted_at = datetime.utcnow()
    db.commit()

    # 清理向量索引
    try:
        from app.services.vector_store import get_store
        get_store().remove(card_id)
    except Exception as e:
        logger.warning(f"card {card_id} 向量移除失败: {e}")
    # 清理知识关联
    db.query(ConceptRelation).filter(
        or_(ConceptRelation.from_card_id == card_id, ConceptRelation.to_card_id == card_id)
    ).delete()
    db.commit()
    return {"ok": True, "id": card_id}


@router.get("/cards/{card_id}/related", response_model=list[CardOut])
def get_related_cards(card_id: int, db: Session = Depends(get_db)):
    rels = (
        db.query(ConceptRelation)
        .filter(or_(ConceptRelation.from_card_id == card_id, ConceptRelation.to_card_id == card_id))
        .all()
    )
    ids = set()
    for r in rels:
        ids.add(r.to_card_id if r.from_card_id == card_id else r.from_card_id)
    if not ids:
        return []
    return db.query(KnowledgeCard).filter(
        KnowledgeCard.id.in_(ids), KnowledgeCard.deleted_at.is_(None),
    ).all()


# ===== Domains =====
@router.get("/domains")
def list_domains(db: Session = Depends(get_db)):
    """所有领域 + 每个领域的卡片数"""
    rows = (
        db.query(KnowledgeCard.domain, func.count(KnowledgeCard.id))
        .filter(KnowledgeCard.deleted_at.is_(None))
        .group_by(KnowledgeCard.domain)
        .all()
    )
    return [{"domain": d or "其他", "count": cnt} for d, cnt in rows]


# ===== Knowledge Graph =====
@router.get("/knowledge-graph")
def get_knowledge_graph(db: Session = Depends(get_db)):
    """知识图谱：节点 + 边"""
    cards = db.query(KnowledgeCard).filter(KnowledgeCard.deleted_at.is_(None)).all()
    rels = db.query(ConceptRelation).all()
    valid_ids = {c.id for c in cards}

    nodes = [
        {
            "id": c.id,
            "label": c.title,
            "domain": c.domain,
            "space_id": c.space_id,
            "tags": c.tags or [],
            "favorite": c.is_favorite,
        }
        for c in cards
    ]
    edges = [
        {
            "from": r.from_card_id,
            "to": r.to_card_id,
            "type": r.relation_type,
            "score": r.similarity_score,
        }
        for r in rels
        if r.from_card_id in valid_ids and r.to_card_id in valid_ids
    ]
    return {"nodes": nodes, "edges": edges}


# ===== V4.1 Card 2.0: Quality Feedback =====
class FeedbackPayload(BaseModel):
    feedback: str  # "helpful" | "inaccurate"


@router.post("/cards/{card_id}/feedback")
def submit_feedback(card_id: int, payload: FeedbackPayload, db: Session = Depends(get_db)):
    """用户对知识卡片质量反馈"""
    c = db.query(KnowledgeCard).filter(
        KnowledgeCard.id == card_id, KnowledgeCard.deleted_at.is_(None),
    ).first()
    if not c:
        raise HTTPException(404, "card not found")

    fb = payload.feedback.strip().lower()
    if fb not in ("helpful", "inaccurate"):
        raise HTTPException(400, "feedback must be 'helpful' or 'inaccurate'")

    c.user_feedback = fb
    db.commit()
    return {"ok": True, "card_id": card_id, "feedback": fb}


# ===== V4.1 Card 2.0: Quick Test =====
@router.get("/cards/{card_id}/quick-test")
def get_quick_test(card_id: int, db: Session = Depends(get_db)):
    """获取快速测试题（不含答案，前端作答后再请求答案）"""
    c = db.query(KnowledgeCard).filter(
        KnowledgeCard.id == card_id, KnowledgeCard.deleted_at.is_(None),
    ).first()
    if not c:
        raise HTTPException(404, "card not found")

    tests = c.quick_test or []
    # 返回问题列表，不包含答案
    questions = [
        {"index": i, "question": t.get("question", "")}
        for i, t in enumerate(tests)
        if isinstance(t, dict) and t.get("question")
    ]
    return {"card_id": card_id, "questions": questions}


class AnswerCheck(BaseModel):
    index: int


@router.post("/cards/{card_id}/quick-test/check")
def check_quick_test_answer(card_id: int, payload: AnswerCheck, db: Session = Depends(get_db)):
    """提交答案索引，返回该题的参考答案"""
    c = db.query(KnowledgeCard).filter(
        KnowledgeCard.id == card_id, KnowledgeCard.deleted_at.is_(None),
    ).first()
    if not c:
        raise HTTPException(404, "card not found")

    tests = c.quick_test or []
    if payload.index < 0 or payload.index >= len(tests):
        raise HTTPException(400, "invalid question index")

    t = tests[payload.index]
    return {
        "card_id": card_id,
        "index": payload.index,
        "question": t.get("question", ""),
        "answer": t.get("answer", ""),
    }
