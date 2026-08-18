"""视频平台识别测试 —— 校验 URL 到平台的归一化映射（纯逻辑，无需网络）"""

import pytest

from app.services.video_agent import detect_platform


class TestDetectPlatform:
    def test_bilibili_long_url(self):
        assert detect_platform("https://www.bilibili.com/video/BV1xx411c7mD") == "bilibili_video"

    def test_bilibili_short_url(self):
        assert detect_platform("https://b23.tv/abcXYZ") == "bilibili_video"

    def test_xiaohongshu(self):
        assert detect_platform("https://www.xiaohongshu.com/explore/123") == "xiaohongshu_video"

    def test_douyin(self):
        assert detect_platform("https://www.douyin.com/video/123") == "douyin_video"

    def test_unknown_url_raises(self):
        with pytest.raises(ValueError):
            detect_platform("https://example.com/foo")