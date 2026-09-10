import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from plugin_test_support import FakeConfig, RestartPlugin, plugin_module


class NotificationLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.platform = None
        self.context = SimpleNamespace(
            _star_manager=None,
            get_platform_inst=lambda _: self.platform,
            send_message=AsyncMock(return_value=True),
        )
        self.config = FakeConfig(
            {
                "platform_id": "qq",
                "umo": "qq:GroupMessage:123",
                "start_ts": time.time() - 10,
                "memory_before": "1GB",
            }
        )
        self.plugin = RestartPlugin(self.context, self.config)
        await self.plugin.initialize()
        self.addAsyncCleanup(self.plugin.terminate)

    def connect(self):
        self.platform = SimpleNamespace(meta=lambda: SimpleNamespace(name="aiocqhttp"))

    async def test_slow_cold_start_waits_for_core_loaded(self):
        # Provider/plugin loading may take longer than the entire retry window.
        now = 0.0
        clock = SimpleNamespace(time=time.time, monotonic=lambda: now)
        real_sleep = asyncio.sleep

        async def next_tick(_):
            await real_sleep(0)

        with (
            patch.object(plugin_module, "time", clock),
            patch.object(plugin_module.asyncio, "sleep", next_tick),
        ):
            plugin = RestartPlugin(self.context, self.config)
            await plugin.initialize()
            self.addAsyncCleanup(plugin.terminate)
            await real_sleep(0)
            now = 500.0
            await real_sleep(0)
            self.connect()
            # Dispatch the lifecycle hook only if registered by the plugin.
            if handler := getattr(plugin, "on_astrbot_loaded", None):
                await handler()
            if plugin._notification_task is not None:
                await plugin._notification_task
        self.context.send_message.assert_awaited_once()
        self.assertEqual(self.config["restart_cache"]["umo"], "")
        self.config.save_config.assert_called_once()

    async def test_hot_reload_recovers_without_core_event(self):
        self.connect()
        reloaded = RestartPlugin(self.context, self.config)
        await reloaded.initialize()
        self.addAsyncCleanup(reloaded.terminate)
        self.assertIsNotNone(reloaded._notification_task)
        await reloaded._notification_task
        self.context.send_message.assert_awaited_once()

    async def test_repeated_core_events_do_not_duplicate_send(self):
        self.connect()
        await self.plugin.on_astrbot_loaded()
        task = self.plugin._notification_task
        await self.plugin.on_astrbot_loaded()
        self.assertIs(task, self.plugin._notification_task)
        await task
        await self.plugin.on_astrbot_loaded()
        self.assertIs(task, self.plugin._notification_task)
        self.context.send_message.assert_awaited_once()

    async def test_platform_appears_after_core_event(self):
        async def connect_on_retry(_):
            self.connect()

        with patch.object(plugin_module.asyncio, "sleep", connect_on_retry):
            await self.plugin.on_astrbot_loaded()
            await self.plugin._notification_task
        self.context.send_message.assert_awaited_once()

    async def test_connection_errors_and_false_result_are_retried(self):
        self.connect()
        self.context.send_message.side_effect = [
            ConnectionError("not connected"),
            False,
            True,
        ]
        with patch.object(plugin_module, "NOTIFICATION_RETRY_INTERVAL", 0):
            await self.plugin.on_astrbot_loaded()
            await self.plugin._notification_task
        self.assertEqual(self.context.send_message.await_count, 3)
        self.config.save_config.assert_called_once()

    async def test_send_timeout_retries(self):
        self.connect()
        attempts = 0

        async def send(**kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                await asyncio.Event().wait()
            return True

        self.context.send_message.side_effect = send
        with (
            patch.object(plugin_module, "SEND_TIMEOUT", 0.01),
            patch.object(plugin_module, "NOTIFICATION_RETRY_INTERVAL", 0),
        ):
            await self.plugin.on_astrbot_loaded()
            await self.plugin._notification_task
        self.assertEqual(attempts, 2)
        self.config.save_config.assert_called_once()

    async def test_exhausted_retry_preserves_cache(self):
        self.connect()
        self.context.send_message.side_effect = ConnectionError("not connected")
        clock = SimpleNamespace(time=time.time, monotonic=lambda: 0)

        async def expire(_):
            clock.monotonic = lambda: 121

        with (
            patch.object(plugin_module, "time", clock),
            patch.object(plugin_module.asyncio, "sleep", expire),
        ):
            await self.plugin.on_astrbot_loaded()
            await self.plugin._notification_task
        self.assertEqual(self.config["restart_cache"]["umo"], "qq:GroupMessage:123")
        self.config.save_config.assert_not_called()

    async def test_terminate_cancels_pending_send_and_ignores_late_hook(self):
        self.connect()
        entered = asyncio.Event()

        async def send(**kwargs):
            entered.set()
            await asyncio.Event().wait()

        self.context.send_message.side_effect = send
        await self.plugin.on_astrbot_loaded()
        task = self.plugin._notification_task
        await entered.wait()
        await self.plugin.terminate()
        self.assertTrue(task.cancelled())
        self.config.save_config.assert_not_called()
        await self.plugin.on_astrbot_loaded()
        self.assertIs(task, self.plugin._notification_task)

    async def test_first_start_does_not_notify_for_new_restart_request(self):
        config = FakeConfig()
        plugin = RestartPlugin(self.context, config)
        await plugin.initialize()
        self.addAsyncCleanup(plugin.terminate)
        self.connect()
        event = SimpleNamespace(
            send=AsyncMock(),
            plain_result=lambda text: text,
            get_platform_id=lambda: "qq",
            unified_msg_origin="qq:GroupMessage:123",
            session_id="123",
        )
        await plugin.restart_system(event)
        config.save_config.assert_called_once()
        plugin.dashboard.restart.assert_awaited_once()
        await plugin.on_astrbot_loaded()
        self.assertIsNone(plugin._notification_task)
        self.context.send_message.assert_not_awaited()

    async def test_new_request_during_send_is_not_cleared(self):
        self.connect()

        async def send(**kwargs):
            self.plugin.cache["start_ts"] += 1
            return True

        self.context.send_message.side_effect = send
        await self.plugin.on_astrbot_loaded()
        await self.plugin._notification_task
        self.assertEqual(self.plugin.cache["umo"], "qq:GroupMessage:123")
        self.config.save_config.assert_not_called()

    async def test_superseded_request_is_not_sent(self):
        self.connect()
        self.plugin.cache["start_ts"] += 1
        await self.plugin.on_astrbot_loaded()
        await self.plugin._notification_task
        self.context.send_message.assert_not_awaited()
