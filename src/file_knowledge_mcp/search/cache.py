"""Simple in-memory cache for search results."""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cached search result."""

    result: Any
    created_at: float
    hits: int = 0
    file_mtimes: dict[str, float] | None = None  # Track file modification times


class SearchCache:
    """LRU-style cache for search results."""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

    def _make_key(self, query: str, path: str, **kwargs) -> str:
        """Generate cache key from search parameters."""
        key_data = f"{query}:{path}:{sorted(kwargs.items())}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    async def get(self, query: str, path: str, **kwargs) -> Any | None:
        """Get cached result if exists and not expired."""
        key = self._make_key(query, path, **kwargs)

        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                return None

            # Check TTL
            if time.time() - entry.created_at > self.ttl_seconds:
                del self._cache[key]
                return None

            entry.hits += 1
            return entry.result

    async def set(self, query: str, path: str, result: Any, **kwargs) -> None:
        """Cache search result."""
        key = self._make_key(query, path, **kwargs)

        async with self._lock:
            # Evict if at capacity
            if len(self._cache) >= self.max_size:
                self._evict_oldest()

            self._cache[key] = CacheEntry(
                result=result,
                created_at=time.time(),
            )

    def _evict_oldest(self) -> None:
        """Remove oldest entry."""
        if not self._cache:
            return

        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].created_at,
        )
        del self._cache[oldest_key]

    async def clear(self) -> None:
        """Clear all cached entries."""
        async with self._lock:
            self._cache.clear()

    @property
    def stats(self) -> dict:
        """Get cache statistics."""
        total_hits = sum(e.hits for e in self._cache.values())
        return {
            "entries": len(self._cache),
            "max_size": self.max_size,
            "total_hits": total_hits,
        }


class SmartSearchCache(SearchCache):
    """Enhanced search cache with file modification time tracking."""

    def __init__(self, knowledge_root: Path, max_size: int = 100, ttl_seconds: int = 300):
        """Initialize smart cache.

        Args:
            knowledge_root: Root directory for documents (for resolving paths)
            max_size: Maximum number of cached entries
            ttl_seconds: Time-to-live for cache entries
        """
        super().__init__(max_size, ttl_seconds)
        self.knowledge_root = knowledge_root.resolve()

    async def get_with_validation(self, query: str, path: str, **kwargs) -> Any | None:
        """Get cached result with file modification time validation.

        Args:
            query: Search query
            path: Search path
            **kwargs: Additional search parameters

        Returns:
            Cached result if valid, None if cache miss or files changed
        """
        key = self._make_key(query, path, **kwargs)

        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                return None

            # Check TTL
            if time.time() - entry.created_at > self.ttl_seconds:
                del self._cache[key]
                return None

            # Validate file modification times if tracked
            if entry.file_mtimes is not None:
                is_valid = await self._validate_file_mtimes(entry.file_mtimes)
                if not is_valid:
                    logger.debug(f"Cache invalidated for query '{query}' - files changed")
                    del self._cache[key]
                    return None

            entry.hits += 1
            return entry.result

    async def set_with_tracking(self, query: str, path: str, result: Any, **kwargs) -> None:
        """Cache search result with file modification time tracking.

        Args:
            query: Search query
            path: Search path
            result: Result to cache
            **kwargs: Additional search parameters
        """
        key = self._make_key(query, path, **kwargs)

        # Collect modification times for files in the search path
        file_mtimes = await self._collect_file_mtimes(path)

        async with self._lock:
            # Evict if at capacity
            if len(self._cache) >= self.max_size:
                self._evict_oldest()

            self._cache[key] = CacheEntry(
                result=result,
                created_at=time.time(),
                file_mtimes=file_mtimes,
            )

    async def invalidate_path(self, path: str) -> int:
        """Invalidate all cache entries related to a path.

        Args:
            path: Path to invalidate (relative or absolute)

        Returns:
            Number of entries invalidated
        """
        async with self._lock:
            # Normalize path
            try:
                if Path(path).is_absolute():
                    search_path = Path(path).relative_to(self.knowledge_root)
                else:
                    search_path = Path(path)
            except ValueError:
                # Path is outside knowledge root
                return 0

            search_path_str = str(search_path)

            # Find entries to invalidate
            to_remove = []
            for key, entry in self._cache.items():
                if entry.file_mtimes is None:
                    continue

                # Check if any tracked file is in the invalidated path
                for file_path in entry.file_mtimes.keys():
                    if file_path.startswith(search_path_str):
                        to_remove.append(key)
                        break

            # Remove entries
            for key in to_remove:
                del self._cache[key]

            if to_remove:
                logger.info(f"Invalidated {len(to_remove)} cache entries for {path}")

            return len(to_remove)

    async def _collect_file_mtimes(self, path: str) -> dict[str, float]:
        """Collect modification times for files in a path.

        Args:
            path: Search path (relative or absolute)

        Returns:
            Dictionary mapping file paths to modification times
        """
        file_mtimes = {}

        try:
            # Resolve path
            if Path(path).is_absolute():
                full_path = Path(path)
            else:
                full_path = self.knowledge_root / path

            # Collect mtimes
            if full_path.is_file():
                # Single file
                try:
                    rel_path = full_path.relative_to(self.knowledge_root)
                    file_mtimes[str(rel_path)] = full_path.stat().st_mtime
                except (ValueError, OSError):
                    pass
            elif full_path.is_dir():
                # Directory - collect all files (limit to avoid overhead)
                count = 0
                max_files = 100  # Limit tracking to avoid memory issues

                for file_path in full_path.rglob("*"):
                    if count >= max_files:
                        break

                    if file_path.is_file():
                        try:
                            rel_path = file_path.relative_to(self.knowledge_root)
                            file_mtimes[str(rel_path)] = file_path.stat().st_mtime
                            count += 1
                        except (ValueError, OSError):
                            pass

        except Exception as e:
            logger.warning(f"Failed to collect file mtimes for {path}: {e}")

        return file_mtimes

    async def _validate_file_mtimes(self, cached_mtimes: dict[str, float]) -> bool:
        """Validate that files haven't changed since caching.

        Args:
            cached_mtimes: Dictionary of cached modification times

        Returns:
            True if all files are unchanged, False otherwise
        """
        for file_path, cached_mtime in cached_mtimes.items():
            try:
                full_path = self.knowledge_root / file_path
                if not full_path.exists():
                    # File was deleted
                    return False

                current_mtime = full_path.stat().st_mtime
                if current_mtime > cached_mtime:
                    # File was modified
                    return False

            except OSError:
                # Error accessing file
                return False

        return True
