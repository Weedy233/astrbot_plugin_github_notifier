"""GitHub 事件数据模型"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class GitHubEvent:
    """GitHub 事件基础模型"""

    id: str
    type: str
    actor: Dict[str, Any]
    repo: Dict[str, Any]
    payload: Dict[str, Any]
    public: bool
    created_at: datetime
    org: Optional[Dict[str, Any]] = None

    @property
    def actor_login(self) -> str:
        """获取触发事件的用户名"""
        return self.actor.get("login", "unknown")

    @property
    def repo_name(self) -> str:
        """获取仓库名称"""
        return self.repo.get("name", "unknown")

    @property
    def repo_url(self) -> str:
        """获取仓库 URL"""
        return f"https://github.com/{self.repo_name}"

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "GitHubEvent":
        """从 API 响应创建事件对象"""
        created_at_str = data.get("created_at", "")
        try:
            # 处理 ISO 8601 格式
            created_at_str = created_at_str.replace("Z", "+00:00")
            created_at = datetime.fromisoformat(created_at_str)
        except (ValueError, TypeError):
            created_at = datetime.utcnow()

        return cls(
            id=data.get("id", ""),
            type=data.get("type", ""),
            actor=data.get("actor", {}),
            repo=data.get("repo", {}),
            payload=data.get("payload", {}),
            public=data.get("public", True),
            created_at=created_at,
            org=data.get("org"),
        )


@dataclass
class PushEventPayload:
    """Push 事件负载"""

    ref: str
    before: str
    after: str
    commits: List[Dict[str, Any]]
    pusher: Dict[str, Any]
    forced: bool = False
    compare: str = ""
    size: int = 0
    distinct_size: int = 0

    @property
    def branch(self) -> str:
        """获取分支名"""
        return self.ref.replace("refs/heads/", "") if self.ref else ""

    @property
    def commit_count(self) -> int:
        """获取提交数量 - 优先使用 size 字段，因为 commits 数组在 Events API 中经常为空"""
        if isinstance(self.size, int) and self.size > 0:
            return self.size
        return len(self.commits)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PushEventPayload":
        # Events API 使用 head，Webhook 使用 after，兼容两者
        after = data.get("after", "") or data.get("head", "")
        return cls(
            ref=data.get("ref", ""),
            before=data.get("before", ""),
            after=after,
            commits=data.get("commits", []) or [],
            pusher=data.get("pusher", {}) or {},
            forced=data.get("forced", False),
            compare=data.get("compare", ""),
            size=data.get("size", 0),
            distinct_size=data.get("distinct_size", 0),
        )


@dataclass
class ReleaseEventPayload:
    """Release 事件负载"""

    action: str
    release: Dict[str, Any]

    @property
    def tag_name(self) -> str:
        """获取标签名"""
        return self.release.get("tag_name", "")

    @property
    def release_name(self) -> str:
        """获取发布名称"""
        return self.release.get("name", "")

    @property
    def is_prerelease(self) -> bool:
        """是否是预发布版本"""
        return self.release.get("prerelease", False)

    @property
    def release_url(self) -> str:
        """获取发布页面 URL"""
        return self.release.get("html_url", "")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReleaseEventPayload":
        return cls(
            action=data.get("action", ""),
            release=data.get("release", {}),
        )


@dataclass
class IssuesEventPayload:
    """Issues 事件负载"""

    action: str
    issue: Dict[str, Any]

    @property
    def issue_number(self) -> int:
        return self.issue.get("number", 0)

    @property
    def issue_title(self) -> str:
        return self.issue.get("title", "")

    @property
    def issue_url(self) -> str:
        return self.issue.get("html_url", "")

    @property
    def state(self) -> str:
        return self.issue.get("state", "")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IssuesEventPayload":
        return cls(
            action=data.get("action", ""),
            issue=data.get("issue", {}),
        )


@dataclass
class PullRequestEventPayload:
    """Pull Request 事件负载"""

    action: str
    pull_request: Dict[str, Any]

    @property
    def pr_number(self) -> int:
        return self.pull_request.get("number", 0)

    @property
    def pr_title(self) -> str:
        return self.pull_request.get("title", "")

    @property
    def pr_url(self) -> str:
        return self.pull_request.get("html_url", "")

    @property
    def state(self) -> str:
        return self.pull_request.get("state", "")

    @property
    def merged(self) -> bool:
        return self.pull_request.get("merged", False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PullRequestEventPayload":
        return cls(
            action=data.get("action", ""),
            pull_request=data.get("pull_request", {}),
        )


@dataclass
class StarEventPayload:
    """Star 事件负载"""

    action: str
    starred_at: Optional[str] = None

    @property
    def is_starred(self) -> bool:
        return self.action == "created"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StarEventPayload":
        return cls(
            action=data.get("action", ""),
            starred_at=data.get("starred_at"),
        )


@dataclass
class ForkEventPayload:
    """Fork 事件负载"""

    forkee: Dict[str, Any]

    @property
    def forked_repo_name(self) -> str:
        return self.forkee.get("full_name", "")

    @property
    def forked_repo_url(self) -> str:
        return self.forkee.get("html_url", "")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ForkEventPayload":
        return cls(
            forkee=data.get("forkee", {}),
        )
