"""Document indexing for faster searches on large collections."""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DocumentMetadata:
    """Metadata for indexed document."""

    path: str
    size_bytes: int
    modified_time: float
    content_hash: str
    format: str
    indexed_at: float


@dataclass
class IndexEntry:
    """Single term entry in the index."""

    term: str
    document_path: str
    frequency: int
    positions: list[int]


class DocumentIndex:
    """Document index for fast text search."""

    def __init__(self, knowledge_root: Path, index_path: Path | None = None):
        """Initialize document index.

        Args:
            knowledge_root: Root directory for documents
            index_path: Path to store index data (default: .fkm_index in knowledge_root)
        """
        self.knowledge_root = knowledge_root.resolve()
        self.index_path = index_path or (self.knowledge_root / ".fkm_index")
        self.index_path.mkdir(exist_ok=True)

        # In-memory index structures
        self._term_index: dict[str, list[IndexEntry]] = {}
        self._document_metadata: dict[str, DocumentMetadata] = {}
        self._lock = asyncio.Lock()

        # Index statistics
        self._stats = {
            "total_documents": 0,
            "total_terms": 0,
            "last_build": None,
            "last_update": None,
        }

    async def build_index(
        self,
        formats: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build or rebuild the complete document index.

        Args:
            formats: List of file extensions to index (e.g., ['.pdf', '.md', '.txt'])
            exclude_patterns: Glob patterns to exclude

        Returns:
            Statistics about the build operation
        """
        logger.info(f"Building document index at {self.index_path}")
        start_time = time.time()

        formats = formats or [".pdf", ".md", ".markdown", ".txt", ".rst"]
        exclude_patterns = exclude_patterns or [".git/*", "__pycache__/*", "*.draft.*"]

        async with self._lock:
            # Clear existing index
            self._term_index.clear()
            self._document_metadata.clear()

            # Find all documents
            documents = self._find_documents(formats, exclude_patterns)
            logger.info(f"Found {len(documents)} documents to index")

            # Index each document
            indexed_count = 0
            failed_count = 0

            for doc_path in documents:
                try:
                    await self._index_document(doc_path)
                    indexed_count += 1
                except Exception as e:
                    logger.error(f"Failed to index {doc_path}: {e}")
                    failed_count += 1

            # Update statistics
            self._stats["total_documents"] = indexed_count
            self._stats["total_terms"] = len(self._term_index)
            self._stats["last_build"] = time.time()

            # Persist index to disk
            await self._save_index()

            elapsed = time.time() - start_time
            logger.info(
                f"Index build complete: {indexed_count} documents, "
                f"{len(self._term_index)} terms in {elapsed:.2f}s"
            )

            return {
                "documents_indexed": indexed_count,
                "documents_failed": failed_count,
                "total_terms": len(self._term_index),
                "elapsed_seconds": elapsed,
            }

    async def update_index(self, changed_files: list[Path]) -> dict[str, Any]:
        """Incrementally update index for changed files.

        Args:
            changed_files: List of file paths that have changed

        Returns:
            Statistics about the update operation
        """
        logger.info(f"Updating index for {len(changed_files)} changed files")
        start_time = time.time()

        async with self._lock:
            updated_count = 0
            removed_count = 0
            failed_count = 0

            for file_path in changed_files:
                try:
                    # Make path relative to knowledge root
                    try:
                        rel_path = file_path.relative_to(self.knowledge_root)
                    except ValueError:
                        # File is outside knowledge root
                        continue

                    rel_path_str = str(rel_path)

                    # If file was deleted, remove from index
                    if not file_path.exists():
                        if rel_path_str in self._document_metadata:
                            self._remove_document_from_index(rel_path_str)
                            removed_count += 1
                        continue

                    # Check if file has actually changed
                    if rel_path_str in self._document_metadata:
                        old_meta = self._document_metadata[rel_path_str]
                        current_mtime = file_path.stat().st_mtime

                        if current_mtime <= old_meta.modified_time:
                            # File hasn't changed
                            continue

                        # Remove old version from index
                        self._remove_document_from_index(rel_path_str)

                    # Index the new/updated document
                    await self._index_document(file_path)
                    updated_count += 1

                except Exception as e:
                    logger.error(f"Failed to update index for {file_path}: {e}")
                    failed_count += 1

            # Update statistics
            self._stats["total_documents"] = len(self._document_metadata)
            self._stats["total_terms"] = len(self._term_index)
            self._stats["last_update"] = time.time()

            # Persist index to disk
            await self._save_index()

            elapsed = time.time() - start_time
            logger.info(
                f"Index update complete: {updated_count} updated, "
                f"{removed_count} removed in {elapsed:.2f}s"
            )

            return {
                "documents_updated": updated_count,
                "documents_removed": removed_count,
                "documents_failed": failed_count,
                "elapsed_seconds": elapsed,
            }

    async def search_index(
        self,
        query: str,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Search using the index.

        Args:
            query: Search query (simple term-based search)
            max_results: Maximum number of results to return

        Returns:
            List of search results with document paths and relevance scores
        """
        async with self._lock:
            # Simple tokenization
            terms = self._tokenize(query.lower())

            if not terms:
                return []

            # Find documents containing any of the terms
            doc_scores: dict[str, float] = {}

            for term in terms:
                entries = self._term_index.get(term, [])

                for entry in entries:
                    # Calculate term frequency score
                    tf_score = entry.frequency / 100.0  # Normalize

                    # Add to document score
                    if entry.document_path in doc_scores:
                        doc_scores[entry.document_path] += tf_score
                    else:
                        doc_scores[entry.document_path] = tf_score

            # Sort by score and return top results
            results = []
            for doc_path, score in sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)[
                :max_results
            ]:
                metadata = self._document_metadata.get(doc_path)
                if metadata:
                    results.append(
                        {
                            "path": doc_path,
                            "score": score,
                            "format": metadata.format,
                            "size_bytes": metadata.size_bytes,
                        }
                    )

            return results

    async def load_index(self) -> bool:
        """Load index from disk.

        Returns:
            True if index was loaded successfully, False otherwise
        """
        metadata_file = self.index_path / "metadata.json"
        terms_file = self.index_path / "terms.json"

        if not metadata_file.exists() or not terms_file.exists():
            logger.info("No existing index found")
            return False

        try:
            async with self._lock:
                # Load metadata
                metadata_data = await asyncio.to_thread(json.loads, metadata_file.read_text())
                self._document_metadata = {
                    path: DocumentMetadata(**meta) for path, meta in metadata_data.items()
                }

                # Load term index
                terms_data = await asyncio.to_thread(json.loads, terms_file.read_text())
                self._term_index = {
                    term: [IndexEntry(**entry) for entry in entries]
                    for term, entries in terms_data.items()
                }

                # Load statistics
                stats_file = self.index_path / "stats.json"
                if stats_file.exists():
                    self._stats = await asyncio.to_thread(json.loads, stats_file.read_text())

                logger.info(
                    f"Loaded index: {len(self._document_metadata)} documents, "
                    f"{len(self._term_index)} terms"
                )
                return True

        except Exception as e:
            logger.error(f"Failed to load index: {e}")
            return False

    async def _save_index(self) -> None:
        """Persist index to disk."""
        try:
            # Save metadata
            metadata_file = self.index_path / "metadata.json"
            metadata_data = {path: asdict(meta) for path, meta in self._document_metadata.items()}
            await asyncio.to_thread(metadata_file.write_text, json.dumps(metadata_data, indent=2))

            # Save term index
            terms_file = self.index_path / "terms.json"
            terms_data = {
                term: [asdict(entry) for entry in entries]
                for term, entries in self._term_index.items()
            }
            await asyncio.to_thread(terms_file.write_text, json.dumps(terms_data, indent=2))

            # Save statistics
            stats_file = self.index_path / "stats.json"
            await asyncio.to_thread(stats_file.write_text, json.dumps(self._stats, indent=2))

            logger.debug("Index saved to disk")

        except Exception as e:
            logger.error(f"Failed to save index: {e}")
            raise

    def _find_documents(self, formats: list[str], exclude_patterns: list[str]) -> list[Path]:
        """Find all documents matching formats and not excluded."""
        documents = []

        for ext in formats:
            # Ensure extension starts with dot
            if not ext.startswith("."):
                ext = f".{ext}"

            pattern = f"**/*{ext}"
            for path in self.knowledge_root.glob(pattern):
                if path.is_file():
                    # Check exclusion patterns
                    rel_path = str(path.relative_to(self.knowledge_root))
                    excluded = False

                    for exclude_pattern in exclude_patterns:
                        from fnmatch import fnmatch

                        if fnmatch(rel_path, exclude_pattern):
                            excluded = True
                            break

                    if not excluded:
                        documents.append(path)

        return documents

    async def _index_document(self, doc_path: Path) -> None:
        """Index a single document."""
        # Read document content
        content = await self._read_document_text(doc_path)

        if not content:
            return

        # Calculate content hash
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        # Create metadata
        stat = doc_path.stat()
        rel_path = str(doc_path.relative_to(self.knowledge_root))

        metadata = DocumentMetadata(
            path=rel_path,
            size_bytes=stat.st_size,
            modified_time=stat.st_mtime,
            content_hash=content_hash,
            format=doc_path.suffix.lower(),
            indexed_at=time.time(),
        )

        self._document_metadata[rel_path] = metadata

        # Tokenize and index terms
        terms = self._tokenize(content.lower())

        # Count term frequencies and positions
        term_data: dict[str, dict[str, Any]] = {}

        for pos, term in enumerate(terms):
            if term not in term_data:
                term_data[term] = {"frequency": 0, "positions": []}

            term_data[term]["frequency"] += 1
            term_data[term]["positions"].append(pos)

        # Add to term index
        for term, data in term_data.items():
            entry = IndexEntry(
                term=term,
                document_path=rel_path,
                frequency=data["frequency"],
                positions=data["positions"][:100],  # Limit positions stored
            )

            if term not in self._term_index:
                self._term_index[term] = []

            self._term_index[term].append(entry)

    async def _read_document_text(self, doc_path: Path) -> str:
        """Read text content from document."""
        try:
            ext = doc_path.suffix.lower()

            if ext == ".pdf":
                # Use pypdf to extract text
                from pypdf import PdfReader

                reader = await asyncio.to_thread(PdfReader, doc_path)
                pages = reader.pages
                text_parts = []

                for page in pages:
                    text = await asyncio.to_thread(page.extract_text)
                    if text:
                        text_parts.append(text)

                return "\n".join(text_parts)
            else:
                # Text file
                return await asyncio.to_thread(doc_path.read_text, encoding="utf-8")

        except Exception as e:
            logger.error(f"Failed to read {doc_path}: {e}")
            return ""

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenization - split on whitespace and punctuation."""
        import re

        # Split on non-alphanumeric characters
        tokens = re.findall(r"\b\w+\b", text)

        # Filter short tokens and common stop words
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
        }

        return [token for token in tokens if len(token) > 2 and token not in stop_words]

    def _remove_document_from_index(self, doc_path: str) -> None:
        """Remove document from index."""
        # Remove from metadata
        if doc_path in self._document_metadata:
            del self._document_metadata[doc_path]

        # Remove from term index
        for term, entries in list(self._term_index.items()):
            self._term_index[term] = [e for e in entries if e.document_path != doc_path]

            # Remove term if no entries left
            if not self._term_index[term]:
                del self._term_index[term]

    @property
    def stats(self) -> dict[str, Any]:
        """Get index statistics."""
        return self._stats.copy()
