"""/api/stats + /api/growth 路由 — 真实学习数据

- 统计全部来自真实学习行为，不依据卡片数做推断
- 新增：复习统计（次数/答题/正确率/连续天数）、空间分布、学习状态分布、复习记录
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import KnowledgeCard, KnowledgeSource, KnowledgeSpace, ReviewAttempt

router = APIRouter()


def _calc_streak(review_dates: set, card_dates: set) -> int:
    """连续学习天数：从今天往回数，当天有复习或新增卡片即算一天"""
    streak = 0
    day = datetime.utcnow().date()
    while True:
        if day.isoformat() in review_dates or day.isoformat() in card_dates:
            streak += 1
            day -= timedelta(days=1)
        else:
            break
    return streak


@router.get("/growth/overview")
def growth_overview(db: Session = Depends(get_db)):
    """首页 + 知识成长中心 共用的统计接口（真实学习数据）"""
    # 卡片总数（排除软删除）
    total_cards = (
        db.query(func.count(KnowledgeCard.id))
        .filter(KnowledgeCard.deleted_at.is_(None))
        .scalar() or 0
    )
    # 来源总数
    total_sources = db.query(func.count(KnowledgeSource.id)).scalar() or 0
    # 按来源类型
    by_type_rows = (
        db.query(KnowledgeSource.source_type, func.count(KnowledgeSource.id))
        .group_by(KnowledgeSource.source_type).all()
    )
    by_type = {t: c for t, c in by_type_rows}

    # 空间分布（替代领域分布）
    space_rows = (
        db.query(KnowledgeSpace.name, func.count(KnowledgeCard.id))
        .outerjoin(KnowledgeCard, KnowledgeCard.space_id == KnowledgeSpace.id)
        .group_by(KnowledgeSpace.id)
        .all()
    )
    space_distribution = {name: cnt for name, cnt in space_rows}

    # 学习状态分布（用户手动标记，非 AI 推断）
    status_rows = (
        db.query(KnowledgeCard.learning_status, func.count(KnowledgeCard.id))
        .filter(KnowledgeCard.deleted_at.is_(None))
        .group_by(KnowledgeCard.learning_status)
        .all()
    )
    learning_status_distribution = {s or "new": c for s, c in status_rows}

    # 兼容旧字段：领域分布（未分类计为「未分类」）
    domain_rows = (
        db.query(KnowledgeCard.domain, func.count(KnowledgeCard.id))
        .filter(KnowledgeCard.deleted_at.is_(None))
        .group_by(KnowledgeCard.domain).all()
    )
    domain_distribution = {}
    for d, c in domain_rows:
        key = d or "未分类"
        domain_distribution[key] = domain_distribution.get(key, 0) + c

    # 最近 7 天新增卡片
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_rows = (
        db.query(
            func.date(KnowledgeCard.created_at).label("d"),
            func.count(KnowledgeCard.id),
        )
        .filter(
            KnowledgeCard.deleted_at.is_(None),
            KnowledgeCard.created_at >= seven_days_ago,
        )
        .group_by("d").order_by("d").all()
    )
    recent_7_days = []
    for i in range(7):
        day = (datetime.utcnow() - timedelta(days=6 - i)).strftime("%Y-%m-%d")
        cnt = next((c for d, c in recent_rows if str(d) == day), 0)
        recent_7_days.append({"date": day, "count": cnt})

    # 复习统计（真实学习数据）
    review_count = db.query(func.count(ReviewAttempt.id)).scalar() or 0
    total_answered = db.query(func.coalesce(func.sum(ReviewAttempt.total), 0)).scalar() or 0
    total_correct = db.query(func.coalesce(func.sum(ReviewAttempt.correct_count), 0)).scalar() or 0
    accuracy = round((total_correct / total_answered) * 100) if total_answered else 0

    # 近 14 天复习量
    fourteen_ago = datetime.utcnow() - timedelta(days=14)
    review_rows = (
        db.query(
            func.date(ReviewAttempt.created_at).label("d"),
            func.count(ReviewAttempt.id),
        )
        .filter(ReviewAttempt.created_at >= fourteen_ago)
        .group_by("d").order_by("d").all()
    )
    recent_14_days = []
    for i in range(14):
        day = (datetime.utcnow() - timedelta(days=13 - i)).strftime("%Y-%m-%d")
        cnt = next((c for d, c in review_rows if str(d) == day), 0)
        recent_14_days.append({"date": day, "count": cnt})

    # 连续学习天数（复习日期 ∪ 新增卡片日期）
    review_dates = {
        str(d) for (d,) in db.query(func.date(ReviewAttempt.created_at)).all()
    }
    card_dates = {
        str(d) for (d,) in db.query(func.date(KnowledgeCard.created_at))
        .filter(KnowledgeCard.deleted_at.is_(None)).all()
    }
    streak_days = _calc_streak(review_dates, card_dates)

    last_review = (
        db.query(ReviewAttempt.created_at)
        .order_by(ReviewAttempt.created_at.desc()).first()
    )

    return {
        "total_cards": total_cards,
        "total_sources": total_sources,
        "by_type": by_type,
        "space_distribution": space_distribution,
        "learning_status_distribution": learning_status_distribution,
        "domain_distribution": domain_distribution,
        "recent_7_days": recent_7_days,
        "today_count": recent_7_days[-1]["count"] if recent_7_days else 0,
        "week_count": sum(d["count"] for d in recent_7_days),
        # 复习统计
        "review_count": review_count,
        "total_answered": total_answered,
        "total_correct": total_correct,
        "accuracy": accuracy,
        "recent_14_days": recent_14_days,
        "streak_days": streak_days,
        "last_review_at": last_review[0].isoformat() if last_review and last_review[0] else None,
    }


@router.get("/growth/review-history")
def review_history(db: Session = Depends(get_db)):
    """复习记录列表（成长页用）"""
    attempts = (
        db.query(ReviewAttempt)
        .order_by(ReviewAttempt.created_at.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "id": a.id,
            "mode": a.mode,
            "scope": a.scope_json,
            "total": a.total,
            "correct_count": a.correct_count,
            "score": a.score,
            "weak_points": a.weak_points_json or [],
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in attempts
    ]


# 兼容旧路径 /api/stats
@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    return growth_overview(db)
