import unittest
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from astrbot_plugin_restart.main import RestartPlugin
except ImportError:
    RestartPlugin = None


class FakeQQOfficialPlatform:
    def __init__(self):
        self._session_scene = {}
        self._session_last_message_id = {}

    def meta(self):
        return SimpleNamespace(name="qq_official")

    def remember_session_scene(self, session_id, scene):
        self._session_scene[session_id] = scene

    def remember_session_message_id(self, session_id, message_id):
        self._session_last_message_id[session_id] = message_id


@unittest.skipIf(RestartPlugin is None, "AstrBot runtime is unavailable")
class QQOfficialContextTests(unittest.TestCase):
    def test_caches_group_send_context(self):
        platform = FakeQQOfficialPlatform()
        platform._session_scene["group-openid"] = "group"
        platform._session_last_message_id["group-openid"] = "older-message-id"
        event = SimpleNamespace(
            session_id="group-openid",
            message_obj=SimpleNamespace(message_id="current-message-id"),
            get_platform_id=lambda: "qq",
        )
        plugin = RestartPlugin.__new__(RestartPlugin)
        plugin.cache = {}
        plugin.context = SimpleNamespace(get_platform_inst=lambda _: platform)

        plugin._cache_platform_send_context(event)

        self.assertEqual(plugin.cache["qqofficial_scene"], "group")
        self.assertEqual(plugin.cache["qqofficial_msg_id"], "current-message-id")

    def test_restores_group_send_context(self):
        plugin = RestartPlugin.__new__(RestartPlugin)
        plugin.cache = {
            "session_id": "group-openid",
            "qqofficial_scene": "group",
            "qqofficial_msg_id": "message-id",
        }
        platform = FakeQQOfficialPlatform()

        plugin._restore_platform_send_context(platform)

        self.assertEqual(platform._session_scene["group-openid"], "group")
        self.assertEqual(
            platform._session_last_message_id["group-openid"], "message-id"
        )

    def test_restores_private_send_context(self):
        plugin = RestartPlugin.__new__(RestartPlugin)
        plugin.cache = {
            "session_id": "user-openid",
            "qqofficial_scene": "friend",
            "qqofficial_msg_id": "message-id",
        }
        platform = FakeQQOfficialPlatform()

        plugin._restore_platform_send_context(platform)

        self.assertEqual(platform._session_scene["user-openid"], "friend")


if __name__ == "__main__":
    unittest.main()
