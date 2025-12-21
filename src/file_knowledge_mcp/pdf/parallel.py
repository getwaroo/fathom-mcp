"""Parallel PDF processing for improved performance."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pypdf import PdfReader

logger = logging.getLogger(__name__)


class ParallelPDFProcessor:
    """Process PDF pages in parallel for better performance."""

    def __init__(self, max_workers: int = 4):
        """Initialize parallel PDF processor.

        Args:
            max_workers: Maximum number of parallel workers
        """
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    async def extract_text_parallel(
        self,
        pdf_path: Path,
        pages: list[int] | None = None,
        include_page_markers: bool = True,
    ) -> str:
        """Extract text from PDF pages in parallel.

        Args:
            pdf_path: Path to PDF file
            pages: Specific page numbers to extract (1-indexed). None = all pages
            include_page_markers: Whether to include "--- Page N ---" markers

        Returns:
            Extracted text content
        """
        # Load PDF reader in thread pool
        reader = await asyncio.to_thread(PdfReader, pdf_path)
        total_pages = len(reader.pages)

        # Determine which pages to process
        if pages:
            # Convert to 0-indexed and filter valid pages
            page_indices = [p - 1 for p in pages if 0 < p <= total_pages]
        else:
            page_indices = list(range(total_pages))

        if not page_indices:
            return ""

        logger.debug(
            f"Extracting text from {len(page_indices)} pages using {self.max_workers} workers"
        )

        # Process pages in chunks for better parallelization
        chunk_size = max(1, len(page_indices) // self.max_workers)
        chunks = [page_indices[i : i + chunk_size] for i in range(0, len(page_indices), chunk_size)]

        # Process chunks in parallel
        tasks = [
            asyncio.to_thread(
                self._extract_chunk,
                reader,
                chunk,
                include_page_markers,
            )
            for chunk in chunks
        ]

        results = await asyncio.gather(*tasks)

        # Combine results
        return "\n".join(results)

    def _extract_chunk(
        self,
        reader: PdfReader,
        page_indices: list[int],
        include_markers: bool,
    ) -> str:
        """Extract text from a chunk of pages (runs in thread pool).

        Args:
            reader: PdfReader instance
            page_indices: List of page indices to extract
            include_markers: Whether to include page markers

        Returns:
            Extracted text for this chunk
        """
        text_parts = []

        for idx in page_indices:
            try:
                if include_markers:
                    page_num = idx + 1
                    text_parts.append(f"--- Page {page_num} ---")

                page_text = reader.pages[idx].extract_text() or ""
                text_parts.append(page_text)

            except Exception as e:
                logger.error(f"Failed to extract text from page {idx}: {e}")
                if include_markers:
                    text_parts.append(f"[Error extracting page {idx + 1}]")

        return "\n".join(text_parts)

    async def extract_metadata(self, pdf_path: Path) -> dict[str, Any]:
        """Extract PDF metadata in parallel.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Dictionary with metadata including page count, TOC, etc.
        """
        reader = await asyncio.to_thread(PdfReader, pdf_path)

        metadata = {
            "pages": len(reader.pages),
            "has_toc": False,
            "toc": None,
        }

        # Extract metadata in parallel tasks
        tasks = [
            asyncio.to_thread(self._extract_pdf_metadata, reader),
            asyncio.to_thread(self._extract_toc, reader),
        ]

        pdf_meta, toc = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle results
        if not isinstance(pdf_meta, Exception) and pdf_meta:
            metadata.update(pdf_meta)

        if not isinstance(toc, Exception) and toc:
            metadata["has_toc"] = True
            metadata["toc"] = toc

        return metadata

    def _extract_pdf_metadata(self, reader: PdfReader) -> dict[str, Any]:
        """Extract PDF document metadata (runs in thread pool)."""
        meta = {}

        if reader.metadata:
            if reader.metadata.get("/Title"):
                meta["title"] = reader.metadata["/Title"]
            if reader.metadata.get("/Author"):
                meta["author"] = reader.metadata["/Author"]
            if reader.metadata.get("/Subject"):
                meta["subject"] = reader.metadata["/Subject"]
            if reader.metadata.get("/Creator"):
                meta["creator"] = reader.metadata["/Creator"]

        return meta

    def _extract_toc(self, reader: PdfReader) -> list[dict] | None:
        """Extract PDF table of contents (runs in thread pool)."""
        try:
            outlines = reader.outline
            if outlines:
                return self._parse_outlines(reader, outlines)
        except Exception as e:
            logger.debug(f"Failed to extract TOC: {e}")

        return None

    def _parse_outlines(self, reader: PdfReader, outlines, depth: int = 0) -> list[dict]:
        """Recursively parse PDF outlines into TOC structure."""
        if depth > 5:  # Limit depth
            return []

        toc = []

        for item in outlines:
            if isinstance(item, list):
                # Nested outlines
                if toc:
                    toc[-1]["children"] = self._parse_outlines(reader, item, depth + 1)
            else:
                # Outline item
                entry = {
                    "title": item.title if hasattr(item, "title") else str(item),
                    "page": None,
                }

                # Try to get page number
                try:
                    if hasattr(item, "page"):
                        page_obj = item.page
                        if page_obj:
                            for i, page in enumerate(reader.pages):
                                if page == page_obj:
                                    entry["page"] = i + 1
                                    break
                except Exception:
                    pass

                toc.append(entry)

        return toc

    async def process_batch(
        self, pdf_paths: list[Path], operation: str = "extract"
    ) -> list[dict[str, Any]]:
        """Process multiple PDFs in parallel.

        Args:
            pdf_paths: List of PDF file paths
            operation: Operation to perform ("extract" or "metadata")

        Returns:
            List of results for each PDF
        """
        if operation == "extract":
            tasks = [self.extract_text_parallel(path) for path in pdf_paths]
        elif operation == "metadata":
            tasks = [self.extract_metadata(path) for path in pdf_paths]
        else:
            raise ValueError(f"Unknown operation: {operation}")

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Format results
        output = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                output.append(
                    {
                        "path": str(pdf_paths[i]),
                        "success": False,
                        "error": str(result),
                    }
                )
            else:
                output.append(
                    {
                        "path": str(pdf_paths[i]),
                        "success": True,
                        "result": result,
                    }
                )

        return output

    def shutdown(self) -> None:
        """Shutdown the thread pool executor."""
        self._executor.shutdown(wait=True)

    def __del__(self):
        """Cleanup on deletion."""
        try:
            self._executor.shutdown(wait=False)
        except Exception:
            pass
