import asyncio
from typing import Callable, Dict, List, Optional, Set
from datetime import datetime

from astrbot.api import logger

from .github_client import GitHubClient
from .subscription_manager import SubscriptionManager
from ..models.event_models import GitHubEvent


class EventPoller:
    KV_KEY_INITIALIZED = "github_notifier_initialized_"
    KV_KEY_LAST_EVENT_TIME = "github_notifier_last_event_time_"

    def __init__(
        self,
        github_client: GitHubClient,
        subscription_manager: SubscriptionManager,
        plugin,
        poll_interval: int = 60,
        respect_poll_interval: bool = True,
    ):
        self.github_client = github_client
        self.subscription_manager = subscription_manager
        self.plugin = plugin
        self.poll_interval = poll_interval
        self.respect_poll_interval = respect_poll_interval

        self._task: Optional[asyncio.Task] = None
        self._running = False

        self._processed_events: Dict[str, Set[str]] = {}
        self._initialized_repos: Set[str] = set()
        self._last_event_times: Dict[str, datetime] = {}
        self._last_poll_time: Dict[str, datetime] = {}

        self._event_callback: Optional[Callable[[str, List[GitHubEvent]], None]] = None

        self.max_events_per_poll = 100

    def set_event_callback(self, callback: Callable[[str, List[GitHubEvent]], None]):
        self._event_callback = callback

    def _parse_repo(self, repo: str) -> tuple:
        parts = repo.split("/")
        if len(parts) == 2:
            return parts[0], parts[1]
        return None, None

    def _get_init_key(self, repo: str) -> str:
        return f"{self.KV_KEY_INITIALIZED}{repo}"

    def _get_last_event_time_key(self, repo: str) -> str:
        return f"{self.KV_KEY_LAST_EVENT_TIME}{repo}"

    async def _is_repo_initialized(self, repo: str) -> bool:
        if repo in self._initialized_repos:
            return True
        initialized = await self.plugin.get_kv_data(self._get_init_key(repo), "")
        if initialized:
            self._initialized_repos.add(repo)
            await self._load_last_event_time(repo)
            return True
        return False

    async def _load_last_event_time(self, repo: str):
        time_str = await self.plugin.get_kv_data(self._get_last_event_time_key(repo), "")
        if time_str:
            try:
                self._last_event_times[repo] = datetime.fromisoformat(time_str)
            except ValueError:
                pass

    async def _mark_repo_initialized(self, repo: str, last_event_time: datetime = None):
        await self.plugin.put_kv_data(self._get_init_key(repo), "1")
        if last_event_time:
            await self.plugin.put_kv_data(
                self._get_last_event_time_key(repo),
                last_event_time.isoformat()
            )
            self._last_event_times[repo] = last_event_time
        self._initialized_repos.add(repo)
        logger.info(f"[EventPoller] 已标记 {repo} 为已初始化")

    async def _update_last_event_time(self, repo: str, event_time: datetime):
        current = self._last_event_times.get(repo)
        if not current or event_time > current:
            self._last_event_times[repo] = event_time
            await self.plugin.put_kv_data(
                self._get_last_event_time_key(repo),
                event_time.isoformat()
            )

    async def start(self):
        if self._running:
            logger.warning("[EventPoller] 轮询服务已在运行")
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(f"[EventPoller] 轮询服务已启动，轮询间隔: {self.poll_interval} 秒")

    async def stop(self):
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
        await asyncio.sleep(10)

        while self._running:
            try:
                await self._do_poll()
            except asyncio.CancelledError:
                logger.info("[EventPoller] 轮询循环已取消")
                break
            except Exception as e:
                logger.error(f"[EventPoller] 轮询出错: {e}")

            wait_time = self.poll_interval
            if self.respect_poll_interval:
                wait_time = max(self.github_client.get_poll_interval(), wait_time)

            logger.debug(f"[EventPoller] 等待 {wait_time} 秒后进行下一次轮询")
            await asyncio.sleep(wait_time)

    async def _do_poll(self):
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

            await asyncio.sleep(1)

    async def _poll_repo(self, repo: str):
        owner, repo_name = self._parse_repo(repo)
        if not owner or not repo_name:
            logger.warning(f"[EventPoller] 无效的仓库名: {repo}")
            return

        events, has_new = await self.github_client.fetch_events(
            owner, repo_name, per_page=self.max_events_per_poll
        )

        if not has_new or not events:
            return

        is_initialized = await self._is_repo_initialized(repo)

        if not is_initialized:
            if events:
                last_event_time = max(e.created_at for e in events)
                self._record_events(repo, events)
                await self._mark_repo_initialized(repo, last_event_time)
                logger.info(f"[EventPoller] {repo} 首次轮询，已记录 {len(events)} 个事件，不推送")
            self._last_poll_time[repo] = datetime.utcnow()
            return

        new_events = self._filter_new_events(repo, events)

        if new_events:
            logger.info(f"[EventPoller] {repo} 发现 {len(new_events)} 个新事件")

            self._record_events(repo, new_events)

            latest_time = max(e.created_at for e in new_events)
            await self._update_last_event_time(repo, latest_time)

            if self._event_callback:
                try:
                    await self._event_callback(repo, new_events)
                except Exception as e:
                    logger.error(f"[EventPoller] 处理 {repo} 事件回调时出错: {e}")

        self._last_poll_time[repo] = datetime.utcnow()

    def _filter_new_events(
        self, repo: str, events: List[GitHubEvent]
    ) -> List[GitHubEvent]:
        if repo not in self._processed_events:
            self._processed_events[repo] = set()

        last_time = self._last_event_times.get(repo)

        new_events = []
        for event in events:
            if event.id in self._processed_events[repo]:
                continue
            if last_time and event.created_at <= last_time:
                continue
            new_events.append(event)

        return new_events

    def _record_events(self, repo: str, events: List[GitHubEvent]):
        if repo not in self._processed_events:
            self._processed_events[repo] = set()

        for event in events:
            self._processed_events[repo].add(event.id)

        if len(self._processed_events[repo]) > 500:
            event_list = list(self._processed_events[repo])
            self._processed_events[repo] = set(event_list[-500:])

    async def force_poll(self, repo: str) -> List[GitHubEvent]:
        owner, repo_name = self._parse_repo(repo)
        if not owner or not repo_name:
            return []

        events, _ = await self.github_client.fetch_events(
            owner, repo_name, per_page=self.max_events_per_poll
        )

        if events:
            self._record_events(repo, events)
            if events:
                latest = max(e.created_at for e in events)
                await self._update_last_event_time(repo, latest)
            self._last_poll_time[repo] = datetime.utcnow()

        return events

    async def initialize_repo(self, repo: str) -> bool:
        owner, repo_name = self._parse_repo(repo)
        if not owner or not repo_name:
            return False

        if await self._is_repo_initialized(repo):
            logger.debug(f"[EventPoller] {repo} 已初始化，跳过")
            return True

        events, _ = await self.github_client.fetch_events(
            owner, repo_name, per_page=self.max_events_per_poll
        )

        if events:
            self._record_events(repo, events)
            last_event_time = max(e.created_at for e in events)
            await self._mark_repo_initialized(repo, last_event_time)

        self._last_poll_time[repo] = datetime.utcnow()
        return True

    def clear_processed_cache(self, repo: str = None):
        if repo:
            self._processed_events.pop(repo, None)
        else:
            self._processed_events.clear()

    def get_stats(self) -> Dict:
        return {
            "running": self._running,
            "interval": self.poll_interval,
            "processed_events": {
                repo: len(ids) for repo, ids in self._processed_events.items()
            },
            "initialized_repos": list(self._initialized_repos),
            "last_event_times": {
                repo: t.isoformat() if t else None
                for repo, t in self._last_event_times.items()
            },
            "last_poll": {
                repo: t.isoformat() if t else None
                for repo, t in self._last_poll_time.items()
            },
        }
