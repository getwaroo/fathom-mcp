"""Shared pytest fixtures."""

import tempfile
from pathlib import Path

import pytest

from file_knowledge_mcp.config import Config, KnowledgeConfig
from file_knowledge_mcp.search.ugrep import UgrepEngine


@pytest.fixture
def temp_knowledge_dir():
    """Create temporary knowledge directory with sample files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create structure
        (root / "games").mkdir()
        (root / "games" / "coop").mkdir()
        (root / "sport").mkdir()

        # Create sample files
        (root / "games" / "Guide.md").write_text("# Game Guide\n\nWelcome to games!")
        (root / "games" / "coop" / "Gloomhaven.md").write_text(
            "# Gloomhaven\n\n## Movement\n\nYou can move up to your speed.\n\n"
            "## Attack\n\nRoll dice to attack."
        )
        (root / "sport" / "Football.md").write_text(
            "# Football Rules\n\n## Offside\n\nA player is offside if..."
        )

        yield root


@pytest.fixture
def config(temp_knowledge_dir):
    """Create config with temp directory."""
    return Config(knowledge=KnowledgeConfig(root=temp_knowledge_dir))


# ============================================================================
# Phase 2 Shared Fixtures
# ============================================================================


@pytest.fixture
def rich_knowledge_dir(temp_knowledge_dir):
    """Extend temp_knowledge_dir with Phase 2-specific test files."""
    root = temp_knowledge_dir

    # Ensure directories exist
    (root / "games").mkdir(exist_ok=True)
    (root / "games" / "coop").mkdir(exist_ok=True)
    (root / "sport").mkdir(exist_ok=True)

    # Create comprehensive test file with multiple concepts
    (root / "games" / "coop" / "Gloomhaven.md").write_text(
        "# Gloomhaven Rules\n\n"
        "## Movement\n\n"
        "Characters can move up to their movement value.\n"
        "Movement is affected by terrain and obstacles.\n"
        "Flying characters ignore terrain penalties during movement.\n\n"
        "## Attack\n\n"
        "Roll dice to attack enemies.\n"
        "Attack damage is modified by armor.\n"
        "Critical hits deal double damage.\n\n"
        "## Defense\n\n"
        "Armor reduces incoming damage.\n"
        "Shield cards provide extra defense.\n\n"
        "## Special Abilities\n\n"
        "Some characters have ranged attacks.\n"
        "Teleport allows you to move instantly.\n"
        "Healing restores hit points.\n"
    )

    # Create another test file
    (root / "games" / "Strategy.md").write_text(
        "# Game Strategy Guide\n\n"
        "## Combat Strategy\n\n"
        "Attack weak enemies first.\n"
        "Use healing wisely.\n\n"
        "## Movement Strategy\n\n"
        "Position is everything in combat.\n"
        "Flying units have mobility advantages.\n"
    )

    # Create a multi-line document for metadata tests
    (root / "sport" / "Rules.txt").write_text(
        "Line 1\n" * 100  # 100 lines
    )

    return root


@pytest.fixture
def rich_config(rich_knowledge_dir):
    """Create config with Phase 2 knowledge directory."""
    return Config(knowledge=KnowledgeConfig(root=rich_knowledge_dir))


@pytest.fixture
def search_engine(rich_config):
    """Create UgrepEngine instance for Phase 2 tests."""
    return UgrepEngine(rich_config)


@pytest.fixture
def pdf_with_toc(rich_knowledge_dir):
    """Create a PDF file with table of contents for testing."""
    from pypdf import PdfWriter

    pdf_path = rich_knowledge_dir / "games" / "manual.pdf"

    writer = PdfWriter()

    # Add 3 pages
    for i in range(3):
        writer.add_blank_page(width=612, height=792)

    # Add metadata
    writer.add_metadata({"/Title": "Game Manual", "/Author": "Test Author"})

    # Add bookmarks (TOC)
    writer.add_outline_item("Introduction", 0)
    writer.add_outline_item("Setup", 1)
    gameplay = writer.add_outline_item("Gameplay", 2)
    writer.add_outline_item("Combat", 2, parent=gameplay)

    with open(pdf_path, "wb") as f:
        writer.write(f)

    return pdf_path
