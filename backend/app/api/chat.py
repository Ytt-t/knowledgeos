"""/api/chat 路由 — V5 结构化回答 + 对话管理"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import get_db, SessionLocal
from app.models.models import ChatSession, ChatMessage, User, KnowledgeCard
from app.schemas import (
    ChatSessionCreate, ChatSessionOut, ChatSessionUpdate,
    ChatMessageCreate, ChatMessageOut,
)
from app.agents.qa import answer

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_default_user(db: Session) -> User:
    u = db.query(User).filter(User.id == 1).first()
    if not u:
        u = User(id=1, nickname="默认用户")
        db.add(u); db.commit(); db.refresh(u)
    return u


# ===== Session CRUD =====
@router.post("/chat/sessions", response_model=ChatSessionOut)
def create_session(payload: ChatSessionCreate, db: Session = Depends(get_db)):
    s = ChatSession(
        user_id=_get_default_user(db).id,
        title=payload.title or "新会话",
        scope_filter=payload.scope.model_dump() if payload.scope else None,
    )
    db.add(s); db.commit(); db.refresh(s)
    return s


@router.get("/chat/sessions", response_model=list[ChatSessionOut])
def list_sessions(db: Session = Depends(get_db)):
    return db.query(ChatSession).order_by(ChatSession.created_at.desc()).all()


@router.patch("/chat/sessions/{session_id}", response_model=ChatSessionOut)
def update_session(session_id: int, payload: ChatSessionUpdate, db: Session = Depends(get_db)):
    """V5: 重命名对话 / 收藏对话"""
    s = db.query(ChatSession).get(session_id)
    if not s:
        raise HTTPException(404, "session not found")

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(s, k, v)
    db.commit(); db.refresh(s)
    return s


@router.delete("/chat/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db)):
    """V5: 删除对话（含所有消息）"""
    s = db.query(ChatSession).get(session_id)
    if not s:
        raise HTTPException(404, "session not found")
    db.delete(s)
    db.commit()
    return {"ok": True, "id": session_id}


@router.delete("/chat/sessions")
def clear_all_sessions(db: Session = Depends(get_db)):
    """V5: 清空所有对话历史"""
    db.query(ChatSession).delete()
    db.commit()
    return {"ok": True, "cleared": True}


# ===== Messages =====
@router.get("/chat/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
def list_messages(session_id: int, db: Session = Depends(get_db)):
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )


@router.post("/chat/sessions/{session_id}/messages", response_model=ChatMessageOut)
async def send_message(
    session_id: int,
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
):
    """发送问题，返回 AI 结构化回答 + 引用卡片 + 思考过程；新会话自动生成标题"""
    session = db.query(ChatSession).get(session_id)
    if not session:
        raise HTTPException(404, "session not found")

    user_msg = ChatMessage(session_id=session_id, role="user", content=payload.content)
    db.add(user_msg); db.commit(); db.refresh(user_msg)

    thinking_buf: list[str] = []
    try:
        result = await answer(
            payload.content, db,
            scope=session.scope_filter,
            mode=payload.mode or "qa",
            on_thinking=lambda t: thinking_buf.append(t),
        )
    except Exception as e:
        logger.exception(f"RAG 问答失败: {e}")
        result = {
            "answer": f"问答失败：{e}",
            "structured_answer": None,
            "cited_card_ids": [],
            "thinking_text": None,
        }

    reply = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=result["answer"],
        cited_card_ids=result["cited_card_ids"],
        structured_answer=result.get("structured_answer"),
        thinking_text=result.get("thinking_text"),
    )
    db.add(reply); db.commit(); db.refresh(reply)

    # V6.1: 新会话自动生成标题（跟用户问的内容相关，方便找历史记录）
    if session.title == "新会话":
        session.title = await _auto_title(payload.content, result.get("answer") or "")
        db.commit()

    return reply


# ===== V9 流式问答（SSE）=====
_STREAM_FREE_SYSTEM = (
    "你是 KnowledgeOS 里的 AI 搭子，一个年轻、直接、有点幽默的 AI 助手。\n"
    "说话风格：\n"
    "- 像懂行的朋友，不端着、不官腔、不啰嗦\n"
    "- 回答准确，不编造；不确定就明说\n"
    "- 重点用 **加粗** 强调，方便扫读\n"
    "- 可以偶尔用 1 个以内的 emoji 或网络用语调节气氛（也可以不用）\n"
    "- 长度跟着问题走：简单问题短答，复杂问题分点讲清"
)

_STREAM_KB_SYSTEM = (
    "你是 KnowledgeOS 的私人知识助手，回答必须和用户自己的知识库强绑定。\n"
    "硬规则（违反任何一条都算失败）：\n"
    "- 只能使用【知识库资料】里的内容作答；资料里没有的，第一句就直说“我的知识库里还没存这个”，不要用你自己的通用知识补全\n"
    "- 严禁把通用知识包装成“你知识库里的内容”——宁可承认不知道，也不能假装有\n"
    "- 答案开头一句话给结论，然后分点；每一条要点都必须在括号里标注来源，格式：要点内容（来自《卡片标题》）\n"
    "- 关键处用 **加粗**，用中文，讲透即可不注水"
)


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@router.post("/chat/sessions/{session_id}/stream")
async def stream_message(session_id: int, payload: ChatMessageCreate):
    """V9: 流式问答（SSE）。
    free = 轻快闲聊（deepseek-chat 流式）
    kb = 知识库问答（混合检索 + 引用，流式输出）
    """
    from app.agents.qa import (
        _scope_filter_cards, _keyword_search, _card_context, _RECENT_INTENT_RE,
    )
    from app.services.vector_store import get_store
    from app.services.deepseek import chat_stream

    mode = (payload.mode or "free").lower()
    if mode in ("qa", "kb"):
        mode = "kb"

    async def event_stream():
        db = SessionLocal()
        try:
            session = db.query(ChatSession).get(session_id)
            if not session:
                yield _sse({"type": "error", "message": "会话不存在，请刷新页面"})
                return

            user_msg = ChatMessage(
                session_id=session_id, role="user", content=payload.content
            )
            db.add(user_msg); db.commit()

            cited_ids: list[int] = []
            system_prompt = _STREAM_FREE_SYSTEM
            user_content = payload.content

            if mode == "kb":
                allowed_ids = _scope_filter_cards(db, session.scope_filter)
                store = get_store()
                merged: dict[int, float] = {}
                for cid, score in store.query(payload.content, top_k=18):
                    if cid in allowed_ids and score >= 0.10:
                        merged[cid] = max(merged.get(cid, 0), score)
                try:
                    for cid, score in _keyword_search(db, payload.content, allowed_ids, 12):
                        merged[cid] = max(merged.get(cid, 0), score)
                except Exception as e:
                    logger.warning(f"关键词检索失败: {e}")

                hits = sorted(merged.items(), key=lambda x: -x[1])[:6]
                if not hits and allowed_ids and _RECENT_INTENT_RE.search(payload.content):
                    recent = (
                        db.query(KnowledgeCard)
                        .filter(
                            KnowledgeCard.id.in_(allowed_ids),
                            KnowledgeCard.deleted_at.is_(None),
                        )
                        .order_by(KnowledgeCard.created_at.desc())
                        .limit(3)
                        .all()
                    )
                    if recent:
                        hits = [(c.id, 0.5) for c in recent]

                if not hits:
                    answer_text = "你的知识库里暂时没有相关的内容。换个问法，或者先去首页捕获一点资料再回来问我～"
                    reply = ChatMessage(
                        session_id=session_id, role="assistant", content=answer_text,
                        cited_card_ids=None,
                    )
                    db.add(reply); db.commit()
                    yield _sse({"type": "done", "message": {
                        "id": reply.id, "role": "assistant", "content": reply.content,
                        "cited_card_ids": [], "structured_answer": None,
                        "thinking_text": None,
                        "created_at": reply.created_at.isoformat() if reply.created_at else None,
                    }})
                    return

                cited_ids = [cid for cid, _ in hits]
                context_parts: list[str] = []
                citation_cards = []
                for cid, _score in hits:
                    card = db.query(KnowledgeCard).get(cid)
                    if not card or card.deleted_at:
                        continue
                    context_parts.append(_card_context(card, len(context_parts) + 1))
                    citation_cards.append({
                        "id": card.id,
                        "title": card.title,
                        "one_liner": card.one_liner or "",
                        "domain": card.domain or "",
                    })
                if not context_parts:
                    answer_text = "知识库暂时没有可引用的内容。"
                    reply = ChatMessage(
                        session_id=session_id, role="assistant", content=answer_text,
                        cited_card_ids=None,
                    )
                    db.add(reply); db.commit()
                    yield _sse({"type": "done", "message": {
                        "id": reply.id, "role": "assistant", "content": reply.content,
                        "cited_card_ids": [], "structured_answer": None,
                        "thinking_text": None,
                        "created_at": reply.created_at.isoformat() if reply.created_at else None,
                    }})
                    return
                yield _sse({"type": "citations", "cards": citation_cards})
                system_prompt = _STREAM_KB_SYSTEM
                user_content = (
                    "【知识库资料】\n"
                    + "\n\n".join(context_parts)
                    + "\n\n【用户问题】\n"
                    + payload.content
                )

            # 最近 12 条消息作为上下文（去掉刚写入的当前问题，最后统一拼 user_content）
            history_rows = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(12)
                .all()
            )
            history = [
                {"role": m.role, "content": m.content}
                for m in reversed(history_rows)
                if m.role in ("user", "assistant")
            ]
            if (
                history
                and history[-1].get("role") == "user"
                and history[-1].get("content") == payload.content
            ):
                history = history[:-1]
            messages = [{"role": "system", "content": system_prompt}] + history
            messages.append({"role": "user", "content": user_content})

            full: list[str] = []
            try:
                async for chunk in chat_stream(
                    messages,
                    model=settings.LLM_CHAT_MODEL,
                    max_tokens=settings.LLM_QA_MAX_TOKENS,
                ):
                    full.append(chunk)
                    yield _sse({"type": "delta", "text": chunk})
            except Exception as e:
                logger.exception(f"流式问答失败: {e}")
                yield _sse({"type": "error", "message": f"回答失败：{e}"})
                return

            answer_text = "".join(full).strip()
            if not answer_text:
                answer_text = "抱歉，这次我没想好怎么回答，换个问法试试？"

            reply = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=answer_text,
                cited_card_ids=cited_ids or None,
            )
            db.add(reply); db.commit()

            if session.title == "新会话":
                session.title = await _auto_title(payload.content, answer_text)
                db.commit()

            yield _sse({"type": "done", "message": {
                "id": reply.id, "role": "assistant", "content": reply.content,
                "cited_card_ids": reply.cited_card_ids or [],
                "structured_answer": None, "thinking_text": None,
                "created_at": reply.created_at.isoformat() if reply.created_at else None,
            }})
        except Exception as e:
            logger.exception(f"stream_message 异常: {e}")
            yield _sse({"type": "error", "message": f"出错了：{e}"})
        finally:
            db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _auto_title(question: str, answer_text: str) -> str:
    """基于用户问题和 AI 回答生成会话标题（V3 轻任务，失败回退截断问题）"""
    from app.core.config import settings
    from app.services.deepseek import chat
    try:
        title = await chat(
            [
                {"role": "system", "content": "你是会话标题生成器。根据用户问题和 AI 回答，生成 3-12 个中文字的对话标题，概括本次对话主题。只输出标题本身，不要引号、标点或任何前缀。"},
                {"role": "user", "content": f"问题：{question}\n\n回答摘要：{(answer_text or '')[:200]}".strip()},
            ],
            model=settings.LLM_CHAT_MODEL,
            temperature=0.3,
            max_tokens=30,
            retries=1,
            timeout=30.0,
        )
        t = title.strip().strip('"\'「」《》').strip()
        if t:
            return t[:15]
    except Exception as e:
        logger.warning(f"自动标题生成失败，回退截断: {e}")
    q = question.strip()
    return q[:20] + ("…" if len(q) > 20 else "")


@router.get("/chat/cited-cards/{card_id}")
def get_cited_card(card_id: int, db: Session = Depends(get_db)):
    c = db.query(KnowledgeCard).get(card_id)
    if not c or c.deleted_at:
        raise HTTPException(404, "card not found")
    ai = c.ai_summary or {}
    return {
        "id": c.id,
        "title": c.title,
        "summary": ai.get("summary", "") if isinstance(ai, dict) else "",
        "one_liner": c.one_liner or "",
        "domain": c.domain,
        "source_id": c.source_id,
    }
