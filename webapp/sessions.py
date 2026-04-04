"""Session stores with TTL/LRU semantics for route modules."""

import os
import pickle
import time
import importlib
import logging
from collections import OrderedDict
from threading import Lock
from typing import Any, Dict, Iterator, MutableMapping, Optional

try:
    redis = importlib.import_module("redis")
except Exception:  # pragma: no cover - optional dependency at import time
    redis = None

logger = logging.getLogger(__name__)


class SessionStore(MutableMapping[str, Dict[str, Any]]):
    """Thread-safe in-memory session store with TTL and max-size eviction."""

    def __init__(self, max_sessions: int = 20, ttl_seconds: int = 86400):
        self._store: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._timestamps: Dict[str, float] = {}
        self._max_sessions = max_sessions
        self._ttl_seconds = ttl_seconds
        self._lock = Lock()

    def _remove(self, session_id: str) -> None:
        self._store.pop(session_id, None)
        self._timestamps.pop(session_id, None)

    def _evict_expired_locked(self) -> None:
        now = time.time()
        expired = [
            sid for sid, ts in self._timestamps.items()
            if now - ts > self._ttl_seconds
        ]
        for sid in expired:
            self._remove(sid)
            logger.info("Expired session removed: %s", sid)

    def cleanup(self) -> None:
        with self._lock:
            self._evict_expired_locked()

    def __getitem__(self, key: str) -> Dict[str, Any]:
        with self._lock:
            self._evict_expired_locked()
            session = self._store[key]
            self._store.move_to_end(key)
            self._timestamps[key] = time.time()
            return session

    def __setitem__(self, key: str, value: Dict[str, Any]) -> None:
        with self._lock:
            self._evict_expired_locked()
            if key not in self._store and len(self._store) >= self._max_sessions:
                oldest_key = next(iter(self._store))
                self._remove(oldest_key)
                logger.info("LRU session evicted: %s", oldest_key)
            self._store[key] = value
            self._store.move_to_end(key)
            self._timestamps[key] = time.time()

    def __delitem__(self, key: str) -> None:
        with self._lock:
            self._remove(key)

    def __iter__(self) -> Iterator[str]:
        with self._lock:
            self._evict_expired_locked()
            return iter(list(self._store.keys()))

    def __len__(self) -> int:
        with self._lock:
            self._evict_expired_locked()
            return len(self._store)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        with self._lock:
            self._evict_expired_locked()
            exists = key in self._store
            if exists:
                self._store.move_to_end(key)
                self._timestamps[key] = time.time()
            return exists

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            self._evict_expired_locked()
            if key not in self._store:
                return default
            self._store.move_to_end(key)
            self._timestamps[key] = time.time()
            return self._store[key]

    def pop(self, key: str, default: Any = None) -> Any:
        with self._lock:
            self._evict_expired_locked()
            if key not in self._store:
                return default
            value = self._store[key]
            self._remove(key)
            return value


class RedisSessionStore(MutableMapping[str, Dict[str, Any]]):
    """Redis-backed session store with TTL and LRU eviction."""

    def __init__(
        self,
        redis_url: str,
        max_sessions: int = 20,
        ttl_seconds: int = 86400,
        key_prefix: str = "peffort:session:",
    ):
        if redis is None:
            raise RuntimeError("redis package not installed. Add 'redis' to requirements.")

        self._client = redis.Redis.from_url(redis_url, decode_responses=False)
        self._max_sessions = max_sessions
        self._ttl_seconds = ttl_seconds
        self._key_prefix = key_prefix
        self._index_key = f"{key_prefix}index"
        self._lock = Lock()

        # Fail fast on startup misconfiguration.
        self._client.ping()

    def _data_key(self, session_id: str) -> str:
        return f"{self._key_prefix}{session_id}"

    def _touch_locked(self, session_id: str) -> None:
        now = time.time()
        self._client.zadd(self._index_key, {session_id: now})
        self._client.expire(self._index_key, self._ttl_seconds * 2)

    def _evict_lru_locked(self) -> None:
        count = self._client.zcard(self._index_key)
        overflow = max(0, count - self._max_sessions)
        if overflow <= 0:
            return
        oldest = self._client.zrange(self._index_key, 0, overflow - 1)
        if not oldest:
            return
        for sid_raw in oldest:
            sid = sid_raw.decode("utf-8") if isinstance(sid_raw, bytes) else str(sid_raw)
            self._client.delete(self._data_key(sid))
            self._client.zrem(self._index_key, sid)
            logger.info("LRU session evicted from Redis: %s", sid)

    def cleanup(self) -> None:
        """Prune index entries pointing to expired/missing Redis values."""
        with self._lock:
            members = self._client.zrange(self._index_key, 0, -1)
            if not members:
                return
            stale: list[str] = []
            for sid_raw in members:
                sid = sid_raw.decode("utf-8") if isinstance(sid_raw, bytes) else str(sid_raw)
                if not self._client.exists(self._data_key(sid)):
                    stale.append(sid)
            if stale:
                self._client.zrem(self._index_key, *stale)

    def __getitem__(self, key: str) -> Dict[str, Any]:
        with self._lock:
            data = self._client.get(self._data_key(key))
            if data is None:
                raise KeyError(key)
            try:
                session = pickle.loads(data)
            except Exception:
                self._client.delete(self._data_key(key))
                self._client.zrem(self._index_key, key)
                raise KeyError(key)
            self._client.expire(self._data_key(key), self._ttl_seconds)
            self._touch_locked(key)
            return session

    def __setitem__(self, key: str, value: Dict[str, Any]) -> None:
        payload = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        with self._lock:
            self._client.setex(self._data_key(key), self._ttl_seconds, payload)
            self._touch_locked(key)
            self._evict_lru_locked()

    def __delitem__(self, key: str) -> None:
        with self._lock:
            deleted = self._client.delete(self._data_key(key))
            self._client.zrem(self._index_key, key)
            if not deleted:
                raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        pattern = f"{self._key_prefix}*"
        prefix_len = len(self._key_prefix)
        keys: list[str] = []
        for key in self._client.scan_iter(match=pattern, count=200):
            key_str = key.decode("utf-8") if isinstance(key, bytes) else str(key)
            if key_str == self._index_key:
                continue
            keys.append(key_str[prefix_len:])
        return iter(keys)

    def __len__(self) -> int:
        return sum(1 for _ in self.__iter__())

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return bool(self._client.exists(self._data_key(key)))

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key: str, default: Any = None) -> Any:
        with self._lock:
            data = self._client.get(self._data_key(key))
            if data is None:
                return default
            self._client.delete(self._data_key(key))
            self._client.zrem(self._index_key, key)
            try:
                return pickle.loads(data)
            except Exception:
                return default


def create_session_store(max_sessions: int = 20, ttl_seconds: int = 86400) -> MutableMapping[str, Dict[str, Any]]:
    """Create session store from environment (Redis preferred when configured)."""
    redis_url: Optional[str] = os.getenv("REDIS_URL", "").strip() or None
    if redis_url:
        logger.info("Using Redis session store")
        return RedisSessionStore(redis_url=redis_url, max_sessions=max_sessions, ttl_seconds=ttl_seconds)
    logger.info("Using in-memory session store")
    return SessionStore(max_sessions=max_sessions, ttl_seconds=ttl_seconds)
