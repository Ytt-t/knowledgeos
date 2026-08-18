"""Retriever Agent — V6 RAG 问答，深度结构化输出 + scope 范围过滤

V6 变化：
1. 回答深度化：删除"结论≤50字/每条≤30字"硬限制，
   conclusion 改 2-4 句完整段落，key_points 每条带 detail 解释，action_advice 2-4 条数组
2. 检索增强：top_k 3→6，阈值 0.2→0.15，context 拼装带 detail/key_cases
3. 调用 smart_json（R1 深度思考 → V3 转 JSON），失败降级纯文本
4. scope 增加 space 类型（用户自定义知识空间）

PRD V3.0 P0：AI Copilot 三种模式
- qa (知识问答)：基于个人知识库回答，引用来源
- connect (知识连接)：发现不同知识之间的关系
- learn (学习辅助)：生成学习路线、面试题、实践任务
"""
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import KnowledgeCard
from app.services.deepseek import chat, smart_json
from app.services.vector_store import get_store

logger = logging.getLogger(__name__)

# ===== V9 混合检索：关键词通道（中文召回率提升）=====
_ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9_]{2,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")

# 用户问“总结/最近/概览”等意图词且检索未命中时，回退到最近知识
_RECENT_INTENT_RE = re.compile(r"(总结|最近|概览|梳理|归纳|复习|学了什么|学到了什么|有什么知识|学的内容)")


def _cjk_bigrams(text: str) -> set[str]:
    """中文连续字符的二元组集合（无分词依赖的轻量相似信号）"""
    grams: set[str] = set()
    for run in _CJK_RE.findall(text or ""):
        for i in range(len(run) - 1):
            grams.add(run[i : i + 2])
    return grams


def _searchable_text(card: KnowledgeCard) -> str:
    """卡片可检索文本：标题 + 关键词 + 标签 + 要点 + 摘要"""
    parts = [card.title or ""]
    parts.extend(card.keywords or [])
    parts.extend(card.tags or [])
    if isinstance(card.core_points, list):
        for p in card.core_points:
            if isinstance(p, dict) and p.get("point"):
                parts.append(str(p["point"]))
            elif isinstance(p, str):
                parts.append(p)
    ai = card.ai_summary or {}
    if isinstance(ai, dict) and ai.get("summary"):
        parts.append(str(ai["summary"]))
    if card.domain:
        parts.append(card.domain)
    return "\n".join(parts)


def _keyword_search(
    db: Session, question: str, allowed_ids: set[int], top_k: int
) -> list[tuple[int, float]]:
    """关键词召回：英文/数字 token + 卡片关键词/标签双向匹配 + CJK 二元组重叠。

    中文 embedding（all-MiniLM-L6-v2）相似度普遍偏低，单独靠向量阈值会漏召回；
    关键词通道给高置信命中打高分，与向量分数取并集后排序。
    """
    ascii_tokens = {t.lower() for t in _ASCII_TOKEN_RE.findall(question)}
    q_bigrams = _cjk_bigrams(question)
    cards = (
        db.query(KnowledgeCard)
        .filter(
            KnowledgeCard.id.in_(allowed_ids),
            KnowledgeCard.deleted_at.is_(None),
        )
        .all()
    )
    q_lower = question.lower()
    scored: list[tuple[int, float]] = []
    for c in cards:
        text = _searchable_text(c).lower()
        score = 0.0
        # 1) 英文/数字 token 命中（如 RAG、DeepSeek）
        if ascii_tokens:
            hit = sum(1 for t in ascii_tokens if t in text)
            if hit:
                score = max(score, 0.9 if hit >= 2 else 0.7)
        # 2) 卡片关键词/标签出现在问题里（AI 生成的关键词最接近用户表述）
        for kw in list(c.keywords or []) + list(c.tags or []):
            kw_s = str(kw).strip()
            if len(kw_s) >= 2 and kw_s.lower() in q_lower:
                score = max(score, 1.0)
        # 3) 标题与问题互相包含
        title = (c.title or "").strip()
        if title:
            if len(title) >= 3 and title.lower() in q_lower:
                score = max(score, 0.95)
            elif len(q_lower) >= 4 and q_lower in title.lower():
                score = max(score, 0.85)
        # 4) CJK 二元组重叠 >= 2
        if q_bigrams:
            overlap = len(q_bigrams & _cjk_bigrams(text))
            if overlap >= 2:
                score = max(score, 0.65)
        if score > 0:
            scored.append((c.id, score))
    scored.sort(key=lambda x: -x[1])
    return scored[:top_k]


# ===== 模式定义（PRD V3.0 P0 + V8）=====
MODE_FREE = "free"        # V8: 自由问答（DeepSeek 原味大脑，知识库自动加分）
MODE_KB = "kb"            # V8: 知识库问答（严格 RAG）
MODE_QA = "qa"            # 兼容旧值（同知识库问答）
MODE_CONNECT = "connect"  # 知识连接（前端已下线，接口保留）
MODE_LEARN = "learn"      # 学习辅助（前端已下线，接口保留）
VALID_MODES = {MODE_FREE, MODE_KB, MODE_QA, MODE_CONNECT, MODE_LEARN}

# 统一结构化 schema（三种模式共用，回答深度要求一致）
SCHEMA_HINT = """{
  "conclusion": "2-4句话的完整结论段落，把问题的答案讲清楚，不是一句话概括",
  "key_points": [
    {"point": "要点标题", "detail": "该要点的详细解释（2-3句），含机制/例子/数据"}
  ],
  "core_points": ["旧格式兼容：与 key_points 相同的要点标题列表"],
  "source_knowledge": [
    {"title": "来源知识标题", "point": "该知识中的关键内容（1-2句）"}
  ],
  "extended_thinking": "基于已有知识的延伸思考（2-4句），指出更深层的联系或下一步方向",
  "action_advice": ["具体可执行的行动建议1", "行动建议2", "行动建议3"]
}"""

SYSTEM_PROMPT = f"""你是基于用户个人知识库的 AI 学习助手（Personal Knowledge Assistant）。

你的核心定位：
- 不是聊天机器人，而是基于用户已有知识的深度回答引擎
- 回答必须深入、完整、有信息量 —— 用户的标准是"比通用 AI 助手更有用"，因为你能结合他自己的知识库

回答要求：
1. 只能基于【知识库资料】回答，不要编造资料中不存在的内容；但可以基于资料做合理的解释、归纳和延伸。
2. 如果知识库资料无法回答，明确说"你的知识库中暂无相关内容"，不要硬答。
3. 回答要深入：每个要点都要有解释，不能只给标题；结论要讲清"是什么+为什么+怎么做"。
4. 用中文回答。
5. 可综合多张知识卡片内容，给出连贯回答。
6. 不要在回答里提"知识卡片"这个词，直接用内容回答。
7. 在 conclusion 和 key_points.detail 中，对关键概念、核心结论使用 **加粗** 强调（如 **RAG** 的核心是**先检索再生成**），帮助用户抓住重点。

输出格式（严格遵循 JSON 结构）：
{SCHEMA_HINT}
"""

USER_TEMPLATE = """【知识库资料】
{context}

【用户问题】
{question}

请基于以上知识库资料深度回答用户问题，严格按 JSON 格式输出。"""


# ===== V8 自由问答模式：DeepSeek 原味大脑，知识库自动加分 =====
FREE_SYSTEM_PROMPT = f"""你是 AI 助手，具备最聪明的通用大模型能力（深度思考版）。

你的核心定位：
- 直接、深入、高质量地回答用户的**任何问题**，像最优秀的通用 AI 一样
- 用户有一个个人知识库。若提供了【知识库资料】，且与问题相关，优先引用其中的内容并结合你的知识做深化；**资料没有的内容，用你自己的知识正常回答，不要被资料限制**
- 知识库是你的加分项，不是枷锁

回答要求：
1. 回答深入完整：讲清"是什么+为什么+怎么做"，每个要点有解释，不能只给标题
2. 用中文回答
3. 在 conclusion 和 key_points.detail 中，对关键概念、核心结论使用 **加粗** 强调
4. 不编造；如果引用了知识库内容，source_knowledge 里标注来源标题

输出格式（严格遵循 JSON 结构）：
{SCHEMA_HINT}
"""

FREE_USER_TEMPLATE = """【用户问题】
{question}

{context_block}

请深度回答用户问题，严格按 JSON 格式输出。"""


# ===== 知识连接模式 Prompt（PRD：发现不同知识之间的关系）=====
CONNECT_SYSTEM_PROMPT = f"""你是 KnowledgeOS 的知识连接发现 Agent。任务：基于用户已有的多张知识卡片，发现它们之间潜在的关联、对比、互补关系。

你的核心价值：
- 找出表面不相关但其实存在深层联系的知识
- 对比相似概念的差异
- 发现知识之间的互补与前置/后置关系
- 每个关系点都要讲清"为什么相关、相关到什么程度、如何组合使用"

输出格式（严格遵循 JSON 结构）：
{SCHEMA_HINT}

要求：
- 只基于提供的知识库资料发现关系，不要编造资料外的内容
- 关系描述要具体（例：A 是 B 的前置基础 / A 与 B 互补 / A 是 B 的特例），并解释为什么
- 在 conclusion 和 key_points.detail 中，对关键概念使用 **加粗** 强调
- 用中文输出
"""

CONNECT_USER_TEMPLATE = """【用户问题/关注点】
{question}

【知识库资料】
{context}

请发现这些知识之间的关联关系，严格按 JSON 格式输出。"""


# ===== 学习辅助模式 Prompt（PRD：学习路线、面试题、实践任务）=====
LEARN_SYSTEM_PROMPT = f"""你是 KnowledgeOS 的学习辅助 Agent。任务：基于用户知识库，生成个性化的学习路线、面试题和实践任务。

输出格式（严格遵循 JSON 结构）：
{SCHEMA_HINT}

要求：
- 学习路线要基于用户已有知识向外延伸，循序渐进，每步给出具体学习内容和方法
- 面试题要能真正检验理解程度，附简短参考思路
- 实践任务要具体可执行（能动手做的东西）
- 在 conclusion 和 key_points.detail 中，对关键概念使用 **加粗** 强调
- 用中文输出
"""

LEARN_USER_TEMPLATE = """【用户学习需求】
{question}

【已有知识库资料】
{context}

请生成学习路线 + 面试题/实践任务，严格按 JSON 格式输出。"""


def _scope_filter_cards(db: Session, scope: Optional[dict]) -> set[int]:
    """根据 scope 过滤出可用的 card_ids"""
    if not scope or scope.get("type") == "all":
        cards = db.query(KnowledgeCard.id).filter(KnowledgeCard.deleted_at.is_(None)).all()
        return {c[0] for c in cards}

    stype = scope.get("type")
    value = scope.get("value")

    q = db.query(KnowledgeCard).filter(KnowledgeCard.deleted_at.is_(None))

    if stype == "space" and value:
        q = q.filter(KnowledgeCard.space_id == value)
    elif stype == "domain" and value:
        q = q.filter(KnowledgeCard.domain == value)
    elif stype == "tags" and value:
        for tag in value:
            q = q.filter(KnowledgeCard.tags.like(f'%"{tag}"%'))
    elif stype == "card_ids" and value:
        q = q.filter(KnowledgeCard.id.in_(value))
    else:
        cards = db.query(KnowledgeCard.id).filter(KnowledgeCard.deleted_at.is_(None)).all()
        return {c[0] for c in cards}

    return {c.id for c in q.all()}


def _card_context(card: KnowledgeCard, idx: int) -> str:
    """把一张卡片拼成检索上下文（V6：带 detail 和案例的完整内容）"""
    parts = [f"【资料{idx}】{card.title}"]

    if card.one_liner:
        parts.append(f"一句话理解：{card.one_liner}")

    if card.core_points and isinstance(card.core_points, list):
        pts = []
        for p in card.core_points:
            if isinstance(p, dict) and p.get("point"):
                detail = str(p.get("detail", "")).strip()
                pts.append(f"- {p['point']}" + (f"：{detail}" if detail else ""))
            elif isinstance(p, str):
                pts.append(f"- {p}")
        if pts:
            parts.append("核心要点：\n" + "\n".join(pts))

    # 兼容旧卡片 ai_summary
    ai = card.ai_summary or {}
    if isinstance(ai, dict):
        if not card.one_liner and ai.get("summary"):
            parts.append(f"摘要：{ai['summary']}")
        if not card.core_points and ai.get("key_points"):
            parts.append("核心要点：\n- " + "\n- ".join(ai["key_points"]))
        if ai.get("structure") and isinstance(ai["structure"], dict):
            for k, subs in ai["structure"].items():
                subs_str = ", ".join(subs) if isinstance(subs, list) else str(subs)
                parts.append(f"知识结构-{k}: {subs_str}")

    if card.key_cases and isinstance(card.key_cases, list):
        cases = []
        for c in card.key_cases:
            if isinstance(c, dict) and c.get("scenario"):
                cases.append(f"- {c['scenario']}：{c.get('application', '')}")
        if cases:
            parts.append("应用案例：\n" + "\n".join(cases))

    if card.misconceptions and isinstance(card.misconceptions, list):
        for m in card.misconceptions:
            if isinstance(m, dict) and m.get("misconception"):
                parts.append(f"常见误区：{m['misconception']} → 正解：{m.get('correction', '')}")

    if card.next_steps and isinstance(card.next_steps, list):
        steps = [s for s in card.next_steps if isinstance(s, str)] if card.next_steps else []
        if steps:
            parts.append("下一步学习建议：\n- " + "\n- ".join(steps))

    if card.keywords:
        parts.append(f"关键词: {', '.join(card.keywords)}")

    return "\n".join(parts)


async def _chat_free(question: str, on_thinking=None) -> dict:
    """V8.1 自由问答 = 纯 DeepSeek 原味：
    无 system 提示词限制、不检索知识库、不结构化 JSON、纯文本自由回答。
    用 R1 深度思考（保留思考过程展示），失败降级 V3。
    """
    thinking_parts: list = []

    def _cap(t: str):
        thinking_parts.append(t)
        if on_thinking:
            on_thinking(t)

    # 零限制：直接发用户消息，没有任何 system 约束
    messages = [{"role": "user", "content": question}]

    try:
        text_answer = await chat(
            messages,
            model=settings.LLM_REASONER_MODEL,
            temperature=None,
            max_tokens=settings.LLM_QA_MAX_TOKENS,
            timeout=settings.LLM_REASONER_TIMEOUT,
            retries=1,
            capture_reasoning=_cap,
        )
    except Exception as e:
        logger.warning(f"R1 自由问答失败，降级 V3: {e}")
        text_answer = await chat(
            messages,
            model=settings.LLM_CHAT_MODEL,
            max_tokens=settings.LLM_QA_MAX_TOKENS,
            retries=1,
        )

    return {
        "answer": text_answer,
        "structured_answer": None,
        "cited_card_ids": [],
        "thinking_text": ("\n".join(thinking_parts))[:2000] or None,
    }


async def answer(
    question: str,
    db: Session,
    *,
    scope: Optional[dict] = None,
    top_k: int = 6,
    score_threshold: float = 0.15,
    mode: str = MODE_FREE,
    on_thinking=None,
) -> dict:
    """基于用户知识库回答问题（V6 深度结构化输出 + PRD 三模式）

    Args:
        scope: {type: "all"|"space"|"domain"|"tags"|"card_ids", value: ...}
        mode: "qa" | "connect" | "learn" (PRD V3.0 P0)
        on_thinking: 可选回调，收到 R1 思维链时触发（AI 思考过程展示）

    Returns:
        {
            answer: str (纯文本兼容),
            structured_answer: dict (V6 结构化),
            cited_card_ids: list[int],
            thinking_text: Optional[str]  (V6.1: AI 思考过程)
        }
    """
    if mode not in VALID_MODES:
        mode = MODE_FREE
    if mode == MODE_QA:
        mode = MODE_KB  # 旧值兼容

    thinking_parts: list = []

    # 1. scope 过滤出可用卡片集合
    allowed_ids = _scope_filter_cards(db, scope)

    # 2. 混合检索（V9: 向量 + 关键词双通道，中文召回率大幅提升）
    store = get_store()
    merged: dict[int, float] = {}
    for cid, score in store.query(question, top_k=top_k * 3):
        if cid in allowed_ids and score >= score_threshold:
            merged[cid] = max(merged.get(cid, 0), score)
    try:
        for cid, score in _keyword_search(db, question, allowed_ids, top_k * 2):
            merged[cid] = max(merged.get(cid, 0), score)
    except Exception as e:
        logger.warning(f"关键词检索失败（不影响向量检索）: {e}")
    hits = sorted(merged.items(), key=lambda x: -x[1])[:top_k]
    logger.info(f"RAG 检索: mode={mode}, scope={scope}, hits={len(hits)}")

    # V8.1 自由问答 = 纯 DeepSeek 原味：不检索知识库、无系统限制、纯文本输出
    if mode == MODE_FREE:
        return await _chat_free(question, on_thinking)

    # 知识库问答：未命中时先看是否属于“总结/最近”类意图，回退到最近知识，否则明确告知
    if not hits:
        if allowed_ids and _RECENT_INTENT_RE.search(question):
            recent_cards = (
                db.query(KnowledgeCard)
                .filter(
                    KnowledgeCard.id.in_(allowed_ids),
                    KnowledgeCard.deleted_at.is_(None),
                )
                .order_by(KnowledgeCard.created_at.desc())
                .limit(3)
                .all()
            )
            if recent_cards:
                hits = [(c.id, 0.5) for c in recent_cards]
                logger.info(f"RAG 检索未命中，回退最近 {len(recent_cards)} 张卡片（意图：{question[:30]}）")
        if not hits:
            return {
                "answer": "你的知识库里暂时没有相关的内容。换个问法，或者先去首页捕获一点资料再回来问我～",
                "structured_answer": None,
                "cited_card_ids": [],
                "thinking_text": None,
            }

    # 3. 拉取卡片详情，拼 context
    cited_ids = []
    context_parts = []
    source_titles = []
    for cid, score in hits:
        card = db.query(KnowledgeCard).get(cid)
        if not card or card.deleted_at:
            continue
        cited_ids.append(cid)
        source_titles.append({"id": cid, "title": card.title})
        context_parts.append(_card_context(card, len(cited_ids)))

    if not context_parts:
        return {
            "answer": "所选知识范围内暂无相关内容。",
            "structured_answer": None,
            "cited_card_ids": [],
            "thinking_text": None,
        }

    # 4. 按模式选择 Prompt（PRD V3.0 P0 三模式）
    if mode == MODE_CONNECT:
        sys_prompt, user_tpl = CONNECT_SYSTEM_PROMPT, CONNECT_USER_TEMPLATE
    elif mode == MODE_LEARN:
        sys_prompt, user_tpl = LEARN_SYSTEM_PROMPT, LEARN_USER_TEMPLATE
    else:
        sys_prompt, user_tpl = SYSTEM_PROMPT, USER_TEMPLATE

    messages = [
        {"role": "system", "content": sys_prompt},
        {
            "role": "user",
            "content": user_tpl.format(
                context="\n\n".join(context_parts), question=question
            ),
        },
    ]

    def _on_thinking(t: str):
        thinking_parts.append(t)

    try:
        result = await smart_json(
            messages,
            temperature=0.3,
            output_max_tokens=settings.LLM_QA_MAX_TOKENS,
            on_thinking=_on_thinking,
        )
    except Exception as e:
        logger.warning(f"结构化回答失败，降级为纯文本: {e}")
        # 降级：纯文本回答
        fallback_messages = [
            {"role": "system", "content": "你是基于用户知识库的AI学习助手。请基于知识库资料深入回答问题，用中文。"},
            {"role": "user", "content": f"知识库：{chr(10).join(context_parts)}\n\n问题：{question}"},
        ]
        text_answer = await chat(fallback_messages, temperature=0.3)
        return {
            "answer": text_answer,
            "structured_answer": None,
            "cited_card_ids": cited_ids,
            "thinking_text": ("\n".join(thinking_parts))[:2000] or None,
        }

    # 5. 清洗结构化结果
    structured = _clean_structured(result, source_titles)
    structured["mode"] = mode

    # 6. 生成纯文本兼容版本
    text_answer = _structured_to_text(structured)

    return {
        "answer": text_answer,
        "structured_answer": structured,
        "cited_card_ids": cited_ids,
        "thinking_text": ("\n".join(thinking_parts))[:2000] or None,
    }


def _clean_structured(result: dict, source_titles: list) -> dict:
    """清洗 LLM 返回的结构化结果（V6 深度 schema）"""
    # conclusion
    conclusion = str(result.get("conclusion", "")).strip()
    if not conclusion:
        conclusion = "暂无法基于知识库直接回答此问题。"

    # key_points: [{point, detail}]（V6 深度要点）
    raw_key = result.get("key_points", []) or []
    key_points = []
    for p in raw_key:
        if isinstance(p, dict) and p.get("point"):
            key_points.append({
                "point": str(p["point"]).strip(),
                "detail": str(p.get("detail", "")).strip(),
            })
        elif isinstance(p, str) and p.strip():
            key_points.append({"point": p.strip(), "detail": ""})

    # core_points: 旧格式兼容（字符串列表）
    raw_points = result.get("core_points", []) or []
    core_points = []
    for p in raw_points:
        if isinstance(p, str) and p.strip():
            core_points.append(p.strip())
        elif isinstance(p, dict) and p.get("point"):
            core_points.append(str(p["point"]).strip())

    # 若两者都没有 → 从 key_points 兜底
    if not key_points and core_points:
        key_points = [{"point": p, "detail": ""} for p in core_points]
    if not core_points and key_points:
        core_points = [k["point"] for k in key_points]
    if not key_points:
        key_points = [{"point": "知识库中相关信息有限", "detail": ""}]
        core_points = ["知识库中相关信息有限"]

    # source_knowledge
    raw_sources = result.get("source_knowledge", []) or []
    source_knowledge = []
    for s in raw_sources:
        if isinstance(s, dict):
            source_knowledge.append({
                "title": str(s.get("title", "")).strip(),
                "point": str(s.get("point", "")).strip(),
            })
        elif isinstance(s, str):
            source_knowledge.append({"title": "", "point": s.strip()})
    # 如果 LLM 没有返回来源，用实际检索到的卡片
    if not source_knowledge:
        source_knowledge = [{"title": t["title"], "point": ""} for t in source_titles]

    # extended_thinking
    extended = str(result.get("extended_thinking", "")).strip()
    if not extended:
        extended = "建议深入学习相关主题的更多资料。"

    # action_advice（V6: 2-4 条数组）
    raw_advice = result.get("action_advice", []) or []
    advice = []
    if isinstance(raw_advice, list):
        for a in raw_advice:
            if isinstance(a, str) and a.strip():
                advice.append(a.strip())
            elif isinstance(a, dict) and a.get("advice"):
                advice.append(str(a["advice"]).strip())
    else:
        advice = [str(raw_advice).strip()] if str(raw_advice).strip() else []
    if not advice:
        advice = ["把上面的知识点用自己的话复述一遍，检验是否真正理解。"]

    return {
        "conclusion": conclusion,
        "key_points": key_points[:6],
        "core_points": core_points[:6],
        "source_knowledge": source_knowledge,
        "extended_thinking": extended,
        "action_advice": advice[:4],
    }


def _structured_to_text(s: dict) -> str:
    """将结构化回答转为纯文本（兼容旧消息格式）"""
    lines = [f"## 结论\n{s['conclusion']}", "", "## 核心观点"]
    for kp in s.get("key_points", []):
        if isinstance(kp, dict) and kp.get("point"):
            lines.append(f"- {kp['point']}")
            if kp.get("detail"):
                lines.append(f"  {kp['detail']}")
        elif isinstance(kp, str):
            lines.append(f"- {kp}")
    lines.append("")
    if s["source_knowledge"]:
        lines.append("## 来源知识")
        for sk in s["source_knowledge"]:
            title = f"【{sk['title']}】" if sk["title"] else ""
            lines.append(f"- {title}{sk['point']}")
        lines.append("")
    lines.append(f"## 延伸思考\n{s['extended_thinking']}")
    lines.append("")
    lines.append("## 行动建议")
    for a in s["action_advice"]:
        lines.append(f"- {a}")
    return "\n".join(lines)
