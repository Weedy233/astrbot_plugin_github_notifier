"""订阅管理器 - 管理会话级别的仓库订阅"""

import json
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

from astrbot.api import logger
from astrbot.api.star import Context


@dataclass
class Subscription:
    """订阅信息"""

    repo: str  # 格式: owner/repo
    subscriber_umo: str  # 订阅者的统一消息来源标识
    created_at: str
    event_types: List[str]  # 订阅的事件类型

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Subscription":
        return cls(**data)


class SubscriptionManager:
    """订阅管理器

    管理仓库与会话的订阅关系:
    - 支持多会话订阅同一仓库
    - 支持单一会话订阅多仓库
    - 支持按事件类型筛选
    - 使用 AstrBot KV 存储持久化
    """

    KV_KEY_SUBSCRIPTIONS = "github_notifier_subscriptions"

    def __init__(self, context: Context):
        self.context = context
        # 内存缓存: repo -> {umo: Subscription}
        self._subscriptions: Dict[str, Dict[str, Subscription]] = {}
        self._loaded = False

    async def _ensure_loaded(self):
        """确保已从 KV 加载数据"""
        if not self._loaded:
            await self._load_from_kv()
            self._loaded = True

    async def _load_from_kv(self):
        """从 KV 存储加载订阅数据"""
        try:
            data = await self.context.get_kv_data(self.KV_KEY_SUBSCRIPTIONS, "")
            if data:
                parsed = json.loads(data)
                self._subscriptions = {}
                for repo, subscribers in parsed.items():
                    self._subscriptions[repo] = {
                        umo: Subscription.from_dict(sub_data)
                        for umo, sub_data in subscribers.items()
                    }
                logger.info(
                    f"[SubscriptionManager] 从 KV 加载了 {len(self._subscriptions)} 个仓库的订阅"
                )
        except Exception as e:
            logger.error(f"[SubscriptionManager] 加载订阅数据失败: {e}")
            self._subscriptions = {}

    async def _save_to_kv(self):
        """保存订阅数据到 KV 存储"""
        try:
            data = {
                repo: {umo: sub.to_dict() for umo, sub in subscribers.items()}
                for repo, subscribers in self._subscriptions.items()
            }
            await self.context.put_kv_data(
                self.KV_KEY_SUBSCRIPTIONS, json.dumps(data, ensure_ascii=False)
            )
        except Exception as e:
            logger.error(f"[SubscriptionManager] 保存订阅数据失败: {e}")

    async def subscribe(
        self,
        repo: str,
        umo: str,
        event_types: Optional[List[str]] = None,
        created_at: str = None,
    ) -> bool:
        """订阅仓库

        Args:
            repo: 仓库名 (格式: owner/repo)
            umo: 统一消息来源标识
            event_types: 订阅的事件类型列表，None 表示订阅所有
            created_at: 订阅时间

        Returns:
            是否是新订阅
        """
        await self._ensure_loaded()

        # 标准化仓库名（小写）
        repo = repo.lower().strip()

        if repo not in self._subscriptions:
            self._subscriptions[repo] = {}

        is_new = umo not in self._subscriptions[repo]

        from datetime import datetime

        subscription = Subscription(
            repo=repo,
            subscriber_umo=umo,
            created_at=created_at or datetime.utcnow().isoformat(),
            event_types=event_types or ["PushEvent", "ReleaseEvent"],
        )

        self._subscriptions[repo][umo] = subscription
        await self._save_to_kv()

        if is_new:
            logger.info(f"[SubscriptionManager] {umo} 订阅了 {repo}")

        return is_new

    async def unsubscribe(self, repo: str, umo: str) -> bool:
        """取消订阅仓库

        Returns:
            是否成功取消
        """
        await self._ensure_loaded()

        repo = repo.lower().strip()

        if repo in self._subscriptions and umo in self._subscriptions[repo]:
            del self._subscriptions[repo][umo]

            # 如果没有订阅者了，删除仓库条目
            if not self._subscriptions[repo]:
                del self._subscriptions[repo]

            await self._save_to_kv()
            logger.info(f"[SubscriptionManager] {umo} 取消订阅了 {repo}")
            return True

        return False

    async def unsubscribe_all(self, umo: str) -> List[str]:
        """取消所有订阅

        Returns:
            被取消的仓库列表
        """
        await self._ensure_loaded()

        unsubscribed = []
        repos_to_remove = []

        for repo, subscribers in list(self._subscriptions.items()):
            if umo in subscribers:
                del subscribers[umo]
                unsubscribed.append(repo)

                if not subscribers:
                    repos_to_remove.append(repo)

        for repo in repos_to_remove:
            del self._subscriptions[repo]

        if unsubscribed:
            await self._save_to_kv()
            logger.info(
                f"[SubscriptionManager] {umo} 取消订阅了所有仓库: {unsubscribed}"
            )

        return unsubscribed

    async def get_subscriptions(self, umo: str) -> List[Subscription]:
        """获取指定会话的所有订阅"""
        await self._ensure_loaded()

        result = []
        for repo, subscribers in self._subscriptions.items():
            if umo in subscribers:
                result.append(subscribers[umo])

        return result

    async def get_subscribers(self, repo: str) -> List[str]:
        """获取订阅指定仓库的所有会话"""
        await self._ensure_loaded()

        repo = repo.lower().strip()
        subscribers = self._subscriptions.get(repo, {})
        return list(subscribers.keys())

    async def get_all_repos(self) -> List[str]:
        """获取所有被订阅的仓库"""
        await self._ensure_loaded()
        return list(self._subscriptions.keys())

    async def is_subscribed(self, repo: str, umo: str) -> bool:
        """检查是否已订阅"""
        await self._ensure_loaded()

        repo = repo.lower().strip()
        return repo in self._subscriptions and umo in self._subscriptions[repo]

    async def get_subscription(self, repo: str, umo: str) -> Optional[Subscription]:
        """获取订阅详情"""
        await self._ensure_loaded()

        repo = repo.lower().strip()
        if repo in self._subscriptions:
            return self._subscriptions[repo].get(umo)
        return None

    async def update_event_types(
        self, repo: str, umo: str, event_types: List[str]
    ) -> bool:
        """更新订阅的事件类型"""
        await self._ensure_loaded()

        repo = repo.lower().strip()

        if repo in self._subscriptions and umo in self._subscriptions[repo]:
            self._subscriptions[repo][umo].event_types = event_types
            await self._save_to_kv()
            return True

        return False

    def get_stats(self) -> Dict[str, int]:
        """获取订阅统计"""
        repo_count = len(self._subscriptions)
        subscriber_count = sum(len(subs) for subs in self._subscriptions.values())
        return {
            "repos": repo_count,
            "subscriptions": subscriber_count,
        }
