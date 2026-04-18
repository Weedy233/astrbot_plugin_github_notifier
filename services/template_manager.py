"""模板管理器 - 管理消息模板与变量替换"""

from typing import Any, Dict, List


class TemplateManager:
    """消息模板管理器
    
    支持:
    - 用户自定义模板 (从配置读取)
    - 默认模板 (硬编码)
    - 变量替换
    """
    
    # 默认模板 - brief (摘要)
    DEFAULT_BRIEF_TEMPLATES: Dict[str, str] = {
        "PushEvent": "📝 {username} 推送了 {commit_count} 个提交到 {branch}",
        "ReleaseEvent": "🏷️ {username} {action} 了版本 {tag_name}",
        "IssuesEvent": "🐛 {username} {action} Issue #{issue_number}: {issue_title}",
        "PullRequestEvent": "🔀 {username} {action} PR #{pr_number}: {pr_title}",
        "WatchEvent": "⭐ {username} Star 了仓库",
        "ForkEvent": "🍴 {username} Fork 了仓库到 {forked_repo}",
    }
    
    # 默认模板 - full (详情)
    DEFAULT_FULL_TEMPLATES: Dict[str, str] = {
        "PushEvent": "📝 [{repo}] 代码推送\n\n👤 推送者: {username}\n🌿 分支: {branch}\n🔢 提交数: {commit_count}\n\n🔗 对比: {compare_url}",
        "ReleaseEvent": "🏷️ [{repo}] 版本发布\n\n👤 发布者: {username}\n📌 标签: {tag_name}\n📝 名称: {release_name}\n\n🔗 详情: {release_url}",
        "IssuesEvent": "🐛 [{repo}] Issue 更新\n\n👤 操作用户: {username}\n📝 操作: {action}\n🔢 Issue: #{issue_number}\n📋 标题: {issue_title}\n📊 状态: {state}\n\n🔗 链接: {issue_url}",
        "PullRequestEvent": "🔀 [{repo}] Pull Request 更新\n\n👤 操作用户: {username}\n📝 操作: {action}\n🔢 PR: #{pr_number}\n📋 标题: {pr_title}\n📊 状态: {state}\n\n🔗 链接: {pr_url}",
        "WatchEvent": "⭐ [{repo}] {username} Star 了仓库！\n\n🔗 {repo_url}",
        "ForkEvent": "🍴 [{repo}] 仓库被 Fork\n\n👤 Fork 者: {username}\n📁 Fork 到: {forked_repo}\n\n🔗 {forked_url}",
    }
    
    def __init__(self, config: Dict[str, Any]):
        """初始化模板管理器
        
        Args:
            config: 插件配置字典
        """
        self.config = config
        self._load_templates()
    
    def _load_templates(self):
        """从配置加载用户自定义模板"""
        # Brief 模板
        self.brief_templates: Dict[str, str] = {}
        self.brief_templates["PushEvent"] = self.config.get("template_push_brief", "") or self.DEFAULT_BRIEF_TEMPLATES["PushEvent"]
        self.brief_templates["ReleaseEvent"] = self.config.get("template_release_brief", "") or self.DEFAULT_BRIEF_TEMPLATES["ReleaseEvent"]
        self.brief_templates["IssuesEvent"] = self.config.get("template_issues_brief", "") or self.DEFAULT_BRIEF_TEMPLATES["IssuesEvent"]
        self.brief_templates["PullRequestEvent"] = self.config.get("template_pr_brief", "") or self.DEFAULT_BRIEF_TEMPLATES["PullRequestEvent"]
        self.brief_templates["WatchEvent"] = self.config.get("template_star_brief", "") or self.DEFAULT_BRIEF_TEMPLATES["WatchEvent"]
        self.brief_templates["ForkEvent"] = self.config.get("template_fork_brief", "") or self.DEFAULT_BRIEF_TEMPLATES["ForkEvent"]
        
        # Full 模板
        self.full_templates: Dict[str, str] = {}
        self.full_templates["PushEvent"] = self.config.get("template_push_full", "") or self.DEFAULT_FULL_TEMPLATES["PushEvent"]
        self.full_templates["ReleaseEvent"] = self.config.get("template_release_full", "") or self.DEFAULT_FULL_TEMPLATES["ReleaseEvent"]
        self.full_templates["IssuesEvent"] = self.config.get("template_issues_full", "") or self.DEFAULT_FULL_TEMPLATES["IssuesEvent"]
        self.full_templates["PullRequestEvent"] = self.config.get("template_pr_full", "") or self.DEFAULT_FULL_TEMPLATES["PullRequestEvent"]
        self.full_templates["WatchEvent"] = self.config.get("template_star_full", "") or self.DEFAULT_FULL_TEMPLATES["WatchEvent"]
        self.full_templates["ForkEvent"] = self.config.get("template_fork_full", "") or self.DEFAULT_FULL_TEMPLATES["ForkEvent"]
    
    def get_brief_template(self, event_type: str) -> str:
        """获取事件摘要模板"""
        return self.brief_templates.get(event_type, "📌 {username} 触发了 {event_type}")
    
    def get_full_template(self, event_type: str) -> str:
        """获取事件详情模板"""
        return self.full_templates.get(event_type, "📌 [{repo}] {event_type}\n\n👤 触发者: {username}\n\n🔗 {repo_url}")
    
    def render_brief(self, event_type: str, context: Dict[str, Any]) -> str:
        """渲染摘要模板
        
        Args:
            event_type: 事件类型
            context: 变量上下文
            
        Returns:
            渲染后的消息
        """
        template = self.get_brief_template(event_type)
        return self._safe_format(template, context)
    
    def render_full(self, event_type: str, context: Dict[str, Any]) -> str:
        """渲染详情模板
        
        Args:
            event_type: 事件类型
            context: 变量上下文
            
        Returns:
            渲染后的消息
        """
        template = self.get_full_template(event_type)
        return self._safe_format(template, context)
    
    def _safe_format(self, template: str, context: Dict[str, Any]) -> str:
        """安全格式化模板
        
        处理模板中的变量替换，缺失变量保留原样或使用空字符串
        """
        result = template
        
        # 按变量名长度降序排序，避免 {branch} 替换影响 {branch_name}
        sorted_keys = sorted(context.keys(), key=len, reverse=True)
        
        for key in sorted_keys:
            value = context[key]
            if value is None:
                value = ""
            elif not isinstance(value, str):
                value = str(value)
            result = result.replace("{" + key + "}", value)
        
        return result
    
    def build_push_context(
        self,
        repo: str,
        username: str,
        branch: str,
        commit_count: int,
        commits: List[Dict[str, Any]],
        compare_url: str,
    ) -> Dict[str, Any]:
        """构建 PushEvent 变量上下文
        
        包含:
        - repo: 仓库名
        - username: 用户名
        - branch: 分支名
        - commit_count: 提交数
        - commit_msg_1~5: 提交消息 1-5
        - commit_sha_1~5: 提交 SHA 1-5 (前7位)
        - compare_url: 对比链接
        - repo_url: 仓库链接
        """
        context = {
            "repo": repo,
            "username": username,
            "branch": branch,
            "commit_count": commit_count,
            "compare_url": compare_url,
            "repo_url": f"https://github.com/{repo}",
        }
        
        # 提取提交消息 (最多5个)
        for i in range(5):
            if i < len(commits):
                commit = commits[i]
                msg = commit.get("message", "").split("\n")[0]
                sha = commit.get("sha", "")[:7]
                context[f"commit_msg_{i + 1}"] = msg
                context[f"commit_sha_{i + 1}"] = sha
            else:
                context[f"commit_msg_{i + 1}"] = ""
                context[f"commit_sha_{i + 1}"] = ""
        
        return context
    
    def build_release_context(
        self,
        repo: str,
        username: str,
        action: str,
        tag_name: str,
        release_name: str,
        release_url: str,
        is_prerelease: bool,
    ) -> Dict[str, Any]:
        """构建 ReleaseEvent 变量上下文"""
        return {
            "repo": repo,
            "username": username,
            "action": action,
            "tag_name": tag_name,
            "release_name": release_name or tag_name,
            "release_url": release_url,
            "is_prerelease": "⚠️ 预发布版本" if is_prerelease else "",
            "repo_url": f"https://github.com/{repo}",
        }
    
    def build_issues_context(
        self,
        repo: str,
        username: str,
        action: str,
        issue_number: int,
        issue_title: str,
        issue_url: str,
        state: str,
    ) -> Dict[str, Any]:
        """构建 IssuesEvent 变量上下文"""
        # Action 映射
        action_map = {
            "opened": "🆕 创建",
            "closed": "✅ 关闭",
            "reopened": "🔄 重新打开",
            "edited": "✏️ 编辑",
        }
        action_display = action_map.get(action, f"📌 {action}")
        
        return {
            "repo": repo,
            "username": username,
            "action": action_display,
            "action_raw": action,
            "issue_number": issue_number,
            "issue_title": issue_title,
            "issue_url": issue_url,
            "state": state,
            "repo_url": f"https://github.com/{repo}",
        }
    
    def build_pr_context(
        self,
        repo: str,
        username: str,
        action: str,
        pr_number: int,
        pr_title: str,
        pr_url: str,
        state: str,
        merged: bool,
    ) -> Dict[str, Any]:
        """构建 PullRequestEvent 变量上下文"""
        # Action 映射
        action_map = {
            "opened": "🆕 创建",
            "closed": "✅ 关闭",
            "reopened": "🔄 重新打开",
            "edited": "✏️ 编辑",
            "synchronize": "🔄 同步",
        }
        action_display = action_map.get(action, f"📌 {action}")
        
        # 合并特殊处理
        if action == "closed" and merged:
            action_display = "🔀 合并"
        
        return {
            "repo": repo,
            "username": username,
            "action": action_display,
            "action_raw": action,
            "pr_number": pr_number,
            "pr_title": pr_title,
            "pr_url": pr_url,
            "state": state,
            "merged": "是" if merged else "否",
            "repo_url": f"https://github.com/{repo}",
        }
    
    def build_star_context(
        self,
        repo: str,
        username: str,
        is_starred: bool,
    ) -> Dict[str, Any]:
        """构建 WatchEvent (Star) 变量上下文"""
        return {
            "repo": repo,
            "username": username,
            "repo_url": f"https://github.com/{repo}",
            "action": "Star" if is_starred else "取消 Star",
        }
    
    def build_fork_context(
        self,
        repo: str,
        username: str,
        forked_repo: str,
        forked_url: str,
    ) -> Dict[str, Any]:
        """构建 ForkEvent 变量上下文"""
        return {
            "repo": repo,
            "username": username,
            "forked_repo": forked_repo,
            "forked_url": forked_url,
            "repo_url": f"https://github.com/{repo}",
        }
