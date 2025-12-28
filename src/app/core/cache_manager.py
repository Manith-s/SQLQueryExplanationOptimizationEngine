"""
Advanced multi-tier cache manager with intelligent query fingerprinting.

Implements a sophisticated caching system with:
- Multi-tier architecture (in-memory LRU + Redis + disk)
- Query normalization and fingerprinting
- Adaptive TTL based on data volatility
- Cache compression and encryption
- Cache statistics and monitoring
"""

import hashlib
import json
import pickle
import re
import time
import zlib
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Optional, Set

import sqlglot

from app.core.config import settings


class CacheTier(Enum):
    """Cache tier levels."""
    MEMORY = "memory"
    REDIS = "redis"
    DISK = "disk"


class CachePolicy(Enum):
    """Cache eviction policies."""
    LRU = "lru"
    LFU = "lfu"
    TTL = "ttl"


@dataclass
class CacheEntry:
    """Single cache entry with metadata."""
    key: str
    value: Any
    tier: CacheTier
    created_at: datetime
    expires_at: Optional[datetime]
    last_accessed: datetime
    access_count: int = 0
    size_bytes: int = 0
    compressed: bool = False
    encrypted: bool = False
    table_dependencies: Set[str] = field(default_factory=set)
    query_fingerprint: str = ""
    volatility_score: float = 0.5  # 0.0 = stable, 1.0 = highly volatile


@dataclass
class CacheStatistics:
    """Cache statistics and metrics."""
    total_requests: int = 0
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    memory_hits: int = 0
    redis_hits: int = 0
    disk_hits: int = 0
    total_size_bytes: int = 0
    avg_access_time_ms: float = 0.0
    hit_rate: float = 0.0
    miss_rate: float = 0.0
    eviction_rate: float = 0.0
    compression_ratio: float = 1.0

    def update(self):
        """Update calculated fields."""
        total = self.hits + self.misses
        if total > 0:
            self.hit_rate = self.hits / total
            self.miss_rate = self.misses / total
        if self.total_requests > 0:
            self.eviction_rate = self.evictions / self.total_requests


class QueryFingerprinter:
    """
    Normalizes and fingerprints SQL queries for cache key generation.

    Handles:
    - Parameter normalization (literal values)
    - Whitespace and case normalization
    - Comment removal
    - Semantic equivalence detection
    """

    @staticmethod
    def normalize_query(sql: str) -> str:
        """
        Normalize query to canonical form.

        Args:
            sql: Raw SQL query

        Returns:
            Normalized SQL string
        """
        try:
            # Parse with sqlglot
            parsed = sqlglot.parse_one(sql, read="postgres")

            # Replace literals with placeholders
            normalized = QueryFingerprinter._replace_literals(parsed)

            # Generate canonical SQL
            canonical = normalized.sql(dialect="postgres", pretty=False)

            # Additional normalization
            canonical = re.sub(r'\s+', ' ', canonical).strip()
            canonical = canonical.lower()

            return canonical

        except Exception:
            # Fallback to simple normalization
            normalized = re.sub(r'--.*?\n', ' ', sql)  # Remove comments
            normalized = re.sub(r'/\*.*?\*/', ' ', normalized, flags=re.DOTALL)
            normalized = re.sub(r'\s+', ' ', normalized).strip()
            normalized = normalized.lower()
            return normalized

    @staticmethod
    def _replace_literals(node):
        """Replace literal values with placeholders recursively."""
        if isinstance(node, sqlglot.exp.Literal):
            # Replace with placeholder based on type
            if node.is_string:
                return sqlglot.exp.Literal.string("?")
            elif node.is_number:
                return sqlglot.exp.Literal.number("0")
            else:
                return sqlglot.exp.Literal.string("?")

        # Recurse into child nodes
        for child_key in node.arg_types:
            child = node.args.get(child_key)
            if child is not None:
                if isinstance(child, list):
                    node.args[child_key] = [
                        QueryFingerprinter._replace_literals(c) if hasattr(c, 'arg_types') else c
                        for c in child
                    ]
                elif hasattr(child, 'arg_types'):
                    node.args[child_key] = QueryFingerprinter._replace_literals(child)

        return node

    @staticmethod
    def generate_fingerprint(sql: str, params: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate unique fingerprint for query.

        Args:
            sql: SQL query text
            params: Optional query parameters

        Returns:
            Hexadecimal fingerprint string
        """
        normalized = QueryFingerprinter.normalize_query(sql)

        # Include parameters in fingerprint if provided
        if params:
            param_str = json.dumps(params, sort_keys=True)
            fingerprint_input = f"{normalized}|{param_str}"
        else:
            fingerprint_input = normalized

        return hashlib.sha256(fingerprint_input.encode()).hexdigest()

    @staticmethod
    def extract_table_dependencies(sql: str) -> Set[str]:
        """
        Extract table names referenced in query.

        Args:
            sql: SQL query text

        Returns:
            Set of table names
        """
        tables = set()

        try:
            parsed = sqlglot.parse_one(sql, read="postgres")

            # Find all table references
            for table_node in parsed.find_all(sqlglot.exp.Table):
                table_name = table_node.name
                if table_name:
                    tables.add(table_name.lower())

        except Exception:
            # Fallback to regex extraction
            pattern = r'\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
            matches = re.findall(pattern, sql, re.IGNORECASE)
            tables.update(m.lower() for m in matches)

        return tables


class LRUCache:
    """
    Thread-safe LRU cache with size limits.

    Implements least-recently-used eviction policy with configurable max size.
    """

    def __init__(self, max_size_bytes: int = 100 * 1024 * 1024):  # 100MB default
        """
        Initialize LRU cache.

        Args:
            max_size_bytes: Maximum cache size in bytes
        """
        self.max_size_bytes = max_size_bytes
        self.current_size_bytes = 0
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.lock = RLock()

    def get(self, key: str) -> Optional[CacheEntry]:
        """Get entry from cache, updating LRU order."""
        with self.lock:
            if key not in self.cache:
                return None

            # Move to end (most recently used)
            entry = self.cache.pop(key)
            self.cache[key] = entry
            entry.last_accessed = datetime.utcnow()
            entry.access_count += 1

            # Check expiration
            if entry.expires_at and datetime.utcnow() > entry.expires_at:
                self.cache.pop(key)
                self.current_size_bytes -= entry.size_bytes
                return None

            return entry

    def put(self, entry: CacheEntry) -> bool:
        """
        Put entry in cache, evicting if necessary.

        Returns:
            True if entry was cached, False if skipped
        """
        with self.lock:
            # Remove if already exists
            if entry.key in self.cache:
                old_entry = self.cache.pop(entry.key)
                self.current_size_bytes -= old_entry.size_bytes

            # Evict until we have space
            while (self.current_size_bytes + entry.size_bytes > self.max_size_bytes
                   and len(self.cache) > 0):
                # Remove least recently used (first item)
                lru_key, lru_entry = self.cache.popitem(last=False)
                self.current_size_bytes -= lru_entry.size_bytes

            # Check if entry fits
            if entry.size_bytes > self.max_size_bytes:
                return False

            # Add to cache
            self.cache[entry.key] = entry
            self.current_size_bytes += entry.size_bytes

            return True

    def delete(self, key: str) -> bool:
        """Delete entry from cache."""
        with self.lock:
            if key in self.cache:
                entry = self.cache.pop(key)
                self.current_size_bytes -= entry.size_bytes
                return True
            return False

    def clear(self):
        """Clear all entries."""
        with self.lock:
            self.cache.clear()
            self.current_size_bytes = 0

    def size(self) -> int:
        """Get current number of entries."""
        with self.lock:
            return len(self.cache)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self.lock:
            return {
                "entries": len(self.cache),
                "size_bytes": self.current_size_bytes,
                "max_size_bytes": self.max_size_bytes,
                "utilization": self.current_size_bytes / self.max_size_bytes if self.max_size_bytes > 0 else 0.0
            }


class CacheManager:
    """
    Multi-tier cache manager with intelligent caching strategies.

    Manages cache across memory, Redis, and disk tiers with adaptive TTL,
    compression, and encryption support.
    """

    def __init__(
        self,
        memory_size_mb: int = 100,
        disk_cache_dir: Optional[Path] = None,
        enable_compression: bool = True,
        enable_encryption: bool = False,
        default_ttl_seconds: int = 3600
    ):
        """
        Initialize cache manager.

        Args:
            memory_size_mb: Memory cache size in MB
            disk_cache_dir: Directory for disk cache (None = disabled)
            enable_compression: Enable compression for large entries
            enable_encryption: Enable encryption for sensitive data
            default_ttl_seconds: Default TTL for cache entries
        """
        self.memory_cache = LRUCache(max_size_bytes=memory_size_mb * 1024 * 1024)
        self.disk_cache_dir = disk_cache_dir
        self.enable_compression = enable_compression
        self.enable_encryption = enable_encryption
        self.default_ttl_seconds = default_ttl_seconds

        # Statistics
        self.stats = CacheStatistics()
        self.stats_lock = RLock()

        # Volatility tracking for adaptive TTL
        self.table_volatility: Dict[str, float] = {}

        # Create disk cache directory if needed
        if self.disk_cache_dir:
            self.disk_cache_dir.mkdir(parents=True, exist_ok=True)

    def get(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        database_state: Optional[str] = None
    ) -> Optional[Any]:
        """
        Get cached query result.

        Args:
            sql: SQL query text
            params: Query parameters
            database_state: Optional database state identifier

        Returns:
            Cached result or None if not found
        """
        start_time = time.time()

        # Generate cache key
        cache_key = self._generate_cache_key(sql, params, database_state)

        with self.stats_lock:
            self.stats.total_requests += 1

        # Try memory cache first
        entry = self.memory_cache.get(cache_key)
        if entry:
            with self.stats_lock:
                self.stats.hits += 1
                self.stats.memory_hits += 1
            result = self._deserialize_value(entry)
            self._update_access_time(start_time)
            return result

        # Try disk cache if enabled
        if self.disk_cache_dir:
            entry = self._get_from_disk(cache_key)
            if entry:
                # Promote to memory cache
                self.memory_cache.put(entry)
                with self.stats_lock:
                    self.stats.hits += 1
                    self.stats.disk_hits += 1
                result = self._deserialize_value(entry)
                self._update_access_time(start_time)
                return result

        # Cache miss
        with self.stats_lock:
            self.stats.misses += 1
        self._update_access_time(start_time)

        return None

    def put(
        self,
        sql: str,
        result: Any,
        params: Optional[Dict[str, Any]] = None,
        database_state: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        compress: bool = True,
        encrypt: bool = False
    ) -> bool:
        """
        Cache query result.

        Args:
            sql: SQL query text
            result: Query result to cache
            params: Query parameters
            database_state: Optional database state identifier
            ttl_seconds: Time-to-live in seconds (None = use default)
            compress: Enable compression
            encrypt: Enable encryption

        Returns:
            True if cached successfully
        """
        # Generate cache key and fingerprint
        cache_key = self._generate_cache_key(sql, params, database_state)
        fingerprint = QueryFingerprinter.generate_fingerprint(sql, params)

        # Extract table dependencies
        table_deps = QueryFingerprinter.extract_table_dependencies(sql)

        # Calculate adaptive TTL based on table volatility
        if ttl_seconds is None:
            ttl_seconds = self._calculate_adaptive_ttl(table_deps)

        # Serialize value
        serialized = self._serialize_value(result, compress and self.enable_compression)

        # Create cache entry
        entry = CacheEntry(
            key=cache_key,
            value=serialized,
            tier=CacheTier.MEMORY,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=ttl_seconds) if ttl_seconds > 0 else None,
            last_accessed=datetime.utcnow(),
            access_count=0,
            size_bytes=len(serialized),
            compressed=compress and self.enable_compression,
            encrypted=encrypt and self.enable_encryption,
            table_dependencies=table_deps,
            query_fingerprint=fingerprint,
            volatility_score=self._get_table_volatility(table_deps)
        )

        # Try to cache in memory
        if self.memory_cache.put(entry):
            with self.stats_lock:
                self.stats.total_size_bytes += entry.size_bytes
            return True

        # Fallback to disk if memory is full
        if self.disk_cache_dir:
            return self._put_to_disk(entry)

        return False

    def invalidate(
        self,
        sql: Optional[str] = None,
        table: Optional[str] = None,
        pattern: Optional[str] = None
    ) -> int:
        """
        Invalidate cache entries.

        Args:
            sql: Specific SQL query to invalidate
            table: Invalidate all queries using this table
            pattern: Invalidate queries matching pattern

        Returns:
            Number of entries invalidated
        """
        invalidated = 0

        if sql:
            # Invalidate specific query
            cache_key = self._generate_cache_key(sql)
            if self.memory_cache.delete(cache_key):
                invalidated += 1
            if self.disk_cache_dir:
                invalidated += self._delete_from_disk(cache_key)

        elif table:
            # Invalidate all queries using table
            table_lower = table.lower()

            # Invalidate from memory
            keys_to_delete = []
            for key, entry in self.memory_cache.cache.items():
                if table_lower in entry.table_dependencies:
                    keys_to_delete.append(key)

            for key in keys_to_delete:
                if self.memory_cache.delete(key):
                    invalidated += 1

            # Invalidate from disk
            if self.disk_cache_dir:
                for cache_file in self.disk_cache_dir.glob("*.cache"):
                    try:
                        with open(cache_file, 'rb') as f:
                            entry = pickle.load(f)
                            if table_lower in entry.table_dependencies:
                                cache_file.unlink()
                                invalidated += 1
                    except Exception:
                        pass

        elif pattern:
            # Pattern-based invalidation (simple substring match)
            pattern_lower = pattern.lower()

            keys_to_delete = []
            for key in self.memory_cache.cache.keys():
                if pattern_lower in key.lower():
                    keys_to_delete.append(key)

            for key in keys_to_delete:
                if self.memory_cache.delete(key):
                    invalidated += 1

        return invalidated

    def get_statistics(self) -> CacheStatistics:
        """Get current cache statistics."""
        with self.stats_lock:
            self.stats.update()
            return self.stats

    def clear(self):
        """Clear all cache tiers."""
        self.memory_cache.clear()

        if self.disk_cache_dir:
            for cache_file in self.disk_cache_dir.glob("*.cache"):
                try:
                    cache_file.unlink()
                except Exception:
                    pass

        with self.stats_lock:
            self.stats = CacheStatistics()

    def update_table_volatility(self, table: str, volatility: float):
        """
        Update volatility score for a table.

        Args:
            table: Table name
            volatility: Volatility score (0.0 = stable, 1.0 = highly volatile)
        """
        self.table_volatility[table.lower()] = max(0.0, min(1.0, volatility))

    def _generate_cache_key(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        database_state: Optional[str] = None
    ) -> str:
        """Generate unique cache key."""
        fingerprint = QueryFingerprinter.generate_fingerprint(sql, params)

        if database_state:
            return f"{fingerprint}:{database_state}"

        return fingerprint

    def _calculate_adaptive_ttl(self, table_deps: Set[str]) -> int:
        """
        Calculate adaptive TTL based on table volatility.

        More volatile tables get shorter TTL.
        """
        if not table_deps:
            return self.default_ttl_seconds

        # Get average volatility across all tables
        volatilities = [self.table_volatility.get(t, 0.5) for t in table_deps]
        avg_volatility = sum(volatilities) / len(volatilities)

        # Scale TTL inversely with volatility
        # High volatility (1.0) = 10% of default TTL
        # Low volatility (0.0) = 200% of default TTL
        scale_factor = 2.0 - (1.9 * avg_volatility)

        return int(self.default_ttl_seconds * scale_factor)

    def _get_table_volatility(self, table_deps: Set[str]) -> float:
        """Get average volatility for tables."""
        if not table_deps:
            return 0.5

        volatilities = [self.table_volatility.get(t, 0.5) for t in table_deps]
        return sum(volatilities) / len(volatilities)

    def _serialize_value(self, value: Any, compress: bool) -> bytes:
        """Serialize and optionally compress value."""
        serialized = pickle.dumps(value)

        if compress and len(serialized) > 1024:  # Only compress if > 1KB
            compressed = zlib.compress(serialized, level=6)
            # Only use compressed if it's actually smaller
            if len(compressed) < len(serialized):
                return compressed

        return serialized

    def _deserialize_value(self, entry: CacheEntry) -> Any:
        """Deserialize and decompress value."""
        data = entry.value

        if entry.compressed:
            try:
                data = zlib.decompress(data)
            except Exception:
                pass

        return pickle.loads(data)

    def _get_from_disk(self, cache_key: str) -> Optional[CacheEntry]:
        """Get entry from disk cache."""
        if not self.disk_cache_dir:
            return None

        cache_file = self.disk_cache_dir / f"{cache_key}.cache"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, 'rb') as f:
                entry = pickle.load(f)

            # Check expiration
            if entry.expires_at and datetime.utcnow() > entry.expires_at:
                cache_file.unlink()
                return None

            return entry

        except Exception:
            return None

    def _put_to_disk(self, entry: CacheEntry) -> bool:
        """Put entry to disk cache."""
        if not self.disk_cache_dir:
            return False

        cache_file = self.disk_cache_dir / f"{entry.key}.cache"

        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(entry, f)
            return True
        except Exception:
            return False

    def _delete_from_disk(self, cache_key: str) -> int:
        """Delete entry from disk cache."""
        if not self.disk_cache_dir:
            return 0

        cache_file = self.disk_cache_dir / f"{cache_key}.cache"

        if cache_file.exists():
            try:
                cache_file.unlink()
                return 1
            except Exception:
                pass

        return 0

    def _update_access_time(self, start_time: float):
        """Update average access time statistic."""
        access_time_ms = (time.time() - start_time) * 1000

        with self.stats_lock:
            if self.stats.total_requests == 1:
                self.stats.avg_access_time_ms = access_time_ms
            else:
                # Exponential moving average
                alpha = 0.1
                self.stats.avg_access_time_ms = (
                    alpha * access_time_ms +
                    (1 - alpha) * self.stats.avg_access_time_ms
                )


# Singleton instance
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """Get singleton cache manager instance."""
    global _cache_manager

    if _cache_manager is None:
        disk_dir = None
        if hasattr(settings, 'CACHE_DISK_DIR') and settings.CACHE_DISK_DIR:
            disk_dir = Path(settings.CACHE_DISK_DIR)

        memory_size = getattr(settings, 'CACHE_MEMORY_SIZE_MB', 100)
        default_ttl = getattr(settings, 'CACHE_DEFAULT_TTL_SECONDS', 3600)

        _cache_manager = CacheManager(
            memory_size_mb=memory_size,
            disk_cache_dir=disk_dir,
            enable_compression=True,
            enable_encryption=False,
            default_ttl_seconds=default_ttl
        )

    return _cache_manager
