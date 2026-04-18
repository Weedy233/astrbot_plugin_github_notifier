# PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-18
**Commit:** bee8f49
**Branch:** main

## OVERVIEW

AstrBot plugin for GitHub repository event notifications via Events API polling. Supports session-level subscriptions, ETag caching, and configurable event types (Push/Release/Issues/PR/Star/Fork).

## STRUCTURE

```
astrbot_plugin_github_notifier/
├── main.py                    # Plugin entry, command handlers, lifecycle
├── metadata.yaml              # AstrBot plugin manifest (version info)
├── _conf_schema.json          # WebUI configuration schema
├── requirements.txt           # aiohttp>=3.8.0
├── services/                  # Business logic layer
│   ├── github_client.py       # GitHub API + ETag + rate limits
│   ├── subscription_manager.py # KV-backed subscription CRUD
│   ├── event_poller.py        # Async polling loop + deduplication
│   ├── message_formatter.py   # Event → chat message formatting
│   └── template_manager.py    # Template config + variable substitution
└── models/                    # Data models
    └── event_models.py        # GitHubEvent + payload dataclasses
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add new command | `main.py` | Use `@filter.command("cmd")` decorator |
| Change poll interval logic | `services/event_poller.py` | `_poll_loop()` method |
| Add event type | `main.py`, `models/event_models.py` | `SUPPORTED_EVENTS` + payload class |
| Modify API calls | `services/github_client.py` | `fetch_events()` method |
| Change message format | `services/message_formatter.py` | Instance methods with template support |
| Customize templates | `_conf_schema.json` | `template_*_brief` / `template_*_full` |
| Subscription persistence | `services/subscription_manager.py` | KV store operations |

## CONVENTIONS

### AstrBot Plugin Patterns (v4+)
- Entry point: `class MyPlugin(Star)` - NO `@register()` decorator (deprecated since v3.5.19)
- `__init__(self, context: Context)` - NO config param
- Commands: `@filter.command("name")` with `async def handler(event: AstrMessageEvent)`
- Responses: `event.set_result(event.plain_result("message"))`
- Config: Access via `context.get_config()` in `__init__`
- KV Storage: `self.get_kv_data()`, `self.put_kv_data()` on plugin instance
- Logging: `from astrbot.api import logger`

### Code Style
- Type hints required on all function signatures
- Chinese docstrings and log messages (project convention)
- Dataclasses for models with `@property` for computed fields
- Factory methods: `from_dict()`, `from_api_response()`
- Async/await throughout

### Relative Imports
```python
from .services.github_client import GitHubClient
from .models.event_models import GitHubEvent
```

### Version Control
- **Semantic Versioning**: `vMAJOR.MINOR.PATCH` in `metadata.yaml`
  - `MAJOR`: Breaking changes
  - `MINOR`: New features (backward compatible)
  - `PATCH`: Bug fixes
- **Update version** in `metadata.yaml` before every commit
- **Report to user** after every push with:
  - Version change
  - Commit hash
  - Change type (feat/fix/refactor/etc.)
  - Summary of changes

## ANTI-PATTERNS (THIS PROJECT)

- No `__init__.py` at root (AstrBot loads plugins differently)
- No tests yet - consider adding `pytest` + `pytest-asyncio`
- No CI/CD pipeline

## UNIQUE STYLES

- ETag caching to reduce API calls (304 = no rate limit consumption)
- Dynamic poll interval from `X-Poll-Interval` header
- Event deduplication via:
  - In-memory event ID cache (500 per repo)
  - KV-persisted `last_event_time` (survives restart)
- Compare API fallback for PushEvent commits (Events API returns empty)
- Private repo indicator when using Token

## COMMANDS

```bash
# Install dependency
pip install aiohttp>=3.8.0

# Lint (if ruff available)
ruff check .
ruff format .
```

## NOTES

- **Rate Limits**: 60/hr unauthenticated, 5000/hr with token
- **API Delay**: Events may be 30s-6h delayed
- **Event Retention**: GitHub keeps only 30 days
- **Token**: Set `github_token` in config for private repos + higher limits
- **Private Repo**: Shows `🔒 私有仓库 (使用 Token 访问)` indicator
