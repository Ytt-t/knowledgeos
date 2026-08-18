"""知识整理 Agent

输入：summary, core_points, 原文片段（可选）
处理：
  1. 抽取核心概念及子概念树
  2. 生成一句话解释、知识结构树、应用场景
  3. 给出学习建议
输出：list[KnowledgeCardCandidate] —— 一个 source 可能产出多个卡片
     （比如一个视频讲了 RAG 和 Agent 两个概念）
"""
import logging
from typing import Optional

from app.services.deepseek import chat_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个知识结构化专家。你的任务是把一段内容总结，拆解成 1~N 张"知识卡片"。

每张知识卡片代表一个独立的核心概念。如果内容只围绕一个概念，就输出 1 张卡片；如果涉及多个独立概念，输出多张。

字段说明：
- concept_name: 概念名（如 "RAG"），简短
- one_line_explanation: 一句话解释这个概念是什么、解决什么问题
- knowledge_structure: 知识结构树，对象形式。key 是概念名，value 是子概念列表。
  例：{"RAG": ["Embedding", "Vector Database", "Retriever", "Generation"]}
- application_scenarios: 应用场景列表，2-4 个具体场景
- learning_suggestion: 下一步学习建议，1-2 句话，指向应该接着学的相关概念

要求：
1. 概念名要准确，能用业界通用术语就用通用术语。
2. 一句话解释要让外行也能懂。
3. 知识结构树要体现概念的内部组成或流程。
4. 全部用中文输出。
"""

USER_TEMPLATE = """【标题】{title}

【内容摘要】
{summary}

【核心观点】
{core_points}

【原文片段】
{snippet}

请输出 JSON，格式如下：
{{
  "cards": [
    {{
      "concept_name": "RAG",
      "one_line_explanation": "让大模型先查资料再回答，减少幻觉",
      "knowledge_structure": {{
        "RAG": ["Embedding", "Vector Database", "Retriever", "Generation"]
      }},
      "application_scenarios": ["企业知识库", "AI客服", "个人笔记问答"],
      "learning_suggestion": "建议接着学习 Embedding 模型选型和 Chunk 切分策略"
    }}
  ]
}}
"""


async def structure(
    summary: str,
    core_points: list[str],
    title: str = "",
    snippet: str = "",
) -> list[dict]:
    """生成结构化知识卡片

    Returns:
        list of {
            concept_name, one_line_explanation,
            knowledge_structure, application_scenarios,
            learning_suggestion
        }
    """
    cp_text = "\n".join(f"- {p}" for p in core_points) or "（无）"
    snippet = (snippet or "")[:3000]  # 原文片段限长，避免 token 浪费

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_TEMPLATE.format(
                title=title or "（无标题）",
                summary=summary,
                core_points=cp_text,
                snippet=snippet or "（无原文片段）",
            ),
        },
    ]

    result = await chat_json(messages)
    if not isinstance(result, dict) or "cards" not in result:
        raise ValueError(f"知识整理 Agent 返回缺少 cards 字段: {result}")

    cards = result["cards"]
    if not isinstance(cards, list) or not cards:
        raise ValueError(f"知识整理 Agent 返回 cards 为空: {result}")

    # schema 校验 + 兜底
    cleaned = []
    for c in cards:
        if not isinstance(c, dict):
            continue
        if not c.get("concept_name"):
            continue
        cleaned.append(
            {
                "concept_name": str(c["concept_name"]),
                "one_line_explanation": str(c.get("one_line_explanation", "")),
                "knowledge_structure": c.get("knowledge_structure", {}) or {},
                "application_scenarios": c.get("application_scenarios", []) or [],
                "learning_suggestion": str(c.get("learning_suggestion", "")),
            }
        )

    if not cleaned:
        raise ValueError("知识整理 Agent 清洗后无有效卡片")
    return cleaned
