# restart_plugin.py
import asyncio
import time
from contextlib import suppress
from copy import copy
from datetime import datetime
from typing import Any

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star_manager import PluginManager

from .dashboard_client import DashboardClient
from .restart_scheduler import RestartScheduler
from .utils import cron_to_human, format_prompt, get_memory_placeholders


DEFAULT_RESTART_PROMPT = "正在重启 AstrBot…"
DEFAULT_COMPLETED_PROMPT = "AstrBot 重启完成（耗时 {elapsed} 秒）{memory_line}"
NOTIFICATION_TIMEOUT = 120
NOTIFICATION_RETRY_INTERVAL = 2
SEND_TIMEOUT = 10
QQ_OFFICIAL_PLATFORM_NAME = "qq_official"


class RestartPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.star_manager: PluginManager = self.context._star_manager  # type: ignore
        self.config = config
        self.cache: dict[str, Any] = config.get("restart_cache", {})
        self.config["restart_cache"] = self.cache
        # 只恢复本次加载时已有的记录，不能把本进程刚收到的重启命令当作完成。
        self._pending_restart = self.cache.copy()
        self.restart_cron = config.get("restart_cron")
        self._notification_task: asyncio.Task | None = None
        self._terminated = False

    # ================== 生命周期 ==================

    async def initialize(self):
        self.dashboard = DashboardClient(self.context)
        await self.dashboard.initialize()
        self.scheduler = RestartScheduler(self.context, self.config, self.dashboard)
        if self.config["restart_switch"]:
            await self.scheduler.start()
        # 冷启动时平台尚未加载，等核心加载完成再开始计时。
        # 热重载不会再次触发 on_astrbot_loaded，已有目标平台时直接恢复。
        platform_id = self._pending_restart.get("platform_id")
        if platform_id and self.context.get_platform_inst(str(platform_id)) is not None:
            self._start_completed_notification()

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self):
        self._start_completed_notification()

    def _start_completed_notification(self) -> None:
        if self._terminated or self._notification_task is not None:
            return
        if not all(
            self._pending_restart.get(k) for k in ("platform_id", "umo", "start_ts")
        ):
            return
        self._notification_task = asyncio.create_task(
            self._send_completed_notification_when_ready(),
            name="restart_completed_notification",
        )

    async def terminate(self):
        self._terminated = True
        if self._notification_task and not self._notification_task.done():
            self._notification_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._notification_task
        await self.dashboard.terminate()
        await self.scheduler.shutdown()
        logger.info("重启插件已终止")

    # ================== 重启完成通知 ==================

    def _prompt_values(
        self,
        *,
        restart_start_ts: float,
        before_memory: str,
    ) -> dict[str, str]:
        memory = get_memory_placeholders()
        now = time.time()
        memory_line = (
            f"\n内存：{memory['memory']}"
            if self.config.get("show_memory_info", True)
            else ""
        )
        return {
            **memory,
            "before_memory": before_memory,
            "after_memory": memory["memory"],
            "memory_line": memory_line,
            "elapsed": f"{max(0, now - restart_start_ts):.2f}",
            "start_time": datetime.fromtimestamp(restart_start_ts).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "finish_time": datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _render_prompt(
        self,
        config_key: str,
        default: str,
        values: dict[str, str],
    ) -> str:
        template = str(self.config.get(config_key) or default)
        try:
            return format_prompt(template, values)
        except (ValueError, AttributeError) as exc:
            logger.warning(f"提示词 {config_key} 格式错误，已使用默认值：{exc}")
            return format_prompt(default, values)

    def _cache_platform_send_context(self, event: AstrMessageEvent) -> None:
        """保存重启后主动发送所需的平台临时上下文。"""
        self.cache["session_id"] = event.session_id
        self.cache["qqofficial_scene"] = ""
        self.cache["qqofficial_msg_id"] = ""

        platform = self.context.get_platform_inst(event.get_platform_id())
        if platform is None or platform.meta().name != QQ_OFFICIAL_PLATFORM_NAME:
            return

        # 群独立会话会把 event.session_id 改成 用户ID_群ID；适配器缓存用原始 ID。
        session_id = event.message_obj.session_id
        self.cache["session_id"] = session_id
        session = copy(event.session)
        session.session_id = session_id
        self.cache["umo"] = str(session)
        scenes = getattr(platform, "_session_scene", {})
        message_ids = getattr(platform, "_session_last_message_id", {})
        self.cache["qqofficial_scene"] = str(scenes.get(session_id) or "")
        self.cache["qqofficial_msg_id"] = str(
            getattr(event.message_obj, "message_id", "")
            or message_ids.get(session_id)
            or ""
        )

    def _restore_platform_send_context(self, platform: Any) -> None:
        """恢复 QQ 官方适配器重启时丢失的内存会话缓存。"""
        if platform.meta().name != QQ_OFFICIAL_PLATFORM_NAME:
            return

        session_id = str(self.cache.get("session_id") or "")
        scene = str(self.cache.get("qqofficial_scene") or "")
        message_id = str(self.cache.get("qqofficial_msg_id") or "")
        if not session_id or scene not in {"group", "channel", "friend"}:
            raise RuntimeError(
                "QQ 官方重启通知缺少原始会话 ID 或场景，无法恢复发送上下文"
            )
        if scene != "friend" and not message_id:
            raise RuntimeError("QQ 官方群/频道重启通知缺少消息 ID，无法恢复发送上下文")

        platform.remember_session_scene(session_id, scene)
        if message_id:
            platform.remember_session_message_id(session_id, message_id)

    async def _send_completed_notification_when_ready(self):
        platform_id = self._pending_restart.get("platform_id")
        restart_umo = self._pending_restart.get("umo")
        restart_start_ts = self._pending_restart.get("start_ts")

        if not restart_umo or not platform_id or not restart_start_ts:
            return

        restart_start_ts = float(restart_start_ts)
        deadline = time.monotonic() + NOTIFICATION_TIMEOUT
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self.cache != self._pending_restart:
                return
            platform = self.context.get_platform_inst(str(platform_id))
            if platform is None:
                await asyncio.sleep(NOTIFICATION_RETRY_INTERVAL)
                continue

            try:
                self._restore_platform_send_context(platform)
                values = self._prompt_values(
                    restart_start_ts=restart_start_ts,
                    before_memory=str(self.cache.get("memory_before") or "未知"),
                )
                msg = self._render_prompt(
                    "restart_completed_prompt",
                    DEFAULT_COMPLETED_PROMPT,
                    values,
                )
                sent = await asyncio.wait_for(
                    self.context.send_message(
                        session=str(restart_umo),
                        message_chain=MessageChain([Plain(msg)]),
                    ),
                    timeout=SEND_TIMEOUT,
                )
                if sent:
                    if self.cache == self._pending_restart:
                        self._clear_restart_cache()
                    logger.info("重启完成通知已发送")
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                logger.warning(f"重启完成通知发送失败，将重试：{exc}")

            await asyncio.sleep(NOTIFICATION_RETRY_INTERVAL)

        logger.error(
            f"重启完成通知在 {NOTIFICATION_TIMEOUT} 秒内发送失败，"
            f"缓存已保留供下次启动重试：{last_error or '平台未就绪'}"
        )

    def _clear_restart_cache(self) -> None:
        self.cache["platform_id"] = ""
        self.cache["umo"] = ""
        self.cache["start_ts"] = 0
        self.cache["memory_before"] = ""
        self.cache["session_id"] = ""
        self.cache["qqofficial_scene"] = ""
        self.cache["qqofficial_msg_id"] = ""
        self.config.save_config()

    # ================== 命令 ==================

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("重启", alias={"restart"})
    async def restart_system(self, event: AstrMessageEvent):
        """重启Astrbot"""
        restart_start_ts = time.time()
        memory = get_memory_placeholders()
        values = self._prompt_values(
            restart_start_ts=restart_start_ts,
            before_memory=memory["memory"],
        )
        msg = self._render_prompt("restart_prompt", DEFAULT_RESTART_PROMPT, values)
        if msg:
            await event.send(event.plain_result(msg))
        self.cache["platform_id"] = event.get_platform_id()
        self.cache["umo"] = event.unified_msg_origin
        self.cache["start_ts"] = restart_start_ts
        self.cache["memory_before"] = memory["memory"]
        self._cache_platform_send_context(event)
        self.config.save_config()

        await self.dashboard.restart()

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("定时重启")
    async def schedule_restart(self, event: AstrMessageEvent, mode: str | None = None):
        """定时重启 开/关"""
        if mode not in ["开", "关"]:
            await event.send(event.plain_result("正确格式：定时重启 开/关"))
            return
        is_restart = mode == "开"
        if is_restart:
            self.config["restart_switch"] = True
            self.config.save_config()
            yield event.plain_result(
                f"已开启定时重启: {cron_to_human(self.config['restart_cron'])}"
            )
            await self.scheduler.start()
        else:
            self.config["restart_switch"] = False
            self.config.save_config()
            yield event.plain_result("已关闭定时重启")
            await self.scheduler.shutdown()

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("重载")
    async def reload_plugin(
        self, event: AstrMessageEvent, target: str | int | None = None
    ):
        """重载 <插件名|序号|空|all>"""
        from astrbot.core.star.star import star_registry as sr

        # 过滤内置插件
        visible = [m for m in sr if not m.reserved]
        if not visible:
            yield event.plain_result("暂无插件")
            return

        # 1. 无参数 -> 展示带序号的插件列表（展示名优先）
        if target is None:
            lines = ["需指定插件序号："]
            for idx, meta in enumerate(visible, start=1):
                show = meta.display_name or meta.name
                lines.append(f"{idx}. {show}")
            await event.send(event.plain_result("\n".join(lines)))
            return

        # 2. 统一把 target 解析成“内部名” plugin_key
        plugin_key = None
        if isinstance(target, int) or str(target).isdigit():
            idx = int(target) - 1
            if 0 <= idx < len(visible):
                plugin_key = visible[idx].name
            else:
                yield event.plain_result("序号超出范围")
                return

        elif str(target).lower() == "all":
            plugin_key = None

        else:  # 字符串：支持展示名或内部名
            tgt = str(target)
            for meta in sr:
                if tgt in str(meta.display_name) or tgt in str(meta.name):
                    plugin_key = meta.name
                    break
            if plugin_key is None:
                yield event.plain_result("未找到该插件")
                return

        # 3. 真正重载
        success, error_message = await self.star_manager.reload(plugin_key)

        # 4. 结果回显：优先用展示名，没有再剥前缀
        if plugin_key is None:
            show_name = "所有插件"
        else:
            if meta := next(
                (m for m in sr if (m.name or m.module_path) == plugin_key), None
            ):
                show_name = str(meta.display_name or meta.name).removeprefix(
                    "astrbot_plugin_"
                )

        if success:
            yield event.plain_result(f"{show_name}重载成功")
        else:
            yield event.plain_result(f"{show_name}重载失败：{error_message}")
