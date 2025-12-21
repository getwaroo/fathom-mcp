"""Tests for browse tools."""

import pytest

from file_knowledge_mcp.tools.browse import _find_document, _list_collections


@pytest.mark.asyncio
async def test_list_collections_root(config):
    result = await _list_collections(config, "")

    assert result["current_path"] == ""
    assert len(result["collections"]) == 2

    names = [c["name"] for c in result["collections"]]
    assert "games" in names
    assert "sport" in names


@pytest.mark.asyncio
async def test_list_collections_nested(config):
    result = await _list_collections(config, "games")

    assert result["current_path"] == "games"
    assert len(result["collections"]) == 1
    assert result["collections"][0]["name"] == "coop"
    assert len(result["documents"]) == 1
    assert result["documents"][0]["name"] == "Guide.md"


@pytest.mark.asyncio
async def test_find_document(config):
    result = await _find_document(config, "gloom", 10)

    assert result["total_found"] == 1
    assert result["matches"][0]["name"] == "Gloomhaven.md"
    # Use Path normalization for cross-platform compatibility
    from pathlib import Path

    assert Path(result["matches"][0]["collection"]) == Path("games/coop")


@pytest.mark.asyncio
async def test_find_document_multiple_matches(config):
    # Search for a common term
    result = await _find_document(config, "Guide", 10)

    assert result["total_found"] >= 1
    # Should find Guide.md
    names = [m["name"] for m in result["matches"]]
    assert "Guide.md" in names
