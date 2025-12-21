"""Tests for MCP prompts functionality."""

import pytest

from file_knowledge_mcp.prompts import (
    _answer_question_prompt,
    _compare_documents_prompt,
    _summarize_document_prompt,
)

# ============================================================================
# MCP Prompts Tests
# ============================================================================


@pytest.mark.asyncio
async def test_prompt_answer_question():
    """Test answer_question prompt generation."""
    args = {"question": "How does movement work?", "collection": "games"}

    messages = _answer_question_prompt(args)

    assert len(messages) == 1
    assert messages[0].role == "user"
    assert "How does movement work?" in messages[0].content.text
    assert "games" in messages[0].content.text
    assert "list_collections" in messages[0].content.text
    assert "search_documents" in messages[0].content.text


@pytest.mark.asyncio
async def test_prompt_answer_question_no_collection():
    """Test answer_question prompt without collection filter."""
    args = {
        "question": "What is teleportation?",
    }

    messages = _answer_question_prompt(args)

    assert len(messages) == 1
    # Should not mention limiting to collection
    text = messages[0].content.text
    assert "What is teleportation?" in text
    assert "Limit your search to" not in text


@pytest.mark.asyncio
async def test_prompt_summarize_document():
    """Test summarize_document prompt generation."""
    args = {"document_path": "games/coop/Gloomhaven.md"}

    messages = _summarize_document_prompt(args)

    assert len(messages) == 1
    assert messages[0].role == "user"
    text = messages[0].content.text
    assert "games/coop/Gloomhaven.md" in text
    assert "get_document_info" in text
    assert "read_document" in text
    assert "structured summary" in text


@pytest.mark.asyncio
async def test_prompt_compare_documents():
    """Test compare_documents prompt generation."""
    args = {
        "doc1": "games/coop/Gloomhaven.md",
        "doc2": "games/Strategy.md",
        "topic": "combat tactics",
    }

    messages = _compare_documents_prompt(args)

    assert len(messages) == 1
    assert messages[0].role == "user"
    text = messages[0].content.text
    assert "games/coop/Gloomhaven.md" in text
    assert "games/Strategy.md" in text
    assert "combat tactics" in text
    assert "search_documents" in text
    assert "search_multiple" in text
    assert "Similarities" in text
    assert "Differences" in text


@pytest.mark.asyncio
async def test_prompt_all_registered_prompts():
    """Test that all prompts can be generated without errors."""
    # Test with minimal arguments
    answer_msgs = _answer_question_prompt({"question": "test"})
    assert len(answer_msgs) > 0

    summarize_msgs = _summarize_document_prompt({"document_path": "test.md"})
    assert len(summarize_msgs) > 0

    compare_msgs = _compare_documents_prompt(
        {"doc1": "doc1.md", "doc2": "doc2.md", "topic": "test"}
    )
    assert len(compare_msgs) > 0


@pytest.mark.asyncio
async def test_prompt_empty_arguments():
    """Test prompts with empty/missing arguments."""
    # Empty args should use defaults
    messages = _answer_question_prompt({})

    assert len(messages) == 1
    # Should still generate valid prompt with empty question
    assert messages[0].role == "user"
