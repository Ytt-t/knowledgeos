"""V7 TTS：edge-tts 封装（微软免费语音合成，中文音色）

- 异步调用（websocket 协议），不阻塞事件循环
- 单段独立 try/except：失败跳过继续，绝不因音频拖垮整期播客
- 无 ffmpeg：edge-tts 直接产出 mp3，前端顺序播放不拼接
"""
import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# A=女声好奇求知派 / B=男声资深讲解派
VOICES = {
    "A": "zh-CN-XiaoxiaoNeural",
    "B": "zh-CN-YunxiNeural",
}


async def synthesize_segment(text: str, speaker: str, out_path: Path, retries: int = 3) -> bool:
    """合成一段语音到 out_path（mp3）。成功 True，失败 False（不抛异常）

    retries: 微软 TTS 对连续高频请求会限流，失败后退避重试
    """
    voice = VOICES.get(speaker, VOICES["A"])
    for attempt in range(retries):
        try:
            import edge_tts
            communicate = edge_tts.Communicate(text, voice)
            await asyncio.wait_for(communicate.save(str(out_path)), timeout=60)
            if out_path.exists() and out_path.stat().st_size > 0:
                return True
        except Exception as e:
            logger.warning(f"TTS 失败 [{voice}] {text[:30]}...: {type(e).__name__} {str(e)[:100]}")
        if attempt < retries - 1:
            await asyncio.sleep(2 * (attempt + 1))  # 退避 2s/4s
    return False
