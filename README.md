# GitHub Notifier for AstrBot

通过 GitHub Events API 轮询仓库事件，支持会话级别的订阅管理。

## 功能特性

- **会话级订阅**: 每个会话（群聊/私聊）独立订阅仓库
- **多事件支持**: Push、Release、Issues、PR、Star、Fork 事件
- **公有/私有仓库**: 支持 public 仓库，通过 Token 访问 private 仓库
- **ETag 缓存**: 减少 API 调用，304 响应不消耗速率限制
- **智能轮询**: 支持 GitHub 建议的轮询间隔动态调整
- **模块化架构**: 拆分解耦，易于扩展和维护

## 安装

1. 将插件文件夹复制到 AstrBot 的 `data/plugins/` 目录
2. 重启 AstrBot 或热重载插件
3. 在 WebUI 中配置 GitHub Token（可选，用于访问私有仓库）

## 配置

在 AstrBot WebUI → 插件管理 → 配置 中设置:

| 配置项 | 说明 | 默认值 |
|-------|------|--------|
| `github_token` | GitHub API Token | 空 |
| `poll_interval` | 轮询间隔（秒） | 60 |
| `max_events_per_message` | 单条消息最大事件数 | 5 |
| `enable_push_event` | 启用 Push 事件通知 | true |
| `enable_release_event` | 启用 Release 事件通知 | true |
| `enable_issues_event` | 启用 Issues 事件通知 | false |
| `enable_pull_request_event` | 启用 PR 事件通知 | false |
| `enable_star_event` | 启用 Star 事件通知 | false |
| `enable_fork_event` | 启用 Fork 事件通知 | false |
| `use_etag_cache` | 启用 ETag 缓存 | true |
| `respect_poll_interval` | 遵守 GitHub 轮询建议 | true |

### 获取 GitHub Token

1. 访问 GitHub Settings → Developer settings → Personal access tokens
2. 生成新的 Token
3. 建议权限: `repo`（访问私有仓库）、`public_repo`（访问公有仓库）

## 使用指南

### 基础命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `/ghsub <owner/repo>` | 订阅仓库 | `/ghsub AstrBotDevs/AstrBot` |
| `/ghunsub <owner/repo>` | 取消订阅 | `/ghunsub AstrBotDevs/AstrBot` |
| `/ghlist` | 查看订阅列表 | `/ghlist` |
| `/ghcheck [owner/repo]` | 立即检查更新 | `/ghcheck` 或 `/ghcheck owner/repo` |
| `/ghstatus` | 查看插件状态 | `/ghstatus` |
| `/ghelp` | 显示帮助 | `/ghelp` |

### 使用示例

订阅仓库:
```
/ghsub AstrBotDevs/AstrBot
```

查看订阅:
```
/ghlist
```

立即检查所有订阅仓库:
```
/ghcheck
```

取消订阅:
```
/ghunsub AstrBotDevs/AstrBot
```

## 项目结构

```
astrbot_plugin_github_notifier/
├── main.py                    # 主插件类
├── metadata.yaml              # 插件元数据
├── _conf_schema.json         # 配置模式
├── requirements.txt          # 依赖
├── README.md                 # 本文件
├── services/                 # 服务层
│   ├── __init__.py
│   ├── github_client.py      # GitHub API 客户端
│   ├── subscription_manager.py  # 订阅管理
│   ├── event_poller.py       # 事件轮询
│   └── message_formatter.py  # 消息格式化
└── models/                   # 数据模型
    ├── __init__.py
    └── event_models.py       # 事件模型
```

## 注意事项

- **速率限制**: 无 Token 时 60 次/小时，有 Token 时 5000 次/小时
- **事件延迟**: GitHub Events API 可能有 30 秒到 6 小时的延迟
- **事件保留**: GitHub 只保留最近 30 天的事件
- **并发限制**: 避免过多的订阅仓库，可能触发速率限制

## 许可证

MIT License
