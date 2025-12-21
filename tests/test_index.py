"""Tests for DocumentIndex."""

import asyncio

import pytest

from file_knowledge_mcp.search.index import DocumentIndex


@pytest.fixture
async def document_index(temp_knowledge_dir):
    """Create document index fixture."""
    index = DocumentIndex(temp_knowledge_dir)
    yield index
    # Cleanup
    await index._lock.acquire()
    index._lock.release()


@pytest.fixture
async def populated_index(temp_knowledge_dir):
    """Create and populate document index."""
    index = DocumentIndex(temp_knowledge_dir)
    await index.build_index(formats=[".txt", ".md"], exclude_patterns=[])
    yield index


class TestDocumentIndexBasics:
    """Test basic index functionality."""

    async def test_index_initialization(self, temp_knowledge_dir):
        """Test index can be initialized."""
        index = DocumentIndex(temp_knowledge_dir)
        assert index.knowledge_root == temp_knowledge_dir.resolve()
        assert index.index_path == temp_knowledge_dir / ".fkm_index"
        assert len(index._term_index) == 0
        assert len(index._document_metadata) == 0

    async def test_index_custom_path(self, temp_knowledge_dir):
        """Test index with custom path."""
        custom_path = temp_knowledge_dir / "custom_index"
        index = DocumentIndex(temp_knowledge_dir, custom_path)
        assert index.index_path == custom_path

    async def test_index_stats(self, document_index):
        """Test index statistics."""
        stats = document_index.stats
        assert "total_documents" in stats
        assert "total_terms" in stats
        assert stats["total_documents"] == 0
        assert stats["total_terms"] == 0


class TestIndexBuilding:
    """Test index building functionality."""

    async def test_build_empty_index(self, document_index):
        """Test building index with no documents."""
        result = await document_index.build_index(formats=[".nonexistent"])
        assert result["documents_indexed"] == 0
        assert result["total_terms"] == 0

    async def test_build_index_with_documents(self, temp_knowledge_dir):
        """Test building index with actual documents."""
        # Create test documents
        doc1 = temp_knowledge_dir / "test1.txt"
        doc1.write_text("hello world python programming")

        doc2 = temp_knowledge_dir / "test2.txt"
        doc2.write_text("python is a great programming language")

        # Build index
        index = DocumentIndex(temp_knowledge_dir)
        result = await index.build_index(formats=[".txt"], exclude_patterns=[])

        assert result["documents_indexed"] == 2
        assert result["total_terms"] > 0
        assert result["documents_failed"] == 0
        assert "elapsed_seconds" in result

    async def test_build_index_with_subdirectories(self, temp_knowledge_dir):
        """Test index building includes subdirectories."""
        # Create nested structure
        subdir = temp_knowledge_dir / "subdir"
        subdir.mkdir()

        (temp_knowledge_dir / "root.txt").write_text("root document")
        (subdir / "nested.txt").write_text("nested document")

        # Build index
        index = DocumentIndex(temp_knowledge_dir)
        result = await index.build_index(formats=[".txt"])

        assert result["documents_indexed"] == 2

    async def test_build_index_excludes_patterns(self, temp_knowledge_dir):
        """Test index respects exclusion patterns."""
        (temp_knowledge_dir / "include.txt").write_text("include this")
        (temp_knowledge_dir / "exclude.draft.txt").write_text("exclude this")

        index = DocumentIndex(temp_knowledge_dir)
        result = await index.build_index(formats=[".txt"], exclude_patterns=["*.draft.*"])

        assert result["documents_indexed"] == 1

    async def test_build_index_updates_stats(self, document_index, temp_knowledge_dir):
        """Test index build updates statistics."""
        (temp_knowledge_dir / "test.txt").write_text("test content")

        await document_index.build_index(formats=[".txt"])

        stats = document_index.stats
        assert stats["total_documents"] == 1
        assert stats["total_terms"] > 0
        assert stats["last_build"] is not None


class TestIndexSearch:
    """Test index search functionality."""

    async def test_search_empty_index(self, document_index):
        """Test searching empty index."""
        results = await document_index.search_index("test query")
        assert results == []

    async def test_search_single_term(self, temp_knowledge_dir):
        """Test searching for single term."""
        (temp_knowledge_dir / "test.txt").write_text("python programming language")

        index = DocumentIndex(temp_knowledge_dir)
        await index.build_index(formats=[".txt"])

        results = await index.search_index("python")
        assert len(results) == 1
        assert "test.txt" in results[0]["path"]
        assert results[0]["score"] > 0

    async def test_search_multiple_terms(self, temp_knowledge_dir):
        """Test searching for multiple terms."""
        (temp_knowledge_dir / "doc1.txt").write_text("python programming")
        (temp_knowledge_dir / "doc2.txt").write_text("javascript programming")
        (temp_knowledge_dir / "doc3.txt").write_text("python and javascript")

        index = DocumentIndex(temp_knowledge_dir)
        await index.build_index(formats=[".txt"])

        # Search for "python programming"
        results = await index.search_index("python programming")
        assert len(results) >= 2

        # doc1 should rank higher (has both terms)
        top_result = results[0]
        assert "doc" in top_result["path"]

    async def test_search_case_insensitive(self, temp_knowledge_dir):
        """Test search is case insensitive."""
        (temp_knowledge_dir / "test.txt").write_text("Python Programming")

        index = DocumentIndex(temp_knowledge_dir)
        await index.build_index(formats=[".txt"])

        results = await index.search_index("python")
        assert len(results) == 1

        results = await index.search_index("PYTHON")
        assert len(results) == 1

    async def test_search_max_results(self, temp_knowledge_dir):
        """Test search respects max_results limit."""
        # Create many documents
        for i in range(20):
            (temp_knowledge_dir / f"doc{i}.txt").write_text("python test")

        index = DocumentIndex(temp_knowledge_dir)
        await index.build_index(formats=[".txt"])

        results = await index.search_index("python", max_results=5)
        assert len(results) == 5

    async def test_search_returns_metadata(self, temp_knowledge_dir):
        """Test search results include metadata."""
        (temp_knowledge_dir / "test.txt").write_text("python test")

        index = DocumentIndex(temp_knowledge_dir)
        await index.build_index(formats=[".txt"])

        results = await index.search_index("python")
        assert len(results) == 1

        result = results[0]
        assert "path" in result
        assert "score" in result
        assert "format" in result
        assert "size_bytes" in result


class TestIndexUpdate:
    """Test incremental index updates."""

    async def test_update_new_file(self, populated_index, temp_knowledge_dir):
        """Test updating index with new file."""
        initial_count = populated_index.stats["total_documents"]

        # Add new file
        new_file = temp_knowledge_dir / "new.txt"
        new_file.write_text("new document content")

        result = await populated_index.update_index([new_file])

        assert result["documents_updated"] == 1
        assert result["documents_removed"] == 0
        assert populated_index.stats["total_documents"] == initial_count + 1

    async def test_update_modified_file(self, temp_knowledge_dir):
        """Test updating index when file is modified."""
        test_file = temp_knowledge_dir / "test.txt"
        test_file.write_text("original content")

        index = DocumentIndex(temp_knowledge_dir)
        await index.build_index(formats=[".txt"])

        # Search for original content
        results = await index.search_index("original")
        assert len(results) == 1

        # Modify file
        await asyncio.sleep(0.1)  # Ensure mtime changes
        test_file.write_text("modified content")

        # Update index
        await index.update_index([test_file])

        # Search should find modified content
        results = await index.search_index("modified")
        assert len(results) == 1

        # Original content should not be found
        results = await index.search_index("original")
        assert len(results) == 0

    async def test_update_deleted_file(self, temp_knowledge_dir):
        """Test updating index when file is deleted."""
        test_file = temp_knowledge_dir / "test.txt"
        test_file.write_text("to be deleted")

        index = DocumentIndex(temp_knowledge_dir)
        await index.build_index(formats=[".txt"])

        initial_count = index.stats["total_documents"]

        # Delete file
        test_file.unlink()

        # Update index
        result = await index.update_index([test_file])

        assert result["documents_removed"] == 1
        assert index.stats["total_documents"] == initial_count - 1

    async def test_update_unchanged_file(self, temp_knowledge_dir):
        """Test updating index with unchanged file."""
        test_file = temp_knowledge_dir / "test.txt"
        test_file.write_text("unchanged content")

        index = DocumentIndex(temp_knowledge_dir)
        await index.build_index(formats=[".txt"])

        # Update with same file (no changes)
        result = await index.update_index([test_file])

        # Should not update unchanged file
        assert result["documents_updated"] == 0

    async def test_update_multiple_files(self, temp_knowledge_dir):
        """Test updating index with multiple files."""
        file1 = temp_knowledge_dir / "file1.txt"
        file2 = temp_knowledge_dir / "file2.txt"
        file3 = temp_knowledge_dir / "file3.txt"

        file1.write_text("file one")
        file2.write_text("file two")

        index = DocumentIndex(temp_knowledge_dir)
        await index.build_index(formats=[".txt"])

        # Modify file1, delete file2, add file3
        await asyncio.sleep(0.1)
        file1.write_text("file one modified")
        file2.unlink()
        file3.write_text("file three")

        result = await index.update_index([file1, file2, file3])

        assert result["documents_updated"] == 2  # file1 and file3
        assert result["documents_removed"] == 1  # file2


class TestIndexPersistence:
    """Test index save and load functionality."""

    async def test_save_and_load_index(self, temp_knowledge_dir):
        """Test saving and loading index."""
        (temp_knowledge_dir / "test.txt").write_text("test content python")

        # Build and save
        index1 = DocumentIndex(temp_knowledge_dir)
        await index1.build_index(formats=[".txt"])

        # Load in new instance
        index2 = DocumentIndex(temp_knowledge_dir)
        loaded = await index2.load_index()

        assert loaded is True
        assert index2.stats["total_documents"] == 1
        assert len(index2._term_index) > 0

        # Search should work on loaded index
        results = await index2.search_index("python")
        assert len(results) == 1

    async def test_load_nonexistent_index(self, document_index):
        """Test loading when no index exists."""
        loaded = await document_index.load_index()
        assert loaded is False

    async def test_save_preserves_stats(self, temp_knowledge_dir):
        """Test saving preserves statistics."""
        (temp_knowledge_dir / "test.txt").write_text("test")

        index1 = DocumentIndex(temp_knowledge_dir)
        await index1.build_index(formats=[".txt"])
        stats1 = index1.stats.copy()

        # Load in new instance
        index2 = DocumentIndex(temp_knowledge_dir)
        await index2.load_index()
        stats2 = index2.stats.copy()

        assert stats1["total_documents"] == stats2["total_documents"]
        assert stats1["total_terms"] == stats2["total_terms"]


class TestIndexTokenization:
    """Test tokenization and term extraction."""

    async def test_tokenize_filters_short_words(self, temp_knowledge_dir):
        """Test tokenization filters very short words."""
        (temp_knowledge_dir / "test.txt").write_text("a ab abc abcd")

        index = DocumentIndex(temp_knowledge_dir)
        await index.build_index(formats=[".txt"])

        # Only "abc" and "abcd" should be indexed (>2 chars)
        results = await index.search_index("abc")
        assert len(results) > 0

        results = await index.search_index("ab")
        assert len(results) == 0

    async def test_tokenize_filters_stop_words(self, temp_knowledge_dir):
        """Test tokenization filters common stop words."""
        (temp_knowledge_dir / "test.txt").write_text("the python and the language")

        index = DocumentIndex(temp_knowledge_dir)
        await index.build_index(formats=[".txt"])

        # "the" and "and" should be filtered out
        assert "the" not in index._term_index
        assert "and" not in index._term_index

        # "python" and "language" should be indexed
        assert "python" in index._term_index
        assert "language" in index._term_index

    async def test_tokenize_handles_punctuation(self, temp_knowledge_dir):
        """Test tokenization handles punctuation correctly."""
        (temp_knowledge_dir / "test.txt").write_text("python! programming, language.")

        index = DocumentIndex(temp_knowledge_dir)
        await index.build_index(formats=[".txt"])

        # Should tokenize without punctuation
        assert "python" in index._term_index
        assert "programming" in index._term_index


class TestIndexConcurrency:
    """Test index thread safety."""

    async def test_concurrent_searches(self, populated_index):
        """Test multiple concurrent searches."""
        tasks = [
            populated_index.search_index("test"),
            populated_index.search_index("python"),
            populated_index.search_index("code"),
        ]

        results = await asyncio.gather(*tasks)
        assert len(results) == 3

    async def test_concurrent_build_and_search(self, temp_knowledge_dir):
        """Test building and searching concurrently."""
        (temp_knowledge_dir / "test.txt").write_text("test content")

        index = DocumentIndex(temp_knowledge_dir)

        # Build in one task
        build_task = asyncio.create_task(index.build_index(formats=[".txt"]))

        # Wait a bit then try to search
        await asyncio.sleep(0.05)
        search_task = asyncio.create_task(index.search_index("test"))

        await build_task
        await search_task
