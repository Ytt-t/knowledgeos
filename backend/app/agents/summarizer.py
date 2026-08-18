"""Knowledge Distillation Agent — V6 知识蒸馏（深度版）

V6 变化（对齐 PRD V3.0「重构AI输出质量」）：
- summary: 200-400 字完整摘要，讲清「是什么/为什么重要/怎么用/常见坑」
- core_points: 3-6 条，每条 {point, detail}，detail 是 2-3 句带解释的深度内容
- 删除顶层 importance 输出 —— 重要性由用户自己决定，AI 不再打标
- next_steps: 2-4 条「具体行动 + 资源方向」，禁止泛泛而谈
- 调用 smart_json（R1 深度思考 → V3 转 JSON）

输出 Knowledge Card 2.0（对齐 PRD V3.0 五要素）：
- one_liner: 一句话理解核心概念
- core_points: 核心知识点 + 详细解释（核心概念）
- knowledge_structure: 知识结构树
- key_cases: 实践应用案例
- next_steps: 下一步学习建议（PRD P0 必备）
- misconceptions: 常见误区
- quick_test: 快速测试题
- quality_score: AI质量评分
- 保留 V4 兼容字段: summary, key_points, keywords, structure
"""
import logging

from app.core.config import settings
from app.services.deepseek import smart_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是 KnowledgeOS 的知识蒸馏 Agent。你的任务不是简单总结，而是将内容「蒸馏」为可理解、可记忆、可复用的深度知识卡片。

你的输出质量标准：必须给出**深度理解**，而不是目录式的要点罗列——让用户读完能真正搞清楚"是什么、为什么重要、怎么用、常见坑"，而非停留在摘要层面。

输出字段说明：
1. title: 卡片标题（10-20字），反映核心主题
2. one_liner: 一句话金句，让用户读完想截图。标准：不超过25字，必须点破最核心的那个洞察（为什么重要 / 和常识反着来 / 一句话说透本质），禁止写成“本文介绍了…”这类目录式概括
3. summary: 200-350字核心摘要，输出 2-3 个自然段落（用换行分隔）：
   第一段：这个概念/知识是什么（定义+核心机制）；
   第二段：为什么重要（解决了什么问题，带来什么价值）；
   第三段：具体怎么用 + 常见的坑或误区。
   关键概念、核心结论用 **加粗** 标重点（每段 1-3 处），让读者扫一眼就能抓住要点。禁止写成要点罗列，要写成连贯的段落。
4. core_points: 3-5个最重要的知识点，宁缺毋滥，每条必须回答"这句话哪来的底气"：
   - point: 一句本质洞察（不超过20字），不是主题词，是有信息量的一句话。反例："RAG很重要"；正例："RAG 的价值不是防幻觉，而是让回答可溯源"
   - detail: 1-2句证据/机制（具体到机制/例子/数据），关键概念用 **加粗** 强调（1-2 处）
   - importance: 重要程度 "high" / "medium" / "low"（仅供内部参考，不直接展示给用户）
5. keywords: 5-8个关键词
6. knowledge_structure: 知识结构树，dict 形式。key 是主题，value 是子主题列表
   例：{"RAG": ["Embedding", "Vector DB", "Retriever", "Generation"]}
7. key_cases: 1-3个关键案例或实际应用场景，每个包含：
   - scenario: 场景描述（要具体，如"做一个客服机器人，用户问退换货政策"）
   - application: 如何在该场景中应用此知识（给出具体做法或设计要点）
8. next_steps: 2-4条下一步学习建议，每条必须给出「具体行动 + 资源方向」，
   例如"动手实现一个最小 RAG 系统（LangChain + Chroma），跑通后再对比原生 LLM 的幻觉率"。禁止"建议多学习""建议深入理解"这类废话。
9. misconceptions: 2-3个常见误区，每个包含：
   - misconception: 错误理解
   - correction: 正确解释（要讲清为什么错）
10. quick_test: 2-3道快速测试题，每个包含：
    - question: 问题（检验理解深度，不要纯记忆题）
    - answer: 参考答案（1-2句）
11. quality_score: 自评质量分数（0-100），包含：
    - completeness: 信息完整度
    - coverage: 重点覆盖率
    - accuracy: 内容准确性
    - total: 综合分数

输出示例（体会深度标准）：
{
  "title": "RAG：检索增强生成",
  "one_liner": "让大模型先查资料再回答，用外部知识约束输出、减少幻觉",
  "summary": "**RAG（检索增强生成）**的核心思路是把「检索」和「生成」拆开：用户提问后，系统先在外部知识库中检索最相关的文档片段，再把片段拼进提示词交给大模型回答。典型流程是：文档切块（Chunking）→ 向量化（Embedding）→ 存入向量库 → 查询时做相似度检索 → 用检索结果约束生成。\n\n它解决的是大模型两大痛点——**知识过期**和**幻觉编造**：模型不需要把所有知识背进参数，知识可以随时更新而无需重新训练；回答时能引用真实来源，可追溯、可验证。\n\n常见坑包括：切块粒度不当导致语义被切断、检索不准时反而误导模型、以及把 RAG 当成万能药却忽略知识库本身的质量。",
  "core_points": [
    {"point": "检索 + 生成解耦", "detail": "模型回答前先从外部知识库检索相关片段，把证据拼进上下文再生成。这样知识可以随时更新，不需要重新训练模型；同时回答能被检索结果约束，天然带上来源，可追溯、可验证。", "importance": "high"}
  ],
  ...
}

要求：
1. 全部用中文输出（专有名词可保留英文）。
2. 一语道破优先：先找到原文最核心的那个洞察，把它放进 one_liner；次要内容不硬凑，core_points 少而精（3-5条）。
3. 深度优先：每条 detail、每个 summary 都要回答"为什么"和"怎么做"，禁止目录式一句话要点。
4. summary 必须分段（用换行分隔段落）+ 关键概念加粗，让用户像读 ChatGPT 的回答一样有阅读欲望。
5. 基于原文提炼，不要编造原文不存在的案例和数据。
6. quality_score 要诚实自评，不要全给满分。
7. 如果原文信息密度低，尽力提炼，不要返回"内容不足"类提示。
"""

USER_TEMPLATE = """【文件名/标题】{title}

【原始文本】
{text}

请输出 JSON：
{{
  "title": "卡片标题（10-20字）",
  "one_liner": "一句话金句（不超过25字，点破最核心的洞察）",
  "summary": "300-500字，2-3个自然段落（是什么/为什么重要/怎么用+坑），关键概念用**加粗**",
  "core_points": [
    {{"point": "一句本质洞察（不超过20字）", "detail": "1-2句证据/机制", "importance": "high"}}
  ],
  "keywords": ["关键词1", "关键词2"],
  "knowledge_structure": {{"主题": ["子主题1", "子主题2"]}},
  "key_cases": [
    {{"scenario": "具体应用场景", "application": "如何在此场景中应用"}}
  ],
  "next_steps": [
    "具体行动 + 资源方向"
  ],
  "misconceptions": [
    {{"misconception": "常见错误理解", "correction": "正确解释（讲清为什么错）"}}
  ],
  "quick_test": [
    {{"question": "测试问题", "answer": "参考答案"}}
  ],
  "quality_score": {{
    "completeness": 85,
    "coverage": 80,
    "accuracy": 90,
    "total": 85
  }}
}}
"""


async def summarize(text: str, title: str = "", on_thinking=None) -> dict:
    """Knowledge Distillation Agent — 生成 Card 2.0 全部字段（V6 深度版）

    Args:
        on_thinking: 可选回调，收到 R1 思维链时触发（捕获流程「思考过程」展示）

    Returns:
        dict 包含 Card 2.0 所有字段 + V4 兼容字段
        importance 恒为 None（重要性由用户自己决定）
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("无文本内容，无法生成知识卡片")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_TEMPLATE.format(title=title or "（无标题）", text=text),
        },
    ]

    result = await smart_json(
        messages,
        temperature=0.3,
        output_max_tokens=settings.LLM_DISTILL_OUTPUT_MAX_TOKENS,
        reasoner_max_tokens=settings.LLM_DISTILL_MAX_TOKENS,
        on_thinking=on_thinking,
    )

    if not isinstance(result, dict):
        raise ValueError(f"知识蒸馏 Agent 返回非 dict: {type(result)}")

    # schema 兜底 + 清洗
    ai_title = str(result.get("title", "")).strip() or title

    # 清洗 core_points（V6: 带 detail）
    raw_points = result.get("core_points", []) or []
    core_points = []
    for p in raw_points:
        if isinstance(p, dict) and p.get("point"):
            core_points.append({
                "point": str(p["point"]),
                "detail": str(p.get("detail", "")),
                "importance": str(p.get("importance", "medium")).lower(),
            })
        elif isinstance(p, str):
            core_points.append({"point": p, "detail": "", "importance": "medium"})

    # 清洗 misconceptions
    raw_misc = result.get("misconceptions", []) or []
    misconceptions = []
    for m in raw_misc:
        if isinstance(m, dict) and m.get("misconception"):
            misconceptions.append({
                "misconception": str(m["misconception"]),
                "correction": str(m.get("correction", "")),
            })

    # 清洗 quick_test
    raw_test = result.get("quick_test", []) or []
    quick_test = []
    for t in raw_test:
        if isinstance(t, dict) and t.get("question"):
            quick_test.append({
                "question": str(t["question"]),
                "answer": str(t.get("answer", "")),
            })

    # 清洗 quality_score
    raw_qs = result.get("quality_score", {}) or {}
    quality_score = {
        "completeness": int(raw_qs.get("completeness", 0)) if isinstance(raw_qs, dict) else 0,
        "coverage": int(raw_qs.get("coverage", 0)) if isinstance(raw_qs, dict) else 0,
        "accuracy": int(raw_qs.get("accuracy", 0)) if isinstance(raw_qs, dict) else 0,
        "total": int(raw_qs.get("total", 0)) if isinstance(raw_qs, dict) else 0,
    }

    # 清洗 knowledge_structure
    ks = result.get("knowledge_structure", {}) or {}
    if not isinstance(ks, dict):
        ks = {}

    # 清洗 key_cases
    raw_cases = result.get("key_cases", []) or []
    key_cases = []
    for c in raw_cases:
        if isinstance(c, dict) and c.get("scenario"):
            key_cases.append({
                "scenario": str(c["scenario"]),
                "application": str(c.get("application", "")),
            })

    # 清洗 next_steps
    raw_steps = result.get("next_steps", []) or []
    next_steps = []
    for s in raw_steps:
        if isinstance(s, str) and s.strip():
            next_steps.append(s.strip())
        elif isinstance(s, dict):
            text = str(s.get("step") or s.get("suggestion") or s.get("advice") or "").strip()
            if text:
                next_steps.append(text)

    # V6: importance 不再由 AI 输出 —— 用户自己决定
    importance = None

    # V4 兼容：从 core_points 提取 key_points
    key_points = [p["point"] for p in core_points]

    return {
        # V4.1 Card 2.0 新字段
        "title": ai_title,
        "one_liner": str(result.get("one_liner", "")),
        "core_points": core_points,
        "knowledge_structure": ks,
        "importance": importance,
        "key_cases": key_cases,
        "next_steps": next_steps,
        "misconceptions": misconceptions,
        "quick_test": quick_test,
        "quality_score": quality_score,
        # V4 兼容字段
        "summary": str(result.get("summary", "")),
        "key_points": key_points,
        "keywords": result.get("keywords", []) or [],
        "structure": ks,
    }
