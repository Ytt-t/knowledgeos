"""AI 学习播客（NotebookLM 式）API 路由

异步生成：POST 建行立即返回 → BackgroundTasks 后台写脚本 + 逐段 TTS → 前端轮询
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import get_db, SessionLocal
from app.models.models import Podcast, KnowledgeCard
from app.agents.podcast_agent import generate_script
from app.agents.qa import _scope_filter_cards, _card_context
from app.services.tts import synthesize_segment

router = APIRouter()
logger = logging.getLogger(__name__)


class PodcastCreate(BaseModel):
    scope: dict  # {space_id: int} | {card_ids: [int]} | {type:"all"}


def _db_factory():
    return SessionLocal()


def _resolve_cards(db: Session, scope: dict) -> list[KnowledgeCard]:
    """按 scope 解析卡片集合（复用 qa 的过滤逻辑）"""
    allowed = _scope_filter_cards(db, scope)
    if not allowed:
        return []
    return (
        db.query(KnowledgeCard)
        .filter(KnowledgeCard.id.in_(allowed), KnowledgeCard.deleted_at.is_(None))
        .order_by(KnowledgeCard.created_at.desc())
        .all()
    )


async def _generate_podcast(podcast_id: int):
    """后台任务：写脚本 → 落库 ready → 逐段 TTS（音频是附加，失败降级纯文字）"""
    db = _db_factory()
    try:
        p = db.query(Podcast).get(podcast_id)
        if not p:
            return

        cards = _resolve_cards(db, p.scope_json or {})
        if not cards:
            p.status = "failed"
            p.error_message = "所选范围内没有知识卡片"
            db.commit()
            return

        context = "\n\n".join(_card_context(c, i + 1) for i, c in enumerate(cards))

        # 1. 写脚本（R1 深度 → 轻任务模型转 JSON）
        result = await generate_script(context)
        p.title = result["title"]
        p.script_json = result["segments"]
        p.status = "ready"
        db.commit()
        logger.info(f"[podcast {podcast_id}] 脚本完成，{len(result['segments'])} 段")

        # 2. 逐段 TTS（失败跳过，audio_count 增量上报；段间延迟防微软限流）
        audio_dir = settings.PODCAST_AUDIO_DIR / str(podcast_id)
        audio_dir.mkdir(parents=True, exist_ok=True)
        for i, seg in enumerate(result["segments"]):
            if i > 0:
                await asyncio.sleep(0.8)  # 限流保护：连续请求会被微软 TTS 断开
            ok = await synthesize_segment(seg["text"], seg["speaker"], audio_dir / f"seg_{i:03d}.mp3")
            if ok:
                p.audio_count = i + 1
                db.commit()
        logger.info(f"[podcast {podcast_id}] TTS 完成 {p.audio_count}/{len(result['segments'])} 段")
    except Exception as e:
        logger.exception(f"[podcast {podcast_id}] 生成失败")
        p = db.query(Podcast).get(podcast_id)
        if p:
            p.status = "failed"
            p.error_message = str(e)[:300]
            db.commit()
    finally:
        db.close()


@router.post("/podcasts")
def create_podcast(payload: PodcastCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """创建播客生成任务（异步，立即返回 id）"""
    p = Podcast(user_id=1, scope_json=payload.scope, status="generating")
    db.add(p); db.commit(); db.refresh(p)
    background_tasks.add_task(_generate_podcast, p.id)
    return {"id": p.id, "status": "generating"}


@router.get("/podcasts")
def list_podcasts(db: Session = Depends(get_db)):
    """播客历史列表"""
    rows = (
        db.query(Podcast)
        .order_by(Podcast.created_at.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "id": p.id,
            "title": p.title or ("生成中…" if p.status == "generating" else "生成失败"),
            "status": p.status,
            "audio_count": p.audio_count,
            "error_message": p.error_message,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in rows
    ]


@router.post("/podcasts/{podcast_id}/retry")
def retry_podcast(
    podcast_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """失败播客重试（复用原 scope，重置脚本与音频）"""
    p = db.query(Podcast).get(podcast_id)
    if not p:
        raise HTTPException(404, "podcast not found")
    if p.status != "failed":
        raise HTTPException(409, f"当前状态（{p.status}）不允许重试")
    p.status = "generating"
    p.error_message = None
    p.script_json = None
    p.audio_count = 0
    db.commit(); db.refresh(p)
    background_tasks.add_task(_generate_podcast, p.id)
    return {"id": p.id, "status": "generating"}


@router.delete("/podcasts/{podcast_id}")
def delete_podcast(podcast_id: int, db: Session = Depends(get_db)):
    """删除播客（含音频目录）"""
    p = db.query(Podcast).get(podcast_id)
    if not p:
        raise HTTPException(404, "podcast not found")
    db.delete(p)
    db.commit()
    audio_dir = settings.PODCAST_AUDIO_DIR / str(podcast_id)
    if audio_dir.exists():
        import shutil
        shutil.rmtree(audio_dir, ignore_errors=True)
    return {"ok": True, "id": podcast_id}


@router.get("/podcasts/{podcast_id}")
def get_podcast(podcast_id: int, db: Session = Depends(get_db)):
    """播客详情：脚本 + 音频段 URL"""
    p = db.query(Podcast).get(podcast_id)
    if not p:
        raise HTTPException(404, "podcast not found")
    segments = p.script_json or []
    audio_urls = []
    for i in range(len(segments)):
        if i < (p.audio_count or 0):
            audio_urls.append(f"/api/podcasts/{podcast_id}/audio/{i}")
        else:
            audio_urls.append(None)
    return {
        "id": p.id,
        "title": p.title,
        "status": p.status,
        "error_message": p.error_message,
        "segments": segments,
        "audio_urls": audio_urls,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@router.get("/podcasts/{podcast_id}/audio/{seg}")
def get_podcast_audio(podcast_id: int, seg: int):
    """音频段文件（seg 为 int，防路径穿越）"""
    if seg < 0 or seg > 100:
        raise HTTPException(400, "invalid segment")
    path = settings.PODCAST_AUDIO_DIR / str(podcast_id) / f"seg_{seg:03d}.mp3"
    if not path.exists():
        raise HTTPException(404, "audio not found")
    return FileResponse(str(path), media_type="audio/mpeg")
