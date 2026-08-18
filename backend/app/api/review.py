"""/api/review 路由 — V6 自定义复习范围 + AI 生成复习题 + 薄弱点分析 + 复习记录

PRD V3.0 复习范围（scope_type）：
- all: 全部知识
- recent: 最近学习（近 7 天新增）
- space: 指定知识空间
- card_ids: 指定知识卡片
- weak: 薄弱知识（历史答题薄弱点 + 未掌握卡片）

复习四模式（mode）：
- understand: 理解模式（概念题为主，检验是否理解）
- apply: 应用模式（应用题为主，检验能否用起来）
- interview: 面试模式（高频考点 + 深度问答）
- quick: 快速检测（判断/选择为主，快速过一遍）

V6 变化：
- question_count 可空：None = 智能题量（按所选卡片数自适应，min(20, max(3, cards*2))）
- evaluate 落库 review_attempts，成长页用真实数据
- 新增 GET /review/weak-points
- 出题/评分走 smart_json（R1 深度思考）
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import KnowledgeCard, ReviewAttempt, WrongQuestion
from app.services.deepseek import smart_json

router = APIRouter()
logger = logging.getLogger(__name__)

VALID_MODES = {"understand", "apply", "interview", "quick"}

# 模式 → 题型偏好 + 指令（PRD V3.0）
# allowed_types: 该模式下允许的题型（硬约束），AI 返回的非法类型会在后处理中被丢弃
MODE_GUIDE = {
    "understand": {
        "label": "理解模式",
        "type_hint": "以 concept（概念理解）题为主，少量 judgment 题",
        "instruction": "重点检验是否真正理解了概念，不要死记硬背式题目",
        "allowed_types": ["concept", "judgment"],
    },
    "apply": {
        "label": "应用模式",
        "type_hint": "以 application（应用题）为主，要求把知识用到具体场景",
        "instruction": "每题给一个具体场景，让用户用所学知识分析或解决",
        "allowed_types": ["application"],
    },
    "interview": {
        "label": "面试模式",
        "type_hint": "覆盖 concept / application / open，偏高频考点与深度问答",
        "instruction": "模拟真实面试场景，包含高频考点、追问式开放题",
        "allowed_types": ["concept", "application", "open"],
    },
    "quick": {
        "label": "快速检测",
        "type_hint": "以 judgment（判断题）为主，少量 concept 题，可快速作答",
        "instruction": "题目要简短，参考答案要干脆，便于快速过一遍",
        "allowed_types": ["judgment", "concept"],
    },
}


class ReviewScope(BaseModel):
    """复习范围选择（V6: question_count 可空 = 智能题量）"""
    scope_type: str = "all"  # all | space | card_ids | recent | weak
    space_id: Optional[int] = None
    card_ids: Optional[list[int]] = None
    question_count: Optional[int] = None  # None = 智能题量
    mode: str = "understand"  # PRD V3.0: understand | apply | interview | quick


class AnswerSubmit(BaseModel):
    """提交答案（V7: is_correct 用于错题本收集，开放题为 None 跳过）"""
    question: str
    user_answer: str
    correct_answer: str
    card_id: Optional[int] = None
    is_correct: Optional[bool] = None


class EvaluatePayload(BaseModel):
    """V6 评估请求：带模式与范围，用于落库复习记录"""
    mode: str = "understand"
    scope: Optional[dict] = None
    submissions: list[AnswerSubmit]


REVIEW_PROMPT = """你是 KnowledgeOS 的复习题生成 Agent。基于用户选择的知识卡片内容，生成高质量的复习题。

核心原则：题目要检验**真懂还是假懂**，让人需要思考才能答对，而不是一眼看穿。

要求：
1. 题型多样化：概念理解（concept）、应用题（application）、判断题（judgment）、开放题（open）
2. concept / application 题必须输出 4 个选项 options（1 个正确答案 + 3 个干扰项）：
   - 干扰项设计规则：易混淆的相近概念（如 RAG 的"检索"与"微调"）、字面相近但含义不同、半对半错（前半句对后半句错）、常见误解（新手最容易犯的错）
   - 干扰项长度与正确项相当，不能明显更长或更短
   - 正确答案绝不能放在固定位置（随机分布）
   - answer 必须是 options 中的原文之一
3. judgment 判断题不输出 options（前端提供"对/错"）；open 开放题不输出 options
4. 题目要有一定的思考深度：考"为什么"和"区别"，不考死记硬背的"是什么"
5. 全部用中文

输出 JSON 格式：
{
  "questions": [
    {
      "type": "concept" | "application" | "judgment" | "open",
      "question": "题目内容",
      "options": ["选项A", "选项B", "选项C", "选项D"],  // 仅 concept/application 有
      "answer": "正确答案（必须在 options 中）",
      "card_id": 对应卡片ID,
      "card_title": "对应卡片标题",
      "difficulty": "easy" | "medium" | "hard"
    }
  ]
}"""

EVALUATION_PROMPT = """你是 KnowledgeOS 的 AI 评分 Agent。评价用户的答题情况。

评分维度：
1. 正确性：答案是否正确
2. 完整度：是否覆盖关键要点
3. 理解深度：是否展现了深入理解

输出 JSON 格式：
{
  "score": 0-100,
  "correctness": 0-100,
  "completeness": 0-100,
  "understanding": 0-100,
  "feedback": "简短评价（2-3句，指出进步和不足）",
  "weak_points": ["薄弱知识点1", "薄弱知识点2"]
}"""


def _resolve_cards(scope: ReviewScope, db: Session) -> list[KnowledgeCard]:
    """按 scope 解析卡片集合（V6 五范围）"""
    q = db.query(KnowledgeCard).filter(KnowledgeCard.deleted_at.is_(None))

    if scope.scope_type == "space" and scope.space_id:
        q = q.filter(KnowledgeCard.space_id == scope.space_id)
    elif scope.scope_type == "card_ids" and scope.card_ids:
        q = q.filter(KnowledgeCard.id.in_(scope.card_ids))
    elif scope.scope_type == "recent":
        q = q.filter(KnowledgeCard.created_at >= datetime.utcnow() - timedelta(days=7))
    elif scope.scope_type == "weak":
        # 薄弱知识：未掌握的卡片 + 近期低分复习涉及的卡片
        weak_ids = _weak_card_ids(db)
        if weak_ids is not None:
            q = q.filter(KnowledgeCard.id.in_(weak_ids))
        else:
            q = q.filter(KnowledgeCard.learning_status.in_(["new", "learning"]))

    return q.order_by(KnowledgeCard.created_at.desc()).limit(50).all()


def _weak_card_ids(db: Session) -> Optional[set]:
    """薄弱卡片 id 集合：历史低分复习涉及的卡片 + 未掌握卡片。
    没有任何复习记录时返回 None（调用方回退为未掌握筛选）。"""
    low_score_attempts = (
        db.query(ReviewAttempt)
        .filter(
            ReviewAttempt.score < 60,
            ReviewAttempt.created_at >= datetime.utcnow() - timedelta(days=14),
        )
        .all()
    )
    ids: set[int] = set()
    for a in low_score_attempts:
        scope_json = a.scope_json or {}
        if scope_json.get("card_ids"):
            ids.update(scope_json["card_ids"])
        elif scope_json.get("scope_type") == "space" and scope_json.get("space_id"):
            ids.update(
                c[0] for c in db.query(KnowledgeCard.id)
                .filter(KnowledgeCard.space_id == scope_json["space_id"],
                        KnowledgeCard.deleted_at.is_(None)).all()
            )

    not_mastered = {
        c[0] for c in db.query(KnowledgeCard.id)
        .filter(KnowledgeCard.deleted_at.is_(None),
                KnowledgeCard.learning_status.in_(["new", "learning"])).all()
    }
    ids.update(not_mastered)
    return ids if ids else None


def _card_context(c: KnowledgeCard) -> str:
    """卡片内容 → 出题上下文（V6 带 detail）"""
    parts = [f"【卡片】{c.title} (ID:{c.id})"]
    if c.one_liner:
        parts.append(f"一句话理解：{c.one_liner}")
    if c.core_points and isinstance(c.core_points, list):
        pts = []
        for p in c.core_points:
            if isinstance(p, dict) and p.get("point"):
                detail = str(p.get("detail", "")).strip()
                pts.append(f"- {p['point']}" + (f"：{detail}" if detail else ""))
            elif isinstance(p, str):
                pts.append(f"- {p}")
        if pts:
            parts.append("核心要点：\n" + "\n".join(pts))
    if c.misconceptions and isinstance(c.misconceptions, list):
        for m in c.misconceptions:
            if isinstance(m, dict) and m.get("misconception"):
                parts.append(f"误区：{m['misconception']} → 正解：{m.get('correction', '')}")
    if c.quick_test and isinstance(c.quick_test, list):
        existing = []
        for t in c.quick_test:
            if isinstance(t, dict) and t.get("question"):
                existing.append(f"Q: {t['question']} A: {t.get('answer', '')}")
        if existing:
            parts.append("已有测试题：\n" + "\n".join(existing))
    return "\n".join(parts)


@router.post("/review/questions")
async def generate_review_questions(scope: ReviewScope, db: Session = Depends(get_db)):
    """V6: 基于用户选择的范围 + 模式生成 AI 复习题（智能题量）"""
    mode = scope.mode if scope.mode in VALID_MODES else "understand"
    guide = MODE_GUIDE[mode]

    cards = _resolve_cards(scope, db)

    if not cards:
        return {"questions": [], "message": "所选范围内暂无知识卡片"}

    # 智能题量：每卡 1-2 题，3-20 之间；显式传入则用传入值
    if scope.question_count is not None:
        qty = max(1, min(30, scope.question_count))
    else:
        qty = min(20, max(3, len(cards) * 2))

    # 收集卡片内容作为上下文
    context_parts = [_card_context(c) for c in cards]

    # AI 生成复习题（按模式给出题型与指令）
    allowed = guide["allowed_types"]
    user_content = f"""【复习模式】{guide['label']}
【题型偏好】{guide['type_hint']}
【硬约束：只允许以下题型】{", ".join(allowed)} —— 严禁出现其他题型
【出题要求】{guide['instruction']}

【知识内容】
{chr(10).join(context_parts)}

请生成 {qty} 道复习题，严格遵循以上模式与题型约束。
注意：judgment 题必须是判断题（陈述一句，让用户判断对错），question 字段直接给出待判断的陈述，answer 字段写明"对/错 + 简短理由"。"""

    messages = [
        {"role": "system", "content": REVIEW_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        result = await smart_json(messages, temperature=0.4)
    except Exception as e:
        logger.exception(f"复习题生成失败: {e}")
        # 降级：使用卡片已有的 quick_test
        questions = []
        for c in cards:
            if c.quick_test and isinstance(c.quick_test, list):
                for t in c.quick_test:
                    if isinstance(t, dict) and t.get("question"):
                        questions.append({
                            "type": "concept",
                            "question": t["question"],
                            "answer": t.get("answer", ""),
                            "card_id": c.id,
                            "card_title": c.title,
                            "difficulty": "medium",
                        })
                        if len(questions) >= qty:
                            break
            if len(questions) >= qty:
                break
        return {"questions": questions[:qty]}

    # 清洗结果：丢弃非法题型（PRD V3.0 模式硬约束）+ 透传 LLM 选项（V8）
    allowed = guide["allowed_types"]
    raw_questions = result.get("questions", []) or []
    questions = []
    for q in raw_questions:
        if not (isinstance(q, dict) and q.get("question")):
            continue
        qtype = str(q.get("type", "concept")).strip().lower()
        # 非法题型直接丢弃，避免 quick 模式混入 application 等题型
        if qtype not in allowed:
            logger.info(f"丢弃非法题型 {qtype}（模式={mode} 仅允许 {allowed}）：{q.get('question','')[:30]}")
            continue
        answer = str(q.get("answer", ""))
        item = {
            "type": qtype,
            "question": str(q["question"]),
            "answer": answer,
            "card_id": q.get("card_id"),
            "card_title": str(q.get("card_title", "")),
            "difficulty": str(q.get("difficulty", "medium")),
        }
        # V8: LLM 出的 4 选项（concept/application），校验 answer 在选项中否则兜底
        raw_options = q.get("options") or []
        if qtype in ("concept", "application") and isinstance(raw_options, list) and len(raw_options) >= 2:
            options = [str(o) for o in raw_options][:4]
            if answer and answer not in options:
                options = [answer] + options[:3]
            item["options"] = options
        questions.append(item)

    return {"questions": questions[:qty]}


# V7 错题本：简化遗忘曲线（间隔天数随错题次数递增）
WRONG_SCHEDULE = [1, 2, 4, 7]


def _wrong_interval(wrong_count: int) -> int:
    return WRONG_SCHEDULE[min(max(wrong_count, 1), len(WRONG_SCHEDULE)) - 1]


def _sync_wrong_questions(db: Session, submissions: list[AnswerSubmit]):
    """把答错的题写入错题本（独立于 AI 评分，评分失败也不丢错题）"""
    seen: set = set()  # 批内去重，防同会话重复题双计
    for s in submissions:
        if s.is_correct is None:
            continue  # 开放题跳过
        key = (s.card_id, s.question.strip())
        if key in seen:
            continue
        seen.add(key)

        row = (
            db.query(WrongQuestion)
            .filter(WrongQuestion.card_id == s.card_id, WrongQuestion.question == s.question.strip())
            .first()
        )
        if s.is_correct is False:
            if row:
                row.wrong_count += 1
                row.interval_days = _wrong_interval(row.wrong_count)
                row.last_reviewed_at = datetime.utcnow()
                row.mastered = False
            else:
                db.add(WrongQuestion(
                    user_id=1,
                    card_id=s.card_id,
                    question=s.question.strip(),
                    user_answer=s.user_answer,
                    correct_answer=s.correct_answer,
                    wrong_count=1,
                    interval_days=1,
                    last_reviewed_at=datetime.utcnow(),
                ))
        elif s.is_correct is True and row and not row.mastered:
            # 答对 → 清零并标记掌握
            row.wrong_count = 0
            row.mastered = True
            row.last_reviewed_at = datetime.utcnow()
    db.commit()


def _simple_correct_count(submissions: list[AnswerSubmit]) -> int:
    return sum(
        1 for s in submissions
        if s.user_answer.strip() and s.correct_answer.strip()
        and s.user_answer.strip() in s.correct_answer.strip()
    )


@router.post("/review/evaluate")
async def evaluate_answers(payload: EvaluatePayload, db: Session = Depends(get_db)):
    """V6: AI 评分 + 薄弱点分析 + 落库复习记录"""
    submissions = payload.submissions or []
    if not submissions:
        return {"score": 0, "feedback": "无答题记录", "weak_points": []}

    answers_text = []
    for i, s in enumerate(submissions, 1):
        answers_text.append(
            f"题目{i}：{s.question}\n用户答案：{s.user_answer}\n参考答案：{s.correct_answer}"
        )

    # V7: 错题本同步（本地判定，先于 AI 评分，互不依赖）
    try:
        _sync_wrong_questions(db, submissions)
    except Exception as e:
        logger.warning(f"错题本同步失败（不影响评分）: {e}")

    user_content = f"请评价以下{len(submissions)}道题的答题情况：\n\n" + "\n\n".join(answers_text)

    messages = [
        {"role": "system", "content": EVALUATION_PROMPT},
        {"role": "user", "content": user_content},
    ]

    result_data = None
    try:
        result = await smart_json(messages, temperature=0.3)
        result_data = {
            "score": int(result.get("score", 0)),
            "correctness": int(result.get("correctness", 0)),
            "completeness": int(result.get("completeness", 0)),
            "understanding": int(result.get("understanding", 0)),
            "feedback": str(result.get("feedback", "")),
            "weak_points": [str(w) for w in (result.get("weak_points", []) or [])],
            "total": len(submissions),
            "correct_count": _simple_correct_count(submissions),
        }
    except Exception as e:
        logger.exception(f"评分失败: {e}")
        # 降级：简单匹配
        correct_count = _simple_correct_count(submissions)
        total = len(submissions)
        score = round((correct_count / total) * 100) if total > 0 else 0
        result_data = {
            "score": score,
            "feedback": f"答对 {correct_count}/{total} 题",
            "weak_points": [],
            "total": total,
            "correct_count": correct_count,
        }

    # V6: 落库复习记录（成长页真实数据来源）
    try:
        card_ids = [s.card_id for s in submissions if s.card_id]
        attempt = ReviewAttempt(
            user_id=1,
            mode=payload.mode if payload.mode in VALID_MODES else "understand",
            scope_json=payload.scope or {"scope_type": "all"},
            total=len(submissions),
            correct_count=result_data["correct_count"],
            score=result_data["score"],
            weak_points_json=result_data["weak_points"],
        )
        if card_ids:
            attempt.scope_json = {**(payload.scope or {}), "card_ids": card_ids}
        db.add(attempt)
        db.commit()
        logger.info(f"复习记录已保存: score={result_data['score']}")
    except Exception as e:
        logger.warning(f"复习记录落库失败（不影响评分返回）: {e}")

    return result_data


@router.get("/review/wrong-questions")
def list_wrong_questions(due_only: bool = False, db: Session = Depends(get_db)):
    """V7 错题本：全部错题 / 仅到期（due_only=True，按遗忘曲线到期 + 未掌握）"""
    q = db.query(WrongQuestion).filter(WrongQuestion.mastered == False)  # noqa: E712
    if due_only:
        now = datetime.utcnow()
        due_ids = []
        for w in q.all():
            last = w.last_reviewed_at
            interval = w.interval_days or 1
            if last is None or last + timedelta(days=interval) <= now:
                due_ids.append(w.id)
        if not due_ids:
            return {"items": [], "total": 0, "due_count": 0, "mastered_count": 0}
        q = db.query(WrongQuestion).filter(WrongQuestion.id.in_(due_ids))

    rows = q.order_by(WrongQuestion.last_reviewed_at.is_(None).desc(),
                      WrongQuestion.created_at.desc()).all()
    mastered_count = (
        db.query(func.count(WrongQuestion.id))
        .filter(WrongQuestion.mastered == True)  # noqa: E712
        .scalar() or 0
    )
    due_total = (
        db.query(func.count(WrongQuestion.id))
        .filter(WrongQuestion.mastered == False)  # noqa: E712
        .scalar() or 0
    )
    items = []
    for w in rows:
        card_title = None
        if w.card_id:
            card = db.query(KnowledgeCard).get(w.card_id)
            if card and not card.deleted_at:
                card_title = card.title
        items.append({
            "id": w.id,
            "card_id": w.card_id,
            "card_title": card_title,
            "question": w.question,
            "user_answer": w.user_answer,
            "correct_answer": w.correct_answer,
            "wrong_count": w.wrong_count,
            "interval_days": w.interval_days,
            "last_reviewed_at": w.last_reviewed_at.isoformat() if w.last_reviewed_at else None,
            "mastered": w.mastered,
        })
    return {
        "items": items,
        "total": len(items),
        "due_count": due_total,
        "mastered_count": mastered_count,
    }


class WrongAnswerSubmit(BaseModel):
    is_correct: bool


@router.post("/review/wrong-questions/{wrong_id}/submit")
def submit_wrong_answer(wrong_id: int, payload: WrongAnswerSubmit, db: Session = Depends(get_db)):
    """V7 错题重考：答对清零掌握；答错次数+1 并重算遗忘曲线间隔"""
    w = db.query(WrongQuestion).get(wrong_id)
    if not w:
        raise HTTPException(404, "wrong question not found")

    if payload.is_correct:
        w.wrong_count = 0
        w.mastered = True
    else:
        w.wrong_count += 1
        w.interval_days = _wrong_interval(w.wrong_count)
        w.mastered = False
    w.last_reviewed_at = datetime.utcnow()
    db.commit(); db.refresh(w)
    return {
        "id": w.id,
        "wrong_count": w.wrong_count,
        "interval_days": w.interval_days,
        "mastered": w.mastered,
    }


@router.get("/review/weak-points")
def review_weak_points(db: Session = Depends(get_db)):
    """V6: 薄弱点汇总（来自真实答题评价）+ 学习状态分布"""
    attempts = (
        db.query(ReviewAttempt)
        .filter(ReviewAttempt.created_at >= datetime.utcnow() - timedelta(days=30))
        .all()
    )
    points: dict[str, dict] = {}
    for a in attempts:
        for w in (a.weak_points_json or []):
            w = str(w).strip()
            if not w:
                continue
            if w not in points:
                points[w] = {"point": w, "count": 0, "last_seen": None}
            points[w]["count"] += 1
            ts = a.created_at.isoformat() if a.created_at else None
            if points[w]["last_seen"] is None or (ts and ts > points[w]["last_seen"]):
                points[w]["last_seen"] = ts

    weak_points = sorted(points.values(), key=lambda x: (-x["count"], x["point"] or ""))

    status_rows = (
        db.query(KnowledgeCard.learning_status, func.count(KnowledgeCard.id))
        .filter(KnowledgeCard.deleted_at.is_(None))
        .group_by(KnowledgeCard.learning_status)
        .all()
    )
    status_distribution = {s or "new": c for s, c in status_rows}

    return {
        "weak_points": weak_points,
        "status_distribution": status_distribution,
    }


@router.get("/review/domains")
def review_domains(db: Session = Depends(get_db)):
    """兼容旧接口：可用于复习的领域列表 + 卡片数"""
    rows = (
        db.query(KnowledgeCard.domain, func.count(KnowledgeCard.id))
        .filter(KnowledgeCard.deleted_at.is_(None), KnowledgeCard.domain != "")
        .group_by(KnowledgeCard.domain)
        .all()
    )
    return [{"domain": d or "其他", "count": cnt} for d, cnt in rows]


@router.get("/review/today")
def review_today(db: Session = Depends(get_db)):
    """V6.3 今日复习队列（GitHub 复习产品模式：Anki 今日队列 / Readwise Daily Review）

    排序规则：
    1. 从未复习过 且 learning_status != mastered 的卡片（新知识，最优先）
    2. 上次复习超过 3 天的卡片（间隔复习）
    3. 近期低分（attempt score < 60）涉及的卡片
    每类内按 created_at 倒序，总上限 15 张。
    """
    # 1. 聚合每张卡的上次复习时间与最低分（来自 review_attempts）
    attempts = db.query(ReviewAttempt).order_by(ReviewAttempt.created_at.asc()).all()
    last_reviewed: dict[int, datetime] = {}
    low_score_ids: set[int] = set()
    for a in attempts:
        scope_json = a.scope_json or {}
        ids = scope_json.get("card_ids") or []
        if not ids and scope_json.get("scope_type") == "all":
            continue  # 全量复习无法归属到具体卡片
        for cid in ids:
            if a.created_at:
                last_reviewed[cid] = a.created_at
            if a.score is not None and a.score < 60:
                low_score_ids.add(cid)

    now = datetime.utcnow()
    three_days_ago = now - timedelta(days=3)

    cards = (
        db.query(KnowledgeCard)
        .filter(KnowledgeCard.deleted_at.is_(None))
        .order_by(KnowledgeCard.created_at.desc())
        .all()
    )

    queue = []
    seen = set()

    def add(card: KnowledgeCard, reason: str):
        if card.id in seen:
            return
        seen.add(card.id)
        last = last_reviewed.get(card.id)
        queue.append({
            "id": card.id,
            "title": card.title,
            "domain": card.domain or "",
            "space_id": card.space_id,
            "learning_status": card.learning_status or "new",
            "reason": reason,
            "last_reviewed_at": last.isoformat() if last else None,
        })

    # 优先级 1: 从未复习 + 未掌握
    for c in cards:
        if c.learning_status == "mastered":
            continue
        if c.id in last_reviewed:
            continue
        add(c, "新知识，还没复习过")
        if len(queue) >= 15:
            break
    # 优先级 2: 超过 3 天没复习
    if len(queue) < 15:
        for c in cards:
            last = last_reviewed.get(c.id)
            if not last or last >= three_days_ago:
                continue
            days = (now - last).days
            add(c, f"已 {days} 天没复习")
            if len(queue) >= 15:
                break
    # 优先级 3: 近期低分涉及的卡片
    if len(queue) < 15:
        for c in cards:
            if c.id not in low_score_ids:
                continue
            add(c, "上次答得不好，建议巩固")
            if len(queue) >= 15:
                break

    return {
        "queue": queue[:15],
        "total": len(queue[:15]),
    }
