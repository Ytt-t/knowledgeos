"""ORM 模型 — V3 对齐 PRD V3.0 / 架构 V2

主要变化（相对 V2）：
- knowledge_cards: 字段大改（title/ai_summary/keywords/domain/tags/is_favorite/is_archived/deleted_at）
- knowledge_sources: source_type 改 pdf/txt/markdown，status 状态机改 extracting/summarizing/classifying
- concept_relations: relation_type 枚举化 + similarity_score
- chat_sessions: 新增 scope_filter
- 新增 growth_snapshots 表
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean, Float,
    Enum as SAEnum
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nickname = Column(String(64), nullable=False, default="默认用户")
    # V8 账号资料
    email = Column(String(128), nullable=True)
    bio = Column(Text, nullable=True)
    signature = Column(String(256), nullable=True)   # 个性签名
    password_hash = Column(String(256), nullable=True)  # pbkdf2_hmac 盐$哈希
    avatar_path = Column(String(256), nullable=True)    # 头像文件路径
    banner_path = Column(String(256), nullable=True)    # 背景图文件路径
    created_at = Column(DateTime, default=datetime.utcnow)

    sources = relationship("KnowledgeSource", back_populates="user")
    cards = relationship("KnowledgeCard", back_populates="user")
    chat_sessions = relationship("ChatSession", back_populates="user")


class KnowledgeSource(Base):
    """知识来源：V4 多模态 — 视频/文档/图片

    source_type 枚举覆盖三种输入形态：
    - 文档: pdf / docx
    - 图片: image
    - 视频: bilibili_video / xiaohongshu_video / douyin_video
    """
    __tablename__ = "knowledge_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    source_type = Column(
        SAEnum("pdf", "docx", "txt", "image",
               "bilibili_video", "xiaohongshu_video", "douyin_video",
               name="source_type"),
        nullable=False,
    )
    platform = Column(String(32))  # 视频来源平台，便于统计和排查
    file_path = Column(String(512))
    source_url = Column(String(512))
    raw_text = Column(Text)

    # V4 状态机: pending → parsing → (去重检测) → summarizing → classifying → done/failed
    # V7: duplicate = 命中重复内容，等待用户决策（终态）
    status = Column(
        SAEnum("pending", "parsing", "summarizing", "classifying",
               "done", "failed", "duplicate", name="source_status"),
        default="pending", nullable=False,
    )
    error_message = Column(Text)
    thinking_text = Column(Text)  # V6.1: R1 思维链节选（捕获流程「思考过程」展示）

    # V7 去重
    content_md5 = Column(String(32), nullable=True)        # 归一化 raw_text 的 MD5
    duplicate_card_id = Column(Integer, nullable=True)     # 命中的已有卡片 id
    force_create = Column(Boolean, default=False)          # 用户选择「仍然新建」

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="sources")
    cards = relationship("KnowledgeCard", back_populates="source", cascade="all, delete-orphan")


class KnowledgeCard(Base):
    """知识卡片 V4.1 — Knowledge Card 2.0

    V4.1 升级为 AI知识蒸馏：
    - one_liner: 一句话理解核心概念
    - core_points: 核心知识点 [{point, importance: high/medium/low}]
    - knowledge_structure: 知识结构树 {主题: [子主题]}
    - importance: 整体重要等级 high/medium/low
    - misconceptions: 常见误区 [{misconception, correction}]
    - quick_test: 快速测试 [{question, answer}]
    - quality_score: AI质量评分 {completeness, coverage, accuracy, total}
    - summary_mode: 总结模式 study/work/research
    - user_feedback: 用户反馈 helpful/inaccurate/null
    V4 保留字段：
    - ai_summary: JSON {summary, key_points[], structure}（兼容旧卡片）
    """
    __tablename__ = "knowledge_cards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("knowledge_sources.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    title = Column(String(256), nullable=False)
    content_type = Column(
        SAEnum("video", "document", "image", name="content_type"),
        default="document", nullable=False,
    )
    ai_summary = Column(JSON)          # V4 兼容: {summary, key_points[], structure}

    # === V4.1 Knowledge Card 2.0 新增字段 ===
    one_liner = Column(Text)            # 一句话理解
    core_points = Column(JSON)          # [{point, importance}]
    knowledge_structure = Column(JSON)  # {主题: [子主题]}
    importance = Column(String(16), default=None)  # V6: 仅用户手动标记 high，AI 不再打标
    key_cases = Column(JSON)             # V5: [{scenario, application}]
    next_steps = Column(JSON)            # PRD V3.0 P0: 下一步学习建议 [str]
    misconceptions = Column(JSON)      # [{misconception, correction}]
    quick_test = Column(JSON)           # [{question, answer}]
    quality_score = Column(JSON)       # {completeness, coverage, accuracy, total}
    summary_mode = Column(String(16), default="study")  # study/work/research
    user_feedback = Column(String(16), nullable=True)    # helpful/inaccurate

    keywords = Column(JSON)             # []
    domain = Column(String(64), default="其他")
    tags = Column(JSON, default=list)   # []

    is_favorite = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    learning_status = Column(String(16), default="new")  # PRD V3.0: new | learning | mastered
    deleted_at = Column(DateTime, nullable=True)  # 软删除

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    source = relationship("KnowledgeSource", back_populates="cards")
    user = relationship("User", back_populates="cards")
    space = relationship("KnowledgeSpace", back_populates="cards")

    # V6: 用户自定义知识空间（PRD V3.0 取消 AI 强制分类）
    # 注意：旧库通过 ALTER TABLE 补列，物理上无 FK 约束（应用层保证），
    # 此处 ForeignKey 仅作 ORM 关联元数据；新库建表时会带上约束。
    space_id = Column(Integer, ForeignKey("knowledge_spaces.id"), nullable=True)
    suggested_space = Column(String(128), nullable=True)  # AI 建议的空间名，供确认面板


class KnowledgeSpace(Base):
    """V6 用户自定义知识空间（PRD V3.0：取消 AI 强制分类）"""
    __tablename__ = "knowledge_spaces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1)
    name = Column(String(128), nullable=False, unique=True)
    icon = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    cards = relationship("KnowledgeCard", back_populates="space")


class WrongQuestion(Base):
    """V7 AI 错题本：复习答错的题，按简化遗忘曲线安排重考"""
    __tablename__ = "wrong_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1)
    card_id = Column(Integer, nullable=True)  # 来源卡片（可能已删，可空）
    question = Column(Text, nullable=False)
    user_answer = Column(Text)                # 首次答错时的答案
    correct_answer = Column(Text, nullable=False)
    wrong_count = Column(Integer, default=1)
    interval_days = Column(Integer, default=1)
    last_reviewed_at = Column(DateTime, nullable=True)
    mastered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Podcast(Base):
    """V7 AI 学习播客（NotebookLM 式）：两位 AI 主持人对话讲解知识"""
    __tablename__ = "podcasts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1)
    title = Column(String(256), nullable=True)
    scope_json = Column(JSON)  # {space_id} | {card_ids}
    script_json = Column(JSON)  # [{speaker:"A"|"B", text}]
    status = Column(String(16), default="generating")  # generating | ready | failed
    audio_count = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReviewAttempt(Base):
    """V6 复习记录：真实学习数据（成长页/薄弱点分析共用）"""
    __tablename__ = "review_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1)
    mode = Column(String(16), nullable=False)  # understand|apply|interview|quick
    scope_json = Column(JSON)                  # {scope_type, space_id, card_ids}
    total = Column(Integer, default=0)
    correct_count = Column(Integer, default=0)
    score = Column(Integer, default=0)
    weak_points_json = Column(JSON)            # [str]
    created_at = Column(DateTime, default=datetime.utcnow)


class ConceptRelation(Base):
    """知识关联（P1 知识图谱）"""
    __tablename__ = "concept_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_card_id = Column(Integer, ForeignKey("knowledge_cards.id"), nullable=False)
    to_card_id = Column(Integer, ForeignKey("knowledge_cards.id"), nullable=False)
    relation_type = Column(
        SAEnum("same_domain", "same_space", "semantic_similar", "manual", name="relation_type"),
        default="semantic_similar",
    )
    similarity_score = Column(Float, default=0.0)


class EmbeddingsIndex(Base):
    """向量索引映射：实际向量在 faiss，这里存映射（V3 保留，当前用 vector_store 管理）"""
    __tablename__ = "embeddings_index"

    id = Column(Integer, primary_key=True, autoincrement=True)
    knowledge_card_id = Column(Integer, ForeignKey("knowledge_cards.id"), nullable=False)
    vector_id = Column(String(128), nullable=False)


class ChatSession(Base):
    """问答会话，V5 新增 is_favorite / updated_at 支持对话管理"""
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(128), default="新会话")
    scope_filter = Column(JSON)  # {type: "all"|"domain"|"tags"|"card_ids", value: ...}
    is_favorite = Column(Boolean, default=False)  # V5: 收藏对话
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(SAEnum("user", "assistant", name="msg_role"), nullable=False)
    content = Column(Text, nullable=False)
    cited_card_ids = Column(JSON)
    structured_answer = Column(JSON)  # V5: 结构化回答 {conclusion, core_points, source_knowledge, extended_thinking, action_advice}
    thinking_text = Column(Text)      # V6.1: AI 思考过程（R1 思维链节选）
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")


class GrowthSnapshot(Base):
    """知识成长统计快照（首页/成长中心/未来 Coach Agent 共用）"""
    __tablename__ = "growth_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    snapshot_date = Column(DateTime, default=datetime.utcnow)
    total_cards = Column(Integer, default=0)
    domain_distribution = Column(JSON)  # {domain: count}
    weak_domains = Column(JSON)          # [domain, ...]
