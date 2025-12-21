"""Tests for FileWatcher."""

import asyncio

import pytest

# Skip all tests if watchfiles is not installed
pytest.importorskip("watchfiles")

from file_knowledge_mcp.search.watcher import FileWatcher, WatcherManager


@pytest.fixture
def file_watcher(temp_knowledge_dir):
    """Create file watcher fixture."""
    watcher = FileWatcher(temp_knowledge_dir)
    yield watcher
    # Cleanup


class TestFileWatcherBasics:
    """Test basic file watcher functionality."""

    def test_watcher_initialization(self, temp_knowledge_dir):
        """Test watcher can be initialized."""
        watcher = FileWatcher(temp_knowledge_dir)
        assert watcher.knowledge_root == temp_knowledge_dir.resolve()
        assert watcher.watch_extensions == set()
        assert not watcher.is_running

    def test_watcher_with_extensions(self, temp_knowledge_dir):
        """Test watcher with specific extensions."""
        watcher = FileWatcher(temp_knowledge_dir, watch_extensions=[".txt", ".md", ".pdf"])
        assert watcher.watch_extensions == {".txt", ".md", ".pdf"}

    def test_watcher_with_callback(self, temp_knowledge_dir):
        """Test watcher with callback function."""
        called = []

        async def callback(changes):
            called.append(changes)

        watcher = FileWatcher(temp_knowledge_dir, on_change_callback=callback)
        assert watcher.on_change == callback

    async def test_watcher_start_requires_watchfiles(self, temp_knowledge_dir):
        """Test that watchfiles dependency is checked."""
        FileWatcher(temp_knowledge_dir)
        # Should not raise ImportError since we've already imported watchfiles
        # This test mainly documents the behavior


class TestFileWatcherFiltering:
    """Test file change filtering."""

    def test_filter_changes_skips_directories(self, file_watcher):
        """Test that directory changes are filtered out."""
        from watchfiles import Change

        changes = {
            (Change.added, str(file_watcher.knowledge_root / "file.txt")),
            (Change.added, str(file_watcher.knowledge_root / "dir")),
        }

        # Create the file so it passes is_file check
        test_file = file_watcher.knowledge_root / "file.txt"
        test_file.write_text("test")

        filtered = file_watcher._filter_changes(changes)

        # Should only include the file
        assert len(filtered) == 1
        assert filtered[0].name == "file.txt"

    def test_filter_changes_skips_hidden_files(self, file_watcher):
        """Test that hidden files are filtered out."""
        from watchfiles import Change

        changes = {
            (Change.added, str(file_watcher.knowledge_root / ".hidden.txt")),
            (Change.added, str(file_watcher.knowledge_root / "visible.txt")),
        }

        visible_file = file_watcher.knowledge_root / "visible.txt"
        visible_file.write_text("test")

        filtered = file_watcher._filter_changes(changes)

        # Should only include visible file
        assert len(filtered) == 1
        assert filtered[0].name == "visible.txt"

    def test_filter_changes_respects_extensions(self, temp_knowledge_dir):
        """Test extension filtering."""
        from watchfiles import Change

        watcher = FileWatcher(temp_knowledge_dir, watch_extensions=[".txt", ".md"])

        # Create test files
        txt_file = temp_knowledge_dir / "test.txt"
        md_file = temp_knowledge_dir / "test.md"
        pdf_file = temp_knowledge_dir / "test.pdf"

        txt_file.write_text("test")
        md_file.write_text("test")
        pdf_file.write_text("test")

        changes = {
            (Change.added, str(txt_file)),
            (Change.added, str(md_file)),
            (Change.added, str(pdf_file)),
        }

        filtered = watcher._filter_changes(changes)

        # Should only include .txt and .md
        assert len(filtered) == 2
        names = {f.name for f in filtered}
        assert "test.txt" in names
        assert "test.md" in names
        assert "test.pdf" not in names

    def test_filter_changes_handles_deleted_files(self, file_watcher):
        """Test filtering of deleted files."""
        from watchfiles import Change

        changes = {
            (Change.deleted, str(file_watcher.knowledge_root / "deleted.txt")),
        }

        filtered = file_watcher._filter_changes(changes)

        # Should include deleted file even though it doesn't exist
        assert len(filtered) == 1


class TestFileWatcherDebouncing:
    """Test debouncing of file changes."""

    async def test_debouncing_accumulates_changes(self, temp_knowledge_dir):
        """Test that multiple rapid changes are accumulated."""
        changes_received = []

        async def callback(changes):
            changes_received.append(changes)

        watcher = FileWatcher(
            temp_knowledge_dir, on_change_callback=callback, watch_extensions=[".txt"]
        )
        watcher._debounce_seconds = 0.1

        # Simulate multiple changes
        file1 = temp_knowledge_dir / "file1.txt"
        file2 = temp_knowledge_dir / "file2.txt"
        file1.write_text("test")
        file2.write_text("test")

        await watcher._handle_changes([file1])
        await watcher._handle_changes([file2])

        # Wait for debounce
        await asyncio.sleep(0.2)

        # Should have received one callback with both files
        assert len(changes_received) == 1
        assert len(changes_received[0]) == 2

    async def test_debouncing_cancels_previous_tasks(self, temp_knowledge_dir):
        """Test that new changes cancel pending debounce tasks."""
        callback_count = [0]

        async def callback(changes):
            callback_count[0] += 1

        watcher = FileWatcher(temp_knowledge_dir, on_change_callback=callback)
        watcher._debounce_seconds = 0.1

        file1 = temp_knowledge_dir / "file1.txt"
        file1.write_text("test")

        # Trigger multiple changes rapidly
        for _ in range(5):
            await watcher._handle_changes([file1])
            await asyncio.sleep(0.02)

        # Wait for final debounce
        await asyncio.sleep(0.15)

        # Should only have one callback (others were cancelled)
        assert callback_count[0] == 1


class TestFileWatcherLifecycle:
    """Test watcher start/stop lifecycle."""

    async def test_watcher_can_be_stopped(self, file_watcher):
        """Test that watcher can be stopped."""
        # Start watcher in background
        task = asyncio.create_task(file_watcher.start_watching())

        # Give it a moment to start
        await asyncio.sleep(0.1)

        assert file_watcher.is_running

        # Stop watcher
        await file_watcher.stop_watching()

        assert not file_watcher.is_running

        # Task should complete
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except TimeoutError:
            pytest.fail("Watcher task did not stop")

    async def test_stop_is_idempotent(self, file_watcher):
        """Test that stopping multiple times is safe."""
        await file_watcher.stop_watching()
        await file_watcher.stop_watching()  # Should not raise

    async def test_cannot_start_twice(self, file_watcher):
        """Test that starting twice raises error."""
        file_watcher._running = True

        with pytest.raises(RuntimeError, match="already running"):
            await file_watcher.start_watching()

        file_watcher._running = False


class TestWatcherManager:
    """Test WatcherManager functionality."""

    async def test_manager_initialization(self, temp_knowledge_dir):
        """Test manager can be initialized."""
        from file_knowledge_mcp.search.index import DocumentIndex

        index = DocumentIndex(temp_knowledge_dir)
        manager = WatcherManager(temp_knowledge_dir, index)

        assert manager.knowledge_root == temp_knowledge_dir.resolve()
        assert manager.document_index == index
        assert manager.watcher is None

    async def test_manager_start_creates_watcher(self, temp_knowledge_dir):
        """Test starting manager creates watcher."""
        from file_knowledge_mcp.search.index import DocumentIndex

        index = DocumentIndex(temp_knowledge_dir)
        manager = WatcherManager(temp_knowledge_dir, index)

        await manager.start(watch_extensions=[".txt"])

        assert manager.watcher is not None
        assert manager.watcher.watch_extensions == {".txt"}

        # Cleanup
        await manager.stop()

    async def test_manager_handles_file_changes(self, temp_knowledge_dir):
        """Test manager updates index on file changes."""
        from file_knowledge_mcp.search.index import DocumentIndex

        # Create initial document
        test_file = temp_knowledge_dir / "test.txt"
        test_file.write_text("initial content")

        # Setup index and manager
        index = DocumentIndex(temp_knowledge_dir)
        await index.build_index(formats=[".txt"])

        manager = WatcherManager(temp_knowledge_dir, index)

        # Simulate file change
        new_file = temp_knowledge_dir / "new.txt"
        new_file.write_text("new content")

        # Call the callback directly
        await manager._on_files_changed([new_file])

        # Index should be updated
        results = await index.search_index("new")
        assert len(results) > 0

    async def test_manager_stop_cleans_up(self, temp_knowledge_dir):
        """Test manager cleanup on stop."""
        from file_knowledge_mcp.search.index import DocumentIndex

        index = DocumentIndex(temp_knowledge_dir)
        manager = WatcherManager(temp_knowledge_dir, index)

        await manager.start()

        # Give it a moment
        await asyncio.sleep(0.1)

        await manager.stop()

        # Watcher should be stopped
        if manager.watcher:
            assert not manager.watcher.is_running

    async def test_manager_start_is_idempotent(self, temp_knowledge_dir):
        """Test starting manager multiple times."""
        from file_knowledge_mcp.search.index import DocumentIndex

        index = DocumentIndex(temp_knowledge_dir)
        manager = WatcherManager(temp_knowledge_dir, index)

        await manager.start()
        await manager.start()  # Should log warning but not crash

        await manager.stop()


class TestIntegration:
    """Integration tests for file watching."""

    @pytest.mark.slow
    async def test_real_file_changes_trigger_updates(self, temp_knowledge_dir):
        """Test that real file changes trigger index updates.

        This is a more realistic integration test that actually watches files.
        """
        from file_knowledge_mcp.search.index import DocumentIndex

        # Setup
        index = DocumentIndex(temp_knowledge_dir)
        await index.build_index(formats=[".txt"])

        manager = WatcherManager(temp_knowledge_dir, index)
        await manager.start(watch_extensions=[".txt"])

        # Give watcher time to start
        await asyncio.sleep(0.2)

        # Create new file
        new_file = temp_knowledge_dir / "watched.txt"
        new_file.write_text("watched content")

        # Wait for file change to be detected and processed
        await asyncio.sleep(3)  # Debounce + processing time

        # Stop watching
        await manager.stop()

        # Index should have been updated
        results = await index.search_index("watched")
        assert len(results) > 0
