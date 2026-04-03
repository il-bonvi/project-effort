"""
Session storage with TTL and LRU eviction.
Compatible with dict-style access used by route modules.
"""

import time
import logging
from collections import OrderedDict
from threading import Lock
from typing import Any, Dict, Iterator, MutableMapping

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
