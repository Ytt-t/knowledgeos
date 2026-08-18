"""FastAPI 主入口 — 单端口部署：/api 提供接口，/ 提供前端静态文件 + SPA 回退"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
# StaticFiles 未使用（改用显式路由托管，避免 mount 拦截 /api 前缀）
# from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.database import init_db
from app.api import sources, cards, chat, stats, review, spaces, podcasts, users

logger = logging.getLogger(__name__)

# 前端构建产物路径：支持部署时把 frontend/dist 拷贝到 backend 下也能跑
_FRONTEND_DIST = (
    Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
)
_FRONTEND_INDEX = _FRONTEND_DIST / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：建表 + 迁移 + 初始化默认用户
    init_db()
    _ensure_default_user()
    _recover_interrupted_sources()
    # V6.3.2: 预热向量库（embedding 模型加载 1-2 分钟，一次性）。
    # 不预热的话第一次问答/入库时会同步加载阻塞事件循环，表现为"页面没反应"。
    _prewarm_vector_store()
    yield


def _prewarm_vector_store():
    """启动时预热向量库：加载 embedding 模型到内存。失败不阻断启动。"""
    try:
        from app.services.vector_store import get_store
        store = get_store()
        logger.info(f"向量库预热完成，现有 {len(store._id_map)} 条向量")
    except Exception as e:
        logger.warning(f"向量库预热失败（不影响启动，首次使用时会重试）: {e}")


def _recover_interrupted_sources():
    """V6: 启动时把上次中断（如 --reload 杀进程）的 source 置 failed，避免永久卡在处理中
    （duplicate 是等待用户决策的终态，不参与恢复）"""
    from app.database import SessionLocal
    from app.models.models import KnowledgeSource
    db = SessionLocal()
    try:
        n = (
            db.query(KnowledgeSource)
            .filter(KnowledgeSource.status.in_(["pending", "parsing", "summarizing", "classifying"]))
            .update({"status": "failed", "error_message": "服务重启导致处理中断，请重新提交"},
                    synchronize_session=False)
        )
        if n:
            db.commit()
            logger.info(f"启动恢复：{n} 个中断的 source 已置 failed")
    finally:
        db.close()


def _ensure_default_user():
    """MVP 阶段单用户，先固定一个默认用户 id=1"""
    from app.database import SessionLocal
    from app.models.models import User
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.id == 1).first():
            db.add(User(id=1, nickname="默认用户"))
            db.commit()
    finally:
        db.close()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
    default_response_class=JSONResponse,
)

# 单端口部署：允许任意 Origin（内网穿透每次域名不同；本地 demo 场景安全性优先放行）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== 接口路由（必须先注册，优先匹配）=====
app.include_router(sources.router, prefix="/api", tags=["sources"])
app.include_router(cards.router, prefix="/api", tags=["cards"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(stats.router, prefix="/api", tags=["stats"])
app.include_router(review.router, prefix="/api", tags=["review"])
app.include_router(spaces.router, prefix="/api", tags=["spaces"])
app.include_router(podcasts.router, prefix="/api", tags=["podcasts"])
app.include_router(users.router, prefix="/api", tags=["users"])


# ===== 前端静态文件 + SPA 回退（兜底，不匹配 /api 时走这里）=====
# 注意：这里不使用 app.mount("/", StaticFiles, html=True) —— 因为它会在路由查找前就拦截，
# 导致 /api 路径命中 static 404。改为显式判断前缀的方式托管静态资源。
_STATIC_EXT = {
    ".js", ".css", ".html", ".map", ".json", ".svg", ".png", ".jpg", ".jpeg",
    ".gif", ".ico", ".woff", ".woff2", ".ttf", ".eot", ".webp", ".mp3", ".pdf",
}


@app.get("/api")
@app.get("/api/health")
def api_health():
    return {"app": settings.APP_NAME, "status": "ok"}


# SPA History 路由兜底 + 静态文件分发
# 优先级：
#   1. /api/* — 交由已注册的接口路由（本函数不处理）
#   2. 带静态扩展名的路径 — 从 frontend/dist 读文件
#   3. 其余路径（/assistant、/review 等）— 返回 index.html，让前端路由接管
@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str, request: Request):
    if request.url.path.startswith("/api") or request.url.path.startswith("/docs") \
            or request.url.path.startswith("/openapi") or request.url.path.startswith("/redoc"):
        # 交给 FastAPI 默认 404/文档处理
        return JSONResponse(
            {"detail": "Not Found", "path": request.url.path},
            status_code=404,
        )

    if not _FRONTEND_DIST.is_dir():
        # 前端未构建
        return {
            "app": settings.APP_NAME,
            "status": "ok",
            "hint": "前端未构建，请执行 `cd frontend && npm run build`",
        }

    # 静态文件：先判断扩展名
    ext = Path(request.url.path).suffix.lower()
    if ext in _STATIC_EXT:
        # /assets/xxx.js 等路径直接映射到 dist 下
        target = (_FRONTEND_DIST / request.url.path.lstrip("/")).resolve()
        try:
            target.relative_to(_FRONTEND_DIST.resolve())  # 防路径穿越
        except ValueError:
            return JSONResponse({"detail": "Bad Request"}, status_code=400)
        if target.is_file():
            return FileResponse(str(target))
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    # SPA：其余所有路由返回 index.html
    if _FRONTEND_INDEX.is_file():
        return FileResponse(str(_FRONTEND_INDEX))

    return {
        "app": settings.APP_NAME,
        "status": "ok",
        "hint": "前端未构建，请执行 `cd frontend && npm run build`",
    }
