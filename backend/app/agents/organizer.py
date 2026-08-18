"""Organizer Agent — V6 标签建议 + 空间建议

V6 变化（PRD V3.0：取消AI强制分类，采用用户自定义知识空间）：
- 删除 23 个预定义领域的强制分类
- 删除 should_archive 自动归档（归档与否由用户决定）
- AI 仅做两件事：
  1. 生成 3-5 个具体标签（检索/筛选用）
  2. 建议一个知识空间：优先匹配用户已有空间，匹配不到给新空间名建议
  轻任务，走 V3 chat_json，不走 smart_json。
"""
import logging

from app.services.deepseek import chat_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是知识标签专家。任务：为一段内容生成标签建议，并推荐一个合适的知识空间。

规则：
1. tags: 生成 3-5 个标签，反映内容核心主题，便于检索和筛选。标签要具体（如"向量数据库"比"数据库"更好），不要和空间名重复。
2. suggested_space: 从【已有知识空间】中选择语义最贴切的一个空间名返回。
   - 如果已有空间都不合适，给出一个新的空间名建议（2-8字，如"英语"、"Python"、"求职面试"）
   - 如果内容太杂确实无法归类，返回 null
3. 你只做建议，用户有最终决定权。不要替用户归档、不要替用户删内容。

全部用中文输出。
"""

USER_TEMPLATE = """【标题】{title}

【内容摘要】
{summary}

【关键词】
{keywords}

【已有知识空间】
{spaces}

请输出 JSON：
{{
  "tags": ["标签1", "标签2", "标签3"],
  "suggested_space": "最贴切的已有空间名 或 新空间名建议 或 null"
}}
"""


async def organize(
    title: str,
    summary: str,
    keywords: list[str],
    space_names: list[str],
) -> dict:
    """生成 { tags, suggested_space }（仅建议，不强制）"""
    kw_text = ", ".join(keywords) if keywords else "（无）"
    spaces_text = "、".join(space_names) if space_names else "（用户还没有创建空间）"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_TEMPLATE.format(
                title=title or "（无标题）",
                summary=summary or "（无摘要）",
                keywords=kw_text,
                spaces=spaces_text,
            ),
        },
    ]

    result = await chat_json(messages, temperature=0.1)
    if not isinstance(result, dict):
        raise ValueError(f"Organizer 返回非 dict: {type(result)}")

    tags = result.get("tags", []) or []
    if not isinstance(tags, list):
        tags = [str(tags)]
    tags = [str(t) for t in tags][:8]

    suggested = result.get("suggested_space")
    if suggested == "null" or suggested == "None":
        suggested = None
    suggested_space = str(suggested).strip() if suggested else None

    return {"tags": tags, "suggested_space": suggested_space}
