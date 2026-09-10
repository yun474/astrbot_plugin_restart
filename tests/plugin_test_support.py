"""Load the real plugin with lightweight stand-ins for AstrBot and service clients."""

import importlib.util
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


def module(name, **attributes):
    result = ModuleType(name)
    result.__dict__.update(attributes)
    return result


class FakeStar:
    def __init__(self, context):
        self.context = context


class FakeConfig(dict):
    def __init__(self, cache=None):
        super().__init__(restart_switch=False, restart_cache=cache or {})
        self.save_config = MagicMock()


@dataclass
class FakeSession:
    platform_id: str
    message_type: str
    session_id: str

    def __str__(self):
        return f"{self.platform_id}:{self.message_type}:{self.session_id}"


def load_plugin():
    name = "_restart_test_plugin"
    if name in sys.modules:
        return sys.modules[name]
    root = Path(__file__).resolve().parents[1]

    def decorator(*args, **kwargs):
        return lambda fn: fn

    filters = SimpleNamespace(
        permission_type=decorator,
        command=decorator,
        on_astrbot_loaded=decorator,
        PermissionType=SimpleNamespace(ADMIN="admin"),
    )
    stubs = {
        "astrbot": module("astrbot"),
        "astrbot.api": module("astrbot.api", logger=logging.getLogger("restart-tests")),
        "astrbot.api.event": module("astrbot.api.event", filter=filters),
        "astrbot.api.star": module("astrbot.api.star", Context=object, Star=FakeStar),
        "astrbot.core.config.astrbot_config": module(
            "astrbot.core.config.astrbot_config", AstrBotConfig=FakeConfig
        ),
        "astrbot.core.message.components": module(
            "astrbot.core.message.components",
            Plain=lambda text: SimpleNamespace(text=text),
        ),
        "astrbot.core.message.message_event_result": module(
            "astrbot.core.message.message_event_result",
            MessageChain=lambda chain: SimpleNamespace(chain=chain),
        ),
        "astrbot.core.platform.astr_message_event": module(
            "astrbot.core.platform.astr_message_event", AstrMessageEvent=object
        ),
        "astrbot.core.star.star_manager": module(
            "astrbot.core.star.star_manager", PluginManager=object
        ),
        f"{name}.dashboard_client": module(
            f"{name}.dashboard_client",
            DashboardClient=lambda context: SimpleNamespace(
                initialize=AsyncMock(), terminate=AsyncMock(), restart=AsyncMock()
            ),
        ),
        f"{name}.restart_scheduler": module(
            f"{name}.restart_scheduler",
            RestartScheduler=lambda *args: SimpleNamespace(
                start=AsyncMock(), shutdown=AsyncMock()
            ),
        ),
    }
    spec = importlib.util.spec_from_file_location(
        name, root / "main.py", submodule_search_locations=[str(root)]
    )
    result = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {**stubs, name: result}):
        spec.loader.exec_module(result)
    sys.modules[name] = result
    return result


plugin_module = load_plugin()
RestartPlugin = plugin_module.RestartPlugin
