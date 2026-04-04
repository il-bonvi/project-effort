"""
Session storage with TTL and LRU eviction.
Compatible with dict-style access used by route modules.
"""

import time
import os
import pickle
import logging
from pathlib import Path
from collections import OrderedDict
from threading import Lock
from typing import Any, Dict, Iterator, MutableMapping

logger = logging.getLogger(__name__)


class SessionStore(MutableMapping[str, Dict[str, Any]]):
    """Thread-safe in-memory session store with TTL and max-size eviction."""

    def __init__(self, max_sessions: int = 20, ttl_seconds: int = 86400, persist_dir: str | None = None):
        self._store: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._timestamps: Dict[str, float] = {}
        self._max_sessions = max_sessions
        self._ttl_seconds = ttl_seconds
        self._lock = Lock()
        self._persist_dir = (persist_dir or os.getenv("SESSION_PERSIST_DIR", "")).strip()
        self._persist_path: Path | None = None

        if self._persist_dir:
            self._persist_path = Path(self._persist_dir)
            self._persist_path.mkdir(parents=True, exist_ok=True)
            logger.info("Session persistence enabled at %s", self._persist_path)

    def _session_file(self, session_id: str) -> Path | None:
        if self._persist_path is None:
            return None
        return self._persist_path / f"{session_id}.pkl"

    def _save_to_disk_locked(self, session_id: str) -> None:
        path = self._session_file(session_id)
        if path is None:
            return
        try:
            payload = {
                'timestamp': self._timestamps.get(session_id, time.time()),
                'data': self._store.get(session_id),
            }
            with path.open('wb') as f:
                pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as exc:
            logger.warning("Failed to persist session %s: %s", session_id, exc)

    def _load_from_disk_locked(self, session_id: str) -> bool:
        path = self._session_file(session_id)
        if path is None or not path.exists():
            return False
        try:
            with path.open('rb') as f:
                payload = pickle.load(f)

            ts = float(payload.get('timestamp', 0))
            data = payload.get('data')
            if not isinstance(data, dict):
                return False

            if time.time() - ts > self._ttl_seconds:
                try:
                    path.unlink()
                except OSError:
                    pass
                return False

            self._store[session_id] = data
            self._store.move_to_end(session_id)
            self._timestamps[session_id] = time.time()
            return True
        except Exception as exc:
            logger.warning("Failed to load persisted session %s: %s", session_id, exc)
            return False

    def _remove(self, session_id: str) -> None:
        self._store.pop(session_id, None)
        self._timestamps.pop(session_id, None)
        path = self._session_file(session_id)
        if path is not None and path.exists():
            try:
                path.unlink()
            except OSError:
                pass

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
            if key not in self._store:
                self._load_from_disk_locked(key)
            session = self._store[key]
            self._store.move_to_end(key)
            self._timestamps[key] = time.time()
            self._save_to_disk_locked(key)
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
            self._save_to_disk_locked(key)

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
            exists = key in self._store or self._load_from_disk_locked(key)
            if exists:
                self._store.move_to_end(key)
                self._timestamps[key] = time.time()
                self._save_to_disk_locked(key)
            return exists

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            self._evict_expired_locked()
            if key not in self._store and not self._load_from_disk_locked(key):
                return default
            self._store.move_to_end(key)
            self._timestamps[key] = time.time()
            self._save_to_disk_locked(key)
            return self._store[key]

    def pop(self, key: str, default: Any = None) -> Any:
        with self._lock:
            self._evict_expired_locked()
            if key not in self._store:
                return default
            value = self._store[key]
            self._remove(key)
            return value
