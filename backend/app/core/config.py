"""KnowledgeOS 后端配置"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "KnowledgeOS"
    DEBUG: bool = True

    # 数据库
    DATABASE_URL: str = "sqlite:///./knowledgeos.db"

    # DeepSeek
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    # 双模型：R1 深度思考 + 轻任务
    LLM_CHAT_MODEL: str = "deepseek-chat"          # 轻任务 + JSON 转译
    LLM_REASONER_MODEL: str = "deepseek-reasoner"  # 深度任务（R1）
    LLM_USE_REASONER: bool = True                  # 开关：False 时全部走轻任务模型
    LLM_DISTILL_MAX_TOKENS: int = 16384            # 知识蒸馏 R1 段（含思维链）
    LLM_DISTILL_OUTPUT_MAX_TOKENS: int = 8192      # JSON 转译段
    LLM_QA_MAX_TOKENS: int = 8192
    LLM_CHAT_TIMEOUT: float = 90.0
    LLM_REASONER_TIMEOUT: float = 300.0            # R1 深度思考可能 1-3 分钟

    # B站：登录态 Cookie（SESSDATA），从浏览器 F12 复制，留空则可能被风控
    BILI_SESSDATA: str = os.getenv("BILI_SESSDATA", "")

    # B站字幕 API 专用头（bilibili.py 使用）
    BILI_HEADERS: dict = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
    }

    # 各平台专属 HTTP 头（yt-dlp 下载音频用，Referer 必须匹配目标平台，否则触发反爬）
    PLATFORM_HEADERS: dict = {
        "bilibili_video": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
        },
        "douyin_video": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.douyin.com/",
        },
        "xiaohongshu_video": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.xiaohongshu.com/",
        },
    }

    # 文件上传
    UPLOAD_DIR: Path = Path("./uploads")

    # 向量库存储目录
    CHROMA_PERSIST_DIR: str = "./chroma_db"

    # 轮询相关
    TASK_POLL_INTERVAL_SEC: int = 3

    # V7 去重（MiniLM 余弦相似度，同文通常 0.95+）
    DEDUP_SIM_THRESHOLD: float = 0.92
    DEDUP_TOP_K: int = 3

    # ===== 安全加固（可选，配置后生效）=====
    # API 访问令牌：设置后，所有 /api 请求都必须携带请求头 X-API-Key 且值一致，否则返回 401。
    # 用于防止接口被公开调用时消耗 DeepSeek 额度（前端需同步配置 VITE_API_KEY）。
    APP_API_KEY: str = os.getenv("APP_API_KEY", "")

    # 允许跨域访问的前端来源（CORS）。默认只放行本地开发地址；
    # 若前端部署在其它域名，请把该域名加进来（JSON 数组）。
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ]

    # 播客音频目录
    PODCAST_AUDIO_DIR: Path = Path("./uploads/podcast")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

# 启动时确保上传目录存在
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
