"""
Caching layer for QEO with TTL and LRU eviction.

Provides caching for:
- EXPLAIN query results
- NL explanations
- Optimization results
- Schema information
"""

import hashlib
import os
import time
from collections import OrderedDict
from typing import Any, Dict, Optional


class TTLCache:
    """Thread-safe TTL cache with LRU eviction."""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        """
        Initialize TTL cache.

        Args:
            max_size: Maximum number of entries
            ttl_seconds: Time-to-live in seconds
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: Dict[str, float] = {}
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache if not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        if key not in self._cache:
            self._misses += 1
            return None

        # Check TTL
        timestamp = self._timestamps.get(key, 0)
        if time.time() - timestamp > self.ttl_seconds:
            # Expired
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)
            self._misses += 1
            return None

        # Move to end (LRU)
        self._cache.move_to_end(key)
        self._hits += 1
        return self._cache[key]

    def set(self, key: str, value: Any) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
        """
        # Update existing or add new
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            self._cache[key] = value

        self._timestamps[key] = time.time()

        # Evict oldest if over size
        while len(self._cache) > self.max_size:
            oldest_key = next(iter(self._cache))
            self._cache.pop(oldest_key)
            self._timestamps.pop(oldest_key, None)

    def delete(self, key: str) -> None:
        """Delete entry from cache."""
        self._cache.pop(key, None)
        self._timestamps.pop(key, None)

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._timestamps.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0

        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 3),
            "ttl_seconds": self.ttl_seconds
        }


def get_cache_key(*args, **kwargs) -> str:
    """
    Generate cache key from arguments.

    Args:
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        MD5 hash of arguments
    """
    # Combine args and kwargs into a string
    key_parts = [str(arg) for arg in args]
    key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    key_string = "|".join(key_parts)

    # Generate MD5 hash
    return hashlib.md5(key_string.encode()).hexdigest()


# Global cache instances
_EXPLAIN_CACHE = TTLCache(
    max_size=int(os.getenv("CACHE_EXPLAIN_SIZE", "500")),
    ttl_seconds=int(os.getenv("CACHE_EXPLAIN_TTL", "300"))  # 5 minutes
)

_NL_CACHE = TTLCache(
    max_size=int(os.getenv("CACHE_NL_SIZE", "200")),
    ttl_seconds=int(os.getenv("CACHE_NL_TTL", "600"))  # 10 minutes
)

_OPTIMIZE_CACHE = TTLCache(
    max_size=int(os.getenv("CACHE_OPTIMIZE_SIZE", "300")),
    ttl_seconds=int(os.getenv("CACHE_OPTIMIZE_TTL", "300"))  # 5 minutes
)

_SCHEMA_CACHE = TTLCache(
    max_size=int(os.getenv("CACHE_SCHEMA_SIZE", "100")),
    ttl_seconds=int(os.getenv("CACHE_SCHEMA_TTL", "1800"))  # 30 minutes
)


def cache_explain_result(sql: str, analyze: bool, result: Dict) -> None:
    """Cache EXPLAIN result."""
    key = get_cache_key("explain", sql, analyze)
    _EXPLAIN_CACHE.set(key, result)


def get_cached_explain_result(sql: str, analyze: bool) -> Optional[Dict]:
    """Get cached EXPLAIN result."""
    key = get_cache_key("explain", sql, analyze)
    return _EXPLAIN_CACHE.get(key)


def cache_nl_explanation(sql: str, plan: Dict, audience: str, style: str, length: str, explanation: str) -> None:
    """Cache natural language explanation."""
    key = get_cache_key("nl", sql, str(plan), audience, style, length)
    _NL_CACHE.set(key, explanation)


def get_cached_nl_explanation(sql: str, plan: Dict, audience: str, style: str, length: str) -> Optional[str]:
    """Get cached natural language explanation."""
    key = get_cache_key("nl", sql, str(plan), audience, style, length)
    return _NL_CACHE.get(key)


def cache_optimize_result(sql: str, what_if: bool, top_k: int, result: Dict) -> None:
    """Cache optimization result."""
    key = get_cache_key("optimize", sql, what_if, top_k)
    _OPTIMIZE_CACHE.set(key, result)


def get_cached_optimize_result(sql: str, what_if: bool, top_k: int) -> Optional[Dict]:
    """Get cached optimization result."""
    key = get_cache_key("optimize", sql, what_if, top_k)
    return _OPTIMIZE_CACHE.get(key)


def cache_schema_info(schema: str, table: Optional[str], info: Dict) -> None:
    """Cache schema information."""
    key = get_cache_key("schema", schema, table or "*")
    _SCHEMA_CACHE.set(key, info)


def get_cached_schema_info(schema: str, table: Optional[str]) -> Optional[Dict]:
    """Get cached schema information."""
    key = get_cache_key("schema", schema, table or "*")
    return _SCHEMA_CACHE.get(key)


def get_all_cache_stats() -> Dict[str, Dict[str, Any]]:
    """Get statistics for all caches."""
    return {
        "explain": _EXPLAIN_CACHE.stats(),
        "nl": _NL_CACHE.stats(),
        "optimize": _OPTIMIZE_CACHE.stats(),
        "schema": _SCHEMA_CACHE.stats()
    }


def clear_all_caches() -> None:
    """Clear all caches."""
    _EXPLAIN_CACHE.clear()
    _NL_CACHE.clear()
    _OPTIMIZE_CACHE.clear()
    _SCHEMA_CACHE.clear()
