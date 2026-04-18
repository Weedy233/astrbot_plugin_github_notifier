"""GitHub API 客户端 - 支持 ETag 缓存和速率限制处理"""

import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import aiohttp
from astrbot.api import logger

from ..models.event_models import GitHubEvent


class RateLimitInfo:
    """速率限制信息"""

    def __init__(self):
        self.limit: int = 60
        self.remaining: int = 60
        self.used: int = 0
        self.reset_timestamp: int = 0

    @property
    def reset_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.reset_timestamp)

    @property
    def is_exceeded(self) -> bool:
        return self.remaining <= 0


class GitHubClient:
    """GitHub Events API 客户端

    特性:
    - ETag 缓存减少 API 调用
    - 自动处理速率限制
    - 支持 Token 认证访问 private 仓库
    - 动态轮询间隔调整
    """

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str = "", use_etag: bool = True):
        self.token = token
        self.use_etag = use_etag
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limit = RateLimitInfo()

        # ETag 缓存: repo_full_name -> (etag, last_modified)
        self._etag_cache: Dict[str, str] = {}

        # 轮询间隔（秒）
        self.poll_interval: int = 60

    def _get_headers(self) -> Dict[str, str]:
        """构建请求头"""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AstrBot-GitHub-Notifier",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _ensure_session(self):
        """确保会话已创建"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=30),
            )

    async def close(self):
        """关闭会话"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def _parse_rate_limit_headers(self, headers: Dict[str, str]):
        """解析速率限制响应头"""
        try:
            self.rate_limit.limit = int(headers.get("X-RateLimit-Limit", 60))
            self.rate_limit.remaining = int(headers.get("X-RateLimit-Remaining", 60))
            self.rate_limit.used = int(headers.get("X-RateLimit-Used", 0))
            self.rate_limit.reset_timestamp = int(headers.get("X-RateLimit-Reset", 0))
        except (ValueError, TypeError):
            pass

    def _parse_poll_interval(self, headers: Dict[str, str]) -> int:
        """解析 GitHub 建议的轮询间隔"""
        try:
            poll_interval = int(headers.get("X-Poll-Interval", 60))
            return max(poll_interval, 60)  # 最少 60 秒
        except (ValueError, TypeError):
            return 60

    async def _wait_for_rate_limit_reset(self):
        """等待速率限制重置"""
        if self.rate_limit.reset_timestamp > 0:
            wait_seconds = (
                self.rate_limit.reset_timestamp - int(datetime.utcnow().timestamp()) + 1
            )
            if wait_seconds > 0:
                logger.warning(f"[GitHub] 速率限制已触发，等待 {wait_seconds} 秒后重试")
                await asyncio.sleep(wait_seconds)

    async def fetch_events(
        self,
        owner: str,
        repo: str,
        per_page: int = 100,
    ) -> Tuple[List[GitHubEvent], bool]:
        """获取仓库事件

        Args:
            owner: 仓库所有者
            repo: 仓库名
            per_page: 每页事件数（最大 100）

        Returns:
            (事件列表, 是否有新事件)
            返回空列表表示没有新事件或请求失败
        """
        await self._ensure_session()

        repo_key = f"{owner}/{repo}"
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/events"
        params = {"per_page": min(per_page, 100)}

        # 构建请求头
        headers = {}
        if self.use_etag and repo_key in self._etag_cache:
            headers["If-None-Match"] = self._etag_cache[repo_key]

        try:
            async with self.session.get(url, params=params, headers=headers) as resp:
                # 更新速率限制信息
                self._parse_rate_limit_headers(dict(resp.headers))

                # 更新轮询间隔
                self.poll_interval = self._parse_poll_interval(dict(resp.headers))

                # 处理 304 Not Modified - 没有新事件
                if resp.status == 304:
                    logger.debug(f"[GitHub] {repo_key} 没有新事件 (304)")
                    return [], False

                # 处理速率限制
                if resp.status in (403, 429):
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        wait_time = int(retry_after)
                        logger.warning(f"[GitHub] 速率限制，等待 {wait_time} 秒后重试")
                        await asyncio.sleep(wait_time)
                    else:
                        await self._wait_for_rate_limit_reset()
                    return [], False

                # 处理其他错误
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(
                        f"[GitHub] 获取 {repo_key} 事件失败: {resp.status} - {text[:100]}"
                    )
                    return [], False

                # 更新 ETag
                if self.use_etag:
                    etag = resp.headers.get("ETag")
                    if etag:
                        self._etag_cache[repo_key] = etag

                # 解析响应
                data = await resp.json()
                events = [GitHubEvent.from_api_response(item) for item in data]

                logger.debug(f"[GitHub] 成功获取 {repo_key} 的 {len(events)} 个事件")
                return events, True

        except asyncio.TimeoutError:
            logger.error(f"[GitHub] 请求 {repo_key} 超时")
            return [], False
        except aiohttp.ClientError as e:
            logger.error(f"[GitHub] 请求 {repo_key} 失败: {e}")
            return [], False
        except Exception as e:
            logger.error(f"[GitHub] 获取 {repo_key} 事件时出错: {e}")
            return [], False

    async def check_repository_access(self, owner: str, repo: str) -> Tuple[bool, str]:
        """检查仓库是否可访问

        Returns:
            (是否可访问, 错误信息)
        """
        await self._ensure_session()

        url = f"{self.BASE_URL}/repos/{owner}/{repo}"

        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    return True, ""
                elif resp.status == 404:
                    return False, "仓库不存在或没有访问权限"
                elif resp.status == 403:
                    return False, "API 速率限制或权限不足"
                else:
                    text = await resp.text()
                    return False, f"HTTP {resp.status}: {text[:100]}"

        except Exception as e:
            return False, str(e)

    def get_poll_interval(self) -> int:
        """获取当前建议的轮询间隔"""
        return self.poll_interval

    def clear_cache(self, owner: str = None, repo: str = None):
        """清除 ETag 缓存"""
        if owner and repo:
            repo_key = f"{owner}/{repo}"
            self._etag_cache.pop(repo_key, None)
        else:
            self._etag_cache.clear()
