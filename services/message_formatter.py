"""消息格式化服务 - 将 GitHub 事件格式化为聊天消息"""

from typing import List

from ..models.event_models import (
    GitHubEvent,
    PushEventPayload,
    ReleaseEventPayload,
    IssuesEventPayload,
    PullRequestEventPayload,
    StarEventPayload,
    ForkEventPayload,
)


class MessageFormatter:
    """消息格式化器

    将 GitHub 事件转换为适合聊天展示的文本消息。
    支持多种事件类型的格式化。
    """

    @staticmethod
    def format_events(
        repo: str,
        events: List[GitHubEvent],
        max_events: int = 5,
    ) -> List[str]:
        """格式化事件列表为多条消息

        Args:
            repo: 仓库名
            events: 事件列表
            max_events: 单条消息的最大事件数

        Returns:
            消息列表
        """
        if not events:
            return []

        # 按事件类型分组
        messages = []

        # 限制每个消息的事件数
        for i in range(0, len(events), max_events):
            chunk = events[i : i + max_events]
            message = MessageFormatter._format_event_chunk(
                repo, chunk, i + 1, len(events)
            )
            messages.append(message)

        return messages

    @staticmethod
    def _format_event_chunk(
        repo: str, events: List[GitHubEvent], start_index: int, total: int
    ) -> str:
        """格式化事件块"""
        if len(events) == 1:
            return MessageFormatter._format_single_event(repo, events[0])

        lines = [
            f"📢 [{repo}] 新动态 ({start_index}-{start_index + len(events) - 1}/{total})",
            "",
        ]

        for i, event in enumerate(events, start_index):
            formatted = MessageFormatter._format_event_brief(event)
            lines.append(f"{i}. {formatted}")

        return "\n".join(lines)

    @staticmethod
    def _format_single_event(repo: str, event: GitHubEvent) -> str:
        """格式化单个事件"""
        event_type = event.type

        if event_type == "PushEvent":
            return MessageFormatter._format_push_event(repo, event)
        elif event_type == "ReleaseEvent":
            return MessageFormatter._format_release_event(repo, event)
        elif event_type == "IssuesEvent":
            return MessageFormatter._format_issues_event(repo, event)
        elif event_type == "PullRequestEvent":
            return MessageFormatter._format_pull_request_event(repo, event)
        elif event_type == "WatchEvent":
            return MessageFormatter._format_star_event(repo, event)
        elif event_type == "ForkEvent":
            return MessageFormatter._format_fork_event(repo, event)
        else:
            return MessageFormatter._format_generic_event(repo, event)

    @staticmethod
    def _format_event_brief(event: GitHubEvent) -> str:
        """格式化事件摘要（用于列表）"""
        event_type = event.type
        actor = event.actor_login

        if event_type == "PushEvent":
            payload = PushEventPayload.from_dict(event.payload)
            branch = payload.branch
            commits = payload.commit_count
            return f"📝 {actor} 推送了 {commits} 个提交到 {branch}"

        elif event_type == "ReleaseEvent":
            payload = ReleaseEventPayload.from_dict(event.payload)
            tag = payload.tag_name
            action = payload.action
            return f"🏷️ {actor} {action} 了版本 {tag}"

        elif event_type == "IssuesEvent":
            payload = IssuesEventPayload.from_dict(event.payload)
            action = payload.action
            number = payload.issue_number
            title = (
                payload.issue_title[:30] + "..."
                if len(payload.issue_title) > 30
                else payload.issue_title
            )
            return f"🐛 {actor} {action} Issue #{number}: {title}"

        elif event_type == "PullRequestEvent":
            payload = PullRequestEventPayload.from_dict(event.payload)
            action = payload.action
            number = payload.pr_number
            title = (
                payload.pr_title[:30] + "..."
                if len(payload.pr_title) > 30
                else payload.pr_title
            )
            return f"🔀 {actor} {action} PR #{number}: {title}"

        elif event_type == "WatchEvent":
            return f"⭐ {actor} Star 了仓库"

        elif event_type == "ForkEvent":
            payload = ForkEventPayload.from_dict(event.payload)
            forked_repo = payload.forked_repo_name
            return f"🍴 {actor} Fork 了仓库到 {forked_repo}"

        else:
            return f"📌 {actor} 触发了 {event_type}"

    @staticmethod
    def _format_push_event(repo: str, event: GitHubEvent) -> str:
        """格式化 Push 事件"""
        payload = PushEventPayload.from_dict(event.payload)

        lines = [
            f"📝 [{repo}] 代码推送",
            "",
            f"👤 推送者: {event.actor_login}",
            f"🌿 分支: {payload.branch}",
            f"🔢 提交数: {payload.commit_count}",
        ]

        if payload.commits:
            lines.append("")
            lines.append("📋 提交详情:")
            for i, commit in enumerate(payload.commits[:5], 1):
                sha = commit.get("sha", "")[:7]
                message = commit.get("message", "").split("\n")[0][:50]
                lines.append(f"  {i}. [{sha}] {message}")

            if len(payload.commits) > 5:
                lines.append(f"  ... 还有 {len(payload.commits) - 5} 个提交")

        if payload.compare:
            lines.append("")
            lines.append(f"🔗 对比: {payload.compare}")

        return "\n".join(lines)

    @staticmethod
    def _format_release_event(repo: str, event: GitHubEvent) -> str:
        """格式化 Release 事件"""
        payload = ReleaseEventPayload.from_dict(event.payload)

        lines = [
            f"🏷️ [{repo}] 版本发布",
            "",
            f"👤 发布者: {event.actor_login}",
            f"📌 标签: {payload.tag_name}",
            f"📝 名称: {payload.release_name}",
        ]

        if payload.is_prerelease:
            lines.append("⚠️ 预发布版本")

        lines.append("")
        lines.append(f"🔗 详情: {payload.release_url}")

        return "\n".join(lines)

    @staticmethod
    def _format_issues_event(repo: str, event: GitHubEvent) -> str:
        """格式化 Issues 事件"""
        payload = IssuesEventPayload.from_dict(event.payload)

        action_map = {
            "opened": "🆕 创建",
            "closed": "✅ 关闭",
            "reopened": "🔄 重新打开",
            "edited": "✏️ 编辑",
        }
        action = action_map.get(payload.action, f"📌 {payload.action}")

        lines = [
            f"🐛 [{repo}] Issue 更新",
            "",
            f"👤 操作用户: {event.actor_login}",
            f"📝 操作: {action}",
            f"🔢 Issue: #{payload.issue_number}",
            f"📋 标题: {payload.issue_title}",
            f"📊 状态: {payload.state}",
            "",
            f"🔗 链接: {payload.issue_url}",
        ]

        return "\n".join(lines)

    @staticmethod
    def _format_pull_request_event(repo: str, event: GitHubEvent) -> str:
        """格式化 Pull Request 事件"""
        payload = PullRequestEventPayload.from_dict(event.payload)

        action_map = {
            "opened": "🆕 创建",
            "closed": "✅ 关闭",
            "reopened": "🔄 重新打开",
            "edited": "✏️ 编辑",
            "synchronize": "🔄 同步",
        }
        action = action_map.get(payload.action, f"📌 {payload.action}")

        if payload.action == "closed" and payload.merged:
            action = "🔀 合并"

        lines = [
            f"🔀 [{repo}] Pull Request 更新",
            "",
            f"👤 操作用户: {event.actor_login}",
            f"📝 操作: {action}",
            f"🔢 PR: #{payload.pr_number}",
            f"📋 标题: {payload.pr_title}",
            f"📊 状态: {payload.state}",
            "",
            f"🔗 链接: {payload.pr_url}",
        ]

        return "\n".join(lines)

    @staticmethod
    def _format_star_event(repo: str, event: GitHubEvent) -> str:
        """格式化 Star 事件"""
        payload = StarEventPayload.from_dict(event.payload)

        if payload.is_starred:
            return (
                f"⭐ [{repo}] {event.actor_login} Star 了仓库！\n\n🔗 {event.repo_url}"
            )
        else:
            return f"💔 [{repo}] {event.actor_login} 取消了 Star"

    @staticmethod
    def _format_fork_event(repo: str, event: GitHubEvent) -> str:
        """格式化 Fork 事件"""
        payload = ForkEventPayload.from_dict(event.payload)

        return (
            f"🍴 [{repo}] 仓库被 Fork\n"
            f"\n"
            f"👤 Fork 者: {event.actor_login}\n"
            f"📁 Fork 到: {payload.forked_repo_name}\n"
            f"\n"
            f"🔗 {payload.forked_repo_url}"
        )

    @staticmethod
    def _format_generic_event(repo: str, event: GitHubEvent) -> str:
        """格式化通用事件"""
        return (
            f"📌 [{repo}] {event.type}\n"
            f"\n"
            f"👤 触发者: {event.actor_login}\n"
            f"⏰ 时间: {event.created_at.isoformat()}\n"
            f"\n"
            f"🔗 {event.repo_url}"
        )

    @staticmethod
    def format_subscription_list(subscriptions: List) -> str:
        """格式化订阅列表"""
        if not subscriptions:
            return "📭 当前没有订阅任何仓库\n\n使用 /ghsub owner/repo 订阅仓库"

        lines = ["📋 你的仓库订阅列表:", ""]

        for i, sub in enumerate(subscriptions, 1):
            repo = sub.repo
            event_types = ", ".join(sub.event_types[:3])
            if len(sub.event_types) > 3:
                event_types += f" 等 {len(sub.event_types)} 种"

            lines.append(f"{i}. 📁 {repo}")
            lines.append(f"   事件类型: {event_types}")

        lines.append("")
        lines.append(
            "💡 提示: 使用 /ghsub owner/repo 添加订阅，/ghunsub owner/repo 取消订阅"
        )

        return "\n".join(lines)

    @staticmethod
    def format_stats(repo_count: int, sub_count: int, poll_stats: dict) -> str:
        """格式化统计信息"""
        lines = [
            "📊 GitHub 通知插件状态",
            "",
            f"📁 监控仓库数: {repo_count}",
            f"🔔 活跃订阅数: {sub_count}",
            "",
            "⚙️ 轮询状态:",
            f"  运行中: {'是' if poll_stats.get('running') else '否'}",
            f"  轮询间隔: {poll_stats.get('interval', 0)} 秒",
            "",
            "📝 已处理事件:",
        ]

        processed = poll_stats.get("processed_events", {})
        if processed:
            for repo, count in processed.items():
                lines.append(f"  {repo}: {count} 个事件")
        else:
            lines.append("  暂无")

        return "\n".join(lines)
