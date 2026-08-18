"""DeepSeek API 客户端 — 双模型

- deepseek-chat：轻任务 + JSON 模式（response_format）
- deepseek-reasoner (R1)：深度任务，两段式（R1 深度文本 → chat 转 JSON）

R1 参数契约（官方）：
- 不支持 temperature / top_p / response_format（传了会 400 或行为异常）
- max_tokens 含思维链（reasoning + answer 合计）
- 响应中 reasoning_content 是思维链，绝不能拼回后续消息

兼容 OpenAI Chat Completions 格式。参考: https://api-docs.deepseek.com/
"""
import json
import logging
import os
import socket
from typing import AsyncIterator, Callable, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

CHAT_URL = f"{settings.DEEPSEEK_BASE_URL}/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TEMPERATURE = 0.3  # 知识抽取场景偏低温度保稳定

# 本地常见代理端口（Clash/mihomo/v2ray 等），直连不通时自动探测
_LOCAL_PROXY_PORTS = (7890, 7891, 7897, 1080, 10808, 10809, 8080, 8888)
_proxy_cache: Optional[str] = None  # None = 未探测，"" = 探测过无可用代理


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.5):
            return True
    except OSError:
        return False


def _is_socks5(port: int) -> bool:
    """socks5 握手探测：发送 \\x05\\x01\\x00，期待响应 \\x05\\x00"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2) as s:
            s.sendall(b"\x05\x01\x00")
            return s.recv(2) == b"\x05\x00"
    except OSError:
        return False


def _pick_proxy() -> Optional[str]:
    """选择代理：环境变量/配置优先，其次探测本地常见代理端口（结果缓存）。

    本地端口先做 socks5 握手探测（Clash 常配纯 socks5 端口），
    socks5 需要 socksio 包（httpx 的 SOCKS 依赖）。
    """
    global _proxy_cache
    if _proxy_cache is not None:
        return _proxy_cache or None

    for key in ("DEEPSEEK_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
        v = os.environ.get(key)
        if v:
            _proxy_cache = v
            logger.info(f"使用代理（环境变量 {key}）: {v}")
            return _proxy_cache

    for port in _LOCAL_PROXY_PORTS:
        if not _port_open(port):
            continue
        if _is_socks5(port):
            url = f"socks5://127.0.0.1:{port}"
        else:
            url = f"http://127.0.0.1:{port}"
        _proxy_cache = url
        logger.info(f"自动探测到本地代理: {url}")
        return _proxy_cache

    _proxy_cache = ""
    logger.warning("未检测到可用代理，DeepSeek 直连可能失败（国内网络通常需要代理）")
    return None


def _make_client(timeout: float) -> httpx.AsyncClient:
    """带代理的 AsyncClient。带代理时禁用环境代理读取，避免冲突。"""
    proxy = _pick_proxy()
    return httpx.AsyncClient(timeout=timeout, proxy=proxy, trust_env=(proxy is None))


class DeepSeekError(RuntimeError):
    pass


def _build_payload(
    model: str,
    messages: list[dict],
    temperature: Optional[float],
    json_mode: bool,
    max_tokens: Optional[int],
) -> dict:
    """按模型构建 payload。reasoner 不传 temperature/response_format。"""
    is_reasoner = model == settings.LLM_REASONER_MODEL
    payload = {"model": model, "messages": messages, "stream": False}
    if not is_reasoner:
        if temperature is not None:
            payload["temperature"] = temperature
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    return payload


async def chat(
    messages: list[dict],
    *,
    model: str = DEFAULT_MODEL,
    temperature: Optional[float] = DEFAULT_TEMPERATURE,
    json_mode: bool = False,
    max_tokens: Optional[int] = None,
    retries: int = 2,
    timeout: Optional[float] = None,
    capture_reasoning: Optional[Callable[[str], None]] = None,
) -> str:
    """调用 DeepSeek Chat Completions

    Args:
        messages: [{role, content}, ...]
        model: deepseek-chat 或 deepseek-reasoner（reasoner 自动去 temperature/json_mode）
        temperature: None 时不传该参数
        json_mode: True 时要求返回 JSON（reasoner 不支持，自动忽略）
        max_tokens: 显式输出上限（reasoner 计数含思维链）
        retries: 失败重试次数
        timeout: httpx 超时（reasoner 任务建议 300）
        capture_reasoning: 可选回调，reasoner 返回思维链（reasoning_content）时调用。
            回调内部必须自行 try/except，异常会被吞掉不影响主流程。

    Returns:
        模型输出的 content 字符串
    """
    if not settings.DEEPSEEK_API_KEY:
        raise DeepSeekError(
            "未配置 DEEPSEEK_API_KEY，请在 backend/.env 设置 "
            "（参考 .env.example）"
        )

    if timeout is None:
        timeout = settings.LLM_CHAT_TIMEOUT

    headers = {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = _build_payload(model, messages, temperature, json_mode, max_tokens)

    last_err: Optional[Exception] = None
    dropped_params = False
    for attempt in range(retries + 1):
        try:
            async with _make_client(timeout) as client:
                r = await client.post(CHAT_URL, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()

            msg = data["choices"][0]["message"]
            content = msg.get("content") or ""
            if msg.get("reasoning_content"):
                logger.info(f"[{model}] 思维链长度 {len(msg['reasoning_content'])} chars")
                if capture_reasoning:
                    try:
                        capture_reasoning(msg["reasoning_content"])
                    except Exception as e:
                        logger.warning(f"capture_reasoning 回调异常（不影响主流程）: {e}")
            if data["choices"][0].get("finish_reason") == "length":
                logger.warning(f"[{model}] 输出被 max_tokens 截断，建议提高上限")
            if not content:
                raise DeepSeekError("DeepSeek 返回空内容")

            # JSON 模式做一次解析校验（reasoner 不支持 json_mode，无 response_format 时跳过）
            if json_mode and payload.get("response_format"):
                try:
                    json.loads(content)
                except json.JSONDecodeError as e:
                    last_err = e
                    logger.warning(f"DeepSeek JSON 解析失败 (attempt {attempt+1}): {e}")
                    continue

            return content
        except httpx.HTTPStatusError as e:
            body = e.response.text[:300] if e.response else ""
            # 防御性降参：官方参数契约漂移时（如 reasoner 突然不支持 max_tokens），
            # 去掉问题参数重试一次
            if e.response is not None and e.response.status_code == 400 and not dropped_params:
                if any(k in body for k in ("max_tokens", "temperature", "response_format")):
                    dropped_params = True
                    logger.warning(f"[{model}] 400 参数错误，去掉相关参数重试: {body}")
                    payload = _build_payload(model, messages, None, False, None)
                    continue
            last_err = e
            logger.warning(f"DeepSeek HTTP {e.response.status_code if e.response else '?'} (attempt {attempt+1}): {body}")
        except (httpx.RequestError, KeyError, IndexError) as e:
            last_err = e
            logger.warning(f"DeepSeek 调用异常 (attempt {attempt+1}): {e}")

    raise DeepSeekError(f"DeepSeek 调用失败（重试 {retries} 次后仍失败）: {last_err}")


async def chat_stream(
    messages: list[dict],
    *,
    model: str = DEFAULT_MODEL,
    temperature: Optional[float] = DEFAULT_TEMPERATURE,
    max_tokens: Optional[int] = None,
    timeout: Optional[float] = None,
) -> AsyncIterator[str]:
    """流式调用 DeepSeek Chat Completions，逐段产出 content 增量。

    用 deepseek-chat 保证首字快、体验顺；reasoner 的思维链不适合流式对话。
    """
    if not settings.DEEPSEEK_API_KEY:
        raise DeepSeekError(
            "未配置 DEEPSEEK_API_KEY，请在 backend/.env 设置（参考 .env.example）"
        )
    if timeout is None:
        timeout = settings.LLM_CHAT_TIMEOUT

    headers = {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = _build_payload(model, messages, temperature, False, max_tokens)
    payload["stream"] = True

    async with _make_client(timeout) as client:
        async with client.stream(
            "POST", CHAT_URL, headers=headers, json=payload
        ) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = (obj.get("choices") or [{}])[0].get("delta") or {}
                chunk = delta.get("content")
                if chunk:
                    yield chunk


async def chat_json(
    messages: list[dict],
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    retries: int = 2,
    max_tokens: Optional[int] = None,
) -> dict:
    """调用 DeepSeek 并直接返回解析后的 dict

    自动在 system 末尾追加 JSON 输出要求。
    """
    # 强化 JSON 输出约束
    msgs = list(messages)
    if msgs and msgs[0]["role"] == "system":
        msgs[0] = {
            "role": "system",
            "content": msgs[0]["content"]
            + "\n\n【输出要求】必须返回合法 JSON，不要包含 markdown 代码块标记、不要任何解释性文字。",
        }
    else:
        msgs.insert(
            0,
            {
                "role": "system",
                "content": "【输出要求】必须返回合法 JSON，不要包含 markdown 代码块标记、不要任何解释性文字。",
            },
        )

    content = await chat(
        msgs, model=model, temperature=temperature, json_mode=True,
        retries=retries, max_tokens=max_tokens,
    )
    return json.loads(content)


async def smart_json(
    messages: list[dict],
    *,
    temperature: float = DEFAULT_TEMPERATURE,
    output_max_tokens: int = 8192,
    reasoner_max_tokens: int = 16384,
    retries: int = 2,
    on_thinking: Optional[Callable[[str], None]] = None,
) -> dict:
    """两段式智能 JSON：R1 深度思考 → chat 转结构化 JSON

    流程：
    1. R1(reasoner) 对原任务深度分析，输出自然语言长文本
    2. chat 把深度分析按原 prompt 的 JSON schema 转译成合法 JSON
    失败（R1 报错/关闭开关）自动降级为纯 chat_json，链路不断。

    Args:
        messages: 原始任务消息（含 system schema 约束 + user 内容）
        on_thinking: 可选回调，收到 R1 思维链时触发（用于展示 AI 思考过程）
    """
    # 开关关闭 → 直接走轻任务模型 chat_json
    if not settings.LLM_USE_REASONER:
        return await chat_json(messages, temperature=temperature, max_tokens=output_max_tokens)

    try:
        # 第一段：R1 深度分析（纯文本，无 json_mode）
        deep_text = await chat(
            messages,
            model=settings.LLM_REASONER_MODEL,
            temperature=None,
            max_tokens=reasoner_max_tokens,
            timeout=settings.LLM_REASONER_TIMEOUT,
            retries=retries,
            capture_reasoning=on_thinking,
        )
        if not deep_text.strip():
            raise DeepSeekError("R1 返回空内容")

        # 第二段：用轻任务模型把深度分析转成 JSON（schema 沿用原 prompt）
        msgs2 = list(messages)
        if msgs2 and msgs2[0]["role"] == "system":
            msgs2[0] = {
                "role": "system",
                "content": msgs2[0]["content"]
                + "\n\n【第二阶段】以下是第一阶段的深度分析，请把它提炼转译成上述 schema 要求的 JSON，"
                "内容必须完整丰富（可压缩措辞但不要丢失要点），禁止输出 JSON 以外的文字。",
            }
        msgs2[-1] = {
            "role": msgs2[-1]["role"],
            "content": msgs2[-1]["content"] + "\n\n【深度分析（数据源，请转译成 JSON）】\n" + deep_text,
        }
        return await chat_json(
            msgs2,
            model=settings.LLM_CHAT_MODEL,
            temperature=temperature,
            max_tokens=output_max_tokens,
            retries=retries,
        )
    except Exception as e:
        logger.warning(f"R1 两段式失败，降级纯 V3: {e}")
        return await chat_json(messages, temperature=temperature, max_tokens=output_max_tokens)
