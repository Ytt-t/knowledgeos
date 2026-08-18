"""Video Agent — V4 覆盖 B站/小红书/抖音

架构 4.1 决策：三平台统一走"通用视频下载 + ASR转写"路线
- B站：优先用 CC 字幕（更准更省钱），拿不到再走 ASR
- 小红书/抖音：无公开字幕接口，直接走 ASR
- 通用方案：yt-dlp 下载音频 → 转写

输出归一化结构：{ raw_text, metadata: {title, platform} }
"""
import asyncio
import logging
import re
from typing import Optional

from app.services import bilibili

logger = logging.getLogger(__name__)

PLATFORM_PATTERNS = {
    "bilibili_video": [
        re.compile(r"bilibili\.com/video/(BV[\w]+)", re.I),
        re.compile(r"b23\.tv/([\w]+)", re.I),
    ],
    "xiaohongshu_video": [
        re.compile(r"xiaohongshu\.com", re.I),
        re.compile(r"xhslink\.com", re.I),
        re.compile(r"xhslink\.cn", re.I),
    ],
    "douyin_video": [
        re.compile(r"douyin\.com", re.I),
        re.compile(r"iesdouyin\.com", re.I),
    ],
}


def detect_platform(url: str) -> str:
    """根据 URL 识别视频平台"""
    for platform, patterns in PLATFORM_PATTERNS.items():
        if any(p.search(url) for p in patterns):
            return platform
    # 兜底：含 bilibili 关键字也算
    if "bilibili" in url.lower() or "b23.tv" in url.lower():
        return "bilibili_video"
    raise ValueError(f"无法识别视频平台: {url}")


async def capture(url: str) -> dict:
    """捕获视频/图文内容，返回归一化结构

    Returns:
        { raw_text: str, metadata: {title, platform} }
    """
    platform = detect_platform(url)
    logger.info(f"Video Agent 识别平台: {platform}")

    if platform == "bilibili_video":
        return await _capture_bilibili(url, platform)
    elif platform == "xiaohongshu_video":
        return await _capture_xiaohongshu(url, platform)
    else:
        # 抖音走通用下载 + ASR
        return await _capture_via_asr(url, platform)


async def _capture_xiaohongshu(url: str, platform: str) -> dict:
    """小红书：先检测内容类型（图文笔记 vs 视频），分别处理

    - 图文笔记（type=normal）：用 Playwright 从 og 标签/JSON-LD 提取文本
    - 视频（type=video）：走 yt-dlp 下载音频 → ASR 转写
    """
    try:
        content_type, title, text = await _fetch_xhs_metadata(url)

        if content_type == "article" and text:
            # 图文笔记：直接用提取的文本
            logger.info(f"小红书图文笔记: {title}")
            return {
                "raw_text": text,
                "metadata": {"title": title, "platform": platform},
            }
        else:
            # 视频内容：走 ASR
            logger.info(f"小红书视频内容，尝试 ASR: {title or url}")
            return await _capture_via_asr(url, platform, fallback_title=title)
    except Exception as e:
        logger.warning(f"小红书元数据提取失败: {e}，尝试 ASR 兜底")
        return await _capture_via_asr(url, platform)


async def _fetch_xhs_metadata(url: str) -> tuple[str, Optional[str], Optional[str]]:
    """用 Playwright 提取小红书页面的内容类型和文本

    Returns:
        (content_type, title, text)
        - content_type: "article"（图文笔记）或 "video"
        - title: 页面标题
        - text: 笔记正文（图文笔记时有效）
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = None
        for _ch in ("msedge", "chrome", None):
            try:
                kw = {"headless": True}
                if _ch:
                    kw["channel"] = _ch
                browser = await p.chromium.launch(**kw)
                break
            except Exception:
                continue
        if not browser:
            raise RuntimeError("无法启动浏览器")

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        logger.info(f"Playwright 访问小红书: {url}")
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            logger.warning("小红书页面加载超时，继续提取元数据")
        await asyncio.sleep(2)

        # 从 og 标签和 JSON-LD 提取元数据
        metadata = await page.evaluate("""
            () => {
                const result = {
                    og_type: '',
                    og_title: '',
                    og_desc: '',
                    json_ld: ''
                };

                // og 标签
                const ogType = document.querySelector('meta[property="og:type"]');
                if (ogType) result.og_type = ogType.getAttribute('content') || '';

                const ogTitle = document.querySelector('meta[property="og:title"]');
                if (ogTitle) result.og_title = ogTitle.getAttribute('content') || '';

                const ogDesc = document.querySelector('meta[property="og:description"]');
                if (ogDesc) result.og_desc = ogDesc.getAttribute('content') || '';

                // JSON-LD Article
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                for (const s of scripts) {
                    try {
                        const data = JSON.parse(s.textContent);
                        if (data['@type'] === 'Article' || data.description) {
                            result.json_ld = JSON.stringify(data);
                            break;
                        }
                    } catch(e) {}
                }

                return result;
            }
        """)

        await browser.close()

        og_type = metadata.get("og_type", "")
        title = metadata.get("og_title", "").replace(" - 小红书", "").strip()
        og_desc = metadata.get("og_desc", "").strip()

        # 从 JSON-LD 提取更完整的描述
        text = og_desc
        json_ld_str = metadata.get("json_ld", "")
        if json_ld_str:
            try:
                import json
                article = json.loads(json_ld_str)
                # JSON-LD 的 description 可能更完整
                ld_desc = article.get("description", "").strip()
                if len(ld_desc) > len(text):
                    text = ld_desc
                if not title:
                    title = article.get("headline", "").strip()
            except Exception:
                pass

        # 判断内容类型
        # og:type=article 是图文笔记；og:type=video 或 URL type=video 是视频
        content_type = "article" if "article" in og_type.lower() else "video"

        logger.info(f"小红书内容类型: {content_type}, 标题: {title}, 文本长度: {len(text)}")
        return content_type, title or None, text or None


async def _capture_bilibili(url: str, platform: str) -> dict:
    """B站：优先 CC 字幕，拿不到走 ASR，ASR 也失败用 desc 兜底"""
    try:
        info = await bilibili.parse_bilibili(url)
        title = info.get("title", "B站视频")
        desc = info.get("desc", "")

        if info.get("raw_transcript"):
            return {
                "raw_text": info["raw_transcript"],
                "metadata": {"title": title, "platform": platform},
            }

        # 无 CC 字幕，尝试 ASR
        logger.info(f"B站无 CC 字幕，尝试 ASR: {title}")
        try:
            return await _capture_via_asr(url, platform, fallback_title=title)
        except Exception as asr_err:
            logger.warning(f"B站 ASR 失败: {asr_err}，使用 desc 兜底")
            # ASR 也失败，用视频简介兜底（保证流程不中断）
            if desc and desc.strip():
                return {
                    "raw_text": f"视频标题：{title}\n视频简介：{desc}",
                    "metadata": {"title": title, "platform": platform},
                }
            raise RuntimeError(
                f"B站视频解析失败：无 CC 字幕、ASR 失败、无简介兜底。ASR 错误: {asr_err}"
            )
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning(f"B站解析失败，尝试通用方案: {e}")
        return await _capture_via_asr(url, platform)


async def _capture_via_asr(
    url: str,
    platform: str,
    fallback_title: Optional[str] = None,
) -> dict:
    """通用方案：yt-dlp 下载音频 → ASR 转写"""
    title = fallback_title or f"{platform} 视频"

    try:
        # 1. yt-dlp 下载音频（只取音频流，省带宽）
        audio_path, dl_error = await _download_audio(url, platform)
        if not audio_path:
            raise RuntimeError(f"音频下载失败: {dl_error or '未知原因'}")

        # 2. ASR 转写
        text = await _transcribe(audio_path)
        return {
            "raw_text": text,
            "metadata": {"title": title, "platform": platform},
        }
    except Exception as e:
        logger.error(f"通用视频解析失败 [{platform}]: {e}")
        raise


async def _download_audio(url: str, platform: str) -> tuple[Optional[str], Optional[str]]:
    """用 yt-dlp 下载音频到临时文件（按平台配置 Headers 与 Cookie）

    Returns: (audio_path, error_message)
        - 成功: (path, None)
        - 失败: (None, error_str)
    """
    import yt_dlp
    import tempfile
    import os

    from app.core.config import settings
    from app.services.cookie_fetcher import fetch_cookies_via_playwright

    tmp_dir = tempfile.mkdtemp(prefix="kos_video_")
    output_template = os.path.join(tmp_dir, "%(id)s.%(ext)s")

    # 按平台获取正确的 HTTP 头（Referer 必须匹配目标平台，否则触发反爬）
    platform_headers = settings.PLATFORM_HEADERS.get(platform, settings.BILI_HEADERS)

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "writesubtitles": False,
        "skip_download": False,
        # 平台专属 HTTP 头
        "http_headers": dict(platform_headers),
    }

    # 按 platform 构建 Cookie 策略（按可靠性排序）：
    # 1. 用户导出的 cookies.txt（通用，所有平台）
    # 2. B站 SESSDATA（仅 B站有效，其它平台域名不匹配）
    # 3. Playwright 自动获取（按平台，支持抖音/小红书）
    # 4. 浏览器自动提取（兜底，需关闭浏览器）
    cookie_strategies = []

    # 策略 1：检查 backend/cookies.txt（用户通过扩展导出的完整 cookies）
    cookies_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cookies.txt")
    if os.path.exists(cookies_file_path):
        cookie_strategies.append(("cookies_file_full", cookies_file_path))
        logger.info(f"发现 cookies.txt 文件: {cookies_file_path}")

    # 策略 2：B站专用 SESSDATA（仅 B站，其它平台域名不匹配）
    if platform == "bilibili_video" and settings.BILI_SESSDATA:
        mini_cookie_file = os.path.join(tmp_dir, "bili_cookies.txt")
        with open(mini_cookie_file, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write(f".bilibili.com\tTRUE\t/\tTRUE\t0\tSESSDATA\t{settings.BILI_SESSDATA}\n")
        cookie_strategies.append(("cookies_file_sessdata", mini_cookie_file))

    # 策略 3：Playwright 自动获取（按平台，支持抖音/小红书）
    cookie_strategies.append(("playwright", None))

    # 策略 4：浏览器自动提取（兜底）
    for browser in ("chrome", "edge"):
        cookie_strategies.append((f"browser:{browser}", browser))

    loop = asyncio.get_event_loop()
    last_error = ""

    for strategy_name, strategy_val in cookie_strategies:
        opts = dict(ydl_opts)  # 每轮用独立副本

        if strategy_name == "playwright":
            # Playwright 无头浏览器自动获取对应平台 cookies
            logger.info(f"yt-dlp 尝试策略: playwright (自动获取 {platform} cookies)")
            sessdata = settings.BILI_SESSDATA if platform == "bilibili_video" else None
            cookie_file = await fetch_cookies_via_playwright(
                platform=platform, video_url=url, sessdata=sessdata
            )
            if not cookie_file:
                last_error = f"Playwright 获取 {platform} cookies 失败"
                logger.warning(f"策略 {strategy_name} 跳过: {last_error}")
                continue
            opts["cookiefile"] = cookie_file
        elif strategy_name.startswith("cookies_file"):
            opts["cookiefile"] = strategy_val
            logger.info(f"yt-dlp 尝试策略: {strategy_name}")
        else:
            opts["cookiesfrombrowser"] = (strategy_val,)
            logger.info(f"yt-dlp 尝试策略: {strategy_name}")

        try:
            await loop.run_in_executor(
                None,
                lambda o=opts: yt_dlp.YoutubeDL(o).download([url]),
            )
            # 下载成功（排除 cookie 文件）
            files = [f for f in os.listdir(tmp_dir) if not f.endswith(".txt")]
            if files:
                logger.info(f"yt-dlp 下载成功 (策略: {strategy_name})")
                return os.path.join(tmp_dir, files[0]), None
            last_error = "下载完成但未找到音频文件"
        except Exception as e:
            last_error = str(e)
            logger.warning(f"yt-dlp 策略 {strategy_name} 失败: {last_error}")
            continue

    # 所有策略都失败，给出可操作的错误信息
    if "412" in last_error:
        error_msg = (
            f"{platform} HTTP 412 风控拦截。\n"
            f"请用浏览器扩展导出完整 cookies.txt 文件放到 backend/cookies.txt：\n"
            f"  1. Chrome 安装扩展 'Get cookies.txt LOCALLY'（或类似扩展）\n"
            f"  2. 在对应平台页面点击扩展导出 cookies\n"
            f"  3. 将导出的 cookies.txt 保存到 backend/ 目录\n"
            f"原始错误: {last_error}"
        )
    elif "Could not copy" in last_error and "cookie" in last_error.lower():
        error_msg = (
            f"无法从浏览器提取 cookies（浏览器正在运行）。\n"
            f"方案一：关闭浏览器后重试\n"
            f"方案二：用浏览器扩展导出 cookies.txt 放到 backend/ 目录\n"
            f"原始错误: {last_error}"
        )
    else:
        error_msg = last_error

    logger.error(f"yt-dlp 所有策略均失败: {error_msg}")
    return None, error_msg


async def _transcribe(audio_path: str) -> str:
    """用 faster-whisper / whisper 做 ASR 转写"""
    try:
        return await _transcribe_whisper(audio_path)
    except Exception as e:
        logger.error(f"ASR 转写失败: {e}")
        raise RuntimeError(f"语音转写失败: {e}") from e


async def _transcribe_whisper(audio_path: str) -> str:
    """用 OpenAI Whisper 做转写"""
    import whisper
    import os

    # Whisper 依赖 ffmpeg 处理音频，系统未安装时用 imageio-ffmpeg 提供的 ffmpeg
    # 注意：imageio_ffmpeg 的文件名是 ffmpeg-win-x86_64-v7.1.exe，不是 ffmpeg.exe
    # 需要复制为 ffmpeg.exe 才能让 subprocess.run(["ffmpeg", ...]) 找到它
    try:
        import imageio_ffmpeg
        import shutil
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        alias_dir = os.path.join(os.path.dirname(ffmpeg_exe), "ffmpeg_alias")
        os.makedirs(alias_dir, exist_ok=True)
        ffmpeg_alias = os.path.join(alias_dir, "ffmpeg.exe")
        if not os.path.exists(ffmpeg_alias):
            shutil.copy2(ffmpeg_exe, ffmpeg_alias)
        os.environ["PATH"] = alias_dir + os.pathsep + os.environ.get("PATH", "")
        logger.info(f"使用 imageio-ffmpeg 提供的 ffmpeg: {ffmpeg_alias}")
    except ImportError:
        logger.warning("imageio-ffmpeg 未安装，Whisper 可能找不到 ffmpeg")

    loop = asyncio.get_event_loop()

    def _do_transcribe():
        model = whisper.load_model("base")  # base 模型，平衡速度和精度
        result = model.transcribe(audio_path, language="zh")
        return result.get("text", "").strip()

    return await loop.run_in_executor(None, _do_transcribe)
