"""/api/sources 路由 — V4 双端点：/url（视频链接）+ /file（文件上传）"""
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models.models import KnowledgeSource, KnowledgeCard, User
from app.schemas import UrlSourceCreate
from app.agents.orchestrator import run_pipeline
from app.services.video_agent import detect_platform

router = APIRouter()
logger = logging.getLogger(__name__)

# 文件上传支持类型
EXT_TO_TYPE = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "docx",
    ".txt": "txt",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
}
MAX_SIZE = 20 * 1024 * 1024


def _db_factory():
    return SessionLocal()


def _get_default_user(db: Session) -> User:
    u = db.query(User).filter(User.id == 1).first()
    if not u:
        u = User(id=1, nickname="默认用户")
        db.add(u); db.commit(); db.refresh(u)
    return u


@router.post("/sources/url")
async def create_url_source(
    payload: UrlSourceCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """提交视频链接（B站/小红书/抖音）"""
    try:
        platform = detect_platform(payload.url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    user = _get_default_user(db)
    source = KnowledgeSource(
        user_id=user.id,
        source_type=platform,
        platform=platform,
        source_url=payload.url,
        status="pending",
    )
    db.add(source); db.commit(); db.refresh(source)

    background_tasks.add_task(run_pipeline, source.id, _db_factory)
    return {"id": source.id, "status": source.status, "source_type": source.source_type}


@router.post("/sources/file")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传文件（PDF/Word/图片）"""
    if not file.filename:
        raise HTTPException(400, "缺少文件名")

    ext = Path(file.filename).suffix.lower()
    if ext not in EXT_TO_TYPE:
        raise HTTPException(400, f"仅支持 PDF/Word/图片，收到 {ext}")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(400, f"文件过大（>{MAX_SIZE // 1024 // 1024}MB）")

    saved_name = f"{uuid.uuid4().hex}{ext}"
    saved_path = Path("uploads") / saved_name
    saved_path.parent.mkdir(parents=True, exist_ok=True)
    with open(saved_path, "wb") as f:
        f.write(content)
    logger.info(f"文件已保存: {saved_path} ({EXT_TO_TYPE[ext]})")

    user = _get_default_user(db)
    source = KnowledgeSource(
        user_id=user.id,
        source_type=EXT_TO_TYPE[ext],
        file_path=str(saved_path),
        status="pending",
    )
    db.add(source); db.commit(); db.refresh(source)

    background_tasks.add_task(run_pipeline, source.id, _db_factory)
    return {"id": source.id, "status": source.status, "source_type": source.source_type}


@router.get("/sources/active")
def list_active_sources(db: Session = Depends(get_db)):
    """V8: 处理中/待决策的 source —— 前端切回首页时恢复进度条与弹窗
    （必须定义在 /sources/{source_id} 之前，否则 active 被当作 source_id）"""
    rows = (
        db.query(KnowledgeSource)
        .filter(KnowledgeSource.status.in_(
            ["pending", "parsing", "summarizing", "classifying", "duplicate", "failed"]))
        .order_by(KnowledgeSource.created_at.desc())
        .all()
    )
    result = []
    for s in rows:
        item = {
            "id": s.id,
            "source_type": s.source_type,
            "status": s.status,
            "thinking_text": s.thinking_text,
            "error_message": s.error_message,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        if s.status == "duplicate" and s.duplicate_card_id:
            dup_card = db.query(KnowledgeCard).get(s.duplicate_card_id)
            item["duplicate_card_id"] = s.duplicate_card_id
            item["duplicate_card_title"] = dup_card.title if dup_card and not dup_card.deleted_at else None
        result.append(item)
    return result


@router.get("/sources/{source_id}")
def get_source(source_id: int, db: Session = Depends(get_db)):
    s = db.query(KnowledgeSource).get(source_id)
    if not s:
        raise HTTPException(404, "source not found")
    # V6: 返回生成的卡片 id，前端确认保存面板用
    card = (
        db.query(KnowledgeCard)
        .filter(KnowledgeCard.source_id == source_id, KnowledgeCard.deleted_at.is_(None))
        .order_by(KnowledgeCard.id.asc())
        .first()
    )
    # V7: 重复内容的已有卡片信息（duplicate 弹窗文案）
    dup_title = None
    if s.duplicate_card_id:
        dup_card = db.query(KnowledgeCard).get(s.duplicate_card_id)
        if dup_card and not dup_card.deleted_at:
            dup_title = dup_card.title
    return {
        "id": s.id,
        "source_type": s.source_type,
        "platform": s.platform,
        "status": s.status,
        "error_message": s.error_message,
        "card_id": card.id if card else None,
        "thinking_text": s.thinking_text,  # V6.1: AI 思考过程（确认面板展示）
        "duplicate_card_id": s.duplicate_card_id,
        "duplicate_card_title": dup_title,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.post("/sources/{source_id}/retry")
def retry_source(
    source_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """V9: 失败来源重试。有 raw_text 时跳过解析（省一次抓取/OCR），无则重跑全链路。"""
    s = db.query(KnowledgeSource).get(source_id)
    if not s:
        raise HTTPException(404, "source not found")
    if s.status != "failed":
        raise HTTPException(409, f"当前状态（{s.status}）不允许重试")
    s.status = "pending"
    s.error_message = None
    s.thinking_text = None
    db.commit(); db.refresh(s)
    background_tasks.add_task(
        run_pipeline,
        s.id,
        _db_factory,
        skip_parsing=bool(s.raw_text and s.raw_text.strip()),
        skip_dedup=bool(s.force_create),
    )
    return {"id": s.id, "status": s.status}


class ContinuePayload(BaseModel):
    action: str  # "create_new" | "discard"


@router.post("/sources/{source_id}/continue")
def continue_source(
    source_id: int,
    payload: ContinuePayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """V7: duplicate 状态下用户决策——仍然新建 / 放弃"""
    s = db.query(KnowledgeSource).get(source_id)
    if not s:
        raise HTTPException(404, "source not found")
    if s.status != "duplicate":
        raise HTTPException(409, "当前状态不允许继续")

    if payload.action == "discard":
        db.delete(s)  # 无卡片引用，硬删安全
        db.commit()
        return {"ok": True, "action": "discard"}

    if payload.action == "create_new":
        # 先置位再调度（幂等：重复点击被 409 拦截）
        s.status = "summarizing"
        s.force_create = True
        db.commit()
        background_tasks.add_task(
            run_pipeline, s.id, _db_factory, skip_parsing=True, skip_dedup=True
        )
        return {"ok": True, "action": "create_new", "status": "summarizing"}

    raise HTTPException(400, "action 必须是 create_new 或 discard")


@router.get("/sources")
def list_sources(limit: int = 50, db: Session = Depends(get_db)):
    return (
        db.query(KnowledgeSource)
        .order_by(KnowledgeSource.created_at.desc())
        .limit(limit)
        .all()
    )
