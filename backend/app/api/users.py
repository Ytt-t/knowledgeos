"""API 路由 — V8 账号系统（单用户 user_id=1，本地单机无登录墙）"""
import hashlib
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import get_db
from app.models.models import User, KnowledgeCard, ReviewAttempt

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB


def _get_user(db: Session) -> User:
    u = db.query(User).filter(User.id == 1).first()
    if not u:
        u = User(id=1, nickname="默认用户")
        db.add(u); db.commit(); db.refresh(u)
    return u


def _hash_password(pwd: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"), bytes.fromhex(salt), 100_000).hex()
    return f"{salt}${digest}"


def _verify_password(pwd: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
        calc = hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"), bytes.fromhex(salt), 100_000).hex()
        return calc == digest
    except Exception:
        return False


def _ts_url(path: str, filename: str) -> str:
    """带时间戳的图片 URL（防浏览器缓存）"""
    if not path or not Path(path).exists():
        return ""
    mtime = int(Path(path).stat().st_mtime)
    return f"/api/users/me/{filename}?ts={mtime}"


class UserUpdate(BaseModel):
    nickname: str | None = None
    email: str | None = None
    bio: str | None = None
    signature: str | None = None


class PasswordUpdate(BaseModel):
    current_password: str | None = None
    new_password: str


@router.get("/users/me")
def get_me(db: Session = Depends(get_db)):
    u = _get_user(db)
    return {
        "id": u.id,
        "nickname": u.nickname,
        "email": u.email or "",
        "bio": u.bio or "",
        "signature": u.signature or "",
        "has_password": bool(u.password_hash),
        "avatar_url": _ts_url(u.avatar_path, "avatar") or None,
        "banner_url": _ts_url(u.banner_path, "banner") or None,
        "total_cards": db.query(KnowledgeCard).filter(KnowledgeCard.deleted_at.is_(None)).count(),
        "review_count": db.query(ReviewAttempt).count(),
    }


@router.put("/users/me")
def update_me(payload: UserUpdate, db: Session = Depends(get_db)):
    u = _get_user(db)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        if v is not None:
            setattr(u, k, str(v).strip()[:512] if k in ("email", "bio", "signature") else str(v).strip()[:64])
    db.commit(); db.refresh(u)
    return get_me(db)


@router.post("/users/me/password")
def set_password(payload: PasswordUpdate, db: Session = Depends(get_db)):
    u = _get_user(db)
    new_pwd = payload.new_password
    if not new_pwd or len(new_pwd) < 4:
        raise HTTPException(400, "密码至少 4 位")
    # 已设置过密码 → 必须验证旧密码
    if u.password_hash:
        if not payload.current_password or not _verify_password(payload.current_password, u.password_hash):
            raise HTTPException(400, "当前密码不正确")
    u.password_hash = _hash_password(new_pwd)
    db.commit()
    return {"ok": True, "has_password": True}


def _save_image(file: UploadFile, kind: str, uid: int) -> str:
    content = file.file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(400, "图片不能超过 5MB")
    if not (file.filename or "").lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        raise HTTPException(400, "仅支持 PNG/JPG/WebP")
    ext = Path(file.filename).suffix.lower()
    out = settings.UPLOAD_DIR / f"{kind}_{uid}_{uuid.uuid4().hex[:8]}{ext}"
    # 清掉旧的同类型图片
    for old in settings.UPLOAD_DIR.glob(f"{kind}_{uid}_*"):
        try:
            old.unlink()
        except Exception:
            pass
    out.write_bytes(content)
    return str(out)


@router.post("/users/me/avatar")
def upload_avatar(file: UploadFile = File(...), db: Session = Depends(get_db)):
    u = _get_user(db)
    u.avatar_path = _save_image(file, "avatar", u.id)
    db.commit()
    return {"ok": True, "avatar_url": _ts_url(u.avatar_path, "avatar")}


@router.post("/users/me/banner")
def upload_banner(file: UploadFile = File(...), db: Session = Depends(get_db)):
    u = _get_user(db)
    u.banner_path = _save_image(file, "banner", u.id)
    db.commit()
    return {"ok": True, "banner_url": _ts_url(u.banner_path, "banner")}


@router.get("/users/me/avatar")
def get_avatar(db: Session = Depends(get_db)):
    u = _get_user(db)
    if not u.avatar_path or not Path(u.avatar_path).exists():
        raise HTTPException(404, "avatar not found")
    return FileResponse(u.avatar_path, media_type="image/png")


@router.get("/users/me/banner")
def get_banner(db: Session = Depends(get_db)):
    u = _get_user(db)
    if not u.banner_path or not Path(u.banner_path).exists():
        raise HTTPException(404, "banner not found")
    return FileResponse(u.banner_path, media_type="image/png")
