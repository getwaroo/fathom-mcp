"""File system watcher for automatic index updates."""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class FileWatcher:
    """Watch file system for changes and trigger callbacks."""

    def __init__(
        self,
        knowledge_root: Path,
        on_change_callback: Callable[[list[Path]], None] | None = None,
        watch_extensions: list[str] | None = None,
    ):
        """Initialize file watcher.

        Args:
            knowledge_root: Root directory to watch
            on_change_callback: Async callback function called with list of changed paths
            watch_extensions: Only watch files with these extensions (e.g., ['.pdf', '.md'])
        """
        self.knowledge_root = knowledge_root.resolve()
        self.on_change = on_change_callback
        self.watch_extensions = set(watch_extensions or [])
        self._watcher_task: asyncio.Task | None = None
        self._running = False

        # Debounce settings to avoid too many updates
        self._debounce_seconds = 2.0
        self._pending_changes: set[Path] = set()
        self._debounce_task: asyncio.Task | None = None

    async def start_watching(self) -> None:
        """Start monitoring file changes.

        Raises:
            ImportError: If watchfiles is not installed
            RuntimeError: If already watching
        """
        if self._running:
            raise RuntimeError("FileWatcher is already running")

        try:
            from watchfiles import awatch
        except ImportError as e:
            raise ImportError(
                "watchfiles is required for file watching. Install with: pip install watchfiles"
            ) from e

        self._running = True
        logger.info(f"Starting file watcher on {self.knowledge_root}")

        try:
            async for changes in awatch(self.knowledge_root, stop_event=None):
                if not self._running:
                    break

                # Filter changes
                changed_paths = self._filter_changes(changes)

                if changed_paths:
                    logger.debug(f"Detected {len(changed_paths)} file changes")
                    await self._handle_changes(changed_paths)

        except asyncio.CancelledError:
            logger.info("File watcher cancelled")
        except Exception as e:
            logger.error(f"File watcher error: {e}")
        finally:
            self._running = False

    async def stop_watching(self) -> None:
        """Stop monitoring file changes."""
        if not self._running:
            return

        logger.info("Stopping file watcher")
        self._running = False

        if self._watcher_task and not self._watcher_task.done():
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass

        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
            try:
                await self._debounce_task
            except asyncio.CancelledError:
                pass

    def _filter_changes(self, changes: set) -> list[Path]:
        """Filter file changes to only include relevant files.

        Args:
            changes: Set of (change_type, path_str) tuples from watchfiles

        Returns:
            List of Path objects for relevant changes
        """
        from watchfiles import Change

        changed_paths = []

        for change_type, path_str in changes:
            path = Path(path_str)

            # Skip if not in knowledge root
            try:
                path.relative_to(self.knowledge_root)
            except ValueError:
                continue

            # Skip directories
            if path.is_dir():
                continue

            # Skip hidden files and common excludes
            if path.name.startswith("."):
                continue

            if any(part.startswith("__pycache__") for part in path.parts):
                continue

            # Filter by extension if specified
            if self.watch_extensions:
                if path.suffix.lower() not in self.watch_extensions:
                    continue

            # Skip deleted files for extension check (they don't exist)
            if change_type == Change.deleted:
                changed_paths.append(path)
            elif path.exists():
                changed_paths.append(path)

        return changed_paths

    async def _handle_changes(self, changed_paths: list[Path]) -> None:
        """Handle file changes with debouncing.

        Args:
            changed_paths: List of paths that changed
        """
        # Add to pending changes
        self._pending_changes.update(changed_paths)

        # Cancel existing debounce task
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        # Start new debounce task
        self._debounce_task = asyncio.create_task(self._debounced_callback())

    async def _debounced_callback(self) -> None:
        """Wait for debounce period, then call the callback."""
        try:
            await asyncio.sleep(self._debounce_seconds)

            if self._pending_changes and self.on_change:
                # Call the callback with accumulated changes
                changes = list(self._pending_changes)
                self._pending_changes.clear()

                logger.info(f"Processing {len(changes)} debounced file changes")

                # Call the callback (it should be async)
                if asyncio.iscoroutinefunction(self.on_change):
                    await self.on_change(changes)
                else:
                    # If it's not async, run it in a thread
                    await asyncio.to_thread(self.on_change, changes)

        except asyncio.CancelledError:
            # Debounce was cancelled, changes will be processed by new task
            pass
        except Exception as e:
            logger.error(f"Error in file change callback: {e}")

    @property
    def is_running(self) -> bool:
        """Check if watcher is currently running."""
        return self._running


class WatcherManager:
    """Manage file watcher lifecycle with the index."""

    def __init__(self, knowledge_root: Path, document_index):
        """Initialize watcher manager.

        Args:
            knowledge_root: Root directory to watch
            document_index: DocumentIndex instance to update on changes
        """
        self.knowledge_root = knowledge_root
        self.document_index = document_index
        self.watcher: FileWatcher | None = None
        self._background_task: asyncio.Task | None = None

    async def start(self, watch_extensions: list[str] | None = None) -> None:
        """Start file watching and automatic index updates.

        Args:
            watch_extensions: File extensions to watch
        """
        if self.watcher and self.watcher.is_running:
            logger.warning("Watcher already running")
            return

        self.watcher = FileWatcher(
            self.knowledge_root,
            on_change_callback=self._on_files_changed,
            watch_extensions=watch_extensions,
        )

        # Start watcher in background
        self._background_task = asyncio.create_task(self.watcher.start_watching())
        logger.info("Started file watcher for automatic index updates")

    async def stop(self) -> None:
        """Stop file watching."""
        if self.watcher:
            await self.watcher.stop_watching()

        if self._background_task and not self._background_task.done():
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped file watcher")

    async def _on_files_changed(self, changed_files: list[Path]) -> None:
        """Handle file changes by updating the index.

        Args:
            changed_files: List of files that changed
        """
        try:
            logger.info(f"Updating index for {len(changed_files)} changed files")
            result = await self.document_index.update_index(changed_files)
            logger.info(
                f"Index updated: {result['documents_updated']} updated, "
                f"{result['documents_removed']} removed"
            )
        except Exception as e:
            logger.error(f"Failed to update index on file change: {e}")
