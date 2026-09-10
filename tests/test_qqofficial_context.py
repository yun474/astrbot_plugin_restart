import unittest
from types import SimpleNamespace

from plugin_test_support import FakeSession, RestartPlugin


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


class QQOfficialContextTests(unittest.TestCase):
    def test_caches_group_send_context(self):
        platform = FakeQQOfficialPlatform()
        platform._session_scene["group-openid"] = "group"
        platform._session_last_message_id["group-openid"] = "older-message-id"
        event = SimpleNamespace(
            session_id="group-openid",
            message_obj=SimpleNamespace(
                message_id="current-message-id", session_id="group-openid"
            ),
            session=FakeSession("qq", "GroupMessage", "group-openid"),
            get_platform_id=lambda: "qq",
        )
        plugin = RestartPlugin.__new__(RestartPlugin)
        plugin.cache = {}
        plugin.context = SimpleNamespace(get_platform_inst=lambda _: platform)

        plugin._cache_platform_send_context(event)

        self.assertEqual(plugin.cache["qqofficial_scene"], "group")
        self.assertEqual(plugin.cache["qqofficial_msg_id"], "current-message-id")

    def test_unique_group_session_uses_original_delivery_id(self):
        platform = FakeQQOfficialPlatform()
        platform._session_scene["group-openid"] = "group"
        event = SimpleNamespace(
            session_id="user-openid_group-openid",
            session=FakeSession("qq", "GroupMessage", "user-openid_group-openid"),
            message_obj=SimpleNamespace(
                session_id="group-openid", message_id="message-id"
            ),
            get_platform_id=lambda: "qq",
        )
        plugin = RestartPlugin.__new__(RestartPlugin)
        plugin.cache = {}
        plugin.context = SimpleNamespace(get_platform_inst=lambda _: platform)

        plugin._cache_platform_send_context(event)

        self.assertEqual(plugin.cache["session_id"], "group-openid")
        self.assertEqual(plugin.cache["umo"], "qq:GroupMessage:group-openid")
        self.assertEqual(plugin.cache["qqofficial_scene"], "group")
        self.assertEqual(event.session.session_id, "user-openid_group-openid")
        restored = FakeQQOfficialPlatform()
        plugin._restore_platform_send_context(restored)
        self.assertEqual(restored._session_scene["group-openid"], "group")
        self.assertEqual(
            restored._session_last_message_id["group-openid"], "message-id"
        )

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

    def test_missing_scene_does_not_silently_skip_send(self):
        plugin = RestartPlugin.__new__(RestartPlugin)
        plugin.cache = {"session_id": "group-openid", "qqofficial_msg_id": "message-id"}
        with self.assertRaisesRegex(RuntimeError, "场景"):
            plugin._restore_platform_send_context(FakeQQOfficialPlatform())

    def test_missing_group_message_id_does_not_silently_skip_send(self):
        plugin = RestartPlugin.__new__(RestartPlugin)
        plugin.cache = {"session_id": "group-openid", "qqofficial_scene": "group"}
        with self.assertRaisesRegex(RuntimeError, "消息 ID"):
            plugin._restore_platform_send_context(FakeQQOfficialPlatform())


if __name__ == "__main__":
    unittest.main()
