"""B站视频解析：标题/时长/简介 + CC字幕

接口说明：
1. 视频信息：https://api.bilibili.com/x/web-interface/view?bvid=xxx
2. 字幕信息：https://api.bilibili.com/x/player/v2?bvid=xxx&cid=xxx
   返回 subtitle.list.subtitles，包含字幕 URL
3. 字幕内容：从 subtitle.url 拉取 json

注意：部分视频无字幕或需登录态，拿不到字幕时返回空字符串，由上层决定是否走 ASR 兜底。
"""
import re
import httpx
from typing import Optional
from urllib.parse import urlparse, parse_qs

from app.core.config import settings


async def _get(url: str, **kwargs) -> dict:
    headers = dict(settings.BILI_HEADERS)
    if settings.BILI_SESSDATA:
        headers["Cookie"] = f"SESSDATA={settings.BILI_SESSDATA}"
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        r = await client.get(url, **kwargs)
        r.raise_for_status()
        return r.json()


def extract_bvid(url: str) -> Optional[str]:
    """从 B站 URL 提取 bvid

    支持形态：
      https://www.bilibili.com/video/BV1xx411c7mD
      https://b23.tv/xxxxx (短链需先跳转，这里 Phase 1 暂不支持)
      https://m.bilibili.com/video/BV1xx411c7mD
    """
    m = re.search(r"BV[0-9A-Za-z]{10}", url)
    return m.group(0) if m else None


async def fetch_video_info(bvid: str) -> dict:
    """获取视频基础信息

    Returns: { title, desc, duration, cid, cover }
    """
    data = await _get(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")
    if data.get("code") != 0:
        raise RuntimeError(f"获取视频信息失败: {data.get('message')}")

    d = data["data"]
    return {
        "title": d.get("title", ""),
        "desc": d.get("desc", ""),
        "duration": d.get("duration", 0),
        "cid": d.get("cid"),
        "cover": d.get("pic", ""),
    }


async def fetch_subtitle(bvid: str, cid: int) -> str:
    """获取 CC 字幕纯文本，无字幕返回 ""

    优先选 zh-CN 字幕，否则取第一个。
    """
    try:
        data = await _get(
            "https://api.bilibili.com/x/player/v2",
            params={"bvid": bvid, "cid": cid},
        )
        if data.get("code") != 0:
            return ""

        subtitles = (data.get("data", {}).get("subtitle", {}) or {}).get("subtitles", []) or []
        if not subtitles:
            return ""

        # 优先中文字幕
        sub = next((s for s in subtitles if s.get("lan", "").startswith("zh")), subtitles[0])
        sub_url = sub.get("subtitle_url", "")
        if sub_url.startswith("//"):
            sub_url = "https:" + sub_url

        sub_data = await _get(sub_url)
        body = sub_data.get("body", []) or []
        return "\n".join(seg.get("content", "") for seg in body).strip()
    except Exception:
        return ""


async def parse_bilibili(url: str) -> dict:
    """完整解析：标题/时长/字幕

    Returns:
        { title, duration, raw_transcript, cover, desc, need_asr }
    """
    bvid = extract_bvid(url)
    if not bvid:
        raise ValueError(f"无法从 URL 解析 bvid: {url}")

    info = await fetch_video_info(bvid)
    transcript = ""
    if info.get("cid"):
        transcript = await fetch_subtitle(bvid, info["cid"])

    return {
        "title": info["title"],
        "duration": info["duration"],
        "desc": info["desc"],
        "cover": info["cover"],
        "raw_transcript": transcript,
        "need_asr": not transcript,  # 没拿到字幕标记需要 ASR
    }
