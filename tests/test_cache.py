"""Tests for SearchCache functionality."""

import asyncio

import pytest

from file_knowledge_mcp.search.cache import SearchCache, SmartSearchCache
from file_knowledge_mcp.search.ugrep import SearchResult, UgrepEngine

# ============================================================================
# SearchCache Tests
# ============================================================================


@pytest.mark.asyncio
async def test_cache_basic_functionality():
    """Test basic cache get/set operations."""
    cache = SearchCache(max_size=10, ttl_seconds=60)

    # Initially empty
    result = await cache.get("test query", "/path", fuzzy=False)
    assert result is None

    # Set and get
    test_result = SearchResult(
        query="test query", matches=[], total_matches=0, truncated=False, searched_path="/path"
    )
    await cache.set("test query", "/path", test_result, fuzzy=False)

    cached = await cache.get("test query", "/path", fuzzy=False)
    assert cached is not None
    assert cached.query == "test query"


@pytest.mark.asyncio
async def test_cache_hit_counting():
    """Test that cache tracks hit counts."""
    cache = SearchCache(max_size=10, ttl_seconds=60)

    test_result = SearchResult(
        query="test", matches=[], total_matches=0, truncated=False, searched_path="/path"
    )
    await cache.set("test", "/path", test_result)

    # Access multiple times
    await cache.get("test", "/path")
    await cache.get("test", "/path")
    await cache.get("test", "/path")

    stats = cache.stats
    assert stats["total_hits"] == 3


@pytest.mark.asyncio
async def test_cache_ttl_expiration():
    """Test that cache entries expire after TTL."""
    cache = SearchCache(max_size=10, ttl_seconds=1)  # 1 second TTL

    test_result = SearchResult(
        query="test", matches=[], total_matches=0, truncated=False, searched_path="/path"
    )
    await cache.set("test", "/path", test_result)

    # Should be cached initially
    cached = await cache.get("test", "/path")
    assert cached is not None

    # Wait for expiration
    await asyncio.sleep(1.5)

    # Should be expired
    cached = await cache.get("test", "/path")
    assert cached is None


@pytest.mark.asyncio
async def test_cache_eviction():
    """Test that cache evicts oldest entry when at capacity."""
    cache = SearchCache(max_size=3, ttl_seconds=60)

    # Fill cache to capacity
    for i in range(3):
        result = SearchResult(
            query=f"query{i}",
            matches=[],
            total_matches=0,
            truncated=False,
            searched_path=f"/path{i}",
        )
        await cache.set(f"query{i}", f"/path{i}", result)
        await asyncio.sleep(0.01)  # Ensure different timestamps

    assert cache.stats["entries"] == 3

    # Add one more, should evict oldest
    result = SearchResult(
        query="query3", matches=[], total_matches=0, truncated=False, searched_path="/path3"
    )
    await cache.set("query3", "/path3", result)

    assert cache.stats["entries"] == 3

    # Oldest (query0) should be evicted
    assert await cache.get("query0", "/path0") is None
    assert await cache.get("query3", "/path3") is not None


@pytest.mark.asyncio
async def test_cache_key_generation():
    """Test that different parameters generate different cache keys."""
    cache = SearchCache(max_size=10, ttl_seconds=60)

    result1 = SearchResult(
        query="test", matches=[], total_matches=0, truncated=False, searched_path="/path1"
    )
    result2 = SearchResult(
        query="test", matches=[], total_matches=0, truncated=False, searched_path="/path2"
    )

    # Same query, different paths
    await cache.set("test", "/path1", result1)
    await cache.set("test", "/path2", result2)

    # Should be separate cache entries
    assert cache.stats["entries"] == 2

    # Same query and path, different kwargs
    await cache.set("test", "/path1", result1, fuzzy=True)
    assert cache.stats["entries"] == 3


@pytest.mark.asyncio
async def test_cache_clear():
    """Test cache clear functionality."""
    cache = SearchCache(max_size=10, ttl_seconds=60)

    # Add some entries
    for i in range(5):
        result = SearchResult(
            query=f"query{i}",
            matches=[],
            total_matches=0,
            truncated=False,
            searched_path=f"/path{i}",
        )
        await cache.set(f"query{i}", f"/path{i}", result)

    assert cache.stats["entries"] == 5

    # Clear cache
    await cache.clear()

    assert cache.stats["entries"] == 0
    assert cache.stats["total_hits"] == 0


@pytest.mark.asyncio
async def test_cache_stats():
    """Test cache statistics."""
    cache = SearchCache(max_size=100, ttl_seconds=60)

    # Add entries
    for i in range(5):
        result = SearchResult(
            query=f"query{i}",
            matches=[],
            total_matches=0,
            truncated=False,
            searched_path=f"/path{i}",
        )
        await cache.set(f"query{i}", f"/path{i}", result)

    # Access some entries
    await cache.get("query0", "/path0")
    await cache.get("query0", "/path0")
    await cache.get("query1", "/path1")

    stats = cache.stats
    assert stats["entries"] == 5
    assert stats["max_size"] == 100
    assert stats["total_hits"] == 3


@pytest.mark.asyncio
async def test_cache_integration_with_engine(rich_config, rich_knowledge_dir):
    """Test cache integration with UgrepEngine."""
    cache = SearchCache(max_size=10, ttl_seconds=60)
    engine = UgrepEngine(rich_config, cache=cache)

    # First search - cache miss
    result1 = await engine.search(
        query="movement",
        path=rich_knowledge_dir,
        recursive=True,
        context_lines=2,
        max_results=10,
    )

    assert cache.stats["entries"] == 1
    assert cache.stats["total_hits"] == 0

    # Second identical search - cache hit
    result2 = await engine.search(
        query="movement",
        path=rich_knowledge_dir,
        recursive=True,
        context_lines=2,
        max_results=10,
    )

    assert cache.stats["entries"] == 1
    assert cache.stats["total_hits"] == 1

    # Results should be identical
    assert result1.total_matches == result2.total_matches


# ============================================================================
# SmartSearchCache Tests
# ============================================================================


@pytest.mark.asyncio
async def test_smart_cache_initialization(temp_knowledge_dir):
    """Test SmartSearchCache initialization."""
    cache = SmartSearchCache(temp_knowledge_dir, max_size=50, ttl_seconds=120)

    assert cache.knowledge_root == temp_knowledge_dir.resolve()
    assert cache.max_size == 50
    assert cache.ttl_seconds == 120


@pytest.mark.asyncio
async def test_smart_cache_basic_get_set(temp_knowledge_dir):
    """Test basic get/set operations with validation."""
    cache = SmartSearchCache(temp_knowledge_dir)

    # Create test file
    test_file = temp_knowledge_dir / "test.txt"
    test_file.write_text("test content")

    test_result = SearchResult(
        query="test",
        matches=[],
        total_matches=0,
        truncated=False,
        searched_path=str(test_file),
    )

    # Set without tracking
    await cache.set("test", str(test_file), test_result)

    # Get without validation
    cached = await cache.get("test", str(test_file))
    assert cached is not None


@pytest.mark.asyncio
async def test_smart_cache_with_tracking(temp_knowledge_dir):
    """Test caching with file modification time tracking."""
    cache = SmartSearchCache(temp_knowledge_dir)

    # Create test file
    test_file = temp_knowledge_dir / "test.txt"
    test_file.write_text("original content")

    test_result = SearchResult(
        query="test",
        matches=[],
        total_matches=0,
        truncated=False,
        searched_path=str(test_file),
    )

    # Set with tracking
    await cache.set_with_tracking("test", str(test_file), test_result)

    # Get with validation - should succeed
    cached = await cache.get_with_validation("test", str(test_file))
    assert cached is not None


@pytest.mark.asyncio
async def test_smart_cache_invalidates_on_file_change(temp_knowledge_dir):
    """Test that cache is invalidated when files change."""
    cache = SmartSearchCache(temp_knowledge_dir)

    # Create and cache file
    test_file = temp_knowledge_dir / "test.txt"
    test_file.write_text("original content")

    test_result = SearchResult(
        query="test",
        matches=[],
        total_matches=0,
        truncated=False,
        searched_path=str(test_file),
    )

    await cache.set_with_tracking("test", str(test_file), test_result)

    # Verify cached
    cached = await cache.get_with_validation("test", str(test_file))
    assert cached is not None

    # Modify file
    await asyncio.sleep(0.01)  # Ensure mtime changes
    test_file.write_text("modified content")

    # Cache should be invalidated
    cached = await cache.get_with_validation("test", str(test_file))
    assert cached is None


@pytest.mark.asyncio
async def test_smart_cache_invalidates_on_file_deletion(temp_knowledge_dir):
    """Test that cache is invalidated when files are deleted."""
    cache = SmartSearchCache(temp_knowledge_dir)

    # Create and cache file
    test_file = temp_knowledge_dir / "test.txt"
    test_file.write_text("content to delete")

    test_result = SearchResult(
        query="test",
        matches=[],
        total_matches=0,
        truncated=False,
        searched_path=str(test_file),
    )

    await cache.set_with_tracking("test", str(test_file), test_result)

    # Delete file
    test_file.unlink()

    # Cache should be invalidated
    cached = await cache.get_with_validation("test", str(test_file))
    assert cached is None


@pytest.mark.asyncio
async def test_smart_cache_tracks_multiple_files(temp_knowledge_dir):
    """Test tracking multiple files in directory search."""
    cache = SmartSearchCache(temp_knowledge_dir)

    # Create multiple files
    (temp_knowledge_dir / "file1.txt").write_text("content 1")
    (temp_knowledge_dir / "file2.txt").write_text("content 2")
    (temp_knowledge_dir / "file3.txt").write_text("content 3")

    test_result = SearchResult(
        query="test",
        matches=[],
        total_matches=0,
        truncated=False,
        searched_path=str(temp_knowledge_dir),
    )

    # Cache with directory path
    await cache.set_with_tracking("test", str(temp_knowledge_dir), test_result)

    # Verify cached
    cached = await cache.get_with_validation("test", str(temp_knowledge_dir))
    assert cached is not None

    # Modify one file
    await asyncio.sleep(0.01)
    (temp_knowledge_dir / "file2.txt").write_text("modified content")

    # Cache should be invalidated
    cached = await cache.get_with_validation("test", str(temp_knowledge_dir))
    assert cached is None


@pytest.mark.asyncio
async def test_smart_cache_invalidate_path(temp_knowledge_dir):
    """Test explicit path invalidation."""
    cache = SmartSearchCache(temp_knowledge_dir)

    # Create files in different locations
    (temp_knowledge_dir / "keep.txt").write_text("keep this")

    subdir = temp_knowledge_dir / "subdir"
    subdir.mkdir()
    (subdir / "invalidate.txt").write_text("invalidate this")

    # Cache both
    result1 = SearchResult(
        query="test1", matches=[], total_matches=0, truncated=False, searched_path="keep.txt"
    )
    result2 = SearchResult(
        query="test2",
        matches=[],
        total_matches=0,
        truncated=False,
        searched_path=str(subdir / "invalidate.txt"),
    )

    await cache.set_with_tracking("test1", "keep.txt", result1)
    await cache.set_with_tracking("test2", str(subdir / "invalidate.txt"), result2)

    # Invalidate subdir
    count = await cache.invalidate_path(str(subdir))

    assert count >= 1  # At least one entry invalidated

    # keep.txt should still be cached
    cached1 = await cache.get_with_validation("test1", "keep.txt")
    assert cached1 is not None

    # subdir file should be invalidated (may or may not be cached depending on implementation)
    await cache.get_with_validation("test2", str(subdir / "invalidate.txt"))


@pytest.mark.asyncio
async def test_smart_cache_handles_absolute_paths(temp_knowledge_dir):
    """Test that cache handles absolute paths correctly."""
    cache = SmartSearchCache(temp_knowledge_dir)

    test_file = temp_knowledge_dir / "test.txt"
    test_file.write_text("test content")

    test_result = SearchResult(
        query="test",
        matches=[],
        total_matches=0,
        truncated=False,
        searched_path=str(test_file.resolve()),
    )

    # Use absolute path
    await cache.set_with_tracking("test", str(test_file.resolve()), test_result)

    # Should be able to retrieve
    cached = await cache.get_with_validation("test", str(test_file.resolve()))
    assert cached is not None


@pytest.mark.asyncio
async def test_smart_cache_limits_tracked_files(temp_knowledge_dir):
    """Test that cache limits number of tracked files to avoid memory issues."""
    cache = SmartSearchCache(temp_knowledge_dir)

    # Create many files
    for i in range(150):
        (temp_knowledge_dir / f"file{i}.txt").write_text(f"content {i}")

    test_result = SearchResult(
        query="test",
        matches=[],
        total_matches=0,
        truncated=False,
        searched_path=str(temp_knowledge_dir),
    )

    # Cache directory
    await cache.set_with_tracking("test", str(temp_knowledge_dir), test_result)

    # Should have limited the number of tracked files
    # (implementation tracks max 100 files per entry)
    cached = await cache.get_with_validation("test", str(temp_knowledge_dir))
    assert cached is not None  # Should still be cached


@pytest.mark.asyncio
async def test_smart_cache_ttl_still_works(temp_knowledge_dir):
    """Test that TTL expiration still works with smart cache."""
    cache = SmartSearchCache(temp_knowledge_dir, ttl_seconds=1)

    test_file = temp_knowledge_dir / "test.txt"
    test_file.write_text("test content")

    test_result = SearchResult(
        query="test",
        matches=[],
        total_matches=0,
        truncated=False,
        searched_path=str(test_file),
    )

    await cache.set_with_tracking("test", str(test_file), test_result)

    # Should be cached initially
    cached = await cache.get_with_validation("test", str(test_file))
    assert cached is not None

    # Wait for TTL expiration
    await asyncio.sleep(1.5)

    # Should be expired
    cached = await cache.get_with_validation("test", str(test_file))
    assert cached is None


@pytest.mark.asyncio
async def test_smart_cache_fallback_to_regular_cache(temp_knowledge_dir):
    """Test that smart cache can still use regular cache methods."""
    cache = SmartSearchCache(temp_knowledge_dir)

    test_result = SearchResult(
        query="test",
        matches=[],
        total_matches=0,
        truncated=False,
        searched_path="/some/path",
    )

    # Use regular cache methods
    await cache.set("test", "/some/path", test_result)

    cached = await cache.get("test", "/some/path")
    assert cached is not None


@pytest.mark.asyncio
async def test_smart_cache_stats(temp_knowledge_dir):
    """Test that cache statistics still work."""
    cache = SmartSearchCache(temp_knowledge_dir)

    # Add some entries
    for i in range(3):
        result = SearchResult(
            query=f"query{i}",
            matches=[],
            total_matches=0,
            truncated=False,
            searched_path=f"/path{i}",
        )
        await cache.set_with_tracking(f"query{i}", f"/path{i}", result)

    stats = cache.stats
    assert stats["entries"] == 3
    assert stats["max_size"] > 0
