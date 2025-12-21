"""Ugrep search engine wrapper."""

import asyncio
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..config import Config
from ..errors import search_timeout
from ..security import FilterSecurity
from .cache import SearchCache, SmartSearchCache

logger = logging.getLogger(__name__)


@dataclass
class SearchMatch:
    """Single search match."""

    file: str
    line_number: int
    text: str
    context_before: list[str]
    context_after: list[str]


@dataclass
class SearchResult:
    """Search operation result."""

    matches: list[SearchMatch]
    total_matches: int
    truncated: bool
    query: str
    searched_path: str


class UgrepEngine:
    """Ugrep-based search engine."""

    def __init__(self, config: Config, cache: SearchCache | None = None):
        self.config = config

        # Use SmartSearchCache if enabled in performance config
        if config.performance.enable_smart_cache and cache is None:
            self.cache = SmartSearchCache(
                config.knowledge.root,
                max_size=config.performance.cache_max_size,
                ttl_seconds=config.performance.cache_ttl_seconds,
            )
        else:
            self.cache = cache or SearchCache(
                max_size=config.performance.cache_max_size,
                ttl_seconds=config.performance.cache_ttl_seconds,
            )

        self._semaphore = asyncio.Semaphore(config.limits.max_concurrent_searches)
        self._filter_security = FilterSecurity(config)
        self._use_smart_cache = isinstance(self.cache, SmartSearchCache)

    async def search(
        self,
        query: str,
        path: Path,
        recursive: bool = True,
        context_lines: int | None = None,
        max_results: int | None = None,
        fuzzy: bool = False,
    ) -> SearchResult:
        """Execute search using ugrep.

        Args:
            query: Boolean search query (space=AND, |=OR, -=NOT)
            path: File or directory to search
            recursive: Search subdirectories
            context_lines: Lines of context (default from config)
            max_results: Max matches (default from config)
            fuzzy: Enable fuzzy matching

        Returns:
            SearchResult with matches

        Raises:
            McpError: On timeout or engine error
        """
        context = context_lines or self.config.search.context_lines
        max_res = max_results or self.config.search.max_results

        # Check cache first (use smart cache if available)
        if self._use_smart_cache:
            cached = await self.cache.get_with_validation(
                query,
                str(path),
                recursive=recursive,
                context_lines=context,
                max_results=max_res,
                fuzzy=fuzzy,
            )
        else:
            cached = await self.cache.get(
                query,
                str(path),
                recursive=recursive,
                context_lines=context,
                max_results=max_res,
                fuzzy=fuzzy,
            )

        if cached is not None:
            logger.debug(f"Cache hit for query: {query}")
            return cached

        # Execute search
        result = await self._execute_search(query, path, recursive, context, max_res, fuzzy)

        # Cache result (use smart cache if available)
        if self._use_smart_cache:
            await self.cache.set_with_tracking(
                query,
                str(path),
                result,
                recursive=recursive,
                context_lines=context,
                max_results=max_res,
                fuzzy=fuzzy,
            )
        else:
            await self.cache.set(
                query,
                str(path),
                result,
                recursive=recursive,
                context_lines=context,
                max_results=max_res,
                fuzzy=fuzzy,
            )

        return result

    async def _execute_search(
        self,
        query: str,
        path: Path,
        recursive: bool,
        context: int,
        max_res: int,
        fuzzy: bool,
    ) -> SearchResult:
        """Execute the actual search (without caching)."""
        # Build command
        cmd = self._build_command(query, path, recursive, context, fuzzy)
        logger.debug(f"Executing: {' '.join(cmd)}")

        async with self._semaphore:
            try:
                result = await asyncio.wait_for(
                    self._run_ugrep(cmd),
                    timeout=self.config.search.timeout_seconds,
                )
            except TimeoutError:
                raise search_timeout(query, self.config.search.timeout_seconds)

        matches = self._parse_output(result.stdout, self.config.knowledge.root)
        truncated = len(matches) > max_res

        return SearchResult(
            matches=matches[:max_res],
            total_matches=len(matches),
            truncated=truncated,
            query=query,
            searched_path=str(path),
        )

    def _build_command(
        self,
        query: str,
        path: Path,
        recursive: bool,
        context_lines: int,
        fuzzy: bool,
    ) -> list[str]:
        """Build ugrep command."""
        cmd = [
            "ugrep",
            "-%",  # Boolean query mode
            "-i",  # Case insensitive
            f"-C{context_lines}",
            "--line-number",
            "--with-filename",  # Always include filename in output
        ]

        if fuzzy:
            cmd.append("-Z")

        if recursive and path.is_dir():
            cmd.append("-r")
            # Add filters for supported formats
            # Build a combined pattern for all extensions
            extensions = sorted(self.config.supported_extensions)
            if extensions:
                # Use glob pattern for each extension
                for ext in extensions:
                    # Ensure extension starts with dot
                    if not ext.startswith("."):
                        ext = f".{ext}"
                    cmd.extend(["--include", f"*{ext}"])
            # PDF filter - validate security before using
            if ".pdf" in self.config.supported_extensions:
                pdf_filter = self.config.get_filter_for_extension(".pdf")
                if pdf_filter and self._filter_security.validate_filter_command(pdf_filter):
                    cmd.append(f"--filter=pdf:{pdf_filter}")
                elif pdf_filter:
                    logger.warning(f"PDF filter blocked by security policy: {pdf_filter}")
        elif path.is_file() and path.suffix.lower() == ".pdf":
            pdf_filter = self.config.get_filter_for_extension(".pdf")
            if pdf_filter and self._filter_security.validate_filter_command(pdf_filter):
                cmd.append(f"--filter=pdf:{pdf_filter}")
            elif pdf_filter:
                logger.warning(f"PDF filter blocked by security policy: {pdf_filter}")

        cmd.append(query)
        cmd.append(str(path))

        return cmd

    async def _run_ugrep(self, cmd: list[str]) -> subprocess.CompletedProcess:
        """Run ugrep in thread pool."""
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
        )
        # Debug output
        logger.debug(f"ugrep command: {' '.join(cmd)}")
        logger.debug(f"ugrep return code: {result.returncode}")
        logger.debug(f"ugrep stdout length: {len(result.stdout)}")
        logger.debug(f"ugrep stderr: {result.stderr}")
        if result.stdout:
            logger.debug(f"ugrep stdout preview: {result.stdout[:500]}")
        return result

    def _parse_output(self, stdout: str, base_path: Path) -> list[SearchMatch]:
        """Parse ugrep output into SearchMatch objects."""
        if not stdout.strip():
            return []

        matches = []
        current_match = None
        context_before = []

        for line in stdout.split("\n"):
            if not line:
                if current_match:
                    matches.append(current_match)
                    current_match = None
                    context_before = []
                continue

            # Parse line format:
            # Match lines: filename:line_number:text
            # Context lines: filename-line_number-text
            # Note: On Windows, paths may contain ':' (e.g., C:\path\file.txt)

            # Try to parse as a match line (uses : separator)
            is_match_line = False
            is_context_line = False

            # Try match line first (colon separator)
            if ":" in line:
                # Match pattern: (path):(digits):(text)
                # Use non-greedy match for path to handle Windows paths correctly
                match = re.match(r"^(.+?):(\d+):(.*)$", line)
                if match:
                    file_path = match.group(1)
                    line_num = match.group(2)
                    text = match.group(3)
                    is_match_line = True

                    if current_match:
                        matches.append(current_match)

                    # Make relative to base
                    try:
                        rel_path = Path(file_path).relative_to(base_path)
                        file_path = str(rel_path)
                    except ValueError:
                        # If can't make relative, use as-is
                        pass

                    current_match = SearchMatch(
                        file=file_path,
                        line_number=int(line_num),
                        text=text,
                        context_before=context_before.copy(),
                        context_after=[],
                    )
                    context_before = []

            # Try context line (dash separator)
            if not is_match_line and "-" in line:
                # Context lines use - instead of :
                # Match pattern: (path)-(digits)-(text)
                match = re.match(r"^(.+?)-(\d+)-(.*)$", line)
                if match:
                    text = match.group(3)
                    is_context_line = True

                    if current_match:
                        current_match.context_after.append(text)
                    else:
                        context_before.append(text)

            # If neither match nor context, treat as context
            if not is_match_line and not is_context_line:
                if current_match:
                    current_match.context_after.append(line)
                else:
                    context_before.append(line)

        if current_match:
            matches.append(current_match)

        return matches


def check_ugrep_installed() -> bool:
    """Check if ugrep is available."""
    try:
        result = subprocess.run(
            ["ugrep", "--version"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False
