# utils.py
from typing import Any


class SafeFormatDict(dict[str, Any]):
    """保留未知占位符，避免配置笔误阻断重启。"""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def format_prompt(template: str, values: dict[str, Any]) -> str:
    """使用给定值渲染提示词，未知占位符保持原样。"""
    return template.format_map(SafeFormatDict(values))


def cron_to_human(cron: str) -> str:
    """
    将 5 段 cron（分 时 日 月 周）转换为中文易读描述
    """
    parts = cron.strip().split()
    if len(parts) != 5:
        raise ValueError("Cron 表达式必须是 5 段（分 时 日 月 周）")

    minute, hour, day, month, week = parts

    def parse_field(val, unit, names=None):
        if val == "*":
            return f"每{unit}"
        if val.startswith("*/"):
            return f"每{val[2:]}{unit}"
        if "," in val:
            items = val.split(",")
            return "、".join(
                names.get(i, f"{i}{unit}") if names else f"{i}{unit}" for i in items
            )
        if "-" in val:
            start, end = val.split("-")
            if names:
                return f"{names[start]}至{names[end]}"
            return f"{start}到{end}{unit}"
        return names.get(val, f"{val}{unit}") if names else f"{val}{unit}"

    week_names = {
        "0": "周日",
        "1": "周一",
        "2": "周二",
        "3": "周三",
        "4": "周四",
        "5": "周五",
        "6": "周六",
    }

    desc = []

    # 周
    if week != "*":
        desc.append(parse_field(week, "", week_names))

    # 月
    if month != "*":
        desc.append(parse_field(month, "月"))

    # 日
    if day != "*":
        desc.append(parse_field(day, "日"))
    elif week == "*":
        desc.append("每天")

    # 时间
    if hour == "*" and minute == "*":
        desc.append("每分钟")
    else:
        time_desc = []
        if hour != "*":
            time_desc.append(parse_field(hour, "点"))
        if minute != "*":
            time_desc.append(parse_field(minute, "分"))
        desc.append(" ".join(time_desc))

    return " ".join(desc)


def get_memory_placeholders(decimal_places: int = 1) -> dict[str, str]:
    """
    获取当前设备内存情况，支持自定义小数位数

    Args:
        decimal_places (int): 小数位数，默认为1位

    Returns:
        可直接用于提示词渲染的内存信息字典。
    """
    import psutil

    # 获取内存信息
    memory = psutil.virtual_memory()

    # 计算已用内存 (总内存 - 可用内存)
    total_memory = memory.total
    available_memory = memory.available
    used_memory = total_memory - memory.available

    # 转换为GB单位
    total_gb = total_memory / (1024**3)
    available_gb = available_memory / (1024**3)
    used_gb = used_memory / (1024**3)

    # 计算使用百分比
    usage_percent = (used_memory / total_memory) * 100

    number_format = f"{{:.{decimal_places}f}}GB"
    used = number_format.format(used_gb)
    available = number_format.format(available_gb)
    total = number_format.format(total_gb)
    percent = f"{usage_percent:.1f}%"
    return {
        "memory": f"{used}/{total}({percent})",
        "used_memory": used,
        "available_memory": available,
        "total_memory": total,
        "memory_percent": percent,
    }


def get_memory_info(decimal_places: int = 1) -> str:
    """兼容旧调用：返回“已用/总量(占用率)”格式的内存信息。"""
    return get_memory_placeholders(decimal_places)["memory"]
