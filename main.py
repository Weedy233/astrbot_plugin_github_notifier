"""GitHub Notifier 主插件类"""

import asyncio
from typing import List

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.event import MessageChain
from astrbot.api.star import Context, Star

from .services.github_client import GitHubClient
from .services.subscription_manager import SubscriptionManager
from .services.event_poller import EventPoller
from .services.message_formatter import MessageFormatter
from .services.template_manager import TemplateManager
from .models.event_models import GitHubEvent


class GitHubNotifierPlugin(Star):
    """GitHub 仓库事件通知插件
    
    通过 GitHub Events API 轮询仓库事件，支持会话级订阅。
    """

    SUPPORTED_EVENTS = [
        "PushEvent",
        "ReleaseEvent",
        "IssuesEvent",
        "PullRequestEvent",
        "WatchEvent",
        "ForkEvent",
    ]

    def __init__(self, context: Context) -> None:
        self.context = context

        config = context.get_config() or {}

        self.github_token = config.get("github_token", "")
        self.poll_interval = max(config.get("poll_interval", 60), 30)
        self.max_events_per_message = max(config.get("max_events_per_message", 5), 1)
        self.use_etag = config.get("use_etag_cache", True)
        self.respect_poll_interval = config.get("respect_poll_interval", True)

        self.enabled_events = {
            "PushEvent": config.get("enable_push_event", True),
            "ReleaseEvent": config.get("enable_release_event", True),
            "IssuesEvent": config.get("enable_issues_event", False),
            "PullRequestEvent": config.get("enable_pull_request_event", False),
            "WatchEvent": config.get("enable_star_event", False),
            "ForkEvent": config.get("enable_fork_event", False),
        }

        self.github_client = GitHubClient(
            token=self.github_token,
            use_etag=self.use_etag,
        )
        self.subscription_manager = SubscriptionManager(self)
        self.event_poller = EventPoller(
            github_client=self.github_client,
            subscription_manager=self.subscription_manager,
            plugin=self,
            poll_interval=self.poll_interval,
            respect_poll_interval=self.respect_poll_interval,
        )
        self.template_manager = TemplateManager(config)
        self.message_formatter = MessageFormatter(self.template_manager)

        self.event_poller.set_event_callback(self._on_new_events)

    async def initialize(self):
        """插件初始化"""
        logger.info(
            f"[GitHubNotifier] 初始化完成，轮询间隔: {self.poll_interval} 秒，"
            f"Token: {'已设置' if self.github_token else '未设置'}"
        )

        # 启动轮询服务
        await self.event_poller.start()

    async def terminate(self):
        """插件卸载"""
        await self.event_poller.stop()
        await self.github_client.close()
        logger.info("[GitHubNotifier] 插件已卸载")

    async def _on_new_events(self, repo: str, events: List[GitHubEvent]):
        """处理新事件"""
        # 过滤已启用的事件类型
        filtered_events = [e for e in events if self.enabled_events.get(e.type, False)]

        if not filtered_events:
            return

        # 为 PushEvent 补充提交信息（Events API 经常返回空的 commits 数组）
        await self._enrich_push_events(repo, filtered_events)

        # 获取订阅此仓库的所有会话
        subscribers = await self.subscription_manager.get_subscribers(repo)

        if not subscribers:
            return

        # 格式化消息
        messages = self.message_formatter.format_events(
            repo, filtered_events, self.max_events_per_message
        )

        # 发送给所有订阅者
        for umo in subscribers:
            for message in messages:
                try:
                    chain = MessageChain().message(message)
                    await self.context.send_message(umo, chain)
                    await asyncio.sleep(0.5)  # 避免发送过快
                except Exception as e:
                    logger.error(f"[GitHubNotifier] 向 {umo} 发送消息失败: {e}")

    async def _enrich_push_events(self, repo: str, events: List[GitHubEvent]):
        """为 PushEvent 补充提交信息

        GitHub Events API 的 PushEvent 经常返回空的 size 和 commits 数组，
        需要调用 Compare API 来获取实际的提交信息。
        """
        from .models.event_models import PushEventPayload

        owner, repo_name = self._parse_repo(repo)

        for event in events:
            if event.type != "PushEvent":
                continue

            payload = PushEventPayload.from_dict(event.payload)

            if payload.commit_count > 0 and payload.commits:
                continue

            if not payload.before or not payload.after:
                continue

            if payload.before == "0000000000000000000000000000000000000000":
                continue

            total_commits, commits = await self.github_client.fetch_compare(
                owner, repo_name, payload.before, payload.after
            )

            if total_commits > 0:
                event.payload["size"] = total_commits
                event.payload["commits"] = commits
                event.payload["compare"] = f"https://github.com/{repo}/compare/{payload.before}...{payload.after}"
                logger.debug(
                    f"[GitHubNotifier] 通过 Compare API 补充 {repo} 的 {total_commits} 个提交信息"
                )

    # ==================== 命令处理器 ====================

    @filter.command("ghsub")
    async def subscribe_repo(self, event: AstrMessageEvent, repo: str = None):
        """订阅仓库通知
        
        用法: /ghsub owner/repo
        示例: /ghsub AstrBotDevs/AstrBot
        """
        if not repo:
            event.set_result(event.plain_result(
                "❌ 请提供仓库名\n\n"
                "用法: /ghsub owner/repo\n"
                "示例: /ghsub AstrBotDevs/AstrBot"
            ))
            return

        if not self._is_valid_repo(repo):
            event.set_result(event.plain_result(
                "❌ 无效的仓库格式\n\n格式应为: owner/repo\n示例: AstrBotDevs/AstrBot"
            ))
            return

        repo = repo.lower().strip()
        umo = event.unified_msg_origin

        if await self.subscription_manager.is_subscribed(repo, umo):
            event.set_result(event.plain_result(
                f"⚠️ 你已经订阅了 {repo}\n\n"
                f"使用 /ghlist 查看所有订阅\n"
                f"使用 /ghunsub {repo} 取消订阅"
            ))
            return

        event.set_result(event.plain_result(f"🔄 正在检查仓库 {repo} ..."))

        owner, repo_name = self._parse_repo(repo)
        is_accessible, error = await self.github_client.check_repository_access(
            owner, repo_name
        )

        if not is_accessible:
            event.set_result(event.plain_result(
                f"❌ 无法访问仓库 {repo}\n\n"
                f"原因: {error}\n\n"
                f"如果是私有仓库，请在配置中设置 GitHub Token"
            ))
            return

        event_types = [k for k, v in self.enabled_events.items() if v]

        await self.subscription_manager.subscribe(
            repo=repo,
            umo=umo,
            event_types=event_types,
        )

        await self.event_poller.initialize_repo(repo)

        event.set_result(event.plain_result(
            f"✅ 成功订阅 {repo}\n\n"
            f"📋 监控事件类型: {', '.join(event_types)}\n"
            f"⏰ 轮询间隔: {self.poll_interval} 秒\n\n"
            f"💡 新的事件将自动推送到此会话"
        ))

    @filter.command("ghunsub")
    async def unsubscribe_repo(self, event: AstrMessageEvent, repo: str = None):
        """取消订阅仓库通知
        
        用法: /ghunsub owner/repo
        不提供参数则取消所有订阅
        """
        umo = event.unified_msg_origin

        if not repo:
            unsubscribed = await self.subscription_manager.unsubscribe_all(umo)

            if unsubscribed:
                event.set_result(event.plain_result(
                    f"✅ 已取消所有订阅\n\n取消的仓库: {', '.join(unsubscribed)}"
                ))
            else:
                event.set_result(event.plain_result(
                    "📭 你没有订阅任何仓库\n\n使用 /ghsub owner/repo 订阅仓库"
                ))
            return

        if not self._is_valid_repo(repo):
            event.set_result(event.plain_result(
                "❌ 无效的仓库格式\n\n格式应为: owner/repo\n示例: AstrBotDevs/AstrBot"
            ))
            return

        repo = repo.lower().strip()

        if await self.subscription_manager.unsubscribe(repo, umo):
            event.set_result(event.plain_result(
                f"✅ 已取消订阅 {repo}\n\n使用 /ghlist 查看剩余订阅"
            ))
        else:
            event.set_result(event.plain_result(
                f"⚠️ 你没有订阅 {repo}\n\n使用 /ghlist 查看所有订阅"
            ))

    @filter.command("ghlist")
    async def list_subscriptions(self, event: AstrMessageEvent):
        """列出当前会话的所有订阅"""
        umo = event.unified_msg_origin
        subscriptions = await self.subscription_manager.get_subscriptions(umo)
        message = self.message_formatter.format_subscription_list(subscriptions)
        event.set_result(event.plain_result(message))

    @filter.command("ghcheck")
    async def check_now(self, event: AstrMessageEvent, repo: str = None):
        """立即检查仓库更新
        
        用法: /ghcheck [owner/repo]
        不提供参数则检查所有订阅的仓库
        """
        umo = event.unified_msg_origin

        if repo:
            if not self._is_valid_repo(repo):
                event.set_result(event.plain_result("❌ 无效的仓库格式"))
                return

            repo = repo.lower().strip()
            event.set_result(event.plain_result(f"🔄 正在检查 {repo} ..."))

            events = await self.event_poller.force_poll(repo)

            if events:
                filtered = [e for e in events if self.enabled_events.get(e.type, False)]

                if filtered:
                    messages = self.message_formatter.format_events(
                        repo, filtered, self.max_events_per_message
                    )
                    for msg in messages:
                        event.set_result(event.plain_result(msg))
                else:
                    event.set_result(event.plain_result(
                        f"📭 {repo} 没有新的事件\n(注意: 部分事件类型可能被禁用)"
                    ))
            else:
                event.set_result(event.plain_result(f"📭 {repo} 没有新的事件"))
        else:
            subscriptions = await self.subscription_manager.get_subscriptions(umo)

            if not subscriptions:
                event.set_result(event.plain_result(
                    "📭 你没有订阅任何仓库\n\n使用 /ghsub owner/repo 订阅仓库"
                ))
                return

            event.set_result(event.plain_result(
                f"🔄 正在检查 {len(subscriptions)} 个订阅的仓库 ..."
            ))

            checked = 0
            found_events = 0

            for sub in subscriptions:
                events = await self.event_poller.force_poll(sub.repo)
                if events:
                    filtered = [
                        e for e in events if self.enabled_events.get(e.type, False)
                    ]
                    found_events += len(filtered)
                    if filtered:
                        await self._on_new_events(sub.repo, events)
                checked += 1
                await asyncio.sleep(0.5)

            event.set_result(event.plain_result(
                f"✅ 检查完成\n\n检查了 {checked} 个仓库\n发现 {found_events} 个新事件"
            ))

    @filter.command("ghstatus")
    async def show_status(self, event: AstrMessageEvent):
        """显示插件状态"""
        stats = self.subscription_manager.get_stats()
        poll_stats = self.event_poller.get_stats()

        lines = [
            "📊 GitHub Notifier 状态",
            "",
            "🔧 配置:",
            f"  Token: {'✅ 已设置' if self.github_token else '❌ 未设置'}",
            f"  轮询间隔: {self.poll_interval} 秒",
            f"  ETag 缓存: {'启用' if self.use_etag else '禁用'}",
            "",
            "📈 统计:",
            f"  监控仓库数: {stats['repos']}",
            f"  活跃订阅数: {stats['subscriptions']}",
            f"  轮询运行中: {'是' if poll_stats['running'] else '否'}",
            "",
            "📋 启用的通知类型:",
        ]

        for event_type, enabled in self.enabled_events.items():
            emoji = "✅" if enabled else "❌"
            name = event_type.replace("Event", "").replace("PullRequest", "PR")
            lines.append(f"  {emoji} {name}")

        lines.extend(
            [
                "",
                "💡 提示:",
                "  /ghlist - 查看订阅列表",
                "  /ghsub owner/repo - 订阅仓库",
                "  /ghunsub owner/repo - 取消订阅",
            ]
        )

        event.set_result(event.plain_result("\n".join(lines)))

    @filter.command("ghelp")
    async def show_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = """🐙 GitHub Notifier 插件使用指南

📌 基础命令:
  /ghsub <owner/repo>    - 订阅仓库通知
  /ghunsub <owner/repo>  - 取消订阅
  /ghlist                - 查看订阅列表
  /ghcheck [owner/repo]  - 立即检查更新
  /ghstatus              - 显示插件状态
  /ghelp                 - 显示此帮助

📋 示例:
  /ghsub AstrBotDevs/AstrBot
  /ghunsub AstrBotDevs/AstrBot
  /ghcheck AstrBotDevs/AstrBot

🔧 配置说明:
  1. 在插件配置中设置 GitHub Token 以访问私有仓库
  2. Token 获取: GitHub Settings → Developer settings → Personal access tokens
  3. 可自定义监控的事件类型和轮询间隔

💡 提示:
  - 支持 public 和 private 仓库
  - 默认只监控 Push 和 Release 事件
  - 使用 ETag 缓存减少 API 调用
"""
        event.set_result(event.plain_result(help_text))

    # ==================== 辅助方法 ====================

    @staticmethod
    def _is_valid_repo(repo: str) -> bool:
        """验证仓库名格式"""
        if not repo or "/" not in repo:
            return False
        parts = repo.split("/")
        if len(parts) != 2:
            return False
        owner, name = parts
        # 简单的验证: 不能为空，不能包含空格
        return bool(owner) and bool(name) and " " not in owner and " " not in name

    @staticmethod
    def _parse_repo(repo: str) -> tuple:
        """解析仓库名"""
        parts = repo.split("/")
        if len(parts) == 2:
            return parts[0], parts[1]
        return None, None
