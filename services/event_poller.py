"""事件轮询服务 - 后台定时轮询仓库事件"""

import asyncio
from typing import Callable, Dict, List, Optional, Set
from datetime import datetime

from astrbot.api import logger

from .github_client import GitHubClient
from .subscription_manager import SubscriptionManager
from ..models.event_models import GitHubEvent


class EventPoller:
    """事件轮询服务

    负责:
    - 定时轮询所有订阅的仓库
    - 跟踪已处理的事件 ID 避免重复推送
    - 按仓库维护轮询状态
    - 处理事件过滤（按类型、时间）
    """

    def __init__(
        self,
        github_client: GitHubClient,
        subscription_manager: SubscriptionManager,
        poll_interval: int = 60,
        respect_poll_interval: bool = True,
    ):
        self.github_client = github_client
        self.subscription_manager = subscription_manager
        self.poll_interval = poll_interval
        self.respect_poll_interval = respect_poll_interval

        # 轮询任务
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # 已处理的事件 ID: repo -> {event_id}
        self._processed_events: Dict[str, Set[str]] = {}

        # 上次轮询时间: repo -> timestamp
        self._last_poll_time: Dict[str, datetime] = {}

        # 事件回调: 收到新事件时调用
        self._event_callback: Optional[Callable[[str, List[GitHubEvent]], None]] = None

        # 每个仓库最大处理事件数
        self.max_events_per_poll = 100

    def set_event_callback(self, callback: Callable[[str, List[GitHubEvent]], None]):
        """设置事件回调函数"""
        self._event_callback = callback

    def _parse_repo(self, repo: str) -> tuple:
        """解析仓库名"""
        parts = repo.split("/")
        if len(parts) == 2:
            return parts[0], parts[1]
        return None, None

    async def start(self):
        """启动轮询服务"""
        if self._running:
            logger.warning("[EventPoller] 轮询服务已在运行")
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(f"[EventPoller] 轮询服务已启动，轮询间隔: {self.poll_interval} 秒")

    async def stop(self):
        """停止轮询服务"""
        if not self._running:
            return

        self._running = False

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("[EventPoller] 轮询服务已停止")

    async def _poll_loop(self):
        """轮询循环"""
        # 首次启动延迟 10 秒，避免立即请求
        await asyncio.sleep(10)

        while self._running:
            try:
                await self._do_poll()
            except asyncio.CancelledError:
                logger.info("[EventPoller] 轮询循环已取消")
                break
            except Exception as e:
                logger.error(f"[EventPoller] 轮询出错: {e}")

            # 计算等待时间
            wait_time = self.poll_interval
            if self.respect_poll_interval:
                # 使用 GitHub 建议的轮询间隔
                wait_time = max(self.github_client.get_poll_interval(), wait_time)

            logger.debug(f"[EventPoller] 等待 {wait_time} 秒后进行下一次轮询")
            await asyncio.sleep(wait_time)

    async def _do_poll(self):
        """执行一次轮询"""
        repos = await self.subscription_manager.get_all_repos()

        if not repos:
            logger.debug("[EventPoller] 没有订阅的仓库，跳过轮询")
            return

        logger.debug(f"[EventPoller] 开始轮询 {len(repos)} 个仓库")

        for repo in repos:
            if not self._running:
                break

            try:
                await self._poll_repo(repo)
            except Exception as e:
                logger.error(f"[EventPoller] 轮询 {repo} 时出错: {e}")

            # 短暂延迟，避免并发请求触发速率限制
            await asyncio.sleep(1)

    async def _poll_repo(self, repo: str):
        """轮询单个仓库"""
        owner, repo_name = self._parse_repo(repo)
        if not owner or not repo_name:
            logger.warning(f"[EventPoller] 无效的仓库名: {repo}")
            return

        # 获取事件
        events, has_new = await self.github_client.fetch_events(
            owner, repo_name, per_page=self.max_events_per_poll
        )

        if not has_new or not events:
            return

        # 过滤已处理的事件
        new_events = self._filter_new_events(repo, events)

        if new_events:
            logger.info(f"[EventPoller] {repo} 发现 {len(new_events)} 个新事件")

            # 记录事件 ID
            self._record_events(repo, events)

            # 调用回调
            if self._event_callback:
                try:
                    await self._event_callback(repo, new_events)
                except Exception as e:
                    logger.error(f"[EventPoller] 处理 {repo} 事件回调时出错: {e}")

        # 更新轮询时间
        self._last_poll_time[repo] = datetime.utcnow()

    def _filter_new_events(
        self, repo: str, events: List[GitHubEvent]
    ) -> List[GitHubEvent]:
        """过滤出未处理过的新事件"""
        if repo not in self._processed_events:
            self._processed_events[repo] = set()

        # 只保留未处理过的事件
        new_events = []
        for event in events:
            if event.id not in self._processed_events[repo]:
                new_events.append(event)

        return new_events

    def _record_events(self, repo: str, events: List[GitHubEvent]):
        """记录已处理的事件 ID"""
        if repo not in self._processed_events:
            self._processed_events[repo] = set()

        # 添加新的事件 ID
        for event in events:
            self._processed_events[repo].add(event.id)

        # 限制存储的事件 ID 数量（保留最近 500 个）
        if len(self._processed_events[repo]) > 500:
            # 将 set 转为列表，保留后 500 个
            event_list = list(self._processed_events[repo])
            self._processed_events[repo] = set(event_list[-500:])

    async def force_poll(self, repo: str) -> List[GitHubEvent]:
        """强制轮询指定仓库（用于手动触发）"""
        owner, repo_name = self._parse_repo(repo)
        if not owner or not repo_name:
            return []

        events, _ = await self.github_client.fetch_events(
            owner, repo_name, per_page=self.max_events_per_poll
        )

        if events:
            self._record_events(repo, events)
            self._last_poll_time[repo] = datetime.utcnow()

        return events

    def clear_processed_cache(self, repo: str = None):
        """清除已处理事件缓存"""
        if repo:
            self._processed_events.pop(repo, None)
        else:
            self._processed_events.clear()

    def get_stats(self) -> Dict:
        """获取轮询统计"""
        return {
            "running": self._running,
            "interval": self.poll_interval,
            "processed_events": {
                repo: len(ids) for repo, ids in self._processed_events.items()
            },
            "last_poll": {
                repo: t.isoformat() if t else None
                for repo, t in self._last_poll_time.items()
            },
        }
