"""图片 OCR 服务 — Image Agent

用 easyocr（基于 PyTorch）做图片文字识别。
用 PIL 读取图片再转 numpy，绕过 OpenCV 中文路径问题。
"""
import logging
import os
import threading
from pathlib import Path

import numpy as np
from PIL import Image

# 模型目录设到项目下（easyocr 实际读取 EASYOCR_MODULE_PATH / MODULE_PATH，
# 之前变量名拼错导致去写 C:\Users\...\.EasyOCR 触发权限错误）
_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / ".easyocr"
_USER_NET_DIR = _MODEL_DIR / "user_network"
_MODEL_DIR.mkdir(parents=True, exist_ok=True)
_USER_NET_DIR.mkdir(parents=True, exist_ok=True)
os.environ["EASYOCR_MODULE_PATH"] = str(_MODEL_DIR)
os.environ["MODULE_PATH"] = str(_MODEL_DIR)

logger = logging.getLogger(__name__)

_reader = None
_reader_lock = threading.Lock()


def _get_reader():
    global _reader
    if _reader is None:
        with _reader_lock:
            if _reader is None:
                import easyocr
                logger.info(f"初始化 easyocr Reader（模型目录: {_MODEL_DIR}）...")
                _reader = easyocr.Reader(
                    ["ch_sim", "en"],
                    gpu=False,
                    verbose=False,
                    model_storage_directory=str(_MODEL_DIR),
                    user_network_directory=str(_USER_NET_DIR),
                    download_enabled=True,
                )
                logger.info("easyocr Reader 就绪")
    return _reader


def extract_text(file_path: str | Path) -> str:
    """从图片中提取文字（用 PIL 读取绕过 OpenCV 中文路径问题）"""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"图片文件不存在: {file_path}")

    reader = _get_reader()

    # 用 PIL 读取图片（支持中文路径），转成 numpy 数组给 easyocr
    img = Image.open(str(file_path)).convert("RGB")
    img_array = np.array(img)

    # detail=0 只返回文本
    results = reader.readtext(img_array, detail=0)
    text = "\n".join(results).strip()

    logger.info(
        f"OCR 识别完成: {file_path.name}, {len(results)} 段文本, {len(text)} 字符"
    )
    return text
