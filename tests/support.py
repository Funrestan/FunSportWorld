"""测试公共隔离设施：临时目录、禁止网络及独立配置路径。"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

IMPORT_DATA = tempfile.TemporaryDirectory(prefix="funsport-import-test-")
os.environ["FUNSPORT_DATA_DIR"] = IMPORT_DATA.name

from funsport import config


class IsolatedCase(unittest.TestCase):
    """为每个测试提供独立的数据目录，并阻止 HTTP 请求。"""

    def setUp(self):
        """把全部配置路径替换为临时路径，测试结束自动还原。"""
        directory = tempfile.TemporaryDirectory(prefix="funsport-unit-")
        self.addCleanup(directory.cleanup)
        self.data = Path(directory.name)
        files = {"DATA_DIR": self.data, "CONFIG_FILE": self.data / "config.json",
                 "IDENTITY_FILE": self.data / "identity.json", "SESSION_FILE": self.data / "session.json",
                 "POINTS_CACHE": self.data / "points_cache.json", "AI_SPORTS": self.data / "ai_sports.json"}
        self.paths = patch.multiple(config, **files)
        self.paths.start()
        self.addCleanup(self.paths.stop)
        network = patch("requests.sessions.Session.request", side_effect=AssertionError("测试禁止真实网络"))
        network.start()
        self.addCleanup(network.stop)
        environment = patch.dict(os.environ, {"FUNSPORT_DATA_DIR": str(self.data), "FUNSPORT_AMAP_KEY": ""})
        environment.start()
        self.addCleanup(environment.stop)
