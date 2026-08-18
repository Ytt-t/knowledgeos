"""配置层冒烟测试 —— 校验核心配置项的合理性与双模型策略"""

from app.core.config import settings


def test_app_name():
    assert settings.APP_NAME == "KnowledgeOS"


def test_dual_model_strategy():
    """深度任务走 reasoner（R1），轻任务走 chat（V3）"""
    assert settings.LLM_REASONER_MODEL
    assert settings.LLM_CHAT_MODEL
    assert settings.LLM_USE_REASONER is True


def test_dedup_threshold_within_range():
    """去重相似度阈值必须落在合法区间 [0,1]"""
    assert 0.0 <= settings.DEDUP_SIM_THRESHOLD <= 1.0


def test_timeout_values_positive():
    assert settings.LLM_CHAT_TIMEOUT > 0
    assert settings.LLM_REASONER_TIMEOUT > 0