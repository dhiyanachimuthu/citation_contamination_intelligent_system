"""
Disk-backed JSON cache for API responses.
Reduces redundant API calls across runs.
"""

import os
import json
import time
import logging
import threading

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


class DiskCache:
    """
    Thread-safe JSON file cache with optional TTL.
    Stores a single flat dict: key -> {value, ts}.
    """

    def __init__(self, filename: str, ttl_seconds: int = 86400 * 7):
        self._path = os.path.join(CACHE_DIR, filename)
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._data: dict = {}
        self._dirty = False
        self._load()

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.info(f"Cache loaded: {self._path} ({len(self._data)} entries)")
            except Exception as e:
                logger.warning(f"Cache load failed ({self._path}): {e}. Starting fresh.")
                self._data = {}

    def _flush(self):
        if not self._dirty:
            return
        os.makedirs(CACHE_DIR, exist_ok=True)
        try:
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, separators=(",", ":"))
            os.replace(tmp, self._path)
            self._dirty = False
        except Exception as e:
            logger.warning(f"Cache flush failed ({self._path}): {e}")

    def get(self, key: str):
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if self._ttl and (time.time() - entry.get("ts", 0)) > self._ttl:
                del self._data[key]
                self._dirty = True
                return None
            return entry["value"]

    def set(self, key: str, value):
        with self._lock:
            self._data[key] = {"value": value, "ts": time.time()}
            self._dirty = True
            self._flush()

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    def size(self) -> int:
        with self._lock:
            return len(self._data)


# Singletons
_citations_cache: DiskCache | None = None
_metadata_cache: DiskCache | None = None


def get_citations_cache() -> DiskCache:
    global _citations_cache
    if _citations_cache is None:
        _citations_cache = DiskCache("cache_citations.json", ttl_seconds=86400 * 7)
    return _citations_cache


def get_metadata_cache() -> DiskCache:
    global _metadata_cache
    if _metadata_cache is None:
        _metadata_cache = DiskCache("cache_metadata.json", ttl_seconds=86400 * 3)
    return _metadata_cache
