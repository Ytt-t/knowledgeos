"""数据库连接与会话管理"""
import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)

# SQLite 需要 check_same_thread=False 才能在 FastAPI 异步环境使用
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 依赖：每请求一个 session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _run_lightweight_migrations():
    """轻量级列迁移：create_all 不会给已存在的表添加新列，这里手动补齐。

    每次新增可空列时，在此登记一次 ALTER TABLE。失败时仅记日志，不阻断启动。
    """
    # (table, column, ddl_column_def)
    pending_columns = [
        # PRD V3.0 P0: 知识蒸馏「下一步学习建议」字段
        ("knowledge_cards", "next_steps", "JSON"),
        # V6: 用户自定义知识空间
        ("knowledge_cards", "space_id", "INTEGER"),
        ("knowledge_cards", "suggested_space", "VARCHAR(128)"),
        # V6.1: AI 思考过程展示
        ("knowledge_sources", "thinking_text", "TEXT"),
        ("chat_messages", "thinking_text", "TEXT"),
        # V7: 上传去重
        ("knowledge_sources", "content_md5", "VARCHAR(32)"),
        ("knowledge_sources", "duplicate_card_id", "INTEGER"),
        ("knowledge_sources", "force_create", "BOOLEAN"),
        # V8: 账号资料
        ("users", "email", "VARCHAR(128)"),
        ("users", "bio", "TEXT"),
        ("users", "signature", "VARCHAR(256)"),
        ("users", "password_hash", "VARCHAR(256)"),
        ("users", "avatar_path", "VARCHAR(256)"),
        ("users", "banner_path", "VARCHAR(256)"),
    ]

    try:
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
    except Exception as e:
        logger.warning(f"迁移检查失败（跳过）: {e}")
        return

    with engine.begin() as conn:
        for table, column, ddl in pending_columns:
            # 按表逐一检查列（V6.1 修复：之前只查 knowledge_cards，多表时误判）
            if table not in existing_tables:
                continue
            cols = {c["name"] for c in inspector.get_columns(table)}
            if column in cols:
                continue
            try:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN "{column}" {ddl}'))
                logger.info(f"迁移：{table}.{column} 列已添加")
            except Exception as e:
                logger.warning(f"迁移 {table}.{column} 失败（可能已存在）: {e}")


def _migrate_spaces():
    """V6：把已有非「其他」domain 转成知识空间并回填 space_id。幂等。

    - 「AI技术」这类有效领域 → 建同名空间 + 卡片回填 space_id
    - 「其他」是占位垃圾值 → 保持 space_id=NULL（未分类）
    """
    try:
        inspector = inspect(engine)
        if not inspector.has_table("knowledge_cards") or not inspector.has_table("knowledge_spaces"):
            return
        cols = {c["name"] for c in inspector.get_columns("knowledge_cards")}
        if "space_id" not in cols:
            return
    except Exception as e:
        logger.warning(f"空间迁移检查失败（跳过）: {e}")
        return

    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT DISTINCT domain FROM knowledge_cards "
            "WHERE domain IS NOT NULL AND domain != '' AND domain != '其他'"
        )).fetchall()
        for (name,) in rows:
            try:
                conn.execute(text(
                    "INSERT OR IGNORE INTO knowledge_spaces (user_id, name, created_at) "
                    "VALUES (1, :n, datetime('now'))"
                ), {"n": name})
                conn.execute(text(
                    "UPDATE knowledge_cards SET space_id = "
                    "(SELECT id FROM knowledge_spaces WHERE name = :n) "
                    "WHERE domain = :n AND space_id IS NULL"
                ), {"n": name})
                logger.info(f"迁移：domain「{name}」→ 知识空间已建并回填")
            except Exception as e:
                logger.warning(f"迁移 domain「{name}」失败: {e}")


def init_db():
    """建表，应用启动时调用"""
    from app.models import models  # noqa: F401  确保 models 被导入
    Base.metadata.create_all(bind=engine)
    _run_lightweight_migrations()
    _migrate_spaces()
