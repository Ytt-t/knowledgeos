"""Pydantic Schema — V4 多模态"""
from datetime import datetime
from typing import Literal, Optional, Any
from pydantic import BaseModel, Field


# ===== Source =====
class UrlSourceCreate(BaseModel):
    """提交视频链接（B站/小红书/抖音）"""
    url: str = Field(..., min_length=1)


class SourceOut(BaseModel):
    id: int
    source_type: str
    platform: Optional[str]
    file_path: Optional[str]
    source_url: Optional[str]
    status: str
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SourceDetailOut(SourceOut):
    cards: list["CardOut"] = []

    class Config:
        from_attributes = True


# ===== Card =====
class CardOut(BaseModel):
    id: int
    source_id: int
    title: str
    content_type: Optional[str] = "document"
    ai_summary: Optional[Any]
    # V4.1 Card 2.0 新字段
    one_liner: Optional[str] = None
    core_points: Optional[Any] = None
    knowledge_structure: Optional[Any] = None
    importance: Optional[str] = None  # V6: AI 不再自动打标，仅用户手动设置
    space_id: Optional[int] = None    # V6: 用户自定义知识空间
    suggested_space: Optional[str] = None
    key_cases: Optional[Any] = None
    next_steps: Optional[Any] = None  # PRD V3.0 P0: 下一步学习建议 [str]
    misconceptions: Optional[Any] = None
    quick_test: Optional[Any] = None
    quality_score: Optional[Any] = None
    summary_mode: Optional[str] = "study"
    user_feedback: Optional[str] = None
    # V4 兼容字段
    keywords: Optional[Any]
    domain: Optional[str]
    tags: Optional[Any]
    is_favorite: bool
    is_archived: bool
    learning_status: Optional[str] = "new"  # PRD V3.0: new | learning | mastered
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CardDetailOut(CardOut):
    """V4.1 Card 2.0 详情：来源信息 + 关联卡片"""
    related_cards: list[CardOut] = []
    source_platform: Optional[str] = None
    source_url: Optional[str] = None
    raw_text: Optional[str] = None


class CardUpdate(BaseModel):
    """PATCH /api/cards/{id} 的可编辑字段"""
    title: Optional[str] = None
    domain: Optional[str] = None
    tags: Optional[list[str]] = None
    is_favorite: Optional[bool] = None
    is_archived: Optional[bool] = None
    learning_status: Optional[str] = None  # PRD V3.0: new | learning | mastered
    space_id: Optional[int] = None          # V6: 移动到知识空间
    importance: Optional[str] = None        # V6: 用户手动标重要（None=清除标记）


# ===== Spaces (V6) =====
class SpaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    icon: Optional[str] = None


class SpaceUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None


# ===== Chat =====
class ScopeFilter(BaseModel):
    type: Literal["all", "space", "domain", "tags", "card_ids"] = "all"
    value: Optional[Any] = None  # space=int, domain=str, tags=[str], card_ids=[int]


class ChatSessionCreate(BaseModel):
    title: Optional[str] = "新会话"
    scope: Optional[ScopeFilter] = None


class ChatSessionUpdate(BaseModel):
    """V5: 对话管理 — 重命名 / 收藏"""
    title: Optional[str] = None
    is_favorite: Optional[bool] = None


class ChatSessionOut(BaseModel):
    id: int
    title: str
    scope_filter: Optional[Any]
    is_favorite: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatMessageCreate(BaseModel):
    content: str = Field(..., min_length=1)
    mode: Optional[str] = "qa"  # PRD V3.0 P0: qa | connect | learn


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    cited_card_ids: Optional[list[int]]
    structured_answer: Optional[Any] = None  # V5: 结构化回答
    thinking_text: Optional[str] = None      # V6.1: AI 思考过程
    created_at: datetime

    class Config:
        from_attributes = True


# ===== Stats / Growth =====
class GrowthOverviewOut(BaseModel):
    total_cards: int
    total_sources: int
    by_type: dict[str, int]
    domain_distribution: dict[str, int]
    recent_7_days: list[dict[str, Any]]


SourceDetailOut.model_rebuild()
CardDetailOut.model_rebuild()
