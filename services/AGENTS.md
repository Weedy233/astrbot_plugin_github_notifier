# SERVICES LAYER

## OVERVIEW

Business logic for GitHub event polling, subscription management, and message formatting.

## WHERE TO LOOK

| Task | File | Method |
|------|------|--------|
| Fetch events from GitHub | `github_client.py` | `fetch_events()` |
| Check repo access | `github_client.py` | `check_repository_access()` |
| Subscribe/unsubscribe | `subscription_manager.py` | `subscribe()`, `unsubscribe()` |
| Get subscribers for repo | `subscription_manager.py` | `get_subscribers()` |
| Start/stop polling | `event_poller.py` | `start()`, `stop()` |
| Force immediate poll | `event_poller.py` | `force_poll()` |
| Format event for chat | `message_formatter.py` | `format_events()` |
| Build template context | `template_manager.py` | `build_*_context()` |
| Render template | `template_manager.py` | `render_brief()`, `render_full()` |

## KEY INTERFACES

```python
# GitHubClient
await client.fetch_events(owner, repo) -> (List[GitHubEvent], has_new)
await client.check_repository_access(owner, repo) -> (bool, error_msg)

# SubscriptionManager  
await manager.subscribe(repo, umo, event_types) -> bool
await manager.get_subscribers(repo) -> List[umo]

# EventPoller
await poller.start()
await poller.stop()
await poller.force_poll(repo) -> List[GitHubEvent]
poller.set_event_callback(async fn(repo, events))

# MessageFormatter (instance methods)
formatter.format_events(repo, events, max_events) -> List[str]

# TemplateManager
manager.build_push_context(repo, username, branch, ...) -> Dict
manager.render_full(event_type, context) -> str
manager.render_brief(event_type, context) -> str
```

## CONVENTIONS

- All methods are async (except MessageFormatter/TemplateManager)
- Services instantiated in `main.py:__init__()`
- EventPoller requires callback: `set_event_callback(fn)`
- SubscriptionManager uses AstrBot KV store: `context.get_kv_data()`
- TemplateManager reads user templates from config, falls back to defaults

## RATE LIMIT HANDLING

`github_client.py` handles:
- 304 Not Modified (ETag hit) → returns `([], False)`
- 403/429 → waits and retries
- Parses `X-RateLimit-*` headers
- Dynamic `poll_interval` from `X-Poll-Interval`
