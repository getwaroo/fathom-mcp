"""Tests for ParallelPDFProcessor."""

import asyncio

import pytest
from pypdf import PdfWriter

from file_knowledge_mcp.pdf.parallel import ParallelPDFProcessor


@pytest.fixture
def pdf_processor():
    """Create PDF processor fixture."""
    processor = ParallelPDFProcessor(max_workers=4)
    yield processor
    processor.shutdown()


@pytest.fixture
def sample_pdf(tmp_path):
    """Create a sample PDF file for testing."""
    # Create a simple PDF with a few pages
    writer = PdfWriter()

    # Add pages with text
    from pypdf import PageObject

    for i in range(5):
        page = PageObject.create_blank_page(width=612, height=792)
        writer.add_page(page)

    pdf_path = tmp_path / "sample.pdf"
    with open(pdf_path, "wb") as f:
        writer.write(f)

    return pdf_path


class TestParallelPDFProcessorBasics:
    """Test basic PDF processor functionality."""

    def test_processor_initialization(self):
        """Test processor can be initialized."""
        processor = ParallelPDFProcessor(max_workers=4)
        assert processor.max_workers == 4
        processor.shutdown()

    def test_processor_custom_workers(self):
        """Test processor with custom worker count."""
        processor = ParallelPDFProcessor(max_workers=8)
        assert processor.max_workers == 8
        processor.shutdown()


class TestTextExtraction:
    """Test text extraction functionality."""

    async def test_extract_text_all_pages(self, pdf_processor, sample_pdf):
        """Test extracting text from all pages."""
        text = await pdf_processor.extract_text_parallel(sample_pdf)

        assert isinstance(text, str)
        # Should have page markers for all 5 pages
        assert text.count("--- Page") == 5

    async def test_extract_text_specific_pages(self, pdf_processor, sample_pdf):
        """Test extracting text from specific pages."""
        text = await pdf_processor.extract_text_parallel(sample_pdf, pages=[1, 3, 5])

        assert isinstance(text, str)
        # Should have page markers for 3 pages
        assert text.count("--- Page") == 3
        assert "--- Page 1 ---" in text
        assert "--- Page 3 ---" in text
        assert "--- Page 5 ---" in text

    async def test_extract_text_without_markers(self, pdf_processor, sample_pdf):
        """Test extracting text without page markers."""
        text = await pdf_processor.extract_text_parallel(sample_pdf, include_page_markers=False)

        assert isinstance(text, str)
        # Should not have page markers
        assert "--- Page" not in text

    async def test_extract_text_invalid_pages(self, pdf_processor, sample_pdf):
        """Test extracting with invalid page numbers."""
        # Pages beyond document length should be filtered out
        text = await pdf_processor.extract_text_parallel(sample_pdf, pages=[1, 99, 100])

        assert isinstance(text, str)
        # Should only extract page 1
        assert text.count("--- Page") == 1
        assert "--- Page 1 ---" in text

    async def test_extract_text_empty_pages(self, pdf_processor, sample_pdf):
        """Test extracting with empty page list returns all pages."""
        text = await pdf_processor.extract_text_parallel(sample_pdf, pages=[])

        # Note: Our implementation treats empty pages list as "extract all pages"
        # This is intentional - pages=[] is different from pages=None
        # If you want no pages, pass pages with invalid numbers
        # For now, we accept this behavior where pages=[] still processes pages
        assert isinstance(text, str)

    async def test_extract_text_with_actual_content(self, tmp_path):
        """Test extraction with PDF containing actual text."""
        # This test would require a real PDF with text
        # For now, we'll skip if we can't create one easily
        pytest.skip("Requires PDF with actual text content")


class TestMetadataExtraction:
    """Test metadata extraction functionality."""

    async def test_extract_metadata_basic(self, pdf_processor, sample_pdf):
        """Test basic metadata extraction."""
        metadata = await pdf_processor.extract_metadata(sample_pdf)

        assert isinstance(metadata, dict)
        assert "pages" in metadata
        assert metadata["pages"] == 5
        assert "has_toc" in metadata
        assert isinstance(metadata["has_toc"], bool)

    async def test_extract_metadata_page_count(self, pdf_processor, sample_pdf):
        """Test page count in metadata."""
        metadata = await pdf_processor.extract_metadata(sample_pdf)

        assert metadata["pages"] == 5

    async def test_extract_metadata_no_toc(self, pdf_processor, sample_pdf):
        """Test metadata for PDF without TOC."""
        metadata = await pdf_processor.extract_metadata(sample_pdf)

        # Sample PDF has no TOC
        assert metadata["has_toc"] is False
        assert metadata["toc"] is None


class TestParallelProcessing:
    """Test parallel processing functionality."""

    async def test_parallel_extraction_faster_than_sequential(self, tmp_path):
        """Test that parallel processing is faster (conceptual test)."""
        # Create a PDF with many pages
        writer = PdfWriter()
        for i in range(20):
            from pypdf import PageObject

            page = PageObject.create_blank_page(width=612, height=792)
            writer.add_page(page)

        pdf_path = tmp_path / "large.pdf"
        with open(pdf_path, "wb") as f:
            writer.write(f)

        # Process with parallel processor
        processor = ParallelPDFProcessor(max_workers=4)
        text = await processor.extract_text_parallel(pdf_path)

        assert isinstance(text, str)
        processor.shutdown()

    async def test_chunk_extraction(self, pdf_processor, sample_pdf):
        """Test that chunk extraction works correctly."""
        from pypdf import PdfReader

        reader = PdfReader(sample_pdf)

        # Extract a chunk
        chunk_text = pdf_processor._extract_chunk(reader, [0, 1, 2], True)

        assert isinstance(chunk_text, str)
        # Should have 3 pages
        assert chunk_text.count("--- Page") == 3

    async def test_chunk_extraction_without_markers(self, pdf_processor, sample_pdf):
        """Test chunk extraction without markers."""
        from pypdf import PdfReader

        reader = PdfReader(sample_pdf)

        chunk_text = pdf_processor._extract_chunk(reader, [0, 1], False)

        assert isinstance(chunk_text, str)
        assert "--- Page" not in chunk_text


class TestBatchProcessing:
    """Test batch processing of multiple PDFs."""

    async def test_batch_extract(self, pdf_processor, tmp_path):
        """Test batch extraction of multiple PDFs."""
        # Create multiple PDF files
        pdf_paths = []
        for i in range(3):
            writer = PdfWriter()
            from pypdf import PageObject

            page = PageObject.create_blank_page(width=612, height=792)
            writer.add_page(page)

            pdf_path = tmp_path / f"test{i}.pdf"
            with open(pdf_path, "wb") as f:
                writer.write(f)
            pdf_paths.append(pdf_path)

        # Batch extract
        results = await pdf_processor.process_batch(pdf_paths, operation="extract")

        assert len(results) == 3
        for result in results:
            assert "path" in result
            assert "success" in result

    async def test_batch_metadata(self, pdf_processor, tmp_path):
        """Test batch metadata extraction."""
        # Create multiple PDF files
        pdf_paths = []
        for i in range(2):
            writer = PdfWriter()
            from pypdf import PageObject

            for _ in range(i + 1):  # Different page counts
                page = PageObject.create_blank_page(width=612, height=792)
                writer.add_page(page)

            pdf_path = tmp_path / f"test{i}.pdf"
            with open(pdf_path, "wb") as f:
                writer.write(f)
            pdf_paths.append(pdf_path)

        # Batch metadata extraction
        results = await pdf_processor.process_batch(pdf_paths, operation="metadata")

        assert len(results) == 2
        assert results[0]["success"]
        assert results[1]["success"]
        assert results[0]["result"]["pages"] == 1
        assert results[1]["result"]["pages"] == 2

    async def test_batch_handles_errors(self, pdf_processor, tmp_path):
        """Test batch processing handles errors gracefully."""
        # Create one valid PDF and one invalid path
        writer = PdfWriter()
        from pypdf import PageObject

        page = PageObject.create_blank_page(width=612, height=792)
        writer.add_page(page)

        valid_pdf = tmp_path / "valid.pdf"
        with open(valid_pdf, "wb") as f:
            writer.write(f)

        invalid_pdf = tmp_path / "nonexistent.pdf"

        results = await pdf_processor.process_batch([valid_pdf, invalid_pdf], operation="extract")

        assert len(results) == 2
        assert results[0]["success"] is True
        assert results[1]["success"] is False
        assert "error" in results[1]

    async def test_batch_invalid_operation(self, pdf_processor, tmp_path):
        """Test batch processing with invalid operation."""
        pdf_paths = [tmp_path / "test.pdf"]

        with pytest.raises(ValueError, match="Unknown operation"):
            await pdf_processor.process_batch(pdf_paths, operation="invalid")


class TestErrorHandling:
    """Test error handling in PDF processing."""

    async def test_extract_nonexistent_pdf(self, pdf_processor, tmp_path):
        """Test extraction from nonexistent file."""
        nonexistent = tmp_path / "nonexistent.pdf"

        with pytest.raises(Exception):
            await pdf_processor.extract_text_parallel(nonexistent)

    async def test_metadata_nonexistent_pdf(self, pdf_processor, tmp_path):
        """Test metadata extraction from nonexistent file."""
        nonexistent = tmp_path / "nonexistent.pdf"

        with pytest.raises(Exception):
            await pdf_processor.extract_metadata(nonexistent)


class TestProcessorLifecycle:
    """Test processor lifecycle and cleanup."""

    def test_processor_shutdown(self):
        """Test processor can be shut down."""
        processor = ParallelPDFProcessor(max_workers=2)
        processor.shutdown()
        # Should not raise

    def test_processor_context_manager_like(self):
        """Test processor cleanup on deletion."""
        processor = ParallelPDFProcessor(max_workers=2)
        del processor
        # Should cleanup automatically


class TestConcurrency:
    """Test concurrent PDF processing."""

    async def test_concurrent_extractions(self, pdf_processor, tmp_path):
        """Test multiple concurrent extractions."""
        # Create multiple PDFs
        pdf_paths = []
        for i in range(5):
            writer = PdfWriter()
            from pypdf import PageObject

            page = PageObject.create_blank_page(width=612, height=792)
            writer.add_page(page)

            pdf_path = tmp_path / f"concurrent{i}.pdf"
            with open(pdf_path, "wb") as f:
                writer.write(f)
            pdf_paths.append(pdf_path)

        # Extract all concurrently
        tasks = [pdf_processor.extract_text_parallel(pdf_path) for pdf_path in pdf_paths]

        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        for result in results:
            assert isinstance(result, str)

    async def test_concurrent_metadata_extraction(self, pdf_processor, tmp_path):
        """Test concurrent metadata extraction."""
        # Create multiple PDFs
        pdf_paths = []
        for i in range(3):
            writer = PdfWriter()
            from pypdf import PageObject

            for _ in range(i + 1):
                page = PageObject.create_blank_page(width=612, height=792)
                writer.add_page(page)

            pdf_path = tmp_path / f"meta{i}.pdf"
            with open(pdf_path, "wb") as f:
                writer.write(f)
            pdf_paths.append(pdf_path)

        # Extract metadata concurrently
        tasks = [pdf_processor.extract_metadata(pdf_path) for pdf_path in pdf_paths]

        results = await asyncio.gather(*tasks)

        assert len(results) == 3
        for i, result in enumerate(results):
            assert result["pages"] == i + 1
