# PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-18
**Commit:** 1125951
**Branch:** main

## OVERVIEW

AstrBot plugin for GitHub repository event notifications via Events API polling. Supports session-level subscriptions, ETag caching, and configurable event types (Push/Release/Issues/PR/Star/Fork).

## STRUCTURE

```
astrbot_plugin_github_notifier/
├── main.py                    # Plugin entry, command handlers, lifecycle
├── metadata.yaml              # AstrBot plugin manifest
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
| Add new command | `main.py:124-378` | Use `@filter.command("cmd")` decorator |
| Change poll interval logic | `services/event_poller.py:89-110` | `_poll_loop()` method |
| Add event type | `main.py:30-37`, `models/event_models.py` | `SUPPORTED_EVENTS` + payload class |
| Modify API calls | `services/github_client.py:108-189` | `fetch_events()` method |
| Change message format | `services/message_formatter.py` | Instance methods with template support |
| Customize templates | `_conf_schema.json` | `template_*_brief` / `template_*_full` |
| Subscription persistence | `services/subscription_manager.py:52-82` | KV store operations |

## CONVENTIONS

### AstrBot Plugin Patterns
- Entry point: `@register()` decorator on `Star` subclass
- Commands: `@filter.command("name")` with `async def handler(event: AstrMessageEvent)`
- Responses: `yield event.plain_result("message")` (generator pattern)
- Config: Access via `self.config.get("key", default)`
- Logging: `from astrbot.api import logger`

### Code Style
- Type hints required on all function signatures
- Docstrings for public methods (Chinese OK)
- Dataclasses for models with `@property` for computed fields
- Factory methods: `from_dict()`, `from_api_response()`
- Async/await throughout

### Relative Imports
```python
from .services.github_client import GitHubClient
from .models.event_models import GitHubEvent
```

## ANTI-PATTERNS (THIS PROJECT)

- No `__init__.py` at root (AstrBot loads plugins differently)
- No tests yet - consider adding `pytest` + `pytest-asyncio`
- No CI/CD pipeline

## UNIQUE STYLES

- Chinese docstrings and log messages (project convention)
- ETag caching to reduce API calls (304 = no rate limit consumption)
- Dynamic poll interval from `X-Poll-Interval` header
- Event ID deduplication with 500-item cache per repo
- KV-backed initialization markers (survives restart)

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
