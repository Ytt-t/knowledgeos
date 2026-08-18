"""Podcast Agent — AI 学习播客（NotebookLM 式）

两位 AI 主持人对话讲解用户的知识：
- A（女声，好奇求知派）：外行视角提问、生活类比、复述要点
- B（男声，资深讲解派）：把知识讲透、纠正误区、举具体例子
"""
import logging

from app.core.config import settings
from app.services.deepseek import smart_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是播客脚本创作 Agent。任务：把用户知识库里的内容写成一段两位主持人聊天的播客脚本，像真人播客一样自然、有信息量、有感染力。

主持人设定：
- A（好奇求知派）：代表外行听众。负责抛出好奇的问题、用生活化类比回应、替听众说出困惑、复述总结要点。语气活泼真诚。
- B（资深讲解派）：把知识讲透。负责深入讲解机制与原理、纠正常见误区、举具体例子、给行动建议。语气沉稳专业。

节目结构（10-18 轮）：
1. 开场 2 轮：A 抛出一个好奇的问题引入主题，B 一句话点题并预告精彩内容
2. 分段讨论 10-13 轮：按知识要点逐段展开。B 每轮讲透 1 个核心点（机制/为什么重要/怎么用），A 用类比、提问、复述推动节奏
3. 误区 1-2 轮：B 指出最常见误区，A 惊叹式回应
4. 总结 2 轮：B 金句收尾 + 行动建议，A 复述 2-3 个最重要的结论

硬约束：
1. 全部口语化，像真人在聊天；专业术语必须先大白话解释一遍再用
2. 每轮 1-3 句、40-120 个中文字（保证语音合成时效）
3. 只能基于提供的知识内容讲解，禁止编造内容
4. 禁止出现"知识卡片""用户上传""资料"等元信息词汇
5. 输出 JSON：{"title": "15字内标题", "segments": [{"speaker": "A"|"B", "text": "对话内容"}]}
"""

USER_TEMPLATE = """【本次播客的知识内容】
{context}

请写一段 10-18 轮的播客脚本，严格按 JSON 格式输出。"""


async def generate_script(context: str) -> dict:
    """生成播客脚本 {title, segments:[{speaker, text}]}"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(context=context)},
    ]
    result = await smart_json(messages, temperature=0.6, output_max_tokens=8192)
    if not isinstance(result, dict):
        raise ValueError(f"播客 Agent 返回非 dict: {type(result)}")

    title = str(result.get("title", "")).strip() or "我的知识播客"
    raw_segments = result.get("segments", []) or []
    segments = []
    for s in raw_segments:
        if not isinstance(s, dict):
            continue
        speaker = str(s.get("speaker", "")).strip().upper()
        text = str(s.get("text", "")).strip()
        if speaker in ("A", "B") and text:
            segments.append({"speaker": speaker, "text": text})
    if not segments:
        raise ValueError("播客脚本为空")

    return {"title": title[:30], "segments": segments[:18]}
