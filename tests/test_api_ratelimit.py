import builtins

from src.api.ratelimit import InMemoryRateLimiter, get_rate_limiter


def test_allows_up_to_limit_then_denies():
    rl = InMemoryRateLimiter(limit=3, window_s=60)
    assert rl.allow("1.2.3.4") is True
    assert rl.allow("1.2.3.4") is True
    assert rl.allow("1.2.3.4") is True
    assert rl.allow("1.2.3.4") is False  # 4th in-window -> denied


def test_separate_keys_have_separate_budgets():
    rl = InMemoryRateLimiter(limit=1, window_s=60)
    assert rl.allow("a") is True
    assert rl.allow("b") is True
    assert rl.allow("a") is False


def test_window_expiry_resets(monkeypatch):
    rl = InMemoryRateLimiter(limit=1, window_s=10)
    base = [1000.0]
    monkeypatch.setattr("src.api.ratelimit.time.monotonic", lambda: base[0])
    assert rl.allow("a") is True
    assert rl.allow("a") is False
    base[0] += 11.0  # advance past the window
    assert rl.allow("a") is True


def test_stale_keys_are_evicted_not_accumulated(monkeypatch):
    # One deque per client IP ever seen would otherwise live for the process
    # lifetime: fully-expired keys must be dropped from the dict.
    rl = InMemoryRateLimiter(limit=1, window_s=10)
    base = [1000.0]
    monkeypatch.setattr("src.api.ratelimit.time.monotonic", lambda: base[0])
    assert rl.allow("a") is True
    assert rl.allow("b") is True
    assert set(rl._hits) == {"a", "b"}
    base[0] += 11.0  # both windows fully expired
    assert rl.allow("c") is True
    assert set(rl._hits) == {"c"}, "expired keys must be evicted"


def test_get_rate_limiter_defaults_to_in_memory(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    rl = get_rate_limiter(limit=5, window_s=60)
    assert isinstance(rl, InMemoryRateLimiter)


def test_get_rate_limiter_falls_back_when_redis_missing(monkeypatch):
    # REDIS_URL set but the redis package import is forced to fail -> graceful in-memory fallback.
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "redis":
            raise ImportError("no redis")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    rl = get_rate_limiter(limit=5, window_s=60)
    assert isinstance(rl, InMemoryRateLimiter)
