"""Read tools: read_document, get_document_info."""

import logging
from datetime import datetime
from pathlib import Path

from mcp.server import Server
from mcp.types import TextContent, Tool
from pypdf import PdfReader

from ..config import Config
from ..errors import document_not_found, file_too_large
from ..pdf.parallel import ParallelPDFProcessor
from ..security import FileAccessControl

logger = logging.getLogger(__name__)


def register_read_tools(server: Server, config: Config) -> None:
    """Register read-related tools."""

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="read_document",
                description="""Read full document content or specific pages.
Use as fallback when search doesn't find what you need.
WARNING: Can return large amounts of text, prefer search when possible.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to document (relative to knowledge root)",
                        },
                        "pages": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Specific pages to read (1-indexed). Empty = all.",
                            "default": [],
                        },
                    },
                    "required": ["path"],
                },
            ),
            Tool(
                name="get_document_info",
                description="""Get document metadata including size, page count, and TOC.
TOC is only available for PDFs with embedded bookmarks.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to document",
                        },
                    },
                    "required": ["path"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "read_document":
            result = await _read_document(config, arguments)
            return [TextContent(type="text", text=format_result(result))]
        elif name == "get_document_info":
            result = await _get_document_info(config, arguments)
            return [TextContent(type="text", text=format_result(result))]

        raise ValueError(f"Unknown tool: {name}")


async def _read_document(config: Config, args: dict) -> dict:
    """Read document content."""
    import asyncio

    path = args["path"]
    pages = args.get("pages", [])

    # Validate path using FileAccessControl
    access_control = FileAccessControl(config.knowledge.root, config)
    full_path = access_control.validate_path(path)

    if not full_path.exists():
        raise document_not_found(path)

    # Check file size
    size_mb = full_path.stat().st_size / (1024 * 1024)
    max_mb = config.search.max_file_size_mb
    if size_mb > max_mb:
        raise file_too_large(path, size_mb, max_mb)

    # Read based on format
    ext = full_path.suffix.lower()

    if ext == ".pdf":
        # Use parallel PDF processor if enabled
        if config.performance.enable_parallel_pdf:
            processor = ParallelPDFProcessor(max_workers=config.performance.max_pdf_workers)
            try:
                content = await processor.extract_text_parallel(
                    full_path, pages=pages if pages else None, include_page_markers=True
                )
                reader = PdfReader(full_path)
                total_pages = len(reader.pages)

                # Determine which pages were read
                if pages:
                    pages_read = [p for p in pages if 0 < p <= total_pages]
                else:
                    pages_read = list(range(1, total_pages + 1))
            finally:
                processor.shutdown()
        else:
            content, total_pages, pages_read = await asyncio.to_thread(_read_pdf, full_path, pages)
    else:
        content = await asyncio.to_thread(full_path.read_text, encoding="utf-8")
        total_pages = 1
        pages_read = [1]

    # Truncate if needed
    max_chars = config.limits.max_document_read_chars
    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars] + "\n...(truncated)"

    return {
        "content": content,
        "pages_read": pages_read,
        "total_pages": total_pages,
        "truncated": truncated,
    }


def _read_pdf(path: Path, pages: list[int]) -> tuple[str, int, list[int]]:
    """Read PDF content."""
    reader = PdfReader(path)
    total_pages = len(reader.pages)

    # Determine which pages to read
    if pages:
        # Convert to 0-indexed, filter valid
        page_indices = [p - 1 for p in pages if 0 < p <= total_pages]
    else:
        page_indices = list(range(total_pages))

    text_parts = []
    for idx in page_indices:
        page_num = idx + 1
        text_parts.append(f"--- Page {page_num} ---")
        text_parts.append(reader.pages[idx].extract_text() or "")

    return "\n".join(text_parts), total_pages, [i + 1 for i in page_indices]


async def _get_document_info(config: Config, args: dict) -> dict:
    """Get document metadata and TOC."""
    import asyncio

    path = args["path"]

    # Validate path using FileAccessControl
    access_control = FileAccessControl(config.knowledge.root, config)
    full_path = access_control.validate_path(path)

    if not full_path.exists():
        raise document_not_found(path)

    stat = full_path.stat()
    ext = full_path.suffix.lower()

    info = {
        "name": full_path.name,
        "path": path,
        "collection": str(Path(path).parent) if Path(path).parent != Path(".") else "",
        "format": ext.lstrip("."),
        "size_bytes": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }

    if ext == ".pdf":
        # Use parallel PDF processor if enabled for metadata extraction
        if config.performance.enable_parallel_pdf:
            processor = ParallelPDFProcessor(max_workers=config.performance.max_pdf_workers)
            try:
                pdf_info = await processor.extract_metadata(full_path)
                info.update(pdf_info)
            finally:
                processor.shutdown()
        else:
            pdf_info = await asyncio.to_thread(_extract_pdf_info, full_path)
            info.update(pdf_info)
    else:
        # For text files, count lines
        content = await asyncio.to_thread(full_path.read_text, encoding="utf-8")
        info["pages"] = 1
        info["lines"] = content.count("\n") + 1
        info["has_toc"] = False
        info["toc"] = None

    return info


def _extract_pdf_info(path: Path) -> dict:
    """Extract PDF metadata and TOC."""
    reader = PdfReader(path)

    info = {
        "pages": len(reader.pages),
        "has_toc": False,
        "toc": None,
    }

    # Try to extract TOC from outlines (bookmarks)
    try:
        outlines = reader.outline
        if outlines:
            info["has_toc"] = True
            info["toc"] = _parse_outlines(reader, outlines)
    except Exception:
        pass  # Some PDFs don't have valid outlines

    # PDF metadata
    if reader.metadata:
        meta = reader.metadata
        info["title"] = meta.get("/Title", None)
        info["author"] = meta.get("/Author", None)

    return info


def _parse_outlines(reader: PdfReader, outlines, depth: int = 0) -> list[dict]:
    """Recursively parse PDF outlines into TOC structure."""
    if depth > 5:  # Limit depth
        return []

    toc = []

    for item in outlines:
        if isinstance(item, list):
            # Nested outlines
            if toc:
                toc[-1]["children"] = _parse_outlines(reader, item, depth + 1)
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


def format_result(result: dict) -> str:
    import json

    return json.dumps(result, indent=2, ensure_ascii=False)
