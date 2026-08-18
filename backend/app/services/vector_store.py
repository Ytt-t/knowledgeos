"""向量库服务 — 基于 faiss + sentence-transformers

架构文档原计划用 Chroma，但 chroma-hnswlib 在 Windows + Python 3.13 + 无 MSVC 时编译失败。
改用 faiss-cpu + sentence-transformers 自封装轻量向量存储，接口语义对齐 Chroma。

- 模型: BAAI/bge-small-zh-v1.5 (512 维，中文检索明显优于 MiniLM)
- 索引: faiss IndexFlatIP (内积，配合 L2 归一化 = 余弦相似度)
- 持久化: 索引存二进制，id 映射存 JSON
- 单例: 模型加载慢，进程内只加载一次
"""
import json
import logging
import threading
from pathlib import Path
from typing import Optional

import faiss
import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
DIM = 512
# bge 官方推荐：查询侧加指令、文档侧不加，中文检索效果最佳
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

PERSIST_DIR = Path(settings.CHROMA_PERSIST_DIR)
PERSIST_DIR.mkdir(parents=True, exist_ok=True)
INDEX_FILE = PERSIST_DIR / "faiss.index"
ID_MAP_FILE = PERSIST_DIR / "id_map.json"


class VectorStore:
    """单例向量库"""

    _instance: Optional["VectorStore"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        # 延迟导入，避免应用启动慢
        from sentence_transformers import SentenceTransformer

        logger.info(f"加载 embedding 模型 {MODEL_NAME}...")
        # local_files_only=True: 模型缓存齐全，强制离线加载。
        # 否则加载时会联网检查版本（HuggingFace 被墙时挂起数分钟，阻塞整个事件循环）
        self._model = SentenceTransformer(MODEL_NAME, local_files_only=True)
        self._index = faiss.IndexFlatIP(DIM)
        self._id_map: list[int] = []  # faiss 内部 idx → card_id
        self._id_to_idx: dict[int, int] = {}  # card_id → faiss idx
        self._load()
        logger.info(
            f"VectorStore 就绪，已有 {len(self._id_map)} 条向量"
        )

    def _load(self):
        if INDEX_FILE.exists() and ID_MAP_FILE.exists():
            self._index = faiss.read_index(str(INDEX_FILE))
            with open(ID_MAP_FILE, "r", encoding="utf-8") as f:
                self._id_map = json.load(f)
            self._id_to_idx = {cid: i for i, cid in enumerate(self._id_map)}

    def _save(self):
        faiss.write_index(self._index, str(INDEX_FILE))
        with open(ID_MAP_FILE, "w", encoding="utf-8") as f:
            json.dump(self._id_map, f)

    def _embed(self, text: str, *, is_query: bool = False) -> np.ndarray:
        """单条文本 → L2 归一化后的向量（bge 查询侧加指令）"""
        if is_query:
            text = QUERY_INSTRUCTION + text
        vec = self._model.encode([text], normalize_embeddings=True)
        return np.array(vec, dtype=np.float32)

    def add(self, card_id: int, text: str):
        """添加/更新一条卡片向量（已存在则跳过）"""
        if card_id in self._id_to_idx:
            logger.info(f"card {card_id} 已在向量库，跳过")
            return
        vec = self._embed(text)
        self._index.add(vec)
        self._id_map.append(card_id)
        self._id_to_idx[card_id] = len(self._id_map) - 1
        self._save()
        logger.info(f"向量入库 card_id={card_id}，总条数 {len(self._id_map)}")

    def remove(self, card_id: int):
        """删除卡片时调用：从索引与映射中移除（IndexFlatIP 支持 remove_ids）"""
        if card_id not in self._id_to_idx:
            return
        idx = self._id_to_idx.pop(card_id)
        ids = np.array([idx], dtype=np.int64)
        try:
            self._index.remove_ids(ids)
        except Exception as e:
            logger.warning(f"faiss remove_ids 失败（跳过）: {e}")
            return
        self._id_map.pop(idx)
        self._id_to_idx = {cid: i for i, cid in enumerate(self._id_map)}
        self._save()
        logger.info(f"向量已移除 card_id={card_id}，剩余 {len(self._id_map)} 条")

    def update(self, card_id: int, text: str):
        """卡片编辑后重新嵌入：先移除旧向量再加新向量"""
        self.remove(card_id)
        self.add(card_id, text)

    def query(self, question: str, top_k: int = 3) -> list[tuple[int, float]]:
        """检索 Top-K 相关卡片

        Returns:
            [(card_id, score), ...] 按 score 降序
        """
        if self._index.ntotal == 0:
            return []
        k = min(top_k, self._index.ntotal)
        vec = self._embed(question, is_query=True)
        scores, indices = self._index.search(vec, k)
        result = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._id_map):
                continue
            result.append((self._id_map[idx], float(score)))
        return result


# 便捷函数
def get_store() -> VectorStore:
    return VectorStore()
