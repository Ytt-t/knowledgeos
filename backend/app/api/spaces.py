"""知识空间 API 路由（用户自定义，取消 AI 强制分类）"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import KnowledgeSpace, KnowledgeCard
from app.schemas import SpaceCreate, SpaceUpdate

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/spaces")
def list_spaces(db: Session = Depends(get_db)):
    """所有知识空间 + 卡片数 + 未分类卡片数"""
    rows = (
        db.query(KnowledgeSpace, func.count(KnowledgeCard.id))
        .outerjoin(
            KnowledgeCard,
            (KnowledgeCard.space_id == KnowledgeSpace.id)
            & (KnowledgeCard.deleted_at.is_(None)),
        )
        .group_by(KnowledgeSpace.id)
        .order_by(KnowledgeSpace.created_at.asc())
        .all()
    )
    unclassified = (
        db.query(func.count(KnowledgeCard.id))
        .filter(
            KnowledgeCard.deleted_at.is_(None),
            KnowledgeCard.space_id.is_(None),
        )
        .scalar() or 0
    )
    return {
        "spaces": [
            {
                "id": s.id,
                "name": s.name,
                "icon": s.icon,
                "card_count": cnt,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s, cnt in rows
        ],
        "unclassified_count": unclassified,
    }


@router.post("/spaces")
def create_space(payload: SpaceCreate, db: Session = Depends(get_db)):
    """新建知识空间（重名返回 400）"""
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "空间名不能为空")
    exists = db.query(KnowledgeSpace).filter(KnowledgeSpace.name == name).first()
    if exists:
        raise HTTPException(400, f"空间「{name}」已存在")
    s = KnowledgeSpace(user_id=1, name=name, icon=payload.icon)
    db.add(s); db.commit(); db.refresh(s)
    return {"id": s.id, "name": s.name, "icon": s.icon, "card_count": 0}


@router.patch("/spaces/{space_id}")
def update_space(space_id: int, payload: SpaceUpdate, db: Session = Depends(get_db)):
    """重命名空间"""
    s = db.query(KnowledgeSpace).get(space_id)
    if not s:
        raise HTTPException(404, "space not found")
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(400, "空间名不能为空")
        dup = db.query(KnowledgeSpace).filter(
            KnowledgeSpace.name == name, KnowledgeSpace.id != space_id
        ).first()
        if dup:
            raise HTTPException(400, f"空间「{name}」已存在")
        s.name = name
        # 同步卡片 domain 字段（兼容旧 UI 筛选）
        db.query(KnowledgeCard).filter(KnowledgeCard.space_id == space_id).update(
            {KnowledgeCard.domain: name}
        )
    if payload.icon is not None:
        s.icon = payload.icon
    db.commit(); db.refresh(s)
    return {"id": s.id, "name": s.name, "icon": s.icon}


@router.delete("/spaces/{space_id}")
def delete_space(space_id: int, db: Session = Depends(get_db)):
    """删除空间：该空间下卡片变为未分类（不删卡片）"""
    s = db.query(KnowledgeSpace).get(space_id)
    if not s:
        raise HTTPException(404, "space not found")
    moved = (
        db.query(KnowledgeCard)
        .filter(KnowledgeCard.space_id == space_id)
        .update({KnowledgeCard.space_id: None})
    )
    db.delete(s)
    db.commit()
    logger.info(f"空间 {space_id} 已删除，{moved} 张卡片变为未分类")
    return {"ok": True, "id": space_id, "unclassified_cards": moved}
