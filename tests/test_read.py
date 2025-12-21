"""Tests for read tools."""

from pathlib import Path

import pytest

from file_knowledge_mcp.errors import ErrorCode, McpError
from file_knowledge_mcp.tools.read import _get_document_info, _read_document


@pytest.mark.asyncio
async def test_read_document_markdown(config):
    """Test reading a markdown document."""
    result = await _read_document(config, {"path": "games/Guide.md", "pages": []})

    assert "Game Guide" in result["content"]
    assert result["total_pages"] == 1
    assert result["pages_read"] == [1]
    assert not result["truncated"]


@pytest.mark.asyncio
async def test_read_document_not_found(config):
    """Test reading non-existent document."""
    with pytest.raises(McpError) as exc_info:
        await _read_document(config, {"path": "nonexistent.md", "pages": []})

    assert exc_info.value.code.value == "1002"  # DOCUMENT_NOT_FOUND


@pytest.mark.asyncio
async def test_read_document_truncation(config):
    """Test that very long documents are truncated."""
    # Create a large file
    large_content = "A" * 200_000  # Larger than max_document_read_chars
    large_file = config.knowledge.root / "large.txt"
    large_file.write_text(large_content)

    result = await _read_document(config, {"path": "large.txt", "pages": []})

    assert result["truncated"]
    assert len(result["content"]) <= config.limits.max_document_read_chars + 100
    assert "(truncated)" in result["content"]


# ============================================================================
# Phase 2: Document Info Tests (get_document_info)
# ============================================================================


@pytest.mark.asyncio
async def test_get_document_info_markdown(rich_config, rich_knowledge_dir):
    """Test get_document_info for markdown file."""
    args = {"path": "games/coop/Gloomhaven.md"}

    result = await _get_document_info(rich_config, args)

    assert result["name"] == "Gloomhaven.md"
    assert result["path"] == "games/coop/Gloomhaven.md"
    assert result["collection"] == str(Path("games/coop"))  # Handle Windows path separators
    assert result["format"] == "md"
    assert result["size_bytes"] > 0
    assert "modified" in result
    assert result["pages"] == 1
    assert result["lines"] > 0
    assert result["has_toc"] is False
    assert result["toc"] is None


@pytest.mark.asyncio
async def test_get_document_info_text_file(rich_config, rich_knowledge_dir):
    """Test get_document_info for text file."""
    args = {"path": "sport/Rules.txt"}

    result = await _get_document_info(rich_config, args)

    assert result["name"] == "Rules.txt"
    assert result["format"] == "txt"
    assert result["pages"] == 1
    assert result["lines"] == 101  # Created with "Line 1\n" * 100 = 100 lines + final line


@pytest.mark.asyncio
async def test_get_document_info_pdf_with_toc(rich_config, pdf_with_toc):
    """Test get_document_info for PDF with table of contents."""
    args = {"path": "games/manual.pdf"}

    result = await _get_document_info(rich_config, args)

    assert result["name"] == "manual.pdf"
    assert result["format"] == "pdf"
    assert result["pages"] == 3
    assert result["has_toc"] is True
    assert result["toc"] is not None
    assert isinstance(result["toc"], list)
    assert len(result["toc"]) > 0

    # Check TOC structure
    toc_titles = [item["title"] for item in result["toc"]]
    assert "Introduction" in toc_titles
    assert "Setup" in toc_titles
    assert "Gameplay" in toc_titles

    # Check metadata
    assert result["title"] == "Game Manual"
    assert result["author"] == "Test Author"


@pytest.mark.asyncio
async def test_get_document_info_pdf_without_toc(rich_knowledge_dir, rich_config):
    """Test get_document_info for PDF without table of contents."""
    from pypdf import PdfWriter

    # Create simple PDF without TOC
    pdf_path = rich_knowledge_dir / "games" / "simple.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)

    with open(pdf_path, "wb") as f:
        writer.write(f)

    args = {"path": "games/simple.pdf"}
    result = await _get_document_info(rich_config, args)

    assert result["pages"] == 1
    assert result["has_toc"] is False
    assert result["toc"] is None


@pytest.mark.asyncio
async def test_get_document_info_nested_toc(rich_knowledge_dir, rich_config):
    """Test get_document_info with nested table of contents."""
    from pypdf import PdfWriter

    pdf_path = rich_knowledge_dir / "games" / "nested.pdf"
    writer = PdfWriter()

    # Add pages
    for i in range(5):
        writer.add_blank_page(width=612, height=792)

    # Create nested TOC
    chapter1 = writer.add_outline_item("Chapter 1", 0)
    writer.add_outline_item("Section 1.1", 1, parent=chapter1)
    writer.add_outline_item("Section 1.2", 2, parent=chapter1)
    chapter2 = writer.add_outline_item("Chapter 2", 3)
    writer.add_outline_item("Section 2.1", 4, parent=chapter2)

    with open(pdf_path, "wb") as f:
        writer.write(f)

    args = {"path": "games/nested.pdf"}
    result = await _get_document_info(rich_config, args)

    assert result["has_toc"] is True
    assert len(result["toc"]) == 2  # 2 top-level chapters

    # Check nested structure
    chapter1_entry = next(item for item in result["toc"] if item["title"] == "Chapter 1")
    assert "children" in chapter1_entry
    assert len(chapter1_entry["children"]) == 2


@pytest.mark.asyncio
async def test_get_document_info_nonexistent(rich_config):
    """Test get_document_info with non-existent file."""
    args = {"path": "nonexistent.md"}

    with pytest.raises(McpError) as exc_info:
        await _get_document_info(rich_config, args)

    assert exc_info.value.code == ErrorCode.DOCUMENT_NOT_FOUND


@pytest.mark.asyncio
async def test_get_document_info_root_level_file(temp_knowledge_dir, rich_config):
    """Test get_document_info for file at root level."""
    # Create file at root
    (temp_knowledge_dir / "root_file.md").write_text("# Root File")

    args = {"path": "root_file.md"}
    result = await _get_document_info(rich_config, args)

    assert result["collection"] == ""  # No collection for root-level files
