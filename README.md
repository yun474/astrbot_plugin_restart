
<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_restart?name=astrbot_plugin_restart&theme=minecraft&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

# astrbot_plugin_restart

_✨ [astrbot](https://github.com/AstrBotDevs/AstrBot) 重启插件 ✨_  

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)
[![GitHub](https://img.shields.io/badge/维护-yun474-blue)](https://github.com/yun474)

</div>

> 注意：Astrbot-v4.24.4更改了部分逻辑，故本插件从v1.1.0开始仅支持Astrbot-v4.24.4之后的版本

## 🤝 介绍

用命令重启、定时自动重启 AstrBot

本仓库基于 [Zhalslar/astrbot_plugin_restart](https://github.com/Zhalslar/astrbot_plugin_restart) 修改维护。

## 📦 安装

- 可以直接在astrbot的插件市场搜索astrbot_plugin_restart，点击安装，耐心等待安装完成即可
- 若是安装失败，可以尝试直接克隆源码：

```bash
# 克隆仓库到插件目录
cd /AstrBot/data/plugins
git clone https://github.com/yun474/astrbot_plugin_restart

# 控制台重启AstrBot
```

## ⌨️ 使用说明

### 命令表

|     命令      |                    说明                    |
|:-------------:|:-----------------------------------------------:|
| 重启 / restart | 重启 AstrBot |
| 定时重启 开 | 开启按 Cron 表达式定时重启 |
| 定时重启 关 | 关闭定时重启 |

### 自定义重启提示词

在插件配置页可修改：

- `发起重启提示词`：收到手动重启命令时发送。
- `重启完成提示词`：AstrBot 重启后，原会话平台恢复可用时发送。

两种提示词均支持以下占位符：

| 占位符 | 内容 | 示例 |
|:--|:--|:--|
| `{memory}` | 当前已用/总内存及占用率 | `8.5GB/16.0GB(53.1%)` |
| `{used_memory}` | 当前已用内存 | `8.5GB` |
| `{available_memory}` | 当前可用内存 | `7.5GB` |
| `{total_memory}` | 总内存 | `16.0GB` |
| `{memory_percent}` | 当前内存占用率 | `53.1%` |
| `{before_memory}` | 发起重启前的完整内存信息 | `8.5GB/16.0GB(53.1%)` |
| `{after_memory}` | 重启后的完整内存信息 | `7.9GB/16.0GB(49.4%)` |
| `{elapsed}` | 从发起重启到通知发送的耗时（秒） | `12.34` |
| `{start_time}` | 发起重启时间 | `2026-08-07 09:30:00` |
| `{finish_time}` | 提示词渲染时间 | `2026-08-07 09:30:12` |
| `{memory_line}` | 兼容原“显示内存”开关的整行文本 | `\n内存：8.5GB/16.0GB(53.1%)` |

例如，可将完成提示设置为：

```text
AstrBot 回来了，用时 {elapsed} 秒
重启前：{before_memory}
重启后：{after_memory}
```

未知占位符会原样保留；花括号格式错误时会回退到默认提示词并记录警告。`显示内存使用情况` 开关只控制默认模板中的 `{memory_line}`，不会屏蔽你主动写入自定义模板的内存占位符。

> 定时重启没有命令来源会话，因此不会发送发起/完成提示；自定义提示用于手动执行 `重启` / `restart` 的场景。

## 👥 贡献指南

- 🌟 Star 这个项目！（点右上角的星星，感谢支持！）
- 🐛 提交 Issue 报告问题
- 💡 提出新功能建议
- 🔧 提交 Pull Request 改进代码

## 📌 注意事项

- 本修改版问题请在 [yun474/astrbot_plugin_restart](https://github.com/yun474/astrbot_plugin_restart/issues) 提交 Issue。
